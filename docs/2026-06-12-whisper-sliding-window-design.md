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

초기 구현은 문자열 overlap 기반으로 한다.

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

정교한 구현이 필요해지면 `word_timestamps=true`를 사용해 시간 기준으로 확정 구간을 계산한다. 초기 구현에서는 비용과 복잡도를 줄이기 위해 문자열 기반으로 시작한다.

## 문장 경계 검출기 개선 계획

최근 운영 로그 기준으로 5~7초 슬라이딩 윈도우는 STT 처리 속도에는 충분하지만, 문장 확정 안정성에는 한계가 있다. `stepSeconds=1.0`으로 같은 오디오 구간이 반복 입력되면 Whisper가 이전 4~6초 문맥을 매번 조금씩 다르게 다시 쓰기 때문이다. 구두점이 늦게 붙거나 누락되는 빠른 발화에서는 `pending`이 길어지고, 결국 `pending_chunks`, `pending_chars`, `slow_pending` 같은 강제 확정으로 긴 발화 덩어리가 확정된다.

문제 신호:

- 확정 이유 중 `replaced` 비율이 높으면 문장 후보가 안정적으로 유지되지 않는다는 뜻이다.
- `pending_chars` p90 또는 max가 크면 문장 경계를 찾지 못해 여러 문장이 한 덩어리로 묶이고 있다는 뜻이다.
- `end_marks_stable=0` 상태에서 `forced_by=pending_chunks` 또는 `forced_by=pending_chars`가 반복되면 구두점 기반 분할이 실패한 것이다.
- 확정 전 녹색 문장이 길게 유지되다가 검은색 확정 문장으로 바뀔 때 이전 문맥이 섞이면 delta 계산만으로는 부족하다.

따라서 다음 단계는 STT 결과를 직접 문장으로 확정하지 않고, 별도 문장 경계 검출기를 통해 안정적인 문장 후보만 추출하는 것이다. 이 기능의 목표는 문장을 새로 고치거나 교정하는 것이 아니라, 원 STT 텍스트 안에서 확정 가능한 경계를 찾는 것이다.

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

### 로그 지표

문장 경계 검출기를 적용하면 기존 `Whisper 문장 진단` 로그에 다음 값을 추가한다.

```text
boundary_backend=sat
boundary_latency=0.03s
boundary_candidates=3
boundary_complete=2
boundary_confirmed=1
boundary_rejected_unstable=1
boundary_pending_chars=42
```

성능 판단 기준:

- `replaced` 확정 비율이 줄어야 한다.
- `forced_by=pending_chunks`, `forced_by=pending_chars`가 줄어야 한다.
- `pending_chars` p90과 max가 낮아져야 한다.
- STT `rtf`와 별도로 `boundary_latency`가 실시간 갱신 주기에 부담을 주지 않아야 한다.

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
권장 방식: final sentence delta만 번역
```

이유:

- 슬라이딩 윈도우는 같은 문맥을 여러 번 포함한다.
- Whisper partial hypothesis는 뒤 청크에서 자주 수정되므로, partial을 바로 번역하면 같은 의미가 여러 줄로 중복 출력된다.
- NLLB 번역 모델은 긴 반복 입력에서 반복 생성이 발생할 수 있다.
- 실시간 번역 연구는 지연을 줄이는 것보다 충분한 source 정보를 읽은 뒤 output을 내는 read/write policy를 중요하게 다룬다. 따라서 source 문장 안정성이 낮을 때는 번역을 기다리는 편이 낫다.

현재 구현 정책:

- STT 출력은 `partial -> staged -> final` 단계를 가진다.
- 전사 창은 partial/staged를 갱신할 수 있지만, 번역 입력은 final 문장만 사용한다.
- `PROVISIONAL_TRANSLATION_ENABLED` 기본값은 `False`다.
- staged 번역을 다시 켜려면 source revision id를 부여하고, 번역 창에서 같은 id 라인을 갱신해야 한다. 이 조건 없이 staged 번역을 append하면 중복 번역이 재발한다.

향후 검토할 선택지:

- Local agreement: 여러 STT 윈도우에서 공통으로 반복 확인된 stable prefix만 final 후보로 승격한다.
- Adaptive latency: 리비전/교체가 많으면 confirm threshold 또는 commit lag를 늘리고, 안정적이면 줄인다.
- Segment trimming 우선: sentence segmenter에만 의존하지 않고 Whisper segment 또는 안정 prefix 기준으로 버퍼를 자른다.
- Sentence segmenter 보강: regex backend 이후 wtpsplit 같은 다국어 문장 경계 모델을 실험하되, GPU/CUDA 요구 시 Fail-Fast를 유지한다.

## 설정 스키마

`whisper` 블록에 다음 키를 추가한다.

```json
{
  "stepSeconds": 1.0,
  "windowSeconds": 4.0,
  "commitLagSeconds": 1.0
}
```

검증 규칙:

- `stepSeconds`: `0.5 <= value <= 5.0`
- `windowSeconds`: `1.0 <= value <= 15.0`
- `commitLagSeconds`: `0.0 <= value < windowSeconds`
- `stepSeconds <= windowSeconds`

기존 `chunkSeconds`는 호환성을 위해 유지한다.

- 새 설정이 없으면 `windowSeconds = chunkSeconds`로 읽는다.
- 새 설정 저장 시에는 `stepSeconds`, `windowSeconds`, `commitLagSeconds`를 명시한다.
- `chunkSeconds`는 당분간 README와 config check에서 legacy key로 설명한다.

## GUI 변경

Whisper 탭에 다음 슬라이더를 추가한다.

- `갱신 주기(초)` -> `stepSeconds`
- `문맥 길이(초)` -> `windowSeconds`
- `확정 지연(초)` -> `commitLagSeconds`

기존 `청크 길이(초)`는 다음 중 하나로 정리한다.

1. `문맥 길이(초)`로 이름을 바꾸고 내부 키를 `windowSeconds`로 연결한다.
2. legacy 호환을 위해 한동안 표시하되 비권장 설명을 붙인다.

초기 구현에서는 혼란을 줄이기 위해 1번을 권장한다.

## 로그

기존 성능 로그는 다음 정보를 포함하도록 확장한다.

```text
Whisper 성능: step=1.0s window=4.0s audio=4.00s stt=0.62s stt_rtf=0.16 committed_chars=32 preview_chars=18 beam=3 max_tokens=96
```

필드:

- `step`: 갱신 주기
- `window`: STT 입력 문맥 길이
- `audio`: 실제 Whisper 입력 오디오 길이
- `stt`: STT 처리 시간
- `stt_rtf`: real-time factor
- `committed_chars`: 이번 턴에 확정 출력한 글자 수
- `preview_chars`: 보류 중인 미확정 글자 수

## 실패 정책

- 설정값 범위가 유효하지 않으면 실행 단계에서 즉시 실패한다.
- `stepSeconds > windowSeconds`는 자동 보정하지 않는다.
- `commitLagSeconds >= windowSeconds`는 자동 보정하지 않는다.
- 설정 오류에는 설정값, 실패 원인, 권장 조치를 함께 출력한다.

## 구현 단계

1. `WhisperConfig`에 `stepSeconds`, `windowSeconds`, `commitLagSeconds` 추가
2. `src/domain/whisper_defaults.py`에 기본값 추가
3. `config_builder`와 config GUI 저장/로드 경로 연결
4. GUI Whisper 탭 슬라이더 추가
5. `_transcribe_loop`를 ring buffer 기반으로 변경
6. 문자열 overlap 기반 delta 계산 함수 추가
7. 번역 입력을 `new_committed_text`로 제한
8. staged 번역 기본 비활성화와 final-only 번역 정책 적용
9. 성능 로그 확장
10. 단위 테스트 추가
11. README에 운영 가이드 업데이트

## 테스트 계획

단위 테스트:

- 설정 기본값 로드
- 설정 범위 검증
- `chunkSeconds` legacy 호환
- 문자열 overlap delta 계산
- 중복 출력 억제
- 빈 delta에서는 번역 미실행

수동 테스트:

- `stepSeconds=1.0`, `windowSeconds=4.0`, `commitLagSeconds=1.0`
- `beamSize=3`, `maxNewTokens=96`
- 영어 STT + 한국어 NLLB 번역
- 한국어 STT + 영어 NLLB 번역
- 무음 구간에서 이전 문장 반복 여부 확인
- 로그의 `stt_rtf`가 1.0보다 충분히 낮은지 확인

## 기대 효과

- 1초 단위 갱신으로 체감 응답성을 유지한다.
- 4초 문맥 입력으로 짧은 청크보다 STT 정확도를 높인다.
- 확정 delta만 출력해 모달 중복을 줄인다.
- 확정 delta만 번역해 NLLB 반복 생성 가능성을 낮춘다.

## 참고 자료

- [Turning Whisper into Real-Time Transcription System](https://arxiv.org/abs/2307.14743): Whisper-Streaming 논문. Whisper가 기본적으로 실시간용이 아니며, local agreement policy와 self-adaptive latency로 안정 prefix를 확정하는 접근을 제안한다.
- [ufal/whisper_streaming](https://github.com/ufal/whisper_streaming): Whisper-Streaming 구현체. `faster-whisper` GPU 백엔드, `min-chunk-size`, `buffer_trimming` 옵션, segment/sentence trimming 전략을 참고했다.
- [Whisper-Streaming README - buffer trimming and sentence segmenter](https://github.com/ufal/whisper_streaming#installation): 기본 `segment` trimming이 품질/지연 측면에서 더 낫다는 설명과 wtpsplit 등 문장 segmenter 선택지를 참고했다.
- [SimulEval: An Evaluation Toolkit for Simultaneous Translation](https://arxiv.org/abs/2007.16193): 실시간 번역은 품질과 지연을 함께 평가해야 하며, read/write 정책이 핵심이라는 점을 참고했다.
- [Wait-info Policy: Balancing Source and Target at Information Level for Simultaneous Machine Translation](https://arxiv.org/abs/2210.11220): source 정보가 충분하지 않을 때 output을 기다리는 정책이 번역 품질과 지연 균형에 중요하다는 점을 참고했다.
- [End-to-End Simultaneous Speech Translation with Differentiable Segmentation](https://arxiv.org/abs/2305.16093): 고정 길이 분할이나 외부 경계 모델이 번역에 불리한 시점에서 speech를 자를 수 있다는 문제의식을 참고했다.
