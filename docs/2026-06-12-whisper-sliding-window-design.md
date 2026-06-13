# Whisper 슬라이딩 윈도우 STT 설계

작성일: 2026-06-12

## 배경

현재 Whisper STT는 설정된 청크 길이만큼 오디오를 모은 뒤, 해당 청크를 한 번 전사하고 결과를 출력한다.

```text
chunkSeconds 수집 -> Whisper STT -> 전사 결과 출력 -> 번역
```

이 방식은 구조가 단순하지만 다음 문제가 있다.

- 청크를 짧게 잡으면 문맥이 부족해 STT 정확도가 떨어질 수 있다.
- 청크를 길게 잡으면 결과 출력 지연이 커진다.
- 청크 경계에서 문장이 잘리면 전사/번역 결과가 불안정해진다.
- 번역까지 매번 전체 문장에 연결하면 중복 번역이나 반복 생성이 발생할 수 있다.

## 목표

- STT 갱신 주기는 짧게 유지한다.
- Whisper에는 더 긴 문맥을 제공한다.
- 모달에는 중복 없이 확정된 새 텍스트만 출력한다.
- 번역은 확정된 새 텍스트만 수행한다.
- 설정값이 유효하지 않으면 자동 폴백 없이 실패한다.
- 업계 기준으로 검증 가능한 형태로 `정확도/지연/리비전`을 동시에 추적한다.

### 논문 기반 목표 정렬

- [Whisper-Streaming, 2023](https://arxiv.org/abs/2307.14743): LocalAgreement 기반으로 partial 결과를 안정 구간만 확정해 flicker 완화.
- [Simul-Whisper, Interspeech 2024](https://www.isca-archive.org/interspeech_2024/wang24ea_interspeech.pdf): cross-attention 정렬 + truncation-detection으로 청크 경계 오차 저감.
- [Stability metrics for streaming ASR, Interspeech 2020](https://www.isca-archive.org/interspeech_2020/shangguan20_interspeech.pdf): UPWR/UPSR로 사용자가 체감하는 리비전 안정성을 정량화.
- [WhisperKit, ICML 2025](https://openreview.net/pdf?id=6lC3MPFbVg): 가설 텍스트(hypothesis)와 확정 텍스트(confirmed text)를 분리해 latency와 정확도 균형.

문서의 구현은 위 4개 논문 축을 따르며, 다음 1차 목표를 둔다.

- **정합성 우선**: confirmed 텍스트만 모달·번역으로 전달.
- **리비전 수치 우선**: pending 기반 강제 확정 감소.
- **처리량 보존**: stepSeconds 갱신 주기 자체를 유지하되 내부 확정 정책만 강화.

## 제안 구조

기존 단일 청크 설정을 다음 세 설정으로 분리한다.

```json
{
  "stepSeconds": 1.0,
  "windowSeconds": 4.0,
  "commitLagSeconds": 1.0
}
```

- `stepSeconds`: STT 갱신 주기. 1초마다 새 결과를 계산한다.
- `windowSeconds`: Whisper에 입력할 최근 오디오 문맥 길이. 최근 3~4초를 입력한다.
- `commitLagSeconds`: 윈도우 끝부분을 바로 확정하지 않고 보류하는 시간. 경계에서 바뀔 수 있는 단어를 안정화한다.

추천 초기값:

```json
{
  "stepSeconds": 1.0,
  "windowSeconds": 4.0,
  "commitLagSeconds": 1.0,
  "beamSize": 3,
  "maxNewTokens": 96
}
```

## 처리 흐름

```text
오디오 입력
  -> ring buffer에 계속 저장
  -> 매 stepSeconds마다 최근 windowSeconds 추출
  -> Whisper STT 실행
  -> 이전 윈도우 결과와 비교
  -> 확정된 새 텍스트만 출력
  -> 확정된 새 텍스트만 번역
```

현재 방식:

```text
0.0s ~ 3.0s -> 전사 -> 출력
3.0s ~ 6.0s -> 전사 -> 출력
```

개선 방식:

```text
0.0s ~ 4.0s -> 전사 -> 일부 확정
1.0s ~ 5.0s -> 전사 -> 새 확정분 출력
2.0s ~ 6.0s -> 전사 -> 새 확정분 출력
```

### 확정/임시 텍스트 분리의 핵심 규칙

WhisperKit과 Whisper-Streaming 구현의 경험을 반영하면, 실제 모달 출력은 항상 `confirmed`만 사용해야 한다.

- `hypothesis_text`: 최신 청크에서 즉시 생성되는 임시 텍스트(내부 비교 전용).
- `confirmed_text`: LocalAgreement(최장 공통 접두사) 또는 경계 탐지 기반으로 확정된 텍스트만 노출.
- 같은 청크를 반복 처리할수록 확정 구간만 누적하고, 미확정 구간은 재작성 대상.
- 최종 출력은 `confirmed_text` 기준 `append-only`로 유지.

## 내부 상태

작업자는 다음 상태를 유지한다.

```text
audio_ring_buffer
last_window_text
committed_text
recent_committed_fragments
```

- `audio_ring_buffer`: 최근 `windowSeconds` 이상의 오디오를 저장한다.
- `last_window_text`: 직전 윈도우의 전체 STT 결과다.
- `committed_text`: 이미 모달에 출력된 누적 텍스트다.
- `recent_committed_fragments`: 반복/중복 억제를 위한 최근 출력 조각이다.

## 확정 텍스트 계산

초기 구현은 문자열 overlap 기반으로 하되, 논문 기반 지표를 추가해 단계적으로 강화한다.

예:

```text
previous: "Folks, I was one of the first people"
current:  "the first people in the United States to take delivery"
new:      "in the United States to take delivery"
```

처리 원칙:

- 이전 윈도우 결과와 현재 윈도우 결과의 가장 긴 겹침을 찾는다.
- 겹치는 앞부분은 이미 처리된 문맥으로 본다.
- 겹치지 않는 새 부분만 `candidate_text`로 만든다.
- `commitLagSeconds`에 해당하는 끝부분은 즉시 확정하지 않는다.
- 새 확정 구간은 **동일 접두사 기준 재확인 횟수(confirmed_count)**를 채워야만 출력한다.

정교한 구현이 필요해지면 `word_timestamps=true`를 사용해 시간 기준으로 확정 구간을 계산한다.

- 1단계(현재): 문자열 LCP 기반 + `confirmed_count`
- 2단계: Simul-Whisper식 truncation signal(경계 토큰 불안정 감지) 도입
- 3단계: word-timestamps 정렬 기준에서의 오디오 기반 확정 영역 계산

## 문장 경계 검출기 개선 계획

최근 운영 로그 기준으로 5~7초 슬라이딩 윈도우는 STT 처리 속도에는 충분하지만, 문장 확정 안정성에는 한계가 있다. `stepSeconds=1.0`으로 같은 오디오 구간이 반복 입력되면 Whisper가 이전 4~6초 문맥을 매번 조금씩 다르게 다시 쓰기 때문이다. 구두점이 늦게 붙거나 누락되는 빠른 발화에서는 `pending`이 길어지고, 결국 `pending_chunks`, `pending_chars`, `slow_pending` 같은 강제 확정으로 긴 발화 덩어리가 확정된다.

문제 신호:

- 확정 이유 중 `replaced` 비율이 높으면 문장 후보가 안정적으로 유지되지 않는다는 뜻이다.
- `pending_chars` p90 또는 max가 크면 문장 경계를 찾지 못해 여러 문장이 한 덩어리로 묶이고 있다는 뜻이다.
- `end_marks_stable=0` 상태에서 `forced_by=pending_chunks` 또는 `forced_by=pending_chars`가 반복되면 구두점 기반 분할이 실패한 것이다.
- 확정 전 녹색 문장이 길게 유지되다가 검은색 확정 문장으로 바뀔 때 이전 문맥이 섞이면 delta 계산만으로는 부족하다.

따라서 다음 단계는 STT 결과를 직접 문장으로 확정하지 않고, 별도 문장 경계 검출기를 통해 안정적인 문장 후보만 추출하는 것이다. 이 기능의 목표는 문장을 새로 고치거나 교정하는 것이 아니라, 원 STT 텍스트 안에서 확정 가능한 경계를 찾는 것이다.

Simul-Whisper의 `cross-attention 기반 정렬 + truncation 검출`은 이 레이어의 핵심 동작과 정합성이 높아, 경계 검출 백엔드 후보의 우선순위 1순위로 둔다.

### 후보 도구

1. `wtpsplit` / SaT

   - 구두점이 부족한 텍스트에서도 문장 경계를 예측하는 다국어 sentence segmentation 모델이다.
   - 한국어, 영어, 중국어를 포함한 다국어 입력에 적용하기 적합하다.
   - 작은 모델(`sat-3l-sm` 등)부터 테스트하고, CUDA/ONNX 경로를 사용할 수 있는지 확인한다.
   - Fail-Fast 정책에 따라 `device=cuda`로 설정했는데 CUDA 초기화나 모델 로딩이 실패하면 CPU fallback 없이 중지한다.

2. NeMo punctuation/capitalization

   - ASR 텍스트의 구두점 복원에는 유용하지만 기본 pretrained 경로가 영어 중심이다.
   - 한국어/중국어 실시간 경로의 기본 후보로 두기에는 적합성이 낮다.

3. LLM 기반 후처리

   - 문장 경계와 문장 교정을 동시에 할 수 있지만, 원음에 없는 문장을 만들어낼 위험이 있다.
   - 사용한다면 원문 단어를 보존하고 경계 위치만 반환하는 검증기 형태로 제한한다. 기본 경로로는 사용하지 않는다.

4. LocalAgreement 기반 경계 스무딩(검토 항목)

- Whisper-Streaming의 핵심 정책을 바탕으로, `stable_prefix`를 계산해 문장 경계 후보와 결합하는 방식.
- 문장 경계 자체를 새로 생성하지 않고, 경계 후보의 안정성 점수만 보강한다.

### 설계 인터페이스

문장 경계 검출은 Whisper 실행 루프에서 분리한다.

```text
src/app/sentence_boundary.py
```

예상 인터페이스:

```python
@dataclass(frozen=True)
class SentenceCandidate:
    text: str
    complete: bool
    confidence: float | None = None

class SentenceBoundaryDetector:
    def split(self, text: str, language: str) -> list[SentenceCandidate]:
        ...
```

초기 backend:

- `regex`: 현재 `_split_completed_sentences()` 기반 구현을 이동한다.
- `sat`: wtpsplit/SaT 기반 구현을 추가한다.

설정 예:

```json
{
  "sentenceBoundary": {
    "backend": "sat",
    "model": "sat-3l-sm",
    "device": "cuda",
    "confirmations": 2
  }
}
```

### 확정 알고리즘 변경

현재 흐름:

```text
stable_text -> delta 계산 -> regex 문장 분할 -> stage/confirm
```

개선 흐름:

```text
stable_text
  -> committed/pending 기준 단어 정렬
  -> sentence boundary detector
  -> complete candidate 추출
  -> 같은 경계가 confirmations회 반복되면 확정
  -> 확정 문장만 번역
```

중요 원칙:

- 문장 끝 구두점이 없어도 boundary detector가 경계를 제안할 수 있어야 한다.
- 단순히 `pending_chars`가 길어졌다는 이유만으로 확정하지 않는다.
- `pending_chunks`는 확정 트리거가 아니라 진단 지표로 낮춘다.
- 확정 전 문장은 녹색 partial 라인으로 계속 업데이트한다.
- 확정 문장은 검은색 final 라인으로 고정하고, 번역 final 입력은 이 확정 문장만 사용한다.
- 기본 번역 정책은 final-only이다. partial/staged 번역은 중복 번역과 premature translation을 만들기 쉬우므로 기본값에서 비활성화한다.
- partial 번역을 다시 허용하는 경우에도 source revision id 기반으로 같은 라인을 갱신해야 하며, append-only 번역 라인으로 처리하지 않는다.

## 안정성 지표(운영 기준)

UPWR/UPSR를 로그로 추가해 리비전 관측성을 확보한다.

- `UPWR`: Unstable Partial Word Ratio(불안정 단어 비율)
- `UPSR`: Unstable Partial Segment Ratio(불안정 세그먼트 비율)
- 후보 개선 지표: `replaced ratio`, `forced_by=pending_chunks`, `forced_by=pending_chars`, `pending_chars p90`, `pending_chars max`

기준 목표(안정성 우선 단계):

- `UPSR`: 20% 하향
- `UPWR`: 15~25% 하향
- `replaced ratio`: 단계별 지속 감소
- `pending_chars p90`: 현재 대비 20% 이상 감소

### 성능 판단 기준:

- `replaced` 확정 비율이 줄어야 한다.
- `forced_by=pending_chunks`, `forced_by=pending_chars`가 줄어야 한다.
- `pending_chars` p90과 max가 낮아져야 한다.
- STT `rtf`와 별도로 `boundary_latency`가 실시간 갱신 주기에 부담을 주지 않아야 한다.
- `UPWR`, `UPSR`은 비교군 대비 하향해야 하며, 번역 품질은 WER 또는 BLEU/CHRF 성능과 함께 추적한다.

### 적용 순서

1. 현재 regex 문장 분할을 `sentence_boundary.py`로 분리한다.
2. 기존 슬라이딩 윈도우 테스트를 새 인터페이스 기준으로 이전한다.
3. boundary backend 설정 스키마와 기본값을 추가한다.
4. `regex` backend로 현재 동작과 동일하게 통과시킨다.
5. `sat` backend를 추가하고 CUDA Fail-Fast 로딩을 구현한다.
6. 로그에 boundary 지표를 추가한다.
7. 같은 로그 조건에서 `regex`와 `sat` 결과를 비교한다.
8. `sat`의 `replaced`, `forced_by`, `pending_chars` 지표가 개선되면 기본값 전환을 검토한다.

## 번역 정책

번역은 전체 윈도우 결과가 아니라 확정된 새 텍스트만 대상으로 한다. 현재 기본 정책은 final-only translation이다.

```text
잘못된 방식: current_window_text 전체 번역
위험한 방식: staged/partial 문장을 append-only 번역
안전한 방식: confirmed_delta만 번역
권고 방식: 번역 대상은 `confirmed_text`에서만 갱신, 같은 revision id 재사용
```

## 구현 우선순위(요약)

1. 문자열 LCP + confirmed_count 기반 stable 확정(현재 구조 최소 변경)
2. 문장 경계 detector 분리 및 `sat` 백엔드 실험
3. UPWR/UPSR/forced 지표 수집
4. 안정성 기준 통과 시 `replacements-trimming` 계층(경계 불안정 토큰 제거) 도입
5. Two-Pass/causal fine-tune 검토(모델 계층 변경 단계)

## 참고 논문

- [Turning Whisper into Real-Time Transcription System](https://arxiv.org/abs/2307.14743)
- [Simul-Whisper](https://www.isca-archive.org/interspeech_2024/wang24ea_interspeech.pdf)
- [Analyzing the Quality and Stability of a Streaming End-to-End On-Device Speech Recognizer](https://www.isca-archive.org/interspeech_2020/shangguan20_interspeech.pdf)
- [WhisperKit](https://openreview.net/pdf?id=6lC3MPFbVg)
- [Adapting Whisper for Streaming Speech Recognition via Two-Pass Decoding](https://arxiv.org/abs/2506.12154)
- [WhisperRT](https://arxiv.org/abs/2508.12301)
