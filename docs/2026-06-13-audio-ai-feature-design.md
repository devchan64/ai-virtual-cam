# 오디오 AI 기능 설계

> 오디오 AI의 STT, 문장 추적, 번역, 출력, 성능 기준을 운영/배포 관점에서 정리한 기능 설계 문서입니다.

작성일: 2026-06-13

## 기능 도메인 분류

프로젝트의 사용자 기능명은 규모와 책임을 기준으로 다음처럼 구분한다.

| 규모 | 도메인 | 책임 |
| --- | --- | --- |
| 1차 기능 | 카메라 | 입력 캡처, 세그멘테이션, 배경 합성, 프레이밍, 가상 카메라 출력 |
| 1차 기능 | 오디오 | 오디오 입력/출력, 믹서, 게이트, 노이즈 처리, 가상 오디오 출력 |
| 2차 기능 | 오디오 AI | 오디오 입력 기반 STT, 문장 경계/리비전 관리, 번역, 전사/번역 창, 모델 캐시/다운로드 검사 |
| 구현 기술 | Whisper/faster-whisper | 오디오 AI에서 선택 가능한 STT 또는 영어 번역 백엔드 |
| 구현 기술 | SaT/NLLB/M2M100 | 오디오 AI에서 선택 가능한 STT, 문장 경계, 번역 백엔드 |

따라서 사용자에게 보이는 탭/창/문서 제목은 `오디오 AI`를 사용한다. 기존 `setting.json`의 `whisper` 블록, `WhisperConfig`, 일부 파일명은 호환성 유지를 위한 내부 계약 이름으로 남긴다. 내부 키를 즉시 변경하면 기존 설정 파일과 테스트 자산을 깨뜨리므로, 별도 마이그레이션 설계 전까지는 사용자 노출 이름과 내부 호환 키를 분리한다.

## 0) 개정 배포 배경

- 기존 문서는 구현 세부 설계를 축적하면서 장기 운영·온보딩에 적합한 레이아웃이 약해졌습니다.
- 본 문서는 **기존 문서의 정식 개정본**을 기준으로 정리해, 구현팀이 바로 반영할 수 있도록 합니다.
- 핵심 변경은 적용 범위, 운영 제약, 검증 포인트를 함께 제시해 배포용 판단 문서로 사용합니다.

## 1) 왜 이 문서가 필요한가 (개편 목적)

이 문서는 오디오 AI를 영상회의 지원 도구로 운영하기 위한 문서입니다. 프로젝트의 큰 기능 축은 카메라와 오디오이며, 오디오 AI는 오디오 영역 안에서 STT, 문장 추적, 번역, 모델 준비를 담당하는 하위 도메인입니다. Whisper는 이 도메인의 이름이 아니라 사용할 수 있는 STT/번역 백엔드 중 하나입니다.

- 1차 목표: 영상회의에서 발생하는 음성 텍스트를 수집해 실시간 번역(회의 지원)으로 제공
- 2차 목표: 자막이 지원되지 않는 영상 스트리밍 환경에서 실시간 스크립트를 생성해 화면 자막을 보완

이 문서는 오디오 AI의 전사, 문장 경계, 번역, 출력, 성능 기준을 정리한다. 슬라이딩 윈도우는 중복/리비전(문장 덮어쓰기)을 줄이고 정확도·지연·안정성을 개선하기 위한 구현 방법 중 하나로 다룬다.

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
  -> STT backend 실행
  -> 직전 윈도우 대비 pending/candidate 비교
  -> 안정 구간만 confirmed로 확정
  -> 최종 출력(모달) 및 번역 큐 투입
```

추천 초기값:

```json
{
  "stepSeconds": 1.5,
  "windowSeconds": 9.0,
  "commitLagSeconds": 2.0,
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

WhisperKit/Streaming 경험을 반영해, 오디오 AI 모달은 항상 `confirmed`만 노출한다.

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
- `commitLagSeconds` 구간은 즉시 확정하지 않는다. 이 값은 STT 윈도우 끝단의 불안정한 tail을 보류하는 입력 안정화 장치이며, 문장 경계 모델의 신뢰도와는 별개의 시간 보류값이다.
- 동일 후보 재확인 횟수(`staged_confirmations`)를 만족할 때만 `confirmed`를 확장한다. 문장 경계 모델이 `completed` 후보를 반환해도 STT 가설 텍스트는 다음 윈도우에서 고쳐질 수 있으므로, 후보 재확인은 ASR revision 안정성을 확인하는 생명주기다.
- 현재 기본 확정 기준은 일반 후보 3회, 강제 후보 4회 재확인이다. 문장 경계 성능이 충분해 보이는 언어/백엔드에서도 확정 지연을 제거하기보다는 `commitLagSeconds`와 재확인 횟수를 분리해 지표 기반으로 낮춘다.
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
- `boundary_detector_language`: 명시된 STT 언어에 맞춰 detector를 재생성하기 위한 현재 detector 언어
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
  - 단, SaT 논문의 주된 문제정의는 일반 텍스트 sentence segmentation이다. Whisper의 sliding-window partial transcript처럼 매 chunk마다 이전 가설이 재작성되는 실시간 ASR 스트림에는 그대로 적합하다고 가정하지 않는다.
  - 운영 기본값으로 유지하더라도 `boundary_complete`, `pending_overrun`, `stage_discard_reason_empty`, `revision churn`을 언어별로 검증해 부적합성이 확인되면 ASR punctuation restoration 계열 모델로 전환한다.
- ASR punctuation restoration / boundary scoring 모델
  - 스트리밍 ASR 논문들은 문장 경계와 구두점 복원을 STT와 별도 문제로 다룬다.
  - 입력 전사 텍스트를 재작성하지 않고 토큰 사이 구두점/경계만 scoring하는 sequence-labeling 또는 non-autoregressive scoring 모델을 우선 검토한다.
  - 중국어/만다린은 공백 기반 word boundary가 없어 Mandarin punctuation restoration 연구처럼 Chinese tokenizer/Jieba류 단위 처리를 포함한 모델을 별도 후보로 본다.
  - generation 기반 LLM 후처리는 원문 보존 위험이 있으므로 운영 기본 후보가 아니라 오프라인 비교군으로 제한한다.
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

문장 경계 검출은 오디오 AI 실행 루프에서 분리되며, 구현은 `src/app/sentence_boundary.py`로 관리한다.
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
        language: str = "en",
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

언어별 후처리 프로필:
- `postProcessingProfile=manual`: 유일하게 지원하는 후처리 프로필이다. 언어별 후처리 선택을 사용하지 않고 `sentenceBoundaryBackend`/`sentenceBoundaryModel`을 모든 언어에 그대로 사용한다.
- STT backend/model은 후처리 프로필과 분리한다. 영어/한국어/중국어는 각각 `sttBackendEn`, `sttBackendKo`, `sttBackendZh`와 대응 모델 설정으로 교체 가능하다. config GUI는 `language` 단일 선택값에 맞는 언어의 백엔드/모델만 표시하고, 언어를 바꾸면 해당 언어의 후보 목록으로 전환한다.
- 현재 영어/한국어의 STT 모델 타입은 `faster-whisper`와 테스트용 `mock`만 제공한다. 영어/한국어용 추가 모델이 검증되면 언어별 backend 후보에 추가한다.
- 중국어 STT 품질 후보군은 `qwen3-asr-transformers`, 후속 `qwen3-asr-vllm-streaming`, Dolphin-CN-Dialect, WeNet으로 재정리한다. `faster-whisper`는 중국어 정확도가 부족해 비교 기준선으로만 유지한다. FunASR STT 계열은 후보군에서 제외하고 폐기 예정으로 둔다.
- 백엔드별 실행 속성은 `whisper_stt_backend_runtime_option_keys()`에서 정의한다. `faster-whisper`는 `computeType`, `beamSize`, `maxNewTokens`, `temperature`를 노출하고, `qwen3-asr-transformers`와 `qwen3-asr-vllm-streaming`은 `computeType`, `maxNewTokens`를 노출한다. 제거된 FunASR STT 계열 속성은 더 이상 화면에 노출하지 않는다.
- config GUI는 후처리 프로필 선택을 제공하지 않는다. `postProcessingProfile`은 계약 호환을 위해 `manual`로 저장하고, 화면에는 실제 운영되는 `sentenceBoundaryBackend`/`sentenceBoundaryModel` 수동 설정만 노출한다.
- config GUI의 오디오 AI 탭은 `입력/실행`, `STT 언어/모델`, `STT 응답/성능`, `문장 경계`, `번역` 그룹으로 구분한다. 선택 언어와 선택 STT 백엔드에 맞는 설정만 해당 그룹 안에서 표시한다.
- 중국어 처리는 의미 보정/문장 경계 결정을 문자 단위 CJK 토큰화나 suffix overlap 휴리스틱에 맡기지 않는다. 공백 없는 텍스트의 경계와 구두점은 후처리 모델의 책임으로 둔다. 다만 pending 텍스트와 다음 STT 윈도우가 같은 CJK no-space 구간을 내부 중간부터 다시 내보내는 경우, 중복 연결을 막기 위한 결합 단계의 overlap 제거는 허용한다. 이 로직은 문장 경계 판단이 아니라 append-only 버퍼 접합 무결성 보정이며, `pending_chars_per_chunk`, `repeat_collapse_chars`, `candidate_duplicate_suppressed`, `final_quality_cjk_internal_gap`로 회귀를 관찰한다.

현재 런타임 제약:
- 모델 준비 순서는 `STT 모델 -> 번역 모델 -> 문장 경계/후처리 모델 -> 입력 장치 열기 -> 전사 루프`다. 입력 캡처와 전사/번역은 모든 모델 준비가 끝난 뒤 시작한다.
- 모델 다운로드는 serve 시작 전 검사와 config GUI의 모델 다운로드 안내창에서만 수행한다. serve 런타임 모델 로딩은 로컬 캐시 전용이며, 캐시가 없거나 부분 다운로드 상태이면 다운로드하지 않고 Fail-Fast로 중지한다.
- setup은 모델 다운로드를 수행하지 않는다. 모델 다운로드는 config GUI의 오디오 AI 모델 다운로드 모달에서만 수행한다.
- 문장 경계 모델 로딩 시작/완료 로그에는 profile, backend, model, device, compute, language를 출력한다. 캐시에 모델이 없으면 런타임 다운로드를 시도하지 않고, Serve 시작 전 다운로드 안내창 또는 오디오 AI 탭의 모델 다운로드 모달을 사용하라는 오류를 출력한다.
- 문장 경계 모델 로딩/분절 실패는 Fail-Fast다. legacy regex나 CPU로 자동 전환하지 않는다.
- `faster-whisper`, SaT, NLLB/M2M100은 serve 런타임에서 로컬 캐시만 사용한다. Hugging Face 네트워크 다운로드는 `scripts/setup/download-whisper-models.py` 경로로만 허용한다. `qwen-asr==0.0.6`은 `transformers==4.57.6`을 요구하므로 두 패키지를 함께 고정한다. qwen-asr의 `gradio` 요구 범위는 넓어 resolver 역추적을 만들 수 있으므로 dry-run에서 확인한 `gradio==6.17.3`도 고정한다. `wtpsplit`은 `huggingface-hub==0.25.2` 메타데이터 제약이 Qwen3-ASR/transformers와 충돌하므로 패키지 자체는 `requirements.txt`에서 직접 해석하지 않고 setup/env sync에서 `--no-deps`로 설치한다. 단, 충돌하지 않는 wtpsplit 런타임 의존성(`cached_property`, `mosestokenizer`, `skops`, `adapters`)은 fresh venv에서도 import가 가능하도록 `requirements.txt`에 명시한다.
- 후처리 backend/model은 manual 설정만 사용한다. 실행 중 명시 언어가 바뀌어도 후처리 backend/model을 언어별로 암묵 변경하지 않는다.

### 8.5 경계 진단 신호(운영 지표)

2026-06-13 중국어 전사 시도에서 관측된 핵심 지표는 다음과 같다.

- 당시 설정: `language=zh`, `model=large-v3`, `device=cuda`, `compute=float16`, `stepSeconds=1.5`, `windowSeconds=7.5`, `commitLagSeconds=1.5`, `beamSize=3`, `sentenceBoundaryBackend=sat`. 이 값은 초기 실험 조건이며 현재 기본값이 아니다.
- 현재 기본 계약은 STT 언어별로 분리한다. 영어/한국어는 `windowSeconds=7.0`, `stepSeconds=1.0`, `commitLagSeconds=2.0`, `maxNewTokens=192`를 기준으로 하고, 중국어는 `windowSeconds=12.0`, `stepSeconds=1.0`, `commitLagSeconds=2.0`, `maxNewTokens=192`를 기준으로 한다.
- 최근 중국어 구간: `perf=125`, `diag=125`, `zh_transcripts=163`, `errors=0`.
- 속도: `stt_rtf avg=0.075`, `p95=0.100`; 계산 성능은 병목이 아님.
- STT 신뢰도: `low_logprob` 후보 무시 12회. STT 자체 품질 문제도 일부 존재한다.
- 경계 품질: `boundary_complete=0`이 82/125, `slow_pending=19`, `stage_discard_reason_empty`가 53회. 이는 문장 경계/리비전 생명주기가 중국어 스트림을 충분히 다루지 못한다는 신호다.
- 2026-06-13 추가 관측: `language=zh` 고정 상태에서도 `Hey guys`, `read ok ready`, `OK,Ready` 같은 영어/중국어 혼합 출력이 발생했다. 이는 후처리 이전의 raw STT 품질 저하 신호다.
- 결론: 중국어 품질 문제는 STT와 경계 처리 양쪽에서 발생한다. raw STT, boundary output, committed output을 분리 평가하되, 중국어는 Whisper large-v3 고정이 아니라 언어별 STT backend 교체 실험을 포함한다. 최근 로그 기준 Whisper/faster-whisper는 중국어에서 문맥과 의미 보존이 충분하지 않아 정확도 기준 후보에서 제외하고, baseline 비교군으로만 취급한다.

운영 진단 기준:

- `replaced` 비율이 높을수록 후보 안정성이 낮음.
- `pending_chars p90/max` 증가 시 문장 경계 미탐으로 다중 문장 묶임 가능성 증가.
- `end_marks_stable=0`에서 `forced_by=pending_chunks` 또는 `forced_by=pending_chars` 반복 시 구두점 기반 분할 실패 의심.
- 확정 전/후 텍스트가 과도하게 교차할 경우 단순 delta 계산만으로는 충분치 않으므로 경계 모듈 경향을 추가 점검.
- `lifecycle_metrics`는 세션 누적 추세를, `chunk_metrics`는 해당 chunk의 이벤트를 추적한다.
- `stage_replace_decision_finalize`가 많으면 staged 후보가 너무 쉽게 교체 확정되는지 확인한다.
- `stage_discard_reason_open_korean_clause`가 많으면 열린 한글 절을 과도하게 폐기하고 있는지 확인한다.
- `pending_overrun`은 pending이 길이/관측 횟수 임계치를 넘었지만 확정되지 않은 상태를 나타낸다. `long_no_boundary`는 경계 모델이 문장 경계를 찾지 못해 번역 지연이 커질 수 있는 신호다. 일반 overrun은 180자/8 chunks 이상, 빠른 overrun은 240자/4 chunks 이상을 기준으로 추적한다.
- `finalize_duplicate_suppressed`가 증가하면 중복 출력은 막고 있지만 앞단 경계/리비전이 불안정하다는 신호로 본다.
- `pending_chars_per_chunk`가 80~100 이상으로 튀면서 `repeat_collapse_chars=0`이면 문장 경계 모델 실패만이 아니라 pending 결합에서 내부 재시작을 그대로 이어붙인 케이스를 의심한다.
- CJK no-space continuation에서 인위적 공백이 삽입되면 `final_quality_cjk_internal_gap`가 증가할 수 있다. 이 지표는 번역 차단용 hard fail이 아니라 pending 결합/출력 접합 품질 관측용으로 사용한다.

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

### 9.2 모델 적합성 검증 계획

STT 모델과 문장 경계 모델의 책임을 분리해 검증한다.

1. `raw_stt_window`: Whisper가 반환한 window 전체 텍스트를 저장한다. 이 값으로 언어별 CER/WER, `avg_logprob`, `no_speech_prob`, language drift를 평가한다.
2. `boundary_input`: 경계 모델에 들어간 텍스트를 저장한다. 이 값은 raw STT와 동일하거나 명시적 normalization만 적용되어야 한다.
3. `boundary_output`: completed/pending, boundary confidence, boundary count를 저장한다. 이 값으로 boundary F1, over-segmentation, under-segmentation, boundary latency를 평가한다.
4. `committed_output`: 실제 모달/번역에 들어간 확정 텍스트를 저장한다. 이 값으로 deletion rate, duplicate insertion rate, revision churn을 평가한다.
5. 같은 raw STT 입력에 대해 `sat`, Mandarin punctuation restoration, streaming punctuation scoring 모델을 오프라인 replay로 비교한다. 운영 코드는 특정 언어별 regex 보강이 아니라 이 비교 결과로 모델을 교체한다.

중국어/만다린의 1차 후보는 공백 없는 텍스트를 직접 처리하거나 Jieba/Chinese tokenizer 기반 경계 단위를 지원하는 punctuation restoration 모델이다. SaT는 일반 텍스트 segmentation 강점은 있으나, streaming ASR partial hypothesis 안정성은 별도 검증 전까지 가정하지 않는다.

### 9.3 중국어 음운/문맥 의존성 근거

중국어 STT 품질 문제는 모델 종류만의 문제가 아니라 언어 구조 자체의 제약과도 연결된다. Mandarin은 가능한 음절 수가 제한적이고 같은 발음에 대응되는 글자/단어 후보가 많다. 짧은 오디오 조각에서는 음향 정보만으로 글자를 고르기 어렵고, 앞뒤 문맥과 도메인 단어 분포가 더 큰 역할을 한다.

근거:

- 중국어 문자음 자료는 Mandarin이 성조 포함 약 1,300개 수준의 음절에 10,000개 이상의 문자가 대응되어 평균적으로 한 음절에 여러 글자가 매핑된다고 설명한다. 이는 `raw_stt_window`가 짧을수록 문자 선택 후보가 크게 남는 구조적 이유다.
- 중국어 word segmentation 자료는 중국어 텍스트가 공백으로 단어 경계를 표시하지 않으며, 같은 문자열도 문맥에 따라 다른 단어 분할이 가능하다고 설명한다. STT가 만든 글자열도 문장 경계와 단어 경계를 함께 추정해야 하므로 짧은 chunk 단위 확정은 불리하다.
- Chinese ASR error correction 연구들은 중국어 ASR 오류가 환경 잡음뿐 아니라 발음/문맥 모호성 때문에 후단 교정이 필요하다고 보고한다. 특히 Pinyin 정보를 함께 쓰는 오류 교정 연구는 발음 표현을 보강하면 text-only 교정보다 안정적으로 개선된다고 보고한다.
- Contextual ASR 연구들은 named entity와 long-tail word 인식에서 homophone 구분이 핵심 문제이며, phoneme-aware 또는 pronunciation-aware context가 CER/WER 개선에 직접 기여한다고 보고한다.
- Qwen3-ASR Technical Report도 공개 벤치마크 점수가 비슷해도 실제 시나리오 품질 차이가 클 수 있다고 전제한다. 우리 운영 로그에서 Qwen3-ASR/FunASR/SenseVoice가 모두 흔들린 것은 특정 모델 하나의 실패가 아니라, 짧은 실시간 window와 중국어 문맥 의존성이 충돌한 결과로 해석한다.

운영 가설:

1. 중국어는 `stepSeconds`만 낮춰 빠르게 갱신하면 오히려 동음 후보가 짧은 fragment로 확정되어 중복/오인식이 늘 수 있다.
2. `windowSeconds`는 영어/한국어보다 길게 잡아 비교해야 한다. 최소 9초 기준선, 12초/15초 비교군을 둔다.
3. `commitLagSeconds`와 staged confirmation은 중국어에서 더 중요하다. tail의 마지막 1~2초가 다음 윈도우에서 글자 선택을 바꾸는 사례를 별도 지표로 추적한다.
4. raw STT가 불안정하면 문장 경계 모델로 해결할 수 없다. 중국어는 `raw_stt_window`의 CER, mixed-script ratio, homophone-like substitution 사례를 먼저 본 뒤 boundary 품질을 평가한다.
5. 후속 개선 후보는 단순 regex가 아니라 pronunciation-aware ASR/error-correction 또는 Pinyin-aware correction 모델이다.

### 9.4 윈도우 확대와 정확도/지연 트레이드오프

운영 로그에서 `windowSeconds`를 키웠을 때 중국어 전사 안정성이 일부 좋아지는 경향이 관측되었다. 이 판단은 스트리밍 ASR 연구 흐름과 일치한다. 공격적으로 짧은 chunk로 전사를 만들면 segment boundary 근처의 음향/언어 문맥이 잘리고, 후속 윈도우에서 수정될 수 있는 글자 후보를 너무 일찍 확정하게 된다.

근거:

- Whisper-Streaming은 Whisper가 본래 실시간 모델이 아니므로 local agreement policy와 self-adaptive latency를 사용해 여러 윈도우에서 합의된 부분만 확정한다. 이는 짧은 chunk 1회 결과보다 겹치는 문맥의 안정성을 우선하는 구조다.
- WhisperPipe는 aggressive chunking이 정확도를 희생할 수 있고, overlapping context window와 dynamic buffering이 segment boundary 정보 손실을 줄인다고 설명한다.
- CarelessWhisper는 encoder-decoder ASR을 저지연 causal streaming으로 바꾸는 것이 쉽지 않다고 설명한다. 즉, Whisper 계열을 짧은 context로 잘라 쓰면 원래 offline/long-form 모델의 강점을 잃을 수 있다.
- 중국어는 동음 후보와 단어 경계 모호성이 커서 긴 문맥의 언어 모델링 효과가 더 중요할 가능성이 높다.

운영 판단:

- `windowSeconds` 확대는 raw STT 품질과 staged 후보 안정성을 개선할 수 있다.
- 그러나 `windowSeconds + commitLagSeconds + staged confirmation`이 체감 확정 지연의 하한을 만든다. 계산 시간이 충분히 빨라도 자막은 늦게 보일 수 있다.
- `windowSeconds`를 무작정 키우면 중복 후보, tail echo, pending overrun, GPU 메모리 사용량이 늘 수 있다.

실험 설계:

1. 영어/한국어 기준선은 `windowSeconds=7.0`, `stepSeconds=1.0`, `commitLagSeconds=2.0`으로 둔다.
2. 중국어 기준선은 `windowSeconds=12.0`, `stepSeconds=1.0`, `commitLagSeconds=2.0`, `maxNewTokens=192`로 둔다. 원문창이 staged 후보를 표시하던 시기의 해석 오류를 제거한 뒤 12초도 유효한 비교값으로 확인했다. `windowSeconds=16.0`, `20.0`, `24.0`, `30.0`은 중국어 장문 안정성 비교군으로 사용한다.
3. 각 비교군에서 `raw_stt_window` CER, mixed-script ratio, repeated final count, pending overrun, final latency를 기록한다.
4. `total_rtf`가 1.0 미만이어도 final latency가 커지면 실시간 자막 UX 실패로 판단한다.
5. 계산 지연과 정책 지연을 분리하기 위해 성능 로그에는 `stt`, `translation`, `total` 외에 `effective_latency_estimate=windowSeconds+commitLagSeconds+total`을 추가하는 것을 검토한다.

### 9.5 중국어 STT backend 교체 검토

2026-06-13 중국어 운영 로그는 후처리 이전의 raw STT 품질 저하를 보여준다. `language=zh` 고정 상태에서도 영어 조각이 섞이고, `low_logprob`/`no_speech` 폐기가 반복되었다. 따라서 중국어 품질 개선은 문장 경계 모델 교체만으로 판단하지 않고, STT backend 자체를 언어별로 분기하는 실험을 포함한다.

#### 후보 1: Qwen3-ASR vLLM streaming

- Qwen3-ASR Technical Report와 공식 모델 카드는 `Qwen3-ASR-0.6B`, `Qwen3-ASR-1.7B`가 중국어, 영어, 한국어를 포함한 30개 언어와 22개 중국어 방언을 지원한다고 설명한다.
- 공식 모델 카드는 offline/streaming 통합 추론, 긴 오디오 전사, transformers 백엔드와 vLLM 백엔드를 제공한다고 설명한다. streaming 경로는 transformers in-process backend보다 vLLM backend 중심으로 검토한다.
- 논문은 1.7B가 오픈소스 ASR 중 SOTA 수준이며, 0.6B는 정확도/효율 균형과 낮은 TTFT를 목표로 한다고 보고한다.
- 2026-06-14 운영 로그에서 Qwen3-ASR도 완전한 서비스 기준을 만족하지는 못했지만, 같은 중국어 실험군 안에서는 Whisper/faster-whisper와 FunASR Paraformer보다 의미 보존과 문장 구조가 더 나은 후보로 관측되었다.
- 현재 GPU VRAM 조건에서는 `Qwen3-ASR-0.6B`를 먼저 검증한다. `1.7B`와 vLLM streaming은 모델 상주 메모리, 번역 모델 동시 사용, 별도 서버 수명주기 정책을 분리해 후속 실험으로 진행한다.

권장 실험값:

```json
{
  "sttBackendZh": "qwen3-asr-transformers",
  "sttModelZh": "qwen3-asr-0.6b",
  "windowSeconds": 30.0,
  "sentenceBoundaryBackendZh": "sat",
  "sentenceBoundaryModelZh": "sat-3l-sm"
}
```

후속 streaming 설계:

- `qwen3-asr-vllm-streaming` 같은 별도 backend를 추가한다.
- in-process STT가 아니라 별도 ASR service backend로 분리해 vLLM 프로세스 수명주기와 GPU 메모리 정책을 관리한다.
- partial/final 이벤트, session id, stream reset, backpressure, model-ready/download-ready 상태를 명시 계약으로 둔다.

#### 후보 2: Dolphin-CN-Dialect

- Dolphin-CN-Dialect는 중국어/방언 중심 ASR 후보로, 중국어 문자 단위 tokenizer와 영어 subword tokenizer를 구분하는 구조가 중국어 동음/문맥 의존성 문제와 맞닿아 있다.
- 중국어/방언 중심 품질 후보로 추적하되, 현재 프로젝트에는 런타임/다운로드/라이선스/모델 캐시 계약이 아직 없다.
- Qwen3보다 통합 불확실성이 크므로 2차 후보로 둔다. 모델 파일 확보, CUDA 추론 경로, streaming 지원 형태, 입력 chunk/cache API를 먼저 검증한다.

검증 체크리스트:

- 공개 모델 가중치와 로컬 캐시 경로를 확인한다.
- CUDA 또는 ONNX Runtime/TensorRT 경로가 현재 RTX 5070 Laptop GPU에서 동작하는지 확인한다.
- streaming API가 partial/final 이벤트를 제공하는지 확인한다.
- Mandarin, Taiwan Mandarin, code-switching, 음식/지명/가격 표현 로그 샘플로 replay 비교한다.

#### 후보 3: WeNet

- WeNet은 streaming/non-streaming E2E ASR을 production-oriented 구조로 제공하며, dynamic chunk와 CTC/attention rescoring 기반으로 latency와 정확도를 조절할 수 있다.
- 중국어 streaming ASR 연구/운영 기반은 탄탄하지만, 현재 프로젝트에는 WeNet 의존성, 모델 캐시, setup 다운로드, Python adapter가 없다.
- 장점은 streaming 구조 검증에 적합하다는 점이고, 단점은 Qwen3 같은 LLM 기반 문맥 품질을 바로 기대하기 어렵고 통합 비용이 크다는 점이다.
- Qwen3 vLLM streaming이 메모리/운영비용 때문에 막히는 경우의 구조 비교군으로 유지한다.

#### 폐기 예정: FunASR STT 계열

- FunASR Paraformer, Paraformer streaming, SenseVoiceSmall은 2026-06-14 운영 로그에서 중국어 STT 원문 품질이 목표에 미치지 못했다.
- FunASR는 속도는 빠르지만 의미 보존, 문장 구조, stage churn 지표가 Qwen3보다 불리했다. `windowSeconds=30`에서도 인접 전사 유사도는 높았지만 stage 교체/폐기가 많고 확정률이 낮았다.
- 따라서 FunASR STT 계열은 신규 품질 후보군에서 제외하고 폐기 대상으로 둔다. `funasr-paraformer`, `funasr-paraformer-streaming`, `funasr-sensevoice` STT backend와 관련 GUI 옵션, 다운로드 대상, 테스트는 제거한다.

#### 보류 후보

- LLM decoder 기반 Fun-ASR-Nano, GLM-ASR-Nano는 정확도 후보로는 가치가 있으나 vLLM/대형 decoder/VRAM 정책이 추가되어 실시간 UI 경로의 1차 후보로 두지 않는다. FormalASR처럼 spoken Chinese를 written Chinese로 직접 정리하는 fine-tuned 계열은 중국어 회의 자막 품질 개선 후보로 추적한다.
- Whisper large-v3는 영어/한국어 기본 STT로 유지 가능하지만, 중국어는 현재 로그 기준 정확도가 부족해 운영 기본값이나 품질 후보로 고정하지 않는다. 중국어에서 Whisper/faster-whisper는 동일 설정 비교를 위한 baseline으로만 유지한다.

#### 언어별 STT backend 설계 원칙

- `backend=faster-whisper` 전역값에 중국어를 묶지 않는다. STT backend도 후처리 backend처럼 언어별 설정을 둔다.
- 예: `sttBackendEn=faster-whisper`, `sttBackendKo=faster-whisper`, `sttBackendZh=qwen3-asr-transformers`. 영어/한국어는 현재 Whisper 계열만 운영 후보로 둔다. 중국어는 Qwen3-ASR를 품질 우선 후보로 두며, `qwen3-asr-vllm-streaming`은 vLLM/mediapipe 의존성 충돌로 공유 `.venv`에서 비활성화하고, 별도 격리 런타임 후보로만 추적한다. Dolphin-CN-Dialect와 WeNet은 후속 streaming 후보로 추적한다. FunASR STT 계열은 폐기 예정이므로 신규 설정 기본값이나 추천 조합에 사용하지 않는다.
- 중국어 backend 로딩 실패는 Fail-Fast다. CPU fallback, Whisper fallback, 다른 STT backend fallback은 자동 수행하지 않는다.
- Whisper 언어 자동 감지는 폐기한다. `language`는 `ko`, `en`, `zh` 중 하나로 명시해야 한다.
- 모델 준비 순서는 `STT 모델 -> 번역 모델 -> 문장 경계/후처리 모델 -> 입력 장치 열기 -> 전사 루프`를 유지한다.
- config GUI의 오디오 AI 모델 다운로드 모달은 현재 설정에 적용된 STT/문장 경계/번역 모델을 대상으로 한다. `./bin/avc setup`은 런타임 의존성 설치만 담당하고 모델 다운로드를 수행하지 않는다.

2026-06-13 구현 상태:

- `WhisperConfig`/`setting.json`에 `sttBackendEn`, `sttModelEn`, `sttBackendKo`, `sttModelKo`, `sttBackendZh`, `sttModelZh`를 추가했다. 후처리는 manual만 지원한다.
- 명시 인식 언어가 `zh`이면 현재 기본값은 `sttBackendZh=qwen3-asr-transformers`, `sttModelZh=qwen3-asr-0.6b`다. `faster-whisper`/`large-v3`는 중국어 품질 기준선 비교군으로만 유지한다.
- 영어/한국어 기본 STT는 `faster-whisper` + `large-v3`를 유지한다.
- `src/app/stt_model.py`가 faster-whisper와 Qwen3-ASR를 동일한 `transcribe()` 인터페이스로 감싼다. FunASR STT 경로는 제거했다.
- 중국어 STT가 Whisper 내장 번역을 지원하지 않는 backend일 때 `translationBackend=whisper` 조합은 Fail-Fast로 중지한다. 중국어 번역은 NLLB/M2M100 등 외부 번역 경로를 사용한다.
- `./bin/avc setup`의 모델 사전 다운로드 기능은 제거했다. 모델 캐시는 config GUI의 오디오 AI 모델 다운로드 모달에서 준비한다.

#### 검증 지표

중국어 backend 교체 평가는 다음 지표를 기존 lifecycle 지표와 함께 본다.

- `CER`: 정답 전사 대비 문자 오류율. 중국어는 WER보다 CER을 우선한다.
- `mixed_script_ratio`: `language=zh`일 때 Latin token이 과도하게 섞이는 비율.
- `low_logprob_reject_rate`, `no_speech_reject_rate`: STT 후보 폐기율.
- `raw_stt_to_committed_deletion_rate`: raw STT에 있던 의미 단위가 committed output에서 사라진 비율.
- `stage_replace_ratio`, `stage_drop_ratio`, `pending_overrun_rate`: 후처리 생명주기 안정성.
- `stt_rtf`, `total_rtf`: 실시간성. 중국어 backend 교체 후에도 p95 total RTF가 1.0 미만이어야 한다.

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

- `split event`: `chunk`, `completed`, `final`, `pending_text`, `forced_by`, `pending_overrun`, `boundary_backend`, `pending_chars`, `pending_chunks`, `pending_chars_per_chunk`
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

오디오 AI 실시간 전사/번역 경로의 품질은 unittest의 성공/실패만으로 판단하지 않는다. `tests/unit/test_whisper_performance_tracking.py`는 누적 운영 로그에서 관측한 중복, 누락, revision, stability 사례를 실행해 현재 로직의 성능 추이를 출력하는 추적 하네스다.

unittest 성공은 테스트 코드가 실행되어 지표가 수집되었다는 의미만 갖는다. 품질 개선 목표는 실행 끝에 출력되는 `[whisper-tracking]`의 `rate`를 올리고 `rate_gap`을 줄이는 것이다.

| 도메인 | 의미 | 목표 케이스 | 목표율 |
| --- | --- | ---: | ---: |
| `revision` | 이전 partial/final 문장이 새 STT 윈도우에서 올바르게 갱신되는지 | 90 | 90% 이상 |
| `distinct` | 서로 다른 문장을 잘못된 revision으로 합치지 않는지 | 25 | 95% 이상 |
| `collapse` | 같은 의미의 인접 반복 문구를 줄일 수 있는지 | 45 | 90% 이상 |
| `stability` | 연속 partial 전사가 전체 재출력 없이 안정적으로 revision되는지 | 10 | 80% 이상 |
| `replacement` | staged 후보 교체 시 보존/폐기/확정 결정이 의도와 맞는지 | 11 | 90% 이상 |
| `pending` | 긴 pending이 확정되지 않는 사유를 지표화해 번역 지연 위험을 추적하는지 | 10 | 90% 이상 |
| `pending_quality` | pending 버퍼에 CJK 반복 n-gram 같은 오염 신호가 누적되는지 | 1 | 100% |
| `final_quality` | final 확정 후보의 짧은 CJK, 언어 불일치, 반복 n-gram 등 품질 플래그를 추적하는지 | 8 | 90% 이상 |
| `coalesce` | 중국어 completed 후보가 같은 STT 윈도우 안에서 여러 개 나올 때 단일 관측 단위로 병합되는지 | 10 | 100% |
| `duplicate_suppression` | 이미 확정/관측된 후보가 중복 출력되지 않도록 억제되는지 | 4 | 100% |
| `runtime_metrics` | 런타임 누적 지표가 안정성 요약으로 올바르게 집계되는지 | 5 | 100% |
| `translation_quality` | 관측된 번역 출력 샘플에서 고유명사/도메인 용어/명백한 환각 회귀를 추적하는지 | 8 | 80% 이상 |
| `stage_candidate` | 중국어 staged 후보를 보류/전환하는 결정이 장기 보류 없이 동작하는지 | 4 | 100% |

`distinct` 목표율을 더 높게 둔 이유는 서로 다른 문장을 병합하면 원문 손실이 발생하고, 이후 번역도 복구할 수 없기 때문이다. `revision`과 `collapse`는 중복을 줄이는 방향의 품질 지표지만, 과도한 병합보다 손실 위험이 낮으므로 초기 목표율을 90%로 둔다. `stability`는 incremental ASR의 partial hypothesis instability와 revokes 문제를 현재 코드의 revision lifecycle에 맞춘 프록시 지표다. `replacement`는 2026-06-13 30분 운영 로그에서 관측된 staged 교체 손실을 직접 추적하기 위해 추가한 지표이며, `open_korean_clause`와 `partial_preserve` 결정의 회귀를 막는다. `pending`은 영어 장문처럼 경계가 늦게 나오는 구간에서 번역 지연 위험을 추적하고, `pending_quality`는 중국어 no-space STT 윈도우의 내부 재시작이 pending에 반복 접합되는 오염 신호를 분리해서 본다. `final_quality`는 final 후보 자체가 번역/복사 대상으로 적합한지 확인하는 품질 축이고, `coalesce`는 중국어 punctuation 모델이 한 STT 윈도우를 여러 completed 후보로 나누면서 단일 staging 슬롯을 반복 교체하는 문제를 추적한다. `translation_quality`는 STT/문장 확정과 분리된 번역 모델 품질 축이다. 이 값은 실제 모델을 실행하는 패스 기준이 아니라, 운영 로그에서 관측한 source/observed 쌍을 기준으로 고유명사 보존, 도메인 용어 보존, 금지 오역을 확인하는 회귀 샘플 지표다. `stage_candidate`는 중국어 짧은 fragment를 즉시 stage하지 않되, 보류 age가 한계에 도달하고 후보가 충분히 성장했을 때 새 관찰 후보로 전환하는지를 추적한다. `runtime_metrics`는 로그 집계 경로가 새 지표를 누락하지 않는지 확인하는 계약 지표다. 2026-06-15 `windowSeconds=30`, `stepSeconds=1` 중국어 모니터링에서는 `stt_step_load > 1`과 Pulse 입력 큐 드롭이 함께 관측되어 `input_queue_drops`를 runtime metric에 추가했다.

### 12.1 운영 규칙

- 성능 추적 테스트의 성공/실패 자체에 품질 통과 의미를 부여하지 않는다.
- 새 로그에서 중복/누락/잘못된 revision이 관측되면 케이스를 추가한다.
- 케이스 추가로 tracking rate가 내려가는 것은 정상적인 관측 신호다.
- 알고리즘, 버퍼 라이프사이클, revision 판단 개선으로 rate를 올리고 gap을 줄인다.
- 목표율 변경은 서비스 요구가 바뀌거나 정답 코퍼스 기반 WER/CER 평가가 도입될 때 문서와 함께 수행한다.
- STT 원문창은 `stt_raw` 이벤트만 표시한다. 원문창의 목적은 문장 경계, pending, staged revision 처리 전 raw STT window 결과를 관찰하는 것이다.
- staged/partial 후보는 원문창에 출력하지 않는다. staged 후보는 final 확정 전 revision lifecycle의 내부 상태이며, raw STT 품질 판단 근거로 사용하지 않는다.
- 최종 복사용 전사 문장은 전사 창에만 표시하고, 번역 입력은 final transcript를 기준으로 한다.

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
- `commitLagSeconds` 기본/운영값은 2.0초로 정렬한다.
- VAD 기반 필터링은 현재 슬라이딩 윈도우 확정 정책과 충돌해 운영 경로에서 제거한다.
- `chunk_metrics`를 추가해 해당 chunk에서 발생한 `stage_start`, `stage_revision`, `stage_replace`, `stage_discard`, `finalized` 등을 즉시 확인한다.
- `pending_overrun`을 추가해 긴 pending이 `long_no_boundary`, `with_end_mark`, `unstable_numeric_tail` 중 어떤 상태인지 추적한다.
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
pending=10/10 rate=1.000 target>=0.90
replacement=11/11 rate=1.000 target>=0.90
coalesce=12/12 rate=1.000 target>=1.00
revision=97/107 rate=0.907 target>=0.90
distinct=38/38 rate=1.000 target>=0.95
collapse=49/53 rate=0.925 target>=0.90
stability=10/10 rate=1.000 target>=0.80
```

## 12.4 2026-06-14 중국어 completed 후보 병합 관측

2026-06-14 중국어 운영 로그에서는 `boundary_complete=2~4`가 같은 chunk 안에서 반복 관측되었다. 기존 생명주기는 completed 후보를 순서대로 staging에 넣었기 때문에 같은 STT 윈도우의 첫 번째 후보가 다음 후보에 의해 `stage_discard_reason_unconfirmed_cjk`로 폐기되었다.

대표 관측:

- chunk 241: `Helps笨蛋，我们是笨蛋...` 다음 `我一直以来你以为它是山楂。`가 같은 chunk에서 발생하며 첫 후보가 폐기됨.
- chunk 242: `你大家不笨蛋...`, `我一直以来你以为它是山楂口味的，很好吃。`, `哎，冰。` 세 후보가 같은 chunk에서 staging을 순차 교체함.
- chunk 251~252: `好朋友...`, `我们不是还要...`, `贴贴脸吗？` 계열 후보가 같은 윈도우 안에서 반복 교체됨.
- chunk 269~270: `果是怎么样？`와 `然后我让小哥哥给我拿了几台测试一下...`가 분리되어 앞 후보가 확정 전 폐기됨.

반영 정책:

- 중국어(`language=zh`)에서는 한 STT 윈도우에서 나온 completed 후보들을 같은 관측 단위로 병합한 뒤 staging에 넣는다.
- 이 병합은 운영 경로의 언어별 문자열 규칙을 늘리는 목적이 아니라, punctuation 모델이 같은 윈도우를 여러 completed fragment로 반환하는 구조를 revision lifecycle에 맞추는 완충 단계다.
- 비중국어는 기존처럼 completed 후보를 개별 문장 단위로 유지한다.
- 병합 발생 시 `completed_coalesced`, `completed_coalesced_lang_zh` 지표와 `오디오 AI completed 후보 병합` 로그를 남긴다.
- `오디오 AI 안정성 지표` 로그는 누적 `stage_replace`, `stage_discard`, `stage_revision`, `finalized`, `completed_coalesced`를 함께 출력해 생명주기 안정성을 관측한다.

2026-06-14 검증 결과:

```text
coalesce=12/12 rate=1.000 target>=1.00
revision=97/107 rate=0.907 target>=0.90
collapse=49/53 rate=0.925 target>=0.90
translation_quality=2/8 rate=0.250 target>=0.80
```

2026-06-14 30분 중국어 STT 모니터링 결과:

```text
replace=570 discard=568 suppressed=266 revision=327 finalized=137 no_result=20
perf_samples=1064 max_stt=0.350s max_total=0.370s avg_total_rtf=0.010 translation=0
```

이 관측에서는 CUDA/FunASR STT 처리 속도는 충분히 빨랐지만, FunASR STT 품질은 충분하지 않았다. 당시 `chunkSeconds=9.0`, `stepSeconds=1.5`, `commitLagSeconds=2.0` 조합은 과거 실험값이며 현재 기본값이 아니다. 병목은 단순 성능 파라미터보다 중국어 STT 품질과 stage 후보 생명주기였다. 특히 짧은 CJK 후보를 보류하는 정책이 필요한 동시에, 보류 age가 `SENTENCE_CONFIRM_MAX_AGE_CHUNKS`에 도달하고 후보가 기존 stage보다 충분히 길어진 경우에는 새 관찰 후보로 전환해야 장기 보류가 줄어든다.

2026-06-14 추가 비교에서는 `windowSeconds=30`에서 raw STT가 덜 흔들리는 경향이 관측되었다. 다만 backend별 의미는 다르다. FunASR Paraformer는 인접 전사 유사도가 높고 처리시간이 빠르지만 stage 교체/폐기가 많고 확정률이 낮았다. Qwen3-ASR 0.6B는 처리시간이 더 길지만 FunASR보다 의미 보존과 문장 구조가 자연스럽고 확정률도 높았다. Whisper/faster-whisper는 중국어 정확도가 부족해 이 비교의 품질 후보가 아니라 baseline으로만 둔다.

대표 로그 지표:

- `qwen3-asr-0.6b`, `window=30`: `replace/chunk=0.55`, `discard/chunk=0.55`, `finalized/chunk=0.11`, STT 평균 `1.109s`.
- `funasr-paraformer`, `window=30`: `replace/chunk=0.74`, `discard/chunk=0.74`, `finalized/chunk=0.04`, STT 평균 `0.290s`.
- `funasr-paraformer`, `window=15`: `replace/chunk=0.25`, `discard/chunk=0.25`, `finalized/chunk=0.22`, STT 평균 `0.129s`.

운영 판단은 Qwen3-ASR를 중국어 품질 우선 후보로 올리고, FunASR STT는 후보군에서 제외해 폐기한다는 것이다. 2026-06-15 기준 기본 계약은 `sttBackendZh=qwen3-asr-transformers`, `sttModelZh=qwen3-asr-0.6b`로 전환한다. 단, 현재 비교는 같은 입력 replay가 아니라 시간대가 다른 운영 로그 기반이므로, 향후 동일 입력 replay에서는 `faster-whisper`, `qwen3-asr-0.6b`, 과거 FunASR 기준선을 비교해 회귀 여부를 확인한다. FunASR 관련 과거 로그는 기준선 기록으로만 문서에 남긴다.

결론은 STT/staging 생명주기 병목과 번역 모델 품질 병목을 분리해서 본다는 것이다. 중국어 completed 병합은 문장 손실과 stage churn을 줄이기 위한 조치이며, 낮은 `translation_quality`는 중한 번역 백엔드/모델 비교 과제로 남긴다.

## 12.5 2026-06-15 중국어 pending 내부 재시작 관측

최근 3개 회전 로그(`avc-whisper.log`, `.1`, `.2`) 집계에서 계산 성능은 병목이 아니었다.

```text
diag=2494 duplicate=491 final=271 replace=160 discard=155 suppressed=29
avg_stt_rtf=0.035 avg_total_rtf=0.035 avg_text_chars=101.5
quality: cjk_internal_gap=194 mixed_latin_zh=37 latin_only_for_zh=6 no_end_marker=3
```

대표 문제는 pending이 길어진 상태에서 다음 STT 윈도우가 같은 CJK 구간을 내부 중간부터 다시 내보내는 경우였다.

```text
pending_tail=...喷枪
new_text=条，然后把这米再切断了，摆成四个墩儿墩儿，然后就是火山的底座，然后上面这个洒的就更像熔岩一样，然后用喷枪
old_result=...喷枪 条，然后把这米再切断了...
```

이 케이스는 문장 경계 모델의 구두점 결정 문제가 아니라 pending/new 접합 단계에서 내부 재시작을 새 continuation으로 오인한 문제다. 따라서 `pending_new_text_combined()`는 CJK no-space 텍스트에 한해 긴 내부 prefix overlap이 확인되면 `pending prefix + new_text`로 병합한다. 서로 다른 중국어 continuation은 인위적 공백을 넣지 않고 그대로 이어붙인다.

반영 후 추적 테스트는 다음 회귀를 포함한다.

- 내부 재시작: `...喷枪` 뒤에 `条，然后...喷枪`이 들어오는 경우 중복 tail을 제거한다.
- 독립 continuation: `这个长得真的好像火山啊` 뒤에 `然后用喷枪把上面烤一下`이 들어오는 경우 공백 없이 이어붙는다.

검증 결과:

```text
sentence boundary/revision/delta/repeat/performance related tests: 440 passed
unit test discover: 567 passed
./bin/avc test: passed, integration skipped=1
```

운영 파라미터 비교에서 영어/한국어는 `windowSeconds=7`이 실시간성과 품질의 균형점으로 관측되었다. 중국어/Qwen3-ASR는 원문창이 staged 후보를 표시하던 시기의 로그 해석 오류 때문에 작은 윈도우의 raw STT 품질을 과소평가했다. 원문창을 `stt_raw` 기반 raw STT window 출력으로 분리한 뒤에는 `windowSeconds=12`도 유효한 시작점으로 본다. `windowSeconds=30`은 문맥 안정성은 상대적으로 좋지만 final script 갱신이 늦고 긴 문장 확정 비용이 커졌다. 또한 `stepSeconds=1`과 결합하면 `stt_step_load`가 1을 초과하고 Pulse 입력 큐 드롭이 발생할 수 있으므로 성능 로그를 함께 확인해야 한다. 2026-06-15 현재 기본 계약값은 언어별로 분리한다. 영어/한국어는 `windowSecondsEn=7`, `windowSecondsKo=7`, `stepSecondsEn=1`, `stepSecondsKo=1`, 중국어는 `windowSecondsZh=12`, `stepSecondsZh=1`을 시작점으로 둔다. 우선순위는 STT 모델 품질과 pending/revision 생명주기 지표 개선이며, `final_quality_cjk_internal_gap`는 공백 없는 CJK 출력에서 false positive가 있을 수 있으므로 hard fail이 아니라 추세 지표로만 사용한다. 안정성 로그에는 `duplicate_suppressed`, `delta_trimmed`, `final_quality`, `translation_skip`, `revision_changed`, `revision_reset`, `pending_quality`, `input_queue_drops`, `quality_blocked_release`를 추가해 중복 억제, 후보 흔들림, pending 버퍼 오염, 처리량 초과, 품질 차단 staged 후보 해제를 분리해서 본다. CJK revision 내용이 실제로 바뀐 경우 confirmations를 1부터 다시 세어 흔들리는 후보가 누적 확인만으로 확정되지 않도록 한다. 품질 차단으로 확정되지 못한 confirmed staged 후보는 revision 후보가 계속 이어지는 동안 보존하지만, age 한계를 넘고 새 후보가 독립된 completed 후보로 관측되면 staged 슬롯을 새 후보에 넘겨 장기 고착을 피한다. 이때 구두점 없는 긴 CJK 후보는 즉시 final로 확정하지 않고 staged 관찰 대상으로만 전환한다.

전사 품질을 볼 때는 세 창/로그의 의미를 구분한다. STT 원문창은 raw STT window 결과이며, 전사 창은 revision lifecycle과 final 확정을 거친 사용자 출력이다. `stable_tail`, `delta_tail`, `pending_tail`, `staged_tail`은 stdout 진단 로그용 상태값이며 창에 표시되는 raw STT 또는 final transcript와 동일한 의미가 아니다.

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
- 다운로드/로딩 단계가 끝나기 전에는 오디오 입력 장치를 열지 않고 전사/번역 job을 시작하지 않는다.

### 14.1 개정 배포 운영 절차

- 배포 직후 24시간은 운영자 모니터링 모드(`pending`·`confirmed`·`rollback` 유사지표)로 1분 단위 확인.
- 회귀가 누적되면 원본 배포 채널로 되돌리고 원인 로그를 묶어 1페이지 인시던트 노트 작성.

## 15) 중국어 번역 백엔드 확장 정책

중국어 STT가 안정화된 뒤 관측한 로그에서는 STT보다 `zh->ko` 번역 품질이 병목으로 나타났다. 특히 지명(`重庆`), 서비스명(`滴滴`, `美团`), 구어체 표현(`Q`)에서 `nllb-200-distilled-600M`의 오역이 반복되었다. 이 문제는 언어별 문자열 휴리스틱을 추가하는 방식보다 번역 백엔드/모델 선택지를 계약 데이터로 관리하고, 동일 테스트 케이스에서 모델별 품질 지표를 비교하는 방식으로 접근한다.

정책은 다음과 같다.

- 번역 백엔드와 모델은 STT 언어를 source language로 보고 사용할 수 있는 조합을 계약 데이터(`WHISPER_TRANSLATION_GROUPS`)에 명시한다.
- GUI는 선택된 STT 언어와 번역 백엔드에 맞는 target/model 목록만 표시한다.
- 저장 검증은 GUI와 같은 계약 데이터를 사용하며, 허용되지 않은 조합은 실행 전 Fail-Fast로 거부한다.
- 휴리스틱 패턴은 범용성 유지 비용이 높으므로 품질 게이트/진단 수준으로 최소화하고, 번역 품질 개선은 모델 교체 또는 백엔드 교체 실험으로 진행한다.

현재 반영한 후보는 다음과 같다.

| 백엔드 | 모델 | 위치 | 판단 |
| --- | --- | --- | --- |
| `nllb-transformers` | `facebook/nllb-200-distilled-600M` | 기본값 | 빠르고 현재 기준선이다. 중국어 고유명사/구어체 오역이 있어 품질 지표상 개선 여지가 크다. |
| `nllb-transformers` | `facebook/nllb-200-distilled-1.3B`, `facebook/nllb-200-1.3B`, `facebook/nllb-200-3.3B` | 추가 옵션 | 같은 백엔드로 모델 크기만 바꾸어 실험할 수 있어 가장 낮은 위험의 품질 개선 후보이다. |
| `m2m100-transformers` | `facebook/m2m100_1.2B` | 신규 백엔드 | 영어 중심 우회가 아닌 직접 many-to-many 번역 모델이며 `zh`/`ko`를 지원한다. NLLB와 다른 계열의 비교군으로 적합하다. |
| `seamless-m4t-v2` | `facebook/seamless-m4t-v2-large` | 후속 후보 | text-to-text와 speech/text translation을 모두 지원하지만 구현/메모리 비용이 크므로 바로 기본 백엔드로 넣지 않는다. |
| LLM 번역 | TowerInstruct, X-ALMA Group6 | 후속 후보 | 중국어/한국어를 포함한 번역 특화 모델이지만 지연/VRAM 비용이 커서 실시간 기본값보다 고품질 실험군으로 분리한다. |

모델 비교는 `translation_quality` 관측 샘플을 기준으로 진행한다. 이 테스트는 source와 observed 번역 결과를 하드코딩한 회귀 샘플이므로 현재 백엔드를 직접 실행하지 않는다. 따라서 서비스 품질 지표를 출력하지만, 실험 기준선 수집을 위해 단위 테스트 실패로 처리하지 않는다. 백엔드 비교 단계에서는 같은 source에 대해 모델별 observed 출력을 별도 샘플로 추가해 비교한다.

## 16) 참고

- [Turning Whisper into Real-Time Transcription System](https://arxiv.org/abs/2307.14743)
- [Simul-Whisper](https://www.isca-archive.org/interspeech_2024/wang24ea_interspeech.pdf)
- [Analyzing the Quality and Stability of a Streaming End-to-End On-Device Speech Recognizer](https://www.isca-archive.org/interspeech_2020/shangguan20_interspeech.pdf)
- [WhisperKit](https://openreview.net/pdf?id=6lC3MPFbVg)
- [Adapting Whisper for Streaming Speech Recognition via Two-Pass Decoding](https://arxiv.org/abs/2506.12154)
- [WhisperRT](https://arxiv.org/abs/2508.12301)
- [WhisperPipe: A Resource-Efficient Streaming Architecture for Real-Time Automatic Speech Recognition](https://arxiv.org/abs/2604.25611)
- [CarelessWhisper: Turning Whisper into a Causal Streaming Model](https://arxiv.org/abs/2508.12301)
- [Whisper: Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356)
- [Conformer: Convolution-augmented Transformer for Speech Recognition](https://arxiv.org/abs/2005.08100)
- [wav2vec 2.0: A Framework for Self-Supervised Learning of Speech Representations](https://arxiv.org/abs/2006.11477)
- [RNN-Transducer: Sequence Modeling with RNN-T for Streaming ASR](https://arxiv.org/abs/1211.3711)
- [Segment Any Text: A Universal Approach for Robust, Efficient and Adaptable Sentence Segmentation](https://arxiv.org/abs/2406.16678)
- [wtpsplit GitHub README](https://github.com/segment-any-text/wtpsplit)
- [Where’s the Point? Self-Supervised Multilingual Punctuation-Agnostic Sentence Segmentation](https://aclanthology.org/2023.acl-long.398/)
- [Streaming Punctuation: A Novel Punctuation Technique Leveraging Bidirectional Context for Continuous Speech Recognition](https://arxiv.org/abs/2301.03819)
- [Efficient Punctuation Restoration via Weighted Lookahead Scoring Method for Streaming ASR Systems](https://arxiv.org/abs/2606.05179)
- [Punctuation Restoration for Singaporean Spoken Languages: English, Malay, and Mandarin](https://arxiv.org/abs/2212.05356)
- [A Small and Fast BERT for Chinese Medical Punctuation Restoration](https://arxiv.org/abs/2308.12568)
- [M2R-Whisper: Multi-stage and Multi-scale Retrieval Augmentation for Enhancing Whisper](https://arxiv.org/abs/2409.11889)
- [Investigating Zero-Shot Generalizability on Mandarin-English Code-Switched ASR and Speech-to-text Translation](https://arxiv.org/abs/2401.00273)
- [FunASR: A Fundamental End-to-End Speech Recognition Toolkit](https://arxiv.org/abs/2305.11013)
- [FunASR GitHub README](https://github.com/modelscope/FunASR)
- [FunAudioLLM: Voice Understanding and Generation Foundation Models for Natural Interaction Between Humans and LLMs](https://arxiv.org/abs/2407.04051)
- [Qwen3-ASR Technical Report](https://arxiv.org/abs/2601.21337)
- [Qwen3-ASR-0.6B Hugging Face Model Card](https://huggingface.co/Qwen/Qwen3-ASR-0.6B)
- [Qwen3-ASR-1.7B Hugging Face Model Card](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)
- [Dolphin-CN-Dialect: Where Chinese Dialects Matter](https://arxiv.org/abs/2605.08961)
- [FormalASR: End-to-End Spoken Chinese to Formal Text](https://arxiv.org/abs/2605.19266)
- [ASR-EC Benchmark: Evaluating Large Language Models on Chinese ASR Error Correction](https://arxiv.org/abs/2412.03075)
- [Large Language Model Should Understand Pinyin for Chinese ASR Error Correction](https://arxiv.org/abs/2409.13262)
- [Pinyin Regularization in Error Correction for Chinese Speech Recognition with Large Language Models](https://arxiv.org/abs/2407.01909)
- [Full-text Error Correction for Chinese Speech Recognition with Large Language Model](https://arxiv.org/abs/2409.07790)
- [PARCO: Phoneme-Augmented Robust Contextual ASR via Contrastive Entity Disambiguation](https://arxiv.org/abs/2509.04357)
- [PAC: Pronunciation-Aware Contextualized Large Language Model-based Automatic Speech Recognition](https://arxiv.org/abs/2509.12647)
- [SenseVoice GitHub README](https://github.com/FunAudioLLM/SenseVoice)
- [SenseVoiceSmall Hugging Face Model Card](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)
- [WeNet: Production oriented Streaming and Non-streaming End-to-End Speech Recognition Toolkit](https://arxiv.org/abs/2102.01547)
- [A Comparative Study of LLM-based ASR and Whisper in Low Resource and Code Switching Scenario](https://arxiv.org/abs/2412.00721)
- [PySBD: Pragmatic Sentence Boundary Disambiguation](https://arxiv.org/abs/2010.09657)
- [NIST SCTK, the NIST Scoring Toolkit](https://github.com/usnistgov/SCTK)
- [Assessing Latency in ASR Systems: A Methodological Perspective for Real-Time Use](https://arxiv.org/abs/2409.05674)
- [Dynamic Latency for CTC-Based Streaming Automatic Speech Recognition With Emformer](https://arxiv.org/abs/2203.15613)
- [Benchmarking LF-MMI, CTC and RNN-T Criteria for Streaming ASR](https://arxiv.org/abs/2011.04785)
- [Evaluating Automatic Speech Recognition in an Incremental Setting](https://arxiv.org/abs/2302.12049)
- [Word Error Rate Estimation Without ASR Output: e-WER2](https://arxiv.org/abs/2008.03403)
- [Assessing ASR Model Quality on Disordered Speech using BERTScore](https://arxiv.org/abs/2209.10591)
- [No Language Left Behind: Scaling Human-Centered Machine Translation](https://arxiv.org/abs/2207.04672)
- [facebook/nllb-200-distilled-600M Model Card](https://huggingface.co/facebook/nllb-200-distilled-600M)
- [facebook/nllb-200-distilled-1.3B Model Card](https://huggingface.co/facebook/nllb-200-distilled-1.3B)
- [facebook/nllb-200-3.3B Model Card](https://huggingface.co/facebook/nllb-200-3.3B)
- [Beyond English-Centric Multilingual Machine Translation](https://arxiv.org/abs/2010.11125)
- [facebook/m2m100_1.2B Model Card](https://huggingface.co/facebook/m2m100_1.2B)
- [SeamlessM4T: Massively Multilingual & Multimodal Machine Translation](https://arxiv.org/abs/2308.11596)
- [Seamless: Multilingual Expressive and Streaming Speech Translation](https://arxiv.org/abs/2312.05187)
- [facebook/seamless-m4t-v2-large Model Card](https://huggingface.co/facebook/seamless-m4t-v2-large)
- [Tower: An Open Multilingual Large Language Model for Translation-Related Tasks](https://arxiv.org/abs/2402.17733)
- [Unbabel/TowerInstruct-7B-v0.2 Model Card](https://huggingface.co/Unbabel/TowerInstruct-7B-v0.2)
- [X-ALMA: Plug & Play Modules and Adaptive Rejection for Quality Translation at Scale](https://arxiv.org/abs/2410.03115)
- [haoranxu/X-ALMA-13B-Group6 Model Card](https://huggingface.co/haoranxu/X-ALMA-13B-Group6)
