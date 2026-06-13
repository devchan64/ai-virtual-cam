# Whisper Sliding-Window STT 리비전 관리 설계

> [개전 배포 버전] 기존 설계문서의 핵심 결정사항을 운영/배포 관점에서 정리한 문서입니다.

작성일: 2026-06-13

## 0) 개정 배포 배경

- 기존 문서는 구현 세부 설계를 축적하면서 장기 운영·온보딩에 적합한 레이아웃이 약해졌습니다.
- 본 문서는 **기존 문서의 정식 개정본**을 기준으로 정리해, 구현팀이 바로 반영할 수 있도록 합니다.
- 핵심 변경은 적용 범위, 운영 제약, 검증 포인트를 함께 제시해 배포용 판단 문서로 사용합니다.

## 1) 왜 이 문서가 필요한가 (개편 목적)

이 문서는 위스퍼 스트리밍 전사에서 생기는 **중복/리비전(문장 덮어쓰기)**를 줄이고, 정확도·지연·안정성(안정적 출력)을 동시에 개선하기 위한 구현 정책을 정리한다.

## 2) 현재 운영 문제

- 짧은 청크는 정확도 저하, 긴 청크는 결과 지연 증가.
- 윈도우 경계에서 문장이 자주 잘려 `pending`이 누적됨.
- 부분 결과를 그대로 출력/번역하면 같은 구간이 반복 갱신되며 문장 품질이 흔들림.
- 다국어 환경(특히 KO/ZH)에서는 구두점 기반 분할이 취약해 경계 오탐이 잦음.

### 2.1 배포 전 확인 포인트

- `pending` 과 `confirmed` 분리가 정확히 구분되는지 확인.
- `sentenceBoundaryBackend` 기본값 및 실패 경로가 정책(폴백 없음)에 맞는지 확인.
- 다국어(특히 KO/ZH) 스트림에서 반복 경계/중복률이 증가하는 구간 존재 여부 확인.

## 2.2 원본 설계 상태 보존 항목(개정판에서 유지)

원본 설계에서 누락 없이 유지해야 할 기본 방침은 다음과 같다.

- 중복 제어/리비전 감소는 `confirmed-only` 출력 + 재확인된 확정 구간만 누적 출력.
- 경계 안정화는 `pending` 기반 강제 확정 패턴(`pending_chunks`, `pending_chars`)을 지표화하고 이를 낮추는 방향으로 단계적 개선.
- 번역은 기본적으로 `final-only`; 중간 상태 번역은 동일 revision 기준 점진 갱신으로만 제한.
- 다국어 장기운영 품질 관점에서 `regex`는 최종 운영 백엔드가 아님.
- 설정 유효성 실패 시 자동 폴백 없이 즉시 실패 노출(Fail-Fast).

## 3) 설계 목표 (문헌 기반)

- **속도**: step 기반 갱신 주기(`stepSeconds`)는 유지.
- **문맥 확보**: `windowSeconds`로 최근 오디오를 충분히 보존.
- **리비전 제한**: `confirmed-only` 정책으로 모달·번역 노출은 안정 구간만 허용.
- **가시성**: 리비전 안정성 지표를 운영 로그에 지속 기록.
- **실패 정책**: 설정 유효성 실패 시 즉시 종료(Fail-Fast), 무조건 fallback 금지.

### 문헌 축약 정렬

- **Whisper-Streaming(2023)**: 부분결과 안정 구간만 확정해 flicker 완화.
- **Simul-Whisper(InterSpeech 2024)**: 경계 감지/attention 기반 truncation 신호를 통한 오차 억제.
- **Streaming ASR Stability(InterSpeech 2020)**: UPWR/UPSR로 체감 품질 반영.
- **WhisperKit(2025)**: 가설 텍스트(hypothesis)와 확정 텍스트(confirmed) 분리로 latency/정확도 균형.

### 3.1 문헌 구현 정렬 항목

- 위 4개 축을 기반으로 **정합성 우선**, **리비전 수치 우선**, **처리량 보존**을 1차 목표로 둔다.

## 4) 기본 처리 파이프라인

```text
오디오 입력
  -> ring buffer 누적
  -> 매 stepSeconds 마다 windowSeconds 구간 채택
  -> Whisper STT 실행
  -> 직전 윈도우 대비 pending/candidate 비교
  -> 안정 구간만 confirmed로 확정
  -> 최종 출력(모달) 및 번역 큐 투입
```

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

운영 체크
- `0.5 <= stepSeconds <= 5.0`
- `stepSeconds <= windowSeconds`
- `0.0 <= commitLagSeconds < windowSeconds`

### 4.1 배포 전 시나리오 예시

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

## 5) 핵심 데이터 모델

- `audio_buffer`: `windowSeconds` 기반 오디오 원본
- `last_window_text`: 직전 윈도우 전체 전사
- `pending_text`: 아직 확정되지 않은 누적 후보
- `committed_text`: 이미 모달 출력된 확정 누적 텍스트
- `recent_committed_fragments`: 반복/중복 억제를 위한 최근 출력 조각(현재 정책에서는 보조 참조)
- `staged_sentence`, `staged_confirmations`, `staged_age`: 문장별 안정성 판단 보조 상태

### 5.1 배포 범위(what is in scope)

- 범위: whisper 슬라이딩 윈도우 파이프라인 내부의 후보 집계/확정 정책, 문장 경계 백엔드 선택, 출력/번역 입력 정책
- 범위 외: 오디오 캡처 계층, 모델 로딩 정책 자체의 교체, GUI 구성 변경
- 제외: `scripts/config/*_tab.py` UI 기본값 편집이 아닌 STT 런타임 정책 자체

## 6) 출력 상태 정의

### 6.1 텍스트 계층

- `hypothesis_text`: 가장 최근 디코딩 결과(내부 비교용)
- `pending_text`: 재작성 가능한 후보구간
- `confirmed_text`: 안정 판정 후 append-only로 출력되는 구간

### 6.2 정합성 규칙

- `confirmed_text`만 모달에 표시.
- `pending`에서 확정되지 않은 구간은 계속 갱신 대상.
- 같은 chunk가 반복되어도 확정 구간만 누적 커밋.
- 출력은 `append-only`로 유지해 중복 번역을 줄임.

### 6.3 배포 수용 기준

- 사용자 화면에는 `confirmed_text`만 출력되어야 함.
- 같은 입력 구간이 같은 창 안에서 서로 다른 최종 문장으로 잦은 전환되지 않아야 함.
- 번역은 `confirmed_text` 기준으로만 발생해야 함.

## 7) 안정성 판단(코드 정합 용어)

문서의 `confirmed_count`는 실제 구현에서 아래 조합으로 해석한다.

- `staged_confirmations`: 동일 후보가 연속으로 재확인된 횟수
- `staged_age`: 후보가 보류 상태로 남은 chunk 수
- `pending_chunks`, `pending_chars`: 강제 확정 트리거 판단 보조값
- `forced_by=pending_chunks|pending_chars|slow_pending`: 예외 확정 근거
- `forced_by=pending_chars`는 진단 신호로 먼저 해석, 즉시 확정보다 우선은 완만한 확인 정책 유지.

### 7.1 개정 배포에서의 용어 정합

- 내부 변수명을 그대로 사용하지 않고 운영 문서에서는 "확정 전 후보", "보류 구간", "강제 확정" 용어를 사용해 교육/온보딩 부담을 낮춘다.

## 8) 문장 경계 처리 전략 (가장 중요)

### 8.1 기본 선언

**`regex`는 다국어 운영 최종 백엔드로 사용하지 않는다.**

이유
- 다국어 텍스트에서 구두점 의존 분할의 오탐·미탐 위험이 커, 장기 품질/안정성 지표를 하향시킴.
- 장기 운영에서 재확인 비용 상승과 `pending_chars` 누적 증가를 유발.

### 8.2 배포 제약

- 본 개정 배포에서는 `regex`를 실서비스 기본 경계기로 사용하지 않음.
- 다국어 미지원 언어(혹은 테스트 부재 언어)에서는 후보 경로 성능을 보수적으로 관찰하고, 신규 장애 유입 시 기능 토글을 통해 즉시 중단할 수 있어야 함.

### 8.3 후보 도구 검토 목록

- `wtpsplit` / SaT
  - 구두점이 부족한 텍스트에서도 문장 경계를 예측.
  - KO/EN/ZH 다국어 적용 적합성 실험 대상.
  - `sat-3l-sm`류 경량 모델부터 검증 권장.
  - CUDA/ONNX 경로 가능 시도, 실패 시 폴백 금지(Fail-Fast).
- NeMo punctuation/capitalization
  - 구두점 복원 참고 가치 있음.
  - 영어 중심 경향이 강해 KO/ZH 기본 백엔드로는 부적합.
- LLM 기반 후처리
  - 경계·교정 동시 수행 위험이 있어 기본 경로로 사용 불가.
  - 필요한 경우 경계 위치만 반환하는 검증기 형태의 제한적 활용만 허용.
- LocalAgreement 기반 경계 스무딩
  - whisper-stable prefix 기반 경계 결합 방식은 병행 검토.

### 8.4 경계 인터페이스(코드 기준)

문장 경계 검출은 Whisper 실행 루프에서 분리되며, 구현은 `src/app/sentence_boundary.py`로 관리한다.
현재 코드 기준 인터페이스는 다음 형태를 따른다.

```python
@dataclass(frozen=True)
class SentenceBoundaryResult:
    completed: list[str]
    pending: str
    backend: str
    boundary_count: int
    soft_boundary_count: int = 0


class SentenceBoundaryDetector:
    def split(
        self,
        pending_text: str,
        new_text: str,
        language: str = "auto",
        *,
        boundary_confidence: float | None = None,
    ) -> SentenceBoundaryResult:
        ...
```

`split_completed_sentences` 래퍼는 현재 구현에서 경계 모듈 호출 진입점으로 간주한다.

초기/실험 backend 정렬:
- `regex`: 과도기 동작 및 기준선 비교용.
- `sat`: 다국어 실험 후보 1순위(최종 채택 전 검증 단계).

### 8.5 경계 진단 신호(운영 지표)

- `replaced` 비율이 높을수록 후보 안정성이 낮음.
- `pending_chars p90/max` 증가 시 문장 경계 미탐으로 다중 문장 묶임 가능성 증가.
- `end_marks_stable=0`에서 `forced_by=pending_chunks` 또는 `forced_by=pending_chars` 반복 시 구두점 기반 분할 실패 의심.
- 확정 전/후 텍스트가 과도하게 교차할 경우 단순 delta 계산만으로는 충분치 않으므로 경계 모듈 경향을 추가 점검.

## 9) 단계별 확정 규칙

1. 이전 윈도우 결과와 현재 윈도우 결과의 LCP(최장 공통 접두사) 비교
2. 겹치지 않는 새 부분을 `candidate_text`로 추출
3. `commitLagSeconds` 구간(윈도우 끝단)은 즉시 확정하지 않음
4. 동일 후보의 `staged_confirmations` 충족 시 `confirmed` 축적
5. 경계 모듈 결과 존재 시 경계 단위로 완료 후보를 `completed`에 적재
6. 문자열 기반 안정화가 불안정하면 `word_timestamps=true` 기반 시간 정합 후보를 검토(향후 단계)
7. 강제 확정은 `forced_by` 트리거일 때만 제한적으로 사용

### 9.1 배포 판단 규칙

- `stable_prefix` 성격을 훼손하지 않고 문장 경계를 제안해야 함.
- 문장 끝 구두점 유무와 무관하게 경계 제안을 허용하되 pending 만료 임계치(길이/횟수)로 과도 확정을 제한.

## 10) 번역 정책

- 기본은 **final-only**.
- `staged/partial` 번역은 기본 비활성.
- 번역 입력은 `confirmed` 텍스트만 사용.
- 부분 번역 필요 시 `revision id` 기반 라인 갱신 정책 적용.

### 10.1 번역 예시

- 잘못: `current_window_text` 전체 번역
- 위험: staged/partial 문장을 append-only 번역
- 안전: `confirmed_delta`만 번역
- 권고: 동일 revision id 갱신(append-only 라인 사용 금지)

### 10.2 배포 체크리스트

- 다국어 `confirmed`만 큐에 들어가는지 확인
- 번역 엔진이 pending 구간 재전송으로 재계산을 반복하는지 추적
- 번역 결과 표시 지연이 `rtf` 기준 허용 범위를 벗어나지 않는지 확인

## 11) 안정성·성능 지표

- `UPWR`(Unstable Partial Word Ratio)
- `UPSR`(Unstable Partial Segment Ratio)
- `replaced ratio`
- `forced_by=pending_chunks`, `forced_by=pending_chars`
- `pending_chars` p90 / max
- `rtf`, `boundary_latency`
- `UPWR`/`UPSR`는 로그로 수집해 리비전 추적 관측성을 확보한다.

### 11.1 권고 목표(안정성 우선 단계)

- `UPSR`: 20% 하향
- `UPWR`: 15~25% 하향
- `replaced ratio`: 단계별 지속 감소
- `pending_chars p90`: 현재 대비 20% 이상 감소

### 11.2 성능 판단 기준

- `replaced` 확정 비율이 감소해야 함.
- `forced_by` 관련 수치가 하락해야 함.
- `pending_chars p90`과 max 감소.
- STT `rtf`와 분리해 `boundary_latency`가 실시간 갱신 주기에 과도 부담을 주지 않아야 함.
- `UPWR`, `UPSR`은 비교군 대비 하향, 번역 품질은 WER/BLEU/CHRF와 같이 추적.

### 11.3 배포 판정 문턱(권고)

- `UPSR` 및 `UPWR`은 이전 릴리스 대비 하향해야 함.
- `pending_chars p90`은 급증(Regression)하지 않아야 함.
- 동일 구간 재번역률이 유의미하게 감소해야 함.

## 12) 점진적 적용 순서

1. 경계 모듈 분리 정리 및 상태/로깅 정리
2. 기존 슬라이딩 윈도우 테스트를 새 인터페이스 기준으로 정합화
3. 설정 스키마/기본값 정합(현재 값은 `sentenceBoundaryBackend` 동작/실패 처리 포함)
4. 다국어 실험 백엔드(`sat`) 정합성 통합
5. 로그 지표 수집 추가 및 통제군 대비 비교
6. 지표 개선 시 기본 backend 전환 결정
7. 동일 환경/동일 로그 조건에서 과도기(`regex`)과 실험 후보(`sat`)를 비교
8. 전환 후 1~2주 관측 기간 동안 안정성 회귀 모니터링

### 12.1 릴리스 기준 (권고)

- **RC 1**: `final-only` 출력/번역 경로, 롤백 계획 동작 검증
- **RC 2**: 문장 경계 백엔드 실험군 비교(sat vs regex baseline)
- **GA 후보**: 다국어 지표 개선이 반복 실험에서 확인되었고 장애율이 기준 내일 때

### 12.2 구현 우선순위(요약)

1. 문자열 LCP + 재확인 카운트 기반 stable 확정(현재 구조 최소 변경)
2. 문장 경계 detector 분리 및 `sat` 백엔드 실험
3. UPWR/UPSR/forced 지표 수집
4. 안정성 기준 통과 시 `replacements-trimming` 계층(경계 불안정 토큰 제거) 도입
5. Two-Pass/causal fine-tune 검토(모델 계층 변경 단계)

## 13) 실패 시 대응(간단 규칙)

- 임계 지표 악화 시 자동 rollback 정책은 문서화하지 않되, 실시간 실행은 즉시 경고 및 운영자 개입 필요.
- 백엔드 초기화/로딩 실패는 조건부 CPU fallback 대신 즉시 실패 노출.

### 13.1 개정 배포 운영 절차

- 배포 직후 24시간은 운영자 모니터링 모드(`pending`·`confirmed`·`rollback` 유사지표)로 1분 단위 확인.
- 회귀가 누적되면 원본 배포 채널로 되돌리고 원인 로그를 묶어 1페이지 인시던트 노트 작성.

## 14) 참고

- [Turning Whisper into Real-Time Transcription System](https://arxiv.org/abs/2307.14743)
- [Simul-Whisper](https://www.isca-archive.org/interspeech_2024/wang24ea_interspeech.pdf)
- [Analyzing the Quality and Stability of a Streaming End-to-End On-Device Speech Recognizer](https://www.isca-archive.org/interspeech_2020/shangguan20_interspeech.pdf)
- [WhisperKit](https://openreview.net/pdf?id=6lC3MPFbVg)
- [Adapting Whisper for Streaming Speech Recognition via Two-Pass Decoding](https://arxiv.org/abs/2506.12154)
- [WhisperRT](https://arxiv.org/abs/2508.12301)
- [Whisper: Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356)
- [Conformer: Convolution-augmented Transformer for Speech Recognition](https://arxiv.org/abs/2005.08100)
- [wav2vec 2.0: A Framework for Self-Supervised Learning of Speech Representations](https://arxiv.org/abs/2006.11477)
- [RNN-Transducer: Sequence Modeling with RNN-T for Streaming ASR](https://arxiv.org/abs/1211.3711)
