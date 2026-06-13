# Whisper 기능 설계

> Whisper 전사, 번역, 출력, 성능 기준을 운영/배포 관점에서 정리한 기능 설계 문서입니다.

작성일: 2026-06-13

## 0) 개정 배포 배경

- 기존 문서는 구현 세부 설계를 축적하면서 장기 운영·온보딩에 적합한 레이아웃이 약해졌습니다.
- 본 문서는 **기존 문서의 정식 개정본**을 기준으로 정리해, 구현팀이 바로 반영할 수 있도록 합니다.
- 핵심 변경은 적용 범위, 운영 제약, 검증 포인트를 함께 제시해 배포용 판단 문서로 사용합니다.

## 1) 왜 이 문서가 필요한가 (개편 목적)

이 문서는 위스퍼 기반 스트리밍 STT를 영상회의 지원 도구로 운영하기 위한 문서입니다.

- 1차 목표: 영상회의에서 발생하는 음성 텍스트를 수집해 실시간 번역(회의 지원)으로 제공
- 2차 목표: 자막이 지원되지 않는 영상 스트리밍 환경에서 실시간 스크립트를 생성해 화면 자막을 보완

이 문서는 위스퍼 기능의 전사, 번역, 출력, 성능 기준을 정리한다. 슬라이딩 윈도우는 중복/리비전(문장 덮어쓰기)을 줄이고 정확도·지연·안정성을 개선하기 위한 구현 방법 중 하나로 다룬다.

## 2) 현재 운영 문제

- 짧은 청크는 정확도 저하, 긴 청크는 결과 지연 증가.
- 윈도우 경계에서 문장이 자주 잘려 `pending`이 누적됨.
- 부분 결과를 그대로 출력/번역하면 같은 구간이 반복 갱신되며 문장 품질이 흔들림.
- 다국어 환경(특히 KO/ZH)에서는 구두점 기반 분할이 취약해 경계 오탐이 잦음.

### 2.1 배포 전 확인 포인트

- `pending` 과 `confirmed` 분리가 정확히 구분되는지 확인.
- `sentenceBoundaryBackend` 기본값 및 실패 경로가 정책(폴백 없음)에 맞는지 확인.
- 다국어(특히 KO/ZH) 스트림에서 반복 경계/중복률이 증가하는 구간 존재 여부 확인.

### 2.2 원본 설계 상태 보존 항목(개정판에서 유지)

원본 설계에서 누락 없이 유지해야 할 기본 방침은 다음과 같다.

- 중복 제어/리비전 감소는 `confirmed-only` 출력 + 재확인된 확정 구간만 누적 출력.
- 경계 안정화는 `pending` 기반 강제 확정 패턴(`pending_chunks`, `pending_chars`)을 지표화하고 이를 낮추는 방향으로 단계적 개선.
- 번역은 기본적으로 `final-only`; 중간 상태 번역은 동일 revision 기준 점진 갱신으로만 제한.
- 다국어 환경에서는 `regex` 운영 시나리오를 폐기함.
- 설정 유효성 실패 시 자동 폴백 없이 즉시 실패 노출(Fail-Fast).


### 2.3 문헌 반영 상태(2026-06-13)

- confirmed-only 출력 + 재확인된 확정 구간만 누적 출력.
- 경계 안정화는 `pending_chunks`, `pending_chars` 기반 지표를 낮추는 방식으로 단계적 강화.
- 번역은 `final-only`를 우선 유지하고 partial/staged 번역은 same revision 갱신으로 제한.
- 다국어 환경에서 `regex` 운영 시나리오는 폐기함.
- `sentence_boundary.py`는 런타임 factory(`create_sentence_boundary_detector`) 기준으로 정합 완료. `split_completed_sentences`는 legacy 회귀 테스트 helper로만 유지.
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

## 4) 슬라이딩 윈도우 처리 파이프라인

```text
audio 입력
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
  "stepSeconds": 1.5,
  "windowSeconds": 7.5,
  "commitLagSeconds": 1.5,
  "beamSize": 3,
  "maxNewTokens": 96,
  "temperature": 0.0,
  "sentenceBoundaryBackend": "sat",
  "sentenceBoundaryModel": "sat-3l-sm",
  "sentenceBoundaryDevice": "cuda",
  "sentenceBoundaryComputeType": "float16"
}
```

운영 체크
- `0.5 <= stepSeconds <= 5.0`
- `stepSeconds <= windowSeconds`
- `0.0 <= commitLagSeconds < windowSeconds`
- `sentenceBoundaryBackend` 운영값은 `sat`, 테스트/격리값은 `mock`만 허용
- `sentenceBoundaryDevice=cuda`, `sentenceBoundaryComputeType=float16`은 운영 기본 경로이며 실패 시 CPU/regex로 자동 전환하지 않음

### 4.1 배포 전 시나리오 예시

현재 방식:

```text
0.0s ~ 3.0s -> 전사 -> 출력
3.0s ~ 6.0s -> 전사 -> 출력
```

### 4.2 확정/임시 텍스트 분리의 핵심 규칙

WhisperKit/Streaming 경험을 반영해, 모달은 항상 `confirmed`만 노출한다.

- `hypothesis_text`: 최신 청크에서 즉시 생성되는 임시 텍스트(내부 비교 전용)
- `confirmed_text`: LCP/경계 기반으로 확정된 텍스트만 노출
- 확정 후보는 이전 결과와의 겹침(`candidate_text`) 제거 후 비교한다.
- 같은 chunk 반복 처리에서도 확정 구간만 누적하고, 미확정 구간은 계속 갱신한다.
- 출력은 `append-only`로 유지한다.

예:

```text
previous: "Folks, I was one of the first people"
current:  "the first people in the United States to take delivery"
new:      "in the United States to take delivery"
```

초기 구현 원칙:
- 이전/현재 결과의 최장 공통 접두사를 찾아 겹친 부분을 고정 문맥으로 본다.
- 겹치지 않는 신규 부분만 `candidate_text`로 계산한다.
- `commitLagSeconds` 구간은 즉시 확정하지 않는다.
- 동일 후보 재확인 횟수(`staged_confirmations`)를 만족할 때만 `confirmed`를 확장한다.
- 현재 기본 확정 기준은 일반 후보 3회, 강제 후보 4회 재확인이다.
- 구두점 없는 한글 열린 절(`이 두 직업은`, `저녁에 퇴근하고` 등)은 반복 관측만으로 확정하지 않고 다음 revision 기회를 유지한다.
- 정교화 단계에서는 `word_timestamps=true` 기반 시간 정합 후보를 도입한다.

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
- `sentence_boundary_detector`: `create_sentence_boundary_detector`로 생성되는 런타임 경계 검출기
- `boundary_detector_language`: `language=auto`일 때 감지 언어 변경에 따라 `sat` detector를 재생성하기 위한 현재 detector 언어
- `staged_sentence`, `staged_confirmations`, `staged_age`, `staged_forced`: 문장별 안정성 판단 보조 상태
- `replacement_decision`: staged 후보 교체 시 판단 사유(`finalize`, `open_korean_clause`, `partial_revision`, `partial_preserve`, `duplicate_or_suffix`, `aged`)
- `lifecycle_metrics`: 세션 누적 전사 라이프사이클 카운터
- `chunk_metrics`: 현재 chunk에서 발생한 라이프사이클 카운터

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
- 번역은 `confirmed`만 큐에 들어가는지 확인.

## 7) 안정성 판단(코드 정합 용어)

문서의 `confirmed_count`는 실제 구현에서 아래 조합으로 해석한다.

- `staged_confirmations`: 동일 후보가 연속으로 재확인된 횟수
- `staged_age`: 후보가 보류 상태로 남은 chunk 수
- `pending_chunks`, `pending_chars`: 강제 확정 트리거 판단 보조값
- `forced_by=pending_chunks|pending_chars|slow_pending`: 예외 확정 근거
- `forced_by=pending_chars`는 진단 신호로 먼저 해석, 즉시 확정보다 완만한 확인 정책 유지.
- `confirmed` 확정은 일반 후보 3회, forced 후보 4회 재확인을 기본으로 한다.
- `open_korean_clause` 후보는 재확인 횟수를 만족해도 확정하지 않고 다음 경계/리비전 후보를 기다린다.
- `partial_preserve`는 candidate가 staged 문장의 끝부분을 공유하거나 명시적 문장부호로 닫힌 staged의 suffix를 이어받는 경우 staged 문장을 보존하는 결정이다.

### 7.1 개정 배포에서의 용어 정합

- 내부 변수명을 그대로 사용하지 않고 운영 문서에서는 "확정 전 후보", "보류 구간", "강제 확정" 용어를 사용해 교육/온보딩 부담을 낮춘다.

## 8) 문장 경계 처리 전략 (가장 중요)

### 8.1 기본 선언

**`regex`는 다국어 운영 백엔드와 기준선 시나리오에서 제거한다.**

이유
- 다국어 텍스트에서 구두점 의존 분할의 오탐·미탐 위험이 커, 장기 품질/안정성 지표를 하향시킴.
- 장기 운영에서 재확인 비용 상승과 `pending_chars` 누적 증가를 유발.

### 8.2 배포 제약

- 본 개정 배포에서는 `regex`를 실서비스 경계기나 비교 기준선으로 사용하지 않음.
- 다국어 미지원 언어(혹은 테스트 부재 언어)에서는 후보 경로 성능을 보수적으로 관찰하고, 신규 장애 유입 시 기능 토글을 통해 즉시 중단할 수 있어야 함.

### 8.3 후보 도구 검토 목록

- `wtpsplit` / SaT
  - `Segment Any Text` 기반 다국어 분절로 구두점이 부족한 텍스트에서도 문장 경계를 제안.
  - `sat-3l-sm` 류 경량 모델부터 KO/EN/ZH 적합성 실험.
  - `device=cuda`, `compute=float16` 경로 우선, 로딩/실행 실패 시 legacy regex/CPU로 폴백 없이 Fail-Fast.
- PySBD
  - 다국어 분절 라이브러리이나 Golden Rule 기반 규칙 확장 비용이 높아 운영 기본값으로 사용하지 않음.
  - 참고 또는 비교군으로만 제한.
- NeMo punctuation/capitalization
  - ASR 텍스트 구두점 복원용 참고 가치.
  - 영어 중심 편향으로 KO/ZH 기본 백엔드로 부적합.
- LLM 기반 후처리
  - 경계와 교정을 동시에 수행하면 원문 보존 위험이 큼.
  - 사용 시 경계 위치 반환만 허용되는 검증기 형태 제한.
- LocalAgreement 기반 경계 스무딩
  - whisper-stable prefix 기반 경계 결합 방식으로 확장 검토.
- 적용 원칙
  - 후보 경로는 STT 텍스트를 재작성하지 않고 경계만 제안.
  - 특정 문구 기반 예외 규칙 추가 확장은 다국어/멀티도메인에서 재발 위험.

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

런타임 호출 진입점은 `create_sentence_boundary_detector`로 생성한 detector의 `split()`이다. `split_completed_sentences` 래퍼는 과거 회귀 테스트와 legacy helper 용도로만 유지하며, 운영 루프에서 사용하지 않는다.

초기/실험 backend 정렬:
- `sat`: 현재 운영 기본 backend. `wtpsplit.SaT` 모델을 로드하며 `device=cuda`, `compute=float16` 경로를 기본으로 한다.
- `mock`: 테스트/격리용 backend. 실제 운영 품질 비교군으로 사용하지 않는다.
- `legacy-regex`: 과거 회귀 테스트 보존용 helper. 운영 backend와 기준선 비교용으로 사용하지 않으며 `WhisperConfig`에서도 허용하지 않는다.

현재 런타임 제약:
- `sat` 로딩 시작/완료 로그에는 backend, model, device, compute, language를 출력한다. 캐시에 모델이 없으면 Hugging Face 다운로드가 발생할 수 있음을 stdout 로그로 남긴다.
- `sat` 로딩/분절 실패는 Fail-Fast다. legacy regex나 CPU로 자동 전환하지 않는다.
- `language=auto`일 때 감지 언어가 바뀌면 `sat` detector를 해당 언어 기준으로 다시 로드한다. 고정 언어 설정에서는 detector 언어를 실행 중 암묵 변경하지 않는다.

### 8.5 경계 진단 신호(운영 지표)

- `replaced` 비율이 높을수록 후보 안정성이 낮음.
- `pending_chars p90/max` 증가 시 문장 경계 미탐으로 다중 문장 묶임 가능성 증가.
- `end_marks_stable=0`에서 `forced_by=pending_chunks` 또는 `forced_by=pending_chars` 반복 시 구두점 기반 분할 실패 의심.
- 확정 전/후 텍스트가 과도하게 교차할 경우 단순 delta 계산만으로는 충분치 않으므로 경계 모듈 경향을 추가 점검.
- `lifecycle_metrics`는 세션 누적 추세를, `chunk_metrics`는 해당 chunk의 이벤트를 추적한다.
- `stage_replace_decision_finalize`가 많으면 staged 후보가 너무 쉽게 교체 확정되는지 확인한다.
- `stage_discard_reason_open_korean_clause`가 많으면 열린 한글 절을 과도하게 폐기하고 있는지 확인한다.
- `finalize_duplicate_suppressed`가 증가하면 중복 출력은 막고 있지만 앞단 경계/리비전이 불안정하다는 신호로 본다.

## 9) 단계별 확정 규칙

1. 이전 윈도우 결과와 현재 윈도우 결과의 LCP(최장 공통 접두사) 비교
2. 겹치지 않는 새 부분을 `candidate_text`로 추출
3. `commitLagSeconds` 구간(윈도우 끝단)은 즉시 확정하지 않음
4. 동일 후보의 `staged_confirmations` 충족 시 `confirmed` 축적
5. 경계 모듈 결과 존재 시 경계 단위로 완료 후보를 `completed`에 적재
6. 문자열 기반 안정화가 불안정하면 `word_timestamps=true` 기반 시간 정합 후보를 검토(향후 단계)
7. 강제 확정은 `forced_by` 트리거일 때만 제한적으로 사용
8. replacement 단계에서 `partial_preserve`로 판단된 후보는 기존 staged 문장을 먼저 보존하고 새 candidate를 다음 stage로 관찰
9. replacement 단계에서 `open_korean_clause`로 판단된 후보는 확정하지 않고 폐기/대기 경로로 보내 다음 문장 경계 후보를 기다림

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

### 10.2 번역 배포 체크리스트

- 다국어 `confirmed`만 큐에 들어가는지 확인
- 번역 엔진이 pending 구간 재전송으로 재계산을 반복하는지 추적
- 번역 결과 표시 지연이 `rtf` 기준 허용 범위를 벗어나지 않는지 확인

## 11) 근거논문 기반 KPI 리포트 프레임(개정판)

운영 판단은 “지표가 좋아졌는가”가 아니라, “개정 목표(중복 감소·지연 제어·번역 안정성)가 달성되었는지”를 문헌 근거 지표로 판정한다.

### 11.1 문헌-지표 정합

- **Turning Whisper into Real-Time Transcription System (2023)**: 실시간 디코딩에서 `confirmed`와 `hypothesis` 분리의 정합성이 핵심.
- **Streaming ASR Stability (Interspeech 2020)**: 사용자 체감 안정성 지표로 `UPWR/UPSR`를 제시, 리비전 품질의 직접 측정치로 사용.
- **Simul-Whisper (InterSpeech 2024)**: 경계 시점의 과도 지연과 안정성 간 트레이드오프를 측정해야 함.
- **WhisperKit (2025)**: confirmed/hypothesis 분리 설계의 운영 적용성은 번역 지연 및 중복 전파 감소에 직접적 반영.
- **Adapting Whisper for Streaming ASR via Two-Pass Decoding (2025)**: 리비전이 줄더라도 지연이 과도하게 늘면 사용자 체감이 저하됨을 전제.

위 근거를 반영해 KPI를 아래 3개 축으로 묶는다.

1. **안정성 축**: 리비전 빈도·규모 감소 (`UPWR`, `UPSR`, `replaced ratio`, `rollback_rate`)
2. **경계 축**: 문장 경계 추정 품질 (`pending_chars`, `forced_by`, `boundary_latency`, `end_marks_stable`)
3. **지연/번역 축**: 실시간성 (`stt_rtf`, `total_rtf`), 번역 부하 (`confirmed_only_delta`, `translation_redundant_ratio`)

### 11.2 실험 설계(동작/동일 조건)

#### A. 비교군 정의

- **Baseline**: 이전 운영 로그와 수집 지표. `sentenceBoundaryBackend=regex` 기준선은 폐기.
- **Candidate A**: `sentenceBoundaryBackend=sat` 기본값(실험군)
- **Candidate B(옵션)**: `sat + pending/강제 확정 임계치 조정`(후속 실험)

#### B. 데이터 분할

- 언어군: `KO`, `EN`, `ZH`를 동일 비율로 운영 동일 조건 재생
- 사용 시나리오:  
  - 일반 회의 발화
  - 연속 낭독/긴 문장
  - 빠른 발화 전환/문장 경계 희박 구간
  - 무음/잡음이 섞인 구간
- 고정 변수: step/window/commitLag, 샘플링 레이트, 모델 크기, 디바이스, 번역 백엔드, UI 렌더링 옵션

#### C. 실행 절차(권장)

1. `baseline`/`candidate`를 동일 오디오 세션 2회 반복 수행(시드 고정).
2. 각 세션당 12~20분, 최소 30분/언어권.
3. 로그 레벨 `INFO`에서 이벤트 텍스트/타임스탬프 저장.
4. 로그 수집 → KPI 집계 스크립트 실행.
5. 주단위로 KPI 시트 생성, 릴리스 문턱과 비교.

### 11.3 지표 정의(수집식)

#### 11.3.1 로그 입력(필수 필드)

- `split event`: `chunk`, `completed`, `final`, `pending_text`, `forced_by`, `boundary_backend`, `pending_chars`, `pending_chunks`, `pending_chars_per_chunk`
- `commit event`: `step`, `window`, `commit_lag`, `stt_elapsed`, `stt_rtf`, `translation_elapsed`, `total_elapsed`, `total_rtf`, `beam`, `max_tokens`, `text_chars`
- `transcript fragment`: `delta_text`, `state(confirmed|pending|partial)`, `revision_id`(있으면)

#### 11.3.2 핵심 KPI 공식

- `UPWR = unstable_word_count / emitted_word_count`
  - 같은 오디오 구간에서 확정 전/후로 **삭제/교체된 단어 수 / 누적 출력 단어 수**
- `UPSR = unstable_segment_count / emitted_segment_count`
  - 확정 세그먼트 기준 교체/삭제 비율
- `ReplacedRatio = replaced_count / emitted_segment_count`
  - `forced_by` 유무와 무관하게 순수 재작성 비율
- `ForcedByRate = (forced_by=pending_chars or pending_chunks count) / split_count`
- `PendingOverrun = pending_chars_p90`, `pending_chars_max`, `slow_pending_count`
- `DupAmplification = total_output_chars / canonical_committed_chars`
  - 1.0에 가까울수록 이상 없음
- `BoundaryLatencyP95 = p95(boundary_detect_end - chunk_end)`(로그에서 경계 처리 구간으로 대체 계산)
- `Latency = p95(stt_rtf)` 및 `p95(total_rtf)`

#### 11.3.3 번역 영향 지표

- `confirmed_only_ratio = confirmed_delta_bytes / total_transcript_bytes`
- `translation_redundant_ratio = duplicated_translation_chars / total_translation_chars`
- `translation_delay_p95 = p95(translation_submit_ts - confirmed_commit_ts)`
- 번역 품질 `WER/BLEU/CHRF`는 오디오 정답 대비 오프라인 점검군에서 별도 계산
  - **번역은 보정용 KPI가 아니라 배포 리스크 지표로 사용**

### 11.4 보고서 생성 워크플로우

#### 리포트 산출물(권장 형식)

- `summary`: config 요약, 실험군/대조군 식별자, 총 세션수, 오디오 길이
- `kpi_by_lang`: 언어별 `UPWR`, `UPSR`, `pending_chars_p90`, `forced_by_rate`, `p95 rtf`, `p95 boundary_latency`
- `kpi_diff`: baseline 대비 Delta 및 상대 개선률
- `risk_flags`: 규정 위반 항목 자동 라벨링
- `go_no_go`: 항목별 자동 판정(정량)

#### 판정 규칙(Go / No-Go / Ramp)

- **Go**
  - `UPWR`, `UPSR`가 baseline 대비 각각 15% 이상 개선
  - `pending_chars_p90`이 baseline 대비 10% 개선
  - `confirmed_only_ratio >= 0.9`
  - `p95(total_rtf)`가 목표값(예: 0.5) 이내
- **No-Go**
  - 임의 1개 이상 중대한 회귀(정량 기준):
    - `p95(total_rtf)`가 baseline 대비 +20% 이상 악화
    - `UPWR` 또는 `UPSR`이 baseline 대비 +15% 이상 악화
    - `DupAmplification > 1.3` 지속
- **Ramp**
  - Go/No-Go 임계 미만이지만 품질 회복 여지가 있는 경우
  - 규칙: `pending_chars`와 `forced_by`가 개선되고 `rtf` 악화가 5% 이하일 때

### 11.5 최소 수집 템플릿(예시)

- 파일: `docs/reports/whisper-sliding-window-kpi-{{date}}.md`
- 기본 항목:
  - 실행 식별자 / 실험군
  - 조건(모델, step/window/commitLag, backend)
  - 언어별 KPI 표
  - 회귀 요약 Top 5 로그 예시
  - 다음 액션(해결/유보/전환) 체크리스트

### 11.6 운영 주기 및 반영 절차

- **일간**: 1회 자동 KPI 수집, 지표 급변 감시(`forced_by`, `UPSR`, `rtf`)
- **주간**: 후보군 비교 리포트 배포 리뷰
- **릴리스 직전 2주**: 동일 세션셋으로 재현성 검증, 최종 판정

## 12) 성능 추적 목표

Whisper 실시간 전사/번역 경로의 품질은 unittest의 성공/실패만으로 판단하지 않는다. `tests/unit/test_whisper_performance_tracking.py`는 누적 운영 로그에서 관측한 중복, 누락, revision, stability 사례를 실행해 현재 로직의 성능 추이를 출력하는 추적 하네스다.

unittest 성공은 테스트 코드가 실행되어 지표가 수집되었다는 의미만 갖는다. 품질 개선 목표는 실행 끝에 출력되는 `[whisper-tracking]`의 `rate`를 올리고 `rate_gap`을 줄이는 것이다.

| 도메인 | 의미 | 목표 케이스 | 목표율 |
| --- | --- | ---: | ---: |
| `revision` | 이전 partial/final 문장이 새 STT 윈도우에서 올바르게 갱신되는지 | 90 | 90% 이상 |
| `distinct` | 서로 다른 문장을 잘못된 revision으로 합치지 않는지 | 25 | 95% 이상 |
| `collapse` | 같은 의미의 인접 반복 문구를 줄일 수 있는지 | 45 | 90% 이상 |
| `stability` | 연속 partial 전사가 전체 재출력 없이 안정적으로 revision되는지 | 10 | 80% 이상 |
| `replacement` | staged 후보 교체 시 보존/폐기/확정 결정이 의도와 맞는지 | 9 | 90% 이상 |

`distinct` 목표율을 더 높게 둔 이유는 서로 다른 문장을 병합하면 원문 손실이 발생하고, 이후 번역도 복구할 수 없기 때문이다. `revision`과 `collapse`는 중복을 줄이는 방향의 품질 지표지만, 과도한 병합보다 손실 위험이 낮으므로 초기 목표율을 90%로 둔다. `stability`는 incremental ASR의 partial hypothesis instability와 revokes 문제를 현재 코드의 revision lifecycle에 맞춘 프록시 지표다. `replacement`는 2026-06-13 30분 운영 로그에서 관측된 staged 교체 손실을 직접 추적하기 위해 추가한 지표이며, `open_korean_clause`와 `partial_preserve` 결정의 회귀를 막는다.

### 12.1 운영 규칙

- 성능 추적 테스트의 성공/실패 자체에 품질 통과 의미를 부여하지 않는다.
- 새 로그에서 중복/누락/잘못된 revision이 관측되면 케이스를 추가한다.
- 케이스 추가로 tracking rate가 내려가는 것은 정상적인 관측 신호다.
- 알고리즘, 버퍼 라이프사이클, revision 판단 개선으로 rate를 올리고 gap을 줄인다.
- 목표율 변경은 서비스 요구가 바뀌거나 정답 코퍼스 기반 WER/CER 평가가 도입될 때 문서와 함께 수행한다.

### 12.2 다음 평가 기준

정답 전사 코퍼스가 준비되면 다음 지표를 추가한다.

- `WER` 또는 한국어/중국어에 적합한 `CER`: 정답 전사 대비 전사 오류율.
- `UPWR`/`UPSR`: 이미 표시된 partial/hypothesis가 확정 전까지 얼마나 흔들리는지 측정한다.
- `deletion rate`: 사용자가 관측한 문장 손실 문제를 직접 측정한다.
- `duplicate insertion rate`: 반복 문장 확정 문제를 직접 측정한다.
- `RTF`: `처리 시간 / 오디오 길이`로 실시간 가능성을 확인한다.
- `latency`: final 문장이 확정되어 전사/번역 창에 표시되기까지의 지연.
- `revokes per second`: 이미 표시된 단어가 뒤 청크에서 수정되는 빈도.
- `word/segment instability`: partial result가 final 전까지 흔들리는 정도.

## 12.3 2026-06-13 운영 관측 반영

30분 운영 로그 모니터링 결과는 다음과 같다.

- 1차 관측 파일: `.tmp/whisper-monitor-20260613-2.log`
- 1차 수집량: 30분, 18,158개 이벤트
- 1차 성능: 평균 `stt_rtf≈0.088`, 최대 `stt_rtf≈0.13`
- 2차 관측 파일: `.tmp/whisper-monitor-20260613-3.log`
- 2차 수집량: 30분, 6,892개 이벤트, 1,124개 chunk, 2,412개 transcript
- 2차 성능: 평균 `stt_rtf≈0.096`, 최대 `stt_rtf≈0.13`, 평균 `total_rtf≈0.097`
- 결론: 계산 성능보다 문장 확정 라이프사이클과 staged 교체 판단 순서가 품질 병목이다.

반영된 변경 사항:

- 일반 후보 확정 기준을 2회에서 3회 재확인으로 조정했다.
- forced 후보 확정 기준은 4회 재확인을 유지한다.
- `commitLagSeconds` 기본/운영값은 1.5초로 정렬한다.
- VAD 기반 필터링은 현재 슬라이딩 윈도우 확정 정책과 충돌해 운영 경로에서 제거한다.
- `chunk_metrics`를 추가해 해당 chunk에서 발생한 `stage_start`, `stage_revision`, `stage_replace`, `stage_discard`, `finalized` 등을 즉시 확인한다.
- `replacement` 추적 테스트를 추가해 staged 교체 결정의 보존/폐기/확정 품질을 별도 관리한다.
- 열린 한글 절은 반복 관측만으로 확정하지 않는다.
- replacement 판단에서도 `open_korean_clause`가 `confirmed`보다 우선한다. 재확인 횟수를 만족해도 열린 절이면 확정하지 않는다.
- partial replacement에서 기존 staged가 문장형으로 닫혔거나 candidate와 tail overlap이 충분하면 staged 문장을 보존한다.

대표 회귀 케이스:

- `이 두 직업은`이 두 번 관측되어 확정됐지만 실제로는 다음 문장의 열린 절이었다.
- `1억을 넣었을 때 2000만원이 깨지는 천만원에서 20% 빠졌을 때 200이 깨지는 느낌`은 4회 관측됐지만 열린 절이므로 다음 candidate로 교체될 때 확정하면 안 된다.
- `특히 스웨덴의 러브블 이란 회사가 지금 제일 잘 나갑니다`가 다음 candidate와 partial overlap되며 폐기될 위험이 있었다.
- `엔진이 아닌 전기로 돌아가기 시작한 건 사실 1920년도 에요 50년 정도가 더 걸렸습니다`처럼 다음 문장 머리와 tail overlap이 섞인 경우 staged 보존이 필요했다.

현재 추적 지표 예시:

```text
replacement=9/9 rate=1.000 target>=0.90
revision=97/107 rate=0.907 target>=0.90
distinct=38/38 rate=1.000 target>=0.95
collapse=49/53 rate=0.925 target>=0.90
stability=10/10 rate=1.000 target>=0.80
```

## 13) 점진적 적용 순서

1. 경계 모듈 분리 정리 및 상태/로깅 정합화
2. 기존 슬라이딩 윈도우 테스트를 새 인터페이스 기준으로 정합화
3. 설정 스키마/기본값 정합(현재 값은 `sentenceBoundaryBackend` 동작/실패 처리 포함)
4. 다국어 기본 백엔드(`sat`)의 CUDA/float16 로딩 및 분절 실패 케이스를 Fail-Fast 기준으로 안정화
5. 로그 지표 수집 추가 및 통제군 대비 비교
6. 지표 개선 시 `sat` 운영 기본값 유지 여부를 재확인
7. 동일 환경/동일 로그 조건에서 `sat` 결과를 이전 운영 로그와 비교하되 `regex`를 재도입하지 않음
8. 전환 후 1~2주 관측 기간 동안 안정성 회귀 모니터링

### 13.1 릴리스 기준 (권고)

- **RC 1**: `final-only` 출력/번역 경로, 롤백 계획 동작 검증
- **RC 2**: `sat` 운영 지표 검증 및 이전 로그 대비 중복/누락 감소 확인
- **GA 후보**: 다국어 지표 개선이 반복 실험에서 확인되었고 장애율이 기준 내일 때

### 13.2 구현 우선순위(요약)

1. 문자열 LCP + 재확인 카운트 기반 stable 확정(현재 구조 최소 변경)
2. 문장 경계 detector 분리 및 `sat` 백엔드 운영 정합화
3. UPWR/UPSR/forced 지표 수집
4. 안정성 기준 통과 시 `replacements-trimming` 계층(경계 불안정 토큰 제거) 도입
5. Two-Pass/causal fine-tune 검토(모델 계층 변경 단계)

## 14) 실패 시 대응(간단 규칙)

- 임계 지표 악화 시 자동 rollback 정책은 문서화하지 않되, 실시간 실행은 즉시 경고 및 운영자 개입 필요.
- 백엔드 초기화/로딩/분절 실패는 조건부 CPU fallback 또는 legacy regex fallback 대신 즉시 실패 노출.
- 모델 다운로드가 필요한 경로는 다운로드 가능성을 사전에 로그로 출력한다.

### 14.1 개정 배포 운영 절차

- 배포 직후 24시간은 운영자 모니터링 모드(`pending`·`confirmed`·`rollback` 유사지표)로 1분 단위 확인.
- 회귀가 누적되면 원본 배포 채널로 되돌리고 원인 로그를 묶어 1페이지 인시던트 노트 작성.

## 15) 참고

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
- [Segment Any Text: A Universal Approach for Robust, Efficient and Adaptable Sentence Segmentation](https://arxiv.org/abs/2406.16678)
- [wtpsplit GitHub README](https://github.com/segment-any-text/wtpsplit)
- [Where’s the Point? Self-Supervised Multilingual Punctuation-Agnostic Sentence Segmentation](https://aclanthology.org/2023.acl-long.398/)
- [PySBD: Pragmatic Sentence Boundary Disambiguation](https://arxiv.org/abs/2010.09657)
- [NIST SCTK, the NIST Scoring Toolkit](https://github.com/usnistgov/SCTK)
- [Assessing Latency in ASR Systems: A Methodological Perspective for Real-Time Use](https://arxiv.org/abs/2409.05674)
- [Dynamic Latency for CTC-Based Streaming Automatic Speech Recognition With Emformer](https://arxiv.org/abs/2203.15613)
- [Benchmarking LF-MMI, CTC and RNN-T Criteria for Streaming ASR](https://arxiv.org/abs/2011.04785)
- [Evaluating Automatic Speech Recognition in an Incremental Setting](https://arxiv.org/abs/2302.12049)
- [Word Error Rate Estimation Without ASR Output: e-WER2](https://arxiv.org/abs/2008.03403)
- [Assessing ASR Model Quality on Disordered Speech using BERTScore](https://arxiv.org/abs/2209.10591)
