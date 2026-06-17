# 받아쓰기 AI 설계 및 실험 노트

## 문서 상태

이 문서는 기존 `docs/2026-06-13-dictation-ai-feature-design.md`와 `docs/2026-06-15-presentation-dictation-segmentation-references.md`를 통합한 기준 설계/실험 노트다. 두 기존 문서는 내용 이관 완료 후 폐기했으며, 원문은 Git 이력에서만 추적한다.

새 변경과 운영 판단은 이 문서에 먼저 반영한다. 커밋 기록 기반 실험 흐름은 [받아쓰기 AI 실험일지](2026-06-16-dictation-ai-experiment-log.md)에 두고, 설정 계약과 기본값은 [받아쓰기 AI 계약과 기본값](2026-06-16-dictation-ai-contract-defaults.md)에 둔다. Qwen3-ASR vLLM streaming, Dolphin-CN-Dialect, WeNet의 세부검증 판단은 [받아쓰기 AI 중국어 STT 후보 세부검증 리포트](2026-06-16-dictation-ai-chinese-stt-candidate-validation.md)에 둔다. 외부 논문, 모델 카드, 구현 링크는 [받아쓰기 AI 참조 레퍼런스 모음](2026-06-16-dictation-ai-reference-index.md)에 둔다.

## 기능 도메인

받아쓰기 AI는 오디오 도메인의 하위 기능이다. 사용자에게는 STT, Whisper, NLLB 같은 기술명을 전면에 내세우지 않고 다음 기능으로 설명한다.

- 받아쓰기 AI 전사: 입력 장치의 음성을 실시간 텍스트로 변환한다.
- 받아쓰기 AI 문장 추적: raw STT 후보를 사용자에게 복사 가능한 final 문장으로 확정한다.
- 받아쓰기 AI 번역: 확정된 final 문장만 번역한다.
- 받아쓰기 AI 원문창: 문장 경계/확정 처리 전 raw STT window 결과를 진단용으로 표시한다.

## 운영 계약

- 실행 진입점은 `./bin/avc`이며, `config`는 설정/GUI, `serve`는 저장된 설정 실행만 담당한다.
- config GUI의 `Serve 시작`으로 실행할 때만 받아쓰기 AI 전사/번역 창을 연다.
- CLI `./bin/avc serve`는 기본적으로 받아쓰기 AI 창을 열지 않는다.
- 받아쓰기 AI 실행은 STT 모델, 번역 모델, STT 결과 문장 경계 처리 모델 준비가 끝난 뒤 입력 장치를 열고 전사를 시작한다.
- 모델 다운로드는 Serve 시작 전 캐시 검사와 모델 다운로드 매니저 창에서만 수행한다. 다운로드 프로세스 출력 감시는 GUI 스레드와 분리된 워커에서 처리하며, Serve 런타임은 로컬 캐시만 사용한다.
- 설정값이 유효하지 않거나 모델/장치 초기화가 실패하면 자동 폴백하지 않고 즉시 실패한다.
- CUDA/float16이 요구되는 실시간 경로는 CPU fallback으로 계속 실행하지 않는다.
- config 오류는 모달만으로 표시하지 않고 stdout에도 출력한다.
- config stdout에는 저장, Serve 시작/중지, 가상 장치 생성/삭제 같은 주요 버튼 동작을 출력한다.

## 배포 범위와 수용 시나리오

배포 범위는 raw STT를 사용자가 복사/번역하는 final 문장으로 안정화하는 경로에 한정한다.

| 구분 | 범위 |
| --- | --- |
| 포함 | sliding window 후보 집계, STT 결과 문장 경계 처리 backend 선택, staged/final 확정 정책, 중복 억제, final-only 번역 입력 정책 |
| 제외 | 오디오 캡처 계층 교체, 카메라/비디오 파이프라인, GUI 레이아웃 전면 개편, 모델 학습 또는 fine-tune |
| 제한 | config GUI는 운영 기본값과 후보 선택만 다루고, 실행 중 자동 backend 전환이나 CPU fallback을 제공하지 않는다. |

배포 수용 시나리오:

| 시나리오 | 수용 기준 |
| --- | --- |
| 같은 음성 구간이 여러 window에 반복 포함됨 | final transcript는 중복 append되지 않고, 이미 확정된 문장은 echo suppression으로 억제된다. |
| 다음 window가 이전 hypothesis를 수정함 | 미확정 `pending`/`staged`만 revision되고, 이미 final인 문장은 되돌리지 않는다. |
| 문장 경계가 늦게 나옴 | pending은 진단 로그로 추적되고, final 후보는 `sentenceFinalizeAge`와 품질 게이트를 통과한 뒤 확정된다. |
| 중국어 no-space 구간이 내부 중간부터 다시 시작됨 | STT/backend 품질과 revision lifecycle에서 관측한다. 학술적 근거가 부족한 pending/new 접합 보정은 운영 요구사항에서 제외한다. |
| 번역이 켜져 있음 | 번역 큐에는 final transcript만 들어가며 staged/partial은 번역하지 않는다. |

## 설정 저장 구조

받아쓰기 AI 설정은 `setting.json`의 `dictationAi` 블록에 저장된다. 초기에는 사용 모델이 Whisper였기 때문에 `whisper` 블록으로 시작했지만, 기능이 STT, STT 결과 문장 경계 처리, 번역, 모델 준비 흐름으로 확장되면서 도메인명과 특정 모델명을 동일하게 가져가는 것이 오류가 되었다. 따라서 현재 저장 기준은 기능 도메인명인 `dictationAi`이고, `whisper`는 과거 기술명/일부 내부 구현 맥락에 남은 호환 명칭으로만 취급한다.

실행 전제:

- 받아쓰기 AI는 Linux + NVIDIA CUDA 전용 기능이다.
- `dictationAi.enabled=true`인 설정은 macOS/Windows 또는 CPU 실행으로 저장/Serve 시작/전사 창 실행할 수 없다.
- STT, STT 결과 문장 경계 처리, 번역 실행 장치는 모두 `cuda`를 기준으로 검증한다.
- 과거 설정 파일에 남은 `cpu` 값은 비활성 설정 호환 로딩용으로만 취급하며 운영 대안으로 사용하지 않는다.

주요 active 키:

- `enabled`
- `inputDevice`
- `backend`
- `model`
- `language`
- `device`
- `computeType`
- `chunkSeconds`
- `windowSeconds`
- `stepSeconds`
- `sentenceFinalizeAge`
- `beamSize`
- `maxNewTokens`
- `temperature`
- `translationEnabled`
- `translationBackend`
- `translationTargetLanguage`
- `translationModel`
- `translationDevice`
- `translationComputeType`
- `translationBeamSize`
- `translationMaxNewTokens`

언어별 STT/STT 결과 문장 경계 처리 설정은 STT 인식 언어를 기준으로 묶는다. 예를 들어 중국어는 `sttBackendZh`, `sttModelZh`, `windowSecondsZh`, `sentenceBoundaryBackendZh`, `sentenceFinalizeAgeZh` 묶음이 화면과 실행값의 기준이다.

번역 backend/model/device/compute/beam/token 설정은 번역 대상 언어를 기준으로 묶는다. 기존 active 키는 현재 선택 대상 언어의 projection으로 유지한다.

받아쓰기 AI UI 언어는 `setting.json`의 `meta.language`에 저장한다. 창 위치와 크기는 `setting.json`과 분리된 `window-geometry.json`에 자동 저장한다. 과거 `setting.json`의 `meta.*Geometry` 값은 마이그레이션용 fallback으로만 읽는다.

- `dictationAiWindowGeometry`
- `dictationAiTranslationWindowGeometry`
- `dictationAiInputMeterWindowGeometry`
- `dictationAiModelDownloadWindowGeometry`

## 핵심 문제 정의

실시간 ASR은 매 step마다 최근 window의 전체 전사 후보를 다시 생성한다. 같은 음성 구간이 여러 window에 반복 포함되므로 raw STT는 다음과 같은 문제를 만든다.

- 같은 문장이 여러 번 출력된다.
- 이미 보인 후보가 뒤 window에서 수정된다.
- 문장 경계가 늦게 나오거나 잘못 나온다.
- 확정되지 않은 문장을 번역하면 번역 중복과 premature translation이 발생한다.

따라서 raw STT 출력은 사용자 final 문장이나 번역 입력으로 직접 사용하지 않는다. 받아쓰기 AI의 핵심은 raw STT 품질, 문장 경계, revision lifecycle, 번역 품질을 분리해 계측하고 각각 개선하는 것이다.

## 실시간 처리 파이프라인

목표는 raw STT window를 사용자 final 문장이나 번역 입력으로 직접 쓰지 않는 것이다. 최소 파이프라인은 중복 window, 뒤늦은 revision, premature translation을 막는 데 필요한 단계만 둔다.

```text
오디오 입력
  ↓
슬라이딩 윈도우 STT
  - 언어별 운영 backend 실행
  - raw STT window 결과 생성
  ↓
안정성/경계 판단
  - 여러 window에서 유지되는 token/char 구간 확인
  - SaT/SBD와 punctuation/right-context로 문장 경계 후보 생성
  ↓
세그먼트 생명주기
  - pending / staged / final / suppressed / revised
  - final은 append-only
  ↓
final-only 번역
```

이 흐름에서는 "음성이 멈췄는가"보다 "토큰이 안정되었는가"와 "의미 경계가 확인되었는가"가 우선이다.

### 적용 상태

| 단계 | 현재 상태 | 적용 판단 |
| --- | --- | --- |
| 슬라이딩 윈도우 STT | 구현됨 | `windowSeconds`, `stepSeconds` 기준으로 최근 오디오 window를 STT 입력으로 사용하고 raw STT window를 원문창에만 표시한다. |
| 정규화/접합 보정 | 폐기 | pending/new overlap 제거, CJK no-space 내부 재시작 접합은 학술적 근거가 부족하므로 운영 요구사항에서 제외한다. detector 입력 생성을 위한 단순 문자열 결합만 수행한다. |
| 안정성/경계 판단 | 구현됨 | stable token/char 신호와 SaT/SBD 경계 후보를 staged 생명주기 입력으로 사용한다. VAD/silence는 운영 경로에서 제외한다. |
| 세그먼트 생명주기 | 구현됨 | `pending`, `staged`, `final`, `suppressed`, `revised`를 분리하고 final은 append-only로 유지한다. |
| final-only 번역 | 구현됨 | 품질 게이트를 통과한 final transcript만 번역 큐에 넣는다. staged/partial 번역은 운영 경로에서 제거한다. |

## 출력 상태와 정합성 규칙

| 상태 | 의미 | 화면 출력 | 번역 큐 |
| --- | --- | --- | --- |
| `raw` | 최신 STT window의 원시 전사 | 원문창만 | 아니오 |
| `pending` | 아직 미완성 tail 또는 판단 보류 구간 | 진단 로그 | 아니오 |
| `staged` | 완료 후보이나 재확인 필요 | 진단 로그 | 아니오 |
| `final` | 복사/번역 가능한 확정 문장 | 전사 창 | 예 |
| `suppressed` | 최근 final echo 또는 중복 후보 | 아니오 | 아니오 |
| `revised` | 다음 raw 결과에서 교체된 staged 후보 | 진단 로그 | 아니오 |

정합성 규칙:

- final transcript는 append-only로 유지한다.
- 이미 final로 확정한 문장은 UI와 번역 큐에서 되돌리지 않는다.
- staged/partial 후보는 다음 window에서 수정될 수 있으므로 번역하지 않는다.
- STT 원문창은 `stt_raw` 이벤트만 표시한다.
- 최종 복사용 문장은 전사 창에만 표시한다.

## 핵심 데이터 모델과 런타임 상태

받아쓰기 AI 런타임 상태는 raw STT window, 경계 후보, staged 후보, final transcript를 분리해 추적한다. 원본 설계 문서의 데이터 모델은 다음 기준으로 통합한다.

| 상태/필드 | 의미 | 운영 판단 |
| --- | --- | --- |
| `audio_buffer` | `windowSeconds` 기준 오디오 원본 | STT 입력 단위다. final 출력 단위와 동일하지 않다. |
| `last_window_text` | 직전 window 전체 전사 | stable token, delta, echo suppression 비교에 사용한다. |
| `pending_text` | 아직 확정되지 않은 누적 후보 | 내부 상태와 진단 로그 대상이며 번역하지 않는다. |
| `committed_text` | 이미 final로 확정된 append-only 텍스트 | 사용자 전사 창과 번역 큐의 기준이다. |
| `recent_committed_fragments` | 최근 final 조각 | echo/중복 억제 보조 참조다. |
| `sentence_boundary_detector` | STT 결과 문장 경계 처리 detector | STT 텍스트를 completed/pending 후보로 나눈다. |
| `boundary_detector_language` | detector가 현재 맞춰진 언어 | 언어 변경 시 detector 재생성 필요 여부를 판단한다. |
| `staged_sentence` | final 전 재확인 중인 완료 후보 | 다음 window에서 revision/교체/확정될 수 있다. |
| `staged_confirmations` | 같은 후보가 재관측된 횟수 | `sentenceFinalizeAge` 기준과 함께 final 승격에 사용한다. |
| `staged_age` | 후보가 staged 상태로 남은 chunk 수 | 품질 게이트를 통과한 후보의 장기 보류를 막는 보조 확정 기준이다. revision lifecycle이 유지되면 누적한다. |
| `staged_forced` | forced 후보 여부 | forced 후보도 별도 재확인과 품질 게이트를 통과해야 한다. |
| `replacement_decision` | staged 교체 판단 사유 | `unconfirmed`, `open_korean_clause`, `partial_revision`, `partial_preserve`, `duplicate_or_suffix`, `aged` 같은 이유를 로그로 남긴다. |
| `lifecycle_metrics` | 세션 누적 생명주기 카운터 | 장기 품질 추세와 회귀 판단에 사용한다. |
| `chunk_metrics` | 현재 chunk 생명주기 카운터 | 특정 chunk에서 stage/revision/final 이벤트가 폭증하는지 본다. |

출력 계층 용어는 다음처럼 정리한다.

| 계층 | 의미 | 정책 |
| --- | --- | --- |
| `hypothesis_text` | 가장 최근 STT window 디코딩 결과 | 내부 비교용이다. 사용자 final로 직접 쓰지 않는다. |
| `pending_text` | 재작성 가능한 후보 구간 | 경계/재확인을 기다린다. |
| `confirmed_text` | 안정 판정 후 append-only 출력되는 구간 | 전사 창과 번역 큐의 입력이다. |

## 문장 경계 처리 전략

### 기본 선언

- 운영/설정 시나리오에서 regex 기반 문장 분할은 폐기한다.
- 문장 경계 후보는 SaT/wtpsplit 같은 다국어 SBD 모델을 우선한다.
- SBD 결과가 완료 문장을 제안해도 즉시 final로 출력하지 않는다.
- final 확정은 staged 후보가 다음 STT window에서 재관측되는지 확인한 뒤 수행한다.
- boundary 실패와 STT 실패를 분리해 계측한다.

### SaT / SBD

Segment Any Text(SaT)는 문장부호가 없거나 noisy한 텍스트에서도 robust sentence segmentation을 목표로 하는 다국어 SBD 모델이다. 받아쓰기 AI에서는 SaT/wtpsplit을 문장 경계 후보 생성 baseline으로 사용하고, 마지막 segment는 기본적으로 pending으로 보수 처리한다.

### Streaming punctuation

Streaming punctuation은 raw STT의 readability와 boundary score를 개선하는 보조 신호다. 긴 받아쓰기에서는 미래 문맥을 너무 적게 보면 마침표를 늦게 또는 잘못 찍고, 너무 오래 기다리면 final latency가 커진다. 따라서 bounded lookahead와 token boundary scoring 방식을 우선한다. LLM free-form rewrite는 원문 rewrite와 alignment 붕괴 위험이 있으므로 기본 경로로 쓰지 않는다.

### VAD와 무음 구간의 비목표

VAD와 silence 길이는 받아쓰기 AI 실시간 처리 파이프라인의 구현 목표에서 제외한다. 음성/비음성 구간 탐지는 일반적으로 유용할 수 있지만, 이 프로젝트의 문장 확정과 번역 큐 투입 기준은 텍스트 안정성, SBD, punctuation/right-context, staged confirmation이다.

근거:

- pause가 sentence boundary와 반드시 일치하지 않는다.
- lecture/presentation 같은 long speech에서는 명확한 silence가 드물다.
- 짧은 pause로 연결된 문장은 VAD가 안정적으로 탐지하기 어렵다.
- sentence end detection은 domain, punctuation, lexical cue, right context를 함께 봐야 한다.

따라서 VAD/무음 길이/발화 종료 예측은 final trigger, boundary confidence 보정, 번역 큐 투입 조건 어디에도 넣지 않는다. 관련 레퍼런스는 제외 근거와 비교군으로만 유지한다.

## 확정 생명주기

주요 이벤트:

- `stage_start`: 새 후보가 staged 상태로 진입한다.
- `stage_revision`: 다음 window 후보가 기존 staged 후보의 revision으로 판정된다.
- `stage_replace`: 다음 후보가 별도 후보로 판정된다.
- `stage_replaced_unconfirmed`: 기존 staged 후보가 확정 기준에 도달하지 못하고 교체된다.
- `stage_finalize_before_replace`: 새 completed 후보가 들어오기 전에 기존 staged 후보를 먼저 확정한다.
- `finalize_recent_echo_suppressed`: 최근 final과 유사한 대체 후보를 중복 억제한다.
- `finalized`: 후보가 final transcript로 확정된다.
- `candidate_duplicate_suppressed`: 이미 committed된 내용과 중복되어 출력하지 않는다.
- `segment_state_pending/staged/final/suppressed/revised`: 상태 전환을 공통 축으로 집계한다. 기존 lifecycle metric은 원인 분석용이고, 이 metric은 상태 비율 관측용이다.

일반 후보는 `sentenceFinalizeAge`만큼 여러 window에서 재확인된 뒤 확정한다. 기본 추천값은 3회다.

중국어에서 한 STT window가 여러 completed 후보를 반환하면 하나의 관찰 단위로 병합한다. 같은 chunk 안 후속 후보가 첫 관찰 후보를 즉시 final로 밀어내지 않도록, 교체 직전 확정은 `sentenceFinalizeAge` 또는 재확인 횟수 기준을 통과한 staged 후보에만 허용한다.

차단/폐기 대상은 명백한 오류로 제한한다.

- 빈 문자열
- 공백 삽입 CJK
- 반복 n-gram
- 중국어 설정에서 라틴 문자만 나온 후보

후보 차단 규칙이 늘어나면 final 생성률이 급격히 낮아질 수 있으므로, 나머지는 staged 교체와 재확인으로 처리한다.

## 경계 인터페이스와 운영 backend

STT 결과 문장 경계 처리는 받아쓰기 AI 실행 루프에서 분리한다. 구현 기준은 `src/app/sentence_boundary.py`의 detector 인터페이스다.

```python
@dataclass(frozen=True)
class SentenceBoundaryResult:
    completed: list[str]
    pending: str
    backend: str
    boundary_count: int
    soft_boundary_count: int = 0
    end_mark_count: int = 0
    right_context_start_count: int = 0


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

운영 루프는 `create_sentence_boundary_detector`로 생성한 detector의 `split()`을 호출한다. `split_completed_sentences` 래퍼는 과거 회귀 테스트와 legacy helper 용도로만 유지하고, 운영 루프와 설정 기본값에는 사용하지 않는다.

backend 정렬:

| backend | 용도 | 운영 판단 |
| --- | --- | --- |
| `sat` | 현재 운영 기본 경계 backend | `wtpsplit.SaT` 계열을 로드하고 `cuda/float16`을 우선한다. 로딩/분절 실패 시 Fail-Fast다. |
| `mock` | 테스트/격리용 | 실제 품질 비교군이나 운영 기본값으로 사용하지 않는다. |
| `legacy-regex` | 과거 회귀 테스트 보존 helper | 운영 backend, 설정 허용값, 기준선 비교군으로 사용하지 않는다. |

STT 결과 문장 경계 처리 계약:

- STT backend/model과 sentence boundary backend/model은 분리한다.
- SBD는 completed/pending 후보를 제안하지만 final을 직접 결정하지 않는다.
- final 승격은 staged confirmation, `sentenceFinalizeAge`, revision lifecycle이 담당한다.
- punctuation/end-mark, right-context 시작 징후, soft boundary, end probability는 `SentenceBoundaryResult`의 관측 지표로 기록한다. 이 값은 final 직접 트리거가 아니라 staged 생명주기 튜닝과 회귀 분석 입력이다.
- 중국어에서 SBD가 한 window 안에 여러 completed 후보를 반환하면 같은 STT window의 하나의 관찰 단위로 병합한다.
- 영어/한국어는 경계 모델 출력 단위를 보존한다.
- boundary backend/model은 명시 설정값만 사용한다. 실행 중 언어에 따라 backend/model을 암묵 변경하지 않는다.

## 언어별 STT 백엔드와 파라미터

### 영어 / 한국어

- 현재 STT: `faster-whisper` + `large-v3`
- 시작값: `windowSeconds=7.0`, `stepSeconds=1.0`, `sentenceFinalizeAge=3`
- 빠른 발화와 문장 누락이 문제라면 `beamSize=3`, `temperature=0.0`, `maxNewTokens=192`를 시작점으로 비교한다.

영어/한국어는 현재 `faster-whisper` 경로에서 준수한 성능으로 판단한다. 7초 window가 실시간성과 품질의 균형점으로 관측되었다.

### 중국어

- Whisper/faster-whisper는 중국어에서는 baseline으로만 둔다.
- 현재 STT는 `qwen3-asr-transformers` + `qwen3-asr-0.6b`다.
- 시작값: `windowSeconds=12.0`, `stepSeconds=1.0`, `sentenceFinalizeAge=2`

중국어는 현재 Qwen 경로에서 준수한 성능으로 판단한다. 공백 기반 단어 경계가 약하고 동음 후보가 많아 긴 문맥이 raw STT 안정성에 도움이 될 수 있다. 하지만 긴 window는 final transcript 갱신 지연과 긴 문장 확정을 증가시킨다. 따라서 STT context와 final commit unit을 분리해서 본다.

## 런타임 의존성과 모델 캐시 제약

받아쓰기 AI는 CUDA/float16 중심의 Fail-Fast 정책을 따른다. 모델과 의존성은 실행 중 암묵 변경하지 않는다.

| 항목 | 현재 판단 |
| --- | --- |
| `faster-whisper`, SaT, NLLB/M2M100 | Serve 런타임에서 로컬 캐시만 사용한다. 캐시가 없거나 부분 다운로드 상태면 다운로드하지 않고 실패한다. |
| 모델 다운로드 | `scripts/setup/download-dictation-ai-models.py`와 config GUI 모델 다운로드 매니저 경로로 제한한다. `serve`는 다운로드를 수행하지 않는다. |
| `qwen-asr` | `qwen-asr==0.0.6`은 `transformers==4.57.6` 요구와 함께 고정한다. |
| `gradio` | qwen-asr 의존성 범위가 넓어 resolver 역추적을 만들 수 있으므로 dry-run에서 확인한 호환 버전을 고정한다. |
| `wtpsplit` | Hugging Face Hub 메타데이터 제약이 Qwen3-ASR/transformers와 충돌할 수 있어 setup/env sync에서 `--no-deps` 설치를 전제로 한다. 필요한 런타임 의존성은 별도 명시한다. |
| fallback | CUDA/float16 요구 경로에서 CPU, regex, Whisper, 다른 STT backend로 자동 대체하지 않는다. |

## 번역 정책

- 기본은 final-only다.
- `staged/partial` 번역은 기본 비활성이다.
- 번역 입력은 `confirmed` 텍스트만 사용한다.
- NLLB 선택 시 Whisper backend는 `task=transcribe`만 수행하고 번역은 NLLB 경로만 사용한다.
- Whisper 내장 `translate` 경로는 영어 번역만 지원한다.
- 중국어/한국어/영어 대상 번역은 `nllb-transformers` 같은 외부 번역 경로를 사용한다.

NLLB 번역 기본 테스트값:

- `translationDevice=cuda`
- `translationComputeType=float16`
- `translationBeamSize=1`
- `translationMaxNewTokens=128`

번역 품질이 부족하면 `translationBeamSize=3` 또는 `translationMaxNewTokens=256`을 비교한다. 실시간 경로에서는 CPU fallback을 허용하지 않는다.

## 운영 파라미터 기준

| 항목 | 영어/한국어 시작값 | 중국어 시작값 | 판단 기준 |
| --- | ---: | ---: | --- |
| `windowSeconds` | 7.0 | 12.0 | raw STT 안정성과 final 지연의 균형 |
| `stepSeconds` | 1.0 | 1.0 | 화면 갱신과 반복 처리량의 균형 |
| `sentenceFinalizeAge` | 3 | 2 | staged 후보 재관측 횟수 |
| `beamSize` | 3 | 3 | 정확도/지연 비교 시작점 |
| `temperature` | 0.0 | 0.0 | 재현성과 안정성 |
| `maxNewTokens` | 192 | 192 | 긴 문장 절단 방지 |
| `translationBeamSize` | 1 | 1 | 실시간 번역 시작점 |
| `translationMaxNewTokens` | 128 | 128 | 번역 지연 제어 |

성능 로그의 `stt_step_load` 또는 `total_step_load`가 1.0을 넘거나 `input_queue_drops`가 1 이상이면 실시간 처리량을 초과한 상태다.

## 품질 지표

받아쓰기 AI 실시간 전사/번역 경로의 품질은 unittest 성공/실패만으로 판단하지 않는다. 테스트는 누적 운영 로그에서 관측한 실패 사례를 실행해 현재 로직의 성능 추이를 출력하는 추적 하네스다. 특히 `test_dictation_ai_performance_tracking.py`는 실패 현상 재현과 튜닝 근거 수집이 목적이며, 개별 tracking case가 모두 성공해야 한다는 품질 게이트가 아니다. unittest 성공은 metric collection이 실행됐다는 의미이고, 출력되는 tracking rate와 gap을 줄이는 것이 개선 목표다.

### 테스트 분류 정책

로그에서 나온 케이스는 기본적으로 성능 추적 케이스로 분류한다. 개별 케이스의 성공/실패는 튜닝 근거이며 품질 게이트가 아니다.

하드 품질 게이트로 둘 수 있는 경우:

- 설정/계약/default 값처럼 입력과 출력이 명확한 public contract
- 이미 확정한 안전 정책: CPU fallback 금지, 번역 큐는 final-only, 명백한 중복 final 억제
- 결정적 helper의 단일 책임이 분명하고, 실패 시 즉시 사용자 출력이 오염되는 경우
- 과거 버그가 재현 가능한 최소 입력으로 축소되어 있고, 모델/로그 분포 변화와 무관한 경우

성능 추적 하네스에 둬야 하는 경우:

- 30분/5분 운영 로그에서 수집한 raw 후보, stage churn, replacement, finalization latency
- `rate`, `gap`, `per_stage_start`, `translation_quality`처럼 추세로 판단해야 하는 항목
- STT 모델 출력 흔들림에 의존하는 케이스
- 파라미터 튜닝 근거용 케이스
- 현재는 실패하지만 다음 로직 개선으로 matched가 올라가야 하는 관측 케이스

정리 방향:

- 새 로그 수집 케이스는 `test_dictation_ai_performance_tracking.py`에 추가한다.
- 기존 unit test의 `from_log/from_monitoring` 케이스는 모두 제거하지 않는다. 중복 억제, 명백한 품질 차단, contract 성격의 helper 검증은 hard regression으로 남길 수 있다.
- 기존 unit test 중 파라미터 튜닝/품질 추세/모델 출력 흔들림에 가까운 케이스는 후속 패치에서 performance tracking으로 이관한다.
- hard regression으로 남긴 로그 기반 unit test는 주석에 어떤 불변 계약을 지키는지 명시한다.
- 중요도가 낮은 품질 게이트 형태 테스트는 폐기한다. single-observation replacement, legacy soft boundary 로그 샘플, 특정 로그 문장 기반 collapse 튜닝 샘플은 hard unittest가 아니라 성능 추적 대상으로만 다룬다.

| 도메인 | 의미 | 목표 |
| --- | --- | ---: |
| `revision` | 이전 partial/final 문장이 새 STT window에서 올바르게 갱신되는지 | 90% 이상 |
| `distinct` | 서로 다른 문장을 잘못된 revision으로 병합하지 않는지 | 95% 이상 |
| `collapse` | 같은 의미의 인접 반복 문구를 줄이는지 | 90% 이상 |
| `stability` | 연속 partial 전사가 전체 재출력 없이 안정적으로 revision되는지 | 80% 이상 |
| `replacement` | staged 후보 교체 시 보존/폐기/확정 결정이 의도와 맞는지 | 90% 이상 |
| `pending` | 긴 pending이 확정되지 않는 사유를 추적하는지 | 90% 이상 |
| `pending_quality` | pending 버퍼에 CJK 반복 n-gram 같은 오염 신호가 누적되는지 | 100% |
| `final_quality` | final 후보의 품질 위험을 추적하는지 | 90% 이상 |
| `finalization` | 로그에서 확정되지 않았거나 과확정된 후보가 현재 정책에서 어떤 방향으로 처리되는지 | 80% 이상 |
| `coalesce` | 중국어 multi-completed 후보를 하나의 관찰 단위로 병합하는지 | 100% |
| `duplicate_suppression` | 이미 확정/관측된 후보가 중복 출력되지 않도록 억제되는지 | 100% |
| `runtime_metrics` | 런타임 누적 지표와 queue/backlog 지표가 안정성 요약으로 올바르게 집계되는지 | 100% |
| `translation_quality` | 번역 출력의 고유명사/도메인 용어/환각 회귀를 추적하는지 | 80% 이상 |

향후 정답 전사 코퍼스가 준비되면 `WER`, 한국어/중국어 `CER`, deletion rate, duplicate insertion rate, finalization latency, revokes per second를 추가한다.

## KPI 리포트 프레임

운영 판단은 "지표가 좋아졌는가"가 아니라 "중복 감소, 지연 제어, 번역 안정성이 달성되었는지"를 본다.

3개 축:

1. 안정성 축: 리비전 빈도와 규모 감소 (`UPWR`, `UPSR`, `replaced ratio`, `rollback_rate`, `finalized_per_stage_start`, `revision_preserve_rate`)
2. 경계 축: 문장 경계 추정 품질 (`pending_chars`, `forced_by`, `boundary_latency`, `end_marks_stable`, `boundary_right_context`)
3. 지연/번역 축: 실시간성 (`stt_rtf`, `total_rtf`, `input_queue_size_peak`, `input_queue_backlog`), 번역 부하 (`confirmed_only_delta`, `translation_redundant_ratio`)

권장 실험 절차:

1. baseline/candidate를 동일 오디오 세션으로 반복 수행한다.
2. 각 세션당 12~20분, 최소 30분/언어권을 확보한다.
3. 로그 레벨 `INFO`에서 이벤트 텍스트/타임스탬프를 저장한다.
4. 로그 수집 뒤 KPI 집계 스크립트를 실행한다.
5. 주 단위로 KPI 리포트를 만들고 릴리스 문턱과 비교한다.

주요 공식:

- `UPWR = unstable_word_count / emitted_word_count`
- `UPSR = unstable_segment_count / emitted_segment_count`
- `DupAmplification = total_output_chars / canonical_committed_chars`
- `Latency = p95(stt_rtf)` 및 `p95(total_rtf)`
- `confirmed_only_ratio = confirmed_delta_bytes / total_transcript_bytes`
- `translation_redundant_ratio = duplicated_translation_chars / total_translation_chars`
- `translation_delay_p95 = p95(translation_submit_ts - confirmed_commit_ts)`

번역 영향 지표:

| 지표 | 의미 | 판단 |
| --- | --- | --- |
| `confirmed_only_ratio` | 전체 transcript 중 final로 확정된 입력 비율 | 0.9 이상을 기본 목표로 둔다. |
| `translation_redundant_ratio` | 중복 번역 문자의 비율 | partial 번역이나 echo 번역이 새는지 확인한다. |
| `translation_delay_p95` | final 확정 후 번역 큐 투입까지의 p95 지연 | 번역 backend 지연과 UI 반영 지연을 분리해 본다. |
| `translation_quality` | 고유명사, 도메인 용어, 금지 오역 회귀 | 현재 회귀 샘플 기반 지표이며, 실제 backend 실행 pass/fail과 분리한다. |
| `BLEU`/`CHRF` | 정답 번역이 있는 오프라인 평가 지표 | 실시간 운영 게이트가 아니라 모델 비교 리포트 보조 지표로 쓴다. |

비교군 정의:

| 비교군 | 의미 |
| --- | --- |
| Baseline | 이전 운영 로그와 수집 지표. `sentenceBoundaryBackend=regex`는 폐기된 기준선이므로 새 운영 기준으로 재사용하지 않는다. |
| Candidate A | `sentenceBoundaryBackend=sat` 기본값 |
| Candidate B | `sat + pending/강제 확정 임계치 조정` 같은 후속 실험 |

권장 로그 입력:

| 이벤트 | 권장 필드 |
| --- | --- |
| split event | `chunk`, `completed`, `final`, `pending_text`, `forced_by`, `pending_overrun`, `boundary_backend`, `boundary_end_marks`, `boundary_right_context`, `segment_state_pending`, `segment_state_staged`, `segment_state_final`, `segment_state_suppressed`, `segment_state_revised`, `pending_chars`, `pending_chunks`, `pending_chars_per_chunk` |
| commit event | `step`, `window`, `stt_elapsed`, `stt_rtf`, `translation_elapsed`, `total_elapsed`, `total_rtf`, `input_queue_drops`, `queue_size`, `queue_peak`, `beam`, `max_tokens`, `text_chars` |
| transcript fragment | `delta_text`, `state`, `revision_id` |

판정 규칙:

| 판정 | 조건 |
| --- | --- |
| Go | `UPWR`, `UPSR`가 baseline 대비 각각 15% 이상 개선되고, `pending_chars_p90`이 10% 이상 개선되며, `confirmed_only_ratio >= 0.9`이고 `p95(total_rtf)`가 목표값 안에 있다. |
| No-Go | `p95(total_rtf)`가 baseline 대비 20% 이상 악화되거나, `UPWR`/`UPSR`이 15% 이상 악화되거나, `DupAmplification > 1.3`이 지속된다. |
| Ramp | Go/No-Go 임계에는 못 미치지만 `pending_chars`와 `forced_by`가 개선되고 `rtf` 악화가 5% 이하인 경우다. |

KPI 리포트 산출물은 `docs/reports/dictation-ai-kpi-{{date}}.md` 형태를 권장한다. 권장 항목은 실행 식별자, 실험군, 조건, 언어별 KPI 표, 회귀 Top 5 로그 예시, 다음 액션 체크리스트다.

운영 주기:

- 일간: 1회 KPI 수집, `forced_by`, `UPSR`, `rtf` 급변 감시.
- 주간: 후보군 비교 리포트 리뷰.
- 릴리스 직전 2주: 동일 세션셋으로 재현성 검증.

## 실험 노트

### 2026-06-13 운영 관측

30분 운영 로그 모니터링에서 계산 성능보다 문장 확정 생명주기와 staged 교체 판단 순서가 품질 병목으로 나타났다.

반영 판단:

- 일반 후보 확정 기준을 2회에서 3회 재확인으로 조정했다.
- forced 후보 확정 기준은 4회 재확인을 유지한다.
- tail 확정 지연 설정은 제거하고 `sentenceFinalizeAge`와 staged confirmation으로 일원화한다.
- VAD 기반 필터링은 슬라이딩 윈도우 확정 정책과 충돌해 운영 경로에서 제거한다.
- 열린 한글 절은 반복 관측만으로 확정하지 않는다.
- partial replacement에서 기존 staged가 문장형으로 닫혔거나 candidate와 tail overlap이 충분하면 staged 문장을 보존한다.

대표 회귀:

- `이 두 직업은`이 두 번 관측되어 확정됐지만 실제로는 다음 문장의 열린 절이었다.
- 긴 금액 설명 문장이 여러 번 관측됐지만 열린 절이므로 다음 candidate로 교체될 때 확정하면 안 됐다.
- 다음 문장 머리와 tail overlap이 섞인 경우 staged 보존이 필요했다.

### 2026-06-14~16 중국어 completed 후보 관찰 단위 조정

중국어 운영 로그에서는 `boundary_complete=2~4`가 같은 chunk 안에서 반복 관측되었다. 기존 생명주기는 completed 후보를 순서대로 staging에 넣었기 때문에 같은 STT window의 첫 번째 후보가 다음 후보에 의해 폐기되거나 즉시 final로 밀리는 문제가 있었다.

반영 판단:

- 중국어 multi-completed 후보는 같은 STT window의 하나의 관찰 단위로 병합한다.
- 영어/한국어는 경계 모델 출력 단위를 보존한다.
- 교체 직전 확정은 `sentenceFinalizeAge` 또는 재확인 횟수 기준을 통과한 후보에만 허용한다.
- CJK revision 내용이 실제로 바뀐 경우 confirmations를 1부터 다시 센다.

대표 비교:

- `qwen3-asr-0.6b`, `window=30`: 의미 보존과 문장 구조가 FunASR보다 자연스러웠지만 final 지연 비용이 있었다.
- `funasr-paraformer`, `window=30`: 처리시간은 빠르지만 stage 교체/폐기가 많고 확정률이 낮았다.
- `funasr-paraformer`, `window=15`: 처리시간은 더 빠르지만 품질 우선 후보로 보기 어렵다.

운영 판단은 Qwen3-ASR를 중국어 품질 우선 후보로 올리고 FunASR STT는 후보군에서 제외한다는 것이다. 단, 기존 비교는 같은 입력 replay가 아니라 시간대가 다른 운영 로그 기반이므로, 향후 동일 입력 replay에서 재검증한다.

### 2026-06-15 중국어 pending 내부 재시작 관측

최근 회전 로그 집계에서는 계산 성능은 병목이 아니었다. 대표 문제는 pending이 길어진 상태에서 다음 STT window가 같은 CJK 구간을 내부 중간부터 다시 내보내는 경우였다.

예시:

```text
pending_tail=...喷枪
new_text=条，然后把这米再切断了，摆成四个墩儿墩儿，然后就是火山的底座，然后上面这个洒的就更像熔岩一样，然后用喷枪
old_result=...喷枪 条，然后把这米再切断了...
```

이 케이스는 SBD 구두점 결정 문제가 아니라 pending/new 접합 단계에서 내부 재시작을 새 continuation으로 오인한 문제로 분류했었다.

폐기 판단:

- CJK no-space 내부 prefix overlap 기반 접합 보정은 학술적 근거가 부족하므로 운영 요구사항에서 제외한다.
- `boundary_input_text()`는 detector 입력을 만들기 위한 단순 결합만 수행한다.
- STT 원문창은 staged 후보가 아니라 raw STT window만 표시해야 한다.

### 2026-06-16 원문창 의미 재정의

전사 품질을 볼 때는 세 창/로그의 의미를 구분한다.

- STT 원문창: raw STT window 결과
- 전사 창: revision lifecycle과 final 확정을 거친 사용자 출력
- stdout 진단 로그: `stable_tail`, `delta_tail`, `pending_tail`, `staged_tail` 같은 내부 상태

원문창이 staged 후보를 표시하던 시기의 로그 해석은 raw STT 품질 판단 근거로 쓰지 않는다.

중국어 성능 추적에서 순수 비중국어/라틴 단독 입력은 제거한다. 이는 중국어 문장 추출 확정 실패가 아니라 입력 언어 불일치 또는 언어 분류 문제로 분리한다.

### 2026-06-16 중국어 5분 운영 모니터링

`qwen3-asr-0.6b`, `window=15.0`, `step=1.0`, `beam=3`, `maxNewTokens=192`, 번역 ON 조건으로 약 5분간 `.tmp/logs/avc-whisper.log`를 추적했다. `stt_step_load`와 `total_step_load`는 대부분 1.0 미만이었고 input queue drop은 관측되지 않아 계산 성능은 병목으로 보지 않는다.

관측된 병목은 확정 생명주기와 품질 차단이다.

- `completed_coalesced`는 정상적으로 증가해 중국어 multi-completed 병합은 동작한다.
- `raw_without_final`이 크게 누적되어 raw STT 관측 대비 final 확정률이 낮다.
- `stage_revision_confirmation_reset`이 높아 후보가 자주 바뀌며 재확인 카운트가 리셋된다.
- `stage_replace`와 `stage_replaced_unconfirmed`이 같은 수준으로 증가해 미확정 staged 교체가 많다.
- CJK delta trim 뒤에도 `很 赞 哎...`처럼 글자 단위 공백 후보가 staged 경로에 남는다.
- `no_end_marker` final은 번역 차단되고 있었지만, `mixed_latin_zh` final은 번역되어 `G配Y T` 같은 오염이 번역 결과로 전달됐다.

반영 판단:

- `mixed_latin_zh` final transcript는 전사 출력에는 남길 수 있지만 번역 큐에는 넣지 않는다.
- 추적 테스트에 `finalization_rate_per_1000`, `replace_unconfirmed_rate_per_1000`, `translation_skip_per_final_quality_per_1000`을 추가한다.
- `window=15.0`은 계산상 가능하지만 기본값으로 승격하지 않는다. `windowSecondsZh=12.0`, `stepSecondsZh=1.0`, `beamSizeZh=3`, `maxNewTokensZh=192`를 유지하고, 확정률/미확정 교체율 개선을 먼저 본다.

### 2026-06-16 stable 지표 적용 후 5분 운영 모니터링

stable token 지표를 추가한 뒤 같은 중국어 실시간 경로를 약 5분 더 관측했다. 처리량은 여전히 충분했다. `stt_step_load`는 대체로 0.3~0.7 구간에 있고 queue drop은 관측되지 않았다. 따라서 이번 단계에서는 `stepSecondsZh`, `windowSecondsZh`, `beamSizeZh`, `maxNewTokensZh`를 조정하지 않는다.

관측된 병목:

- `stable_token_ratio`가 높은 chunk에서도 후보 자체가 글자 단위 공백 CJK로 변환되면 staged 교체와 confirmation reset을 유발했다.
- `raw_without_final`과 `stage_revision_confirmation_reset`은 계속 누적됐다.
- `stage_replace_decision_unconfirmed_cjk`와 `stage_replaced_unconfirmed`가 누적되어, 불안정 후보를 stage에 올리기 전에 차단할 필요가 있었다.
- `stable_overlap_source=suffix_prefix`는 정상 final 직전에도 관측되어 sliding overlap 지표가 유효한 진단 신호임을 확인했다.

반영 판단:

- `spaced_cjk`, `cjk_repeated_ngram`, `latin_only_for_zh`, `empty` 후보는 stage 진입 전에 차단한다. 단, `latin_only_for_zh`는 방어적 차단 지표일 뿐 중국어 문장 추출 성능 테스트 케이스로 누적하지 않는다.
- `short_cjk`, `no_end_marker`, `mixed_latin_zh`는 stage 진입 차단 대상에 넣지 않는다. 전사 보존 필요성이 있으므로 final/translation 품질 게이트에서만 다룬다.
- 안정성 요약 로그에 `stage_candidate_quality_blocked`, `stage_candidate_quality`를 추가해 차단 건수와 flag 수를 분리해서 본다.
- 추적 테스트에 `stage_candidate_quality_blocked`, `stage_candidate_quality`, `stage_candidate_quality_spaced_cjk`, `stage_candidate_quality_no_end_marker`를 추가한다.
- 다음 관측에서는 `stage_candidate_quality_blocked` 증가와 함께 `stage_replaced_unconfirmed`, `stage_revision_confirmation_reset`, `raw_without_final`이 줄어드는지 본다.

추가 5분 모니터링 결과:

- stage 후보 품질 차단은 실제 운영 로그에서 반복적으로 동작했다. `spaced_cjk,cjk_internal_gap,no_end_marker` 조합 후보가 stage에 올라가지 않아 해당 chunk의 즉시 교체/confirmation reset은 줄었다.
- 누적 지표 기준으로 `stage_candidate_quality_blocked`는 증가했지만, `raw_without_final`과 `stage_revision_confirmation_reset`은 여전히 높았다. 이는 품질 차단만으로는 sliding window 시작점 흔들림을 설명하기 부족하다는 신호다.
- 여러 chunk에서 Qwen window가 같은 의미 구간을 내부에 유지하면서도 prefix 또는 suffix-prefix로는 맞지 않아 `stable_token_ratio=0`, `stable_overlap_source=none`으로 기록됐다.
- 처리 부하는 계속 안정적이었다. `stt_step_load`와 `total_step_load`가 병목 신호를 만들지 않았으므로 런타임 파라미터는 유지한다.

추가 반영 판단:

- `stable_internal_chars`, `stable_internal_ratio`를 진단 지표로 추가한다. 이 값은 이전/현재 window의 최장 내부 공통 구간을 측정한다. 이후 내부 overlap은 CJK revision confirmation 보존의 보조 feature로 승격했다.
- `stable_overlap_source=none`이면서 `stable_internal_ratio`가 높은 케이스를 추적 테스트에 추가한다. 이후 같은 패턴이 반복되면 내부 공통 구간을 revision lifecycle의 보조 feature로 승격할지 별도 검증한다.
- 안정성 요약 로그에 `stage_candidate_quality_cjk_internal_gap`, `stage_candidate_quality_mixed_latin_zh`를 추가한다. `mixed_latin_zh` 단독 stage 차단은 하지 않지만, 오염 후보가 다른 차단 flag와 함께 얼마나 나타나는지 관측한다.
- 추적 테스트의 stable metric 케이스를 4개로 늘려 prefix, suffix-prefix, 내부 overlap, stage 후보 품질 차단을 모두 유지한다.

내부 overlap 보조 신호 적용:

- `stable_overlap_source=none`이고 `stable_internal_ratio>=0.75`인 CJK stage revision은 완전히 다른 후보라기보다 window 시작점이 흔들린 동일 구간 재표현일 가능성이 높다.
- 이 조건에서는 final 확정 기준을 완화하지 않는다. 대신 `stage_revision_confirmation_reset`을 올리지 않고 기존 confirmation count를 유지한다.
- 안정성 요약 로그에 `revision_preserved_internal`을 추가해 reset 감소와 보존 증가를 함께 본다.
- 추적 테스트에 `stage_revision_confirmation_preserved_internal`을 추가한다. 다음 운영 관측에서는 `revision_preserved_internal` 증가가 오확정 증가로 이어지는지 `final_quality`, `translation_skip_final_quality`, recent echo 억제 지표와 함께 검증한다.

상태 전환 metric 추가:

- `segment_state_pending/staged/final/suppressed/revised`를 안정성 요약 로그와 runtime tracking에 추가한다.
- `pending`은 tail 보류, `staged`는 후보 stage 진입, `final`은 append-only 확정, `suppressed`는 중복/echo/품질 차단, `revised`는 stage revision 관측을 의미한다.
- 다음 관측에서는 `segment_state_suppressed`와 `segment_state_revised`가 높을 때 원인 metric인 `stage_candidate_quality_*`, `stage_revision_confirmation_reset`, `candidate_duplicate_suppressed`, `finalize_recent_echo_suppressed` 중 어느 쪽이 주도하는지 분리한다.

### 2026-06-16 내부 overlap 적용 후 5분 운영 모니터링

내부 overlap 보조 신호를 적용한 뒤 중국어 실시간 경로를 약 5분 더 관측했다.

관측값:

- chunk 320 누적 기준 `finalized=19`, `raw_without_final=300`, `stage_replaced_unconfirmed=63`, `stage_revision_confirmation_preserved_internal=30`, `stage_revision_confirmation_reset=109`였다.
- `stable_internal_ratio>=0.75` 케이스는 `revision_preserved_internal`로 분리되어 reset을 줄였지만, 0.60대 내부 overlap을 가진 같은 문맥 확장 리비전은 여전히 reset됐다.
- 예: `stable_internal_chars=65`, `stable_internal_ratio=0.619`, `stable_overlap_source=none`인 chunk는 같은 문맥 확장인데 reset됐다.
- `stable_internal_chars=39`, `stable_internal_ratio=0.867`처럼 ratio는 높지만 내부 공통 구간이 짧은 케이스도 있어 ratio 단독 완화는 위험하다.
- `stage_candidate_quality_blocked`는 32까지 누적되어 `spaced_cjk`, `cjk_internal_gap`, `cjk_repeated_ngram` 차단이 계속 동작했다.
- 후반 일부 구간에서 `stt_step_load`가 2.9 내외로 올라가고 queue가 30대까지 쌓였지만 drop은 없었다. 반복/혼합언어 구간의 STT 출력 흔들림이 원인으로 보이며, 기본 런타임 파라미터는 유지한다.

튜닝 반영:

- CJK revision confirmation 보존 기준을 `stable_internal_ratio>=0.60`과 `stable_internal_chars>=40`의 동시 조건으로 조정한다.
- final 확정 기준은 그대로 유지한다. 이 튜닝은 reset 완화만 수행하며 확정/번역 큐 진입을 직접 앞당기지 않는다.
- 안정성 요약 로그에 `revision_internal_high`, `revision_internal_mid`, `revision_internal_low`를 추가한다.
- 추적 테스트에 high bucket 보존 케이스와 mid bucket reset 케이스를 추가한다.

### 2026-06-17 중국어 30분 운영 모니터링

중국어 실시간 경로를 약 30분 모니터링했다. 실행 조건은 운영 로그 기준 `qwen3-asr-0.6b`, `window=15.0`, `step=1.0`, `beam=3`, `maxNewTokens=192`다.

관측값:

- `stt_step_load`와 `total_step_load`는 대부분 1.0 미만이고 `input_queue_drops=0`으로 유지되어 계산 성능은 주 병목으로 보지 않는다.
- 일부 구간에서 queue가 순간적으로 50까지 쌓였다. drop은 없었지만 queue peak/backlog는 별도 추적 지표가 필요하다.
- chunk 656 누적 스냅샷 기준 `finalized=36`, `stage_start=141`, `stage_replaced_unconfirmed=104`, `stage_revision_confirmation_preserved_internal=121`, `stage_revision_confirmation_reset=192`였다.
- 위 스냅샷의 `finalized_per_stage_start`는 약 0.255, `stage_replaced_unconfirmed_per_stage_start`는 약 0.738, `revision_preserve_rate`는 약 0.387이다.
- `stage_candidate_quality_blocked`, `raw_without_final`, `segment_state_revised/suppressed`가 계속 누적되어 품질 병목은 처리량보다 staged 생명주기 churn에 가깝다.
- 문장형 후보가 보이더라도 `staged_confirmations=1/3` 또는 `2/3` 상태에서 다음 window 재표현으로 reset/교체되어 final까지 도달하지 않는 사례가 반복됐다.
- 기존 구현은 revision 처리 때 `staged_age`를 0으로 되돌려, completed 후보가 매 chunk 나오는 중국어 경로에서 age 기반 확정이 사실상 누적되기 어려웠다.

반영 판단:

- 기본 런타임 파라미터는 유지한다. 현재 로그만으로 `windowSecondsZh`, `stepSecondsZh`, `beamSizeZh`, `maxNewTokensZh`를 변경할 근거는 부족하다.
- `input_queue_size_peak`, `input_queue_backlog_chunk`를 런타임 지표에 추가해 순간 backlog와 drop 없는 지연 누적을 구분한다.
- `finalized_per_stage_start`, `stage_replaced_unconfirmed_per_stage_start`, `revision_preserve_rate`를 tracking metric으로 추가한다.
- revision으로 같은 staged lifecycle이 유지될 때 `staged_age`를 누적한다.
- CJK 후보는 첫 관측 확정을 계속 막되, 짧은 조각/글자 단위 공백/반복 n-gram/내부 공백 오염이 없는 후보가 2회 이상 관측되거나 age 기준을 채우면 `stable_cjk`/`aged` 사유로 final 승격할 수 있게 한다.
- `stage_finalize_stable_cjk`, `stage_age_finalize`, `stage_age_quality_blocked` 지표를 추가해 완화된 CJK 확정 경로, age 기준 확정, age 품질 차단을 별도로 추적한다.
- age 기준 확정도 `short_cjk`, `spaced_cjk`, `cjk_internal_gap`, `cjk_repeated_ngram`, `latin_only_for_zh` 품질 게이트를 통과해야 한다. 다만 순수 비중국어/라틴 단독 입력은 중국어 확정 성능 판단에서 제외한다.
- 패치 반영 후 새 실행 초반 chunk 431 누적 기준 `finalized=70`, `stage_start=115`, `stage_replaced_unconfirmed=44`, `stage_age_finalize=41`, `stage_finalize_stable_cjk=25`가 관측됐다. 초기 스냅샷이므로 장기 판단은 보류하지만, `finalized_per_stage_start`는 약 0.609로 이전 장기 스냅샷의 약 0.255보다 개선 방향이다.
- 30분 모니터링 종료 직전 chunk 761 누적 기준 `finalized=120`, `stage_start=195`, `stage_replaced_unconfirmed=72`, `input_queue_drops=0`, `input_queue_size_peak=10`이었다. 확정률은 개선 방향이지만, age 품질 게이트 보완 전 실행 로그가 섞여 있으므로 다음 실행에서 `stage_age_quality_blocked`와 `final_quality_short_cjk/spaced_cjk` 변화를 다시 확인한다.
- 추적 테스트에 이번 30분 운영 로그 스냅샷을 추가한다.
- 학술적 근거가 부족한 pending/new 접합 보정은 재도입하지 않는다.

### 2026-06-17 후속 30분 운영 모니터링

로그 회전 보존 개수를 1000개로 늘린 뒤 중국어 실시간 경로를 다시 관측했다. 분석 범위는 `.tmp/logs/avc-whisper.log*`의 `2026-06-17 00:11:59`부터 `00:41:59`까지 약 30분이다. 실행 조건은 로그 기준 `qwen3-asr-0.6b`, `window=15.0`, `step=1.0`, `beam=3`, `maxNewTokens=192`, 번역 OFF 구간 중심이다.

관측값:

- `perf` 로그 1039개 기준 평균 `total_step_load≈0.63`, 최대 `1.39`, `input_queue_drops_total=0`, 최대 `queue_peak=10`이었다.
- `completed=1 final=0` 진단은 863회, `final=1` 진단은 651회 관측됐다. completed 후보가 있어도 stage/품질/중복 억제 상태로 남는 경우가 여전히 많다.
- 주요 이벤트는 `stage_candidate_quality_blocked=184`, `stage_replaced_unconfirmed=84`, `stage_revision_reset=379`, `stage_age_finalize=108`, `stage_finalize_stable_cjk=44`, `confirmed_finalize=11`, `translation_skip_final_quality=104`였다.
- 대표 품질 차단은 글자 단위 공백 CJK였다. 예: `顶 级 的 夏 威 夷 对 品 质 之 上 的 很 好 吃 好 看 这 个 哇 好 吃`.
- 대표 final 품질 관측은 `no_end_marker` 또는 `short_cjk,no_end_marker`였다. 예: `好乖好棒好棒怎么那么棒你看他还去当指挥交通的`, `拍照那我们就进去耶`.
- 안정 신호가 높아도 첫 관측 또는 단일 교체 후보인 경우에는 final로 보내지 않는 현재 정책이 유지됐다. 예: chunk 80의 긴 CJK 후보는 `stable_token_ratio=0.924`였지만 `staged_confirmations=1`, `staged_age=0`이라 `unconfirmed_cjk` 교체로 남았다.

튜닝 판단:

- 계산 처리량은 병목이 아니므로 `stepSecondsZh=1.0`, `beamSizeZh=3`, `maxNewTokensZh=192`는 유지한다.
- 2026-06-17 SaT 벤치(`tests/eval/dictation_ai/sbd_text_cases.sample.jsonl`, 캐시 모델/CUDA) 기준 `sentenceFinalizeAgeZh=2`가 현재 기본 후보 중 가장 낫다. `no_end_marker` final은 0으로 유지하면서 `finalized=20`, `stage_start=34`, `finalized_per_stage_start=0.588`로 age 3의 `finalized=19`, `stage_start=35`, `finalized_per_stage_start=0.543`보다 확정 지표가 개선됐다. 4 이상은 `finalized=18`, `finalized_per_stage_start=0.514`로 누락 쪽으로 기운다.
- `windowSecondsZh=15.0`은 현재 STT 안정성과 확정 지연의 균형점으로 유지한다. 이번 구간에서 queue drop이 없으므로 처리량 때문에 줄일 근거는 없다.
- 로직 변경은 보류한다. 이번 구간의 주된 보강은 성능 추적 케이스 누적이며, `stable_token_ratio`가 높은 단일 관측 후보를 곧바로 final로 올리는 정책은 과확정 위험이 있어 다음 로그 비교 뒤 판단한다.

반영:

- 성능 추적 테스트의 `final_quality`, `finalization`, `runtime_metrics` 케이스를 보강했다.
- `finalization` tracking에는 stage 품질 차단, short/no-end 관측 후보, age final, 단일 관측 교체 보류 케이스를 추가했다.
- 순수 비중국어/라틴 단독 후보는 중국어 성능 추적 케이스에서 제거했다. 이후 성능 추적은 중국어 후보가 확정되지 않은 문장 추출 사례에 집중한다.
- runtime aggregate에는 `finalized_per_stage_start`, `stage_replaced_unconfirmed_per_stage_start`, `finalization_rate_per_1000`, `stage_candidate_quality_*`, `translation_skip`을 비교할 수 있도록 이번 30분 스냅샷을 추가했다.
- 다음 개선 판단은 `stage_replaced_unconfirmed_per_stage_start`가 낮아지는지와 `final_quality_no_end_marker`가 과도하게 늘지 않는지를 함께 본다.

## 배포 순서와 실패 대응

점진적 적용 순서:

1. 경계 모듈 분리 정리 및 상태/로깅 정합화
2. 기존 슬라이딩 윈도우 테스트를 새 인터페이스 기준으로 정합화
3. 설정 스키마/기본값 정합
4. 다국어 기본 백엔드의 CUDA/float16 로딩과 Fail-Fast 기준 안정화
5. 로그 지표 수집 추가 및 통제군 대비 비교
6. 동일 환경/동일 로그 조건에서 결과 비교
7. 전환 후 1~2주 관측 기간 동안 안정성 회귀 모니터링

릴리스 기준:

| 단계 | 기준 |
| --- | --- |
| RC 1 | `final-only` 출력/번역 경로와 실패 대응 계획이 동작한다. |
| RC 2 | `sat` 운영 지표가 이전 로그 대비 중복/누락을 줄이고, 다국어 경계 회귀가 허용 범위 안에 있다. |
| GA 후보 | KO/EN/ZH 지표 개선이 반복 실험에서 확인되고 장애율이 기준 안에 있다. |

실패 대응:

- 백엔드 초기화/로딩/분절 실패는 조건부 CPU fallback 또는 legacy regex fallback 대신 즉시 실패한다.
- 모델 다운로드가 필요한 경로는 다운로드 가능성을 사전에 로그로 출력한다.
- 다운로드/로딩 단계가 끝나기 전에는 오디오 입력 장치를 열지 않고 전사/번역 job을 시작하지 않는다.
- 임계 지표가 악화되면 자동 rollback보다 운영자 개입과 원인 로그 수집을 우선한다.
- 배포 직후 24시간은 `pending`, `confirmed`, `stage_replaced_unconfirmed`, `raw_without_final`, `translation_quality`를 짧은 주기로 확인한다.
- 회귀가 누적되면 원본 배포 채널로 되돌리고 원인 로그를 묶어 1페이지 인시던트 노트를 작성한다.
