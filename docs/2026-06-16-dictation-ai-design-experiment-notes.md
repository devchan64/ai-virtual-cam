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
| 중국어 no-space 구간이 내부 중간부터 다시 시작됨 | 내부 prefix overlap을 제거해 접합하고, 서로 다른 continuation에는 인위적 공백을 넣지 않는다. |
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
- 중국어/CJK처럼 공백 기반 단어 경계가 약한 언어에서 pending 접합이 흔들린다.
- 확정되지 않은 문장을 번역하면 번역 중복과 premature translation이 발생한다.

따라서 raw STT 출력은 사용자 final 문장이나 번역 입력으로 직접 사용하지 않는다. 받아쓰기 AI의 핵심은 raw STT 품질, 문장 경계, revision lifecycle, 번역 품질을 분리해 계측하고 각각 개선하는 것이다.

## 실시간 처리 파이프라인

이 섹션의 흐름을 받아쓰기 AI 신규 기준 파이프라인으로 둔다. 단, 모든 단계가 현재 코드에 같은 수준으로 final 결정에 반영되어 있다는 뜻은 아니다. 현재 운영 코드는 sliding window, 언어별 STT, pending/new 접합, stable token 지표, SaT/SBD 후보, staged/final 생명주기, final-only 번역을 갖고 있고, Semantic Boundary Detection의 일부 feature는 후속 구현으로 남긴다.

```text
오디오 입력
  ↓
슬라이딩 윈도우 생성
  ↓
언어별 STT backend 실행
  - faster-whisper / Qwen3-ASR 등
  - raw STT window 결과 생성
  ↓
정규화 및 접합
  - 이전 pending tail과 새 raw의 overlap 비교
  - CJK no-space 구간은 문자 n-gram/prefix overlap 비교
  - 최근 final echo 억제
  ↓
Stable Token Detection
  - 여러 ASR window에서 유지되는 토큰/문자 구간 확인
  - 영어/한국어는 토큰 similarity와 문자 similarity를 함께 사용
  - CJK는 문자 n-gram, prefix/suffix overlap, 내부 prefix overlap 우선
  ↓
Semantic Boundary Detection
  - SaT/SBD 기반 문장 경계 후보
  - streaming punctuation/end probability
  - right context에서 새 문장 시작 징후 확인
  - VAD/silence는 보조 feature
  ↓
세그먼트 상태관리
  - pending / staged / final / suppressed / revised
  ↓
실시간 번역
  - final 세그먼트만 번역 큐에 투입
```

이 흐름에서는 "음성이 멈췄는가"보다 "토큰이 안정되었는가"와 "의미 경계가 확인되었는가"가 우선이다.

### 적용 상태

| 단계 | 현재 상태 | 적용 판단 |
| --- | --- | --- |
| 오디오 입력/슬라이딩 윈도우 | 구현됨 | `windowSeconds`, `stepSeconds` 기준으로 최근 오디오 window를 STT 입력으로 사용한다. |
| 언어별 STT backend | 구현됨 | 영어/한국어는 `faster-whisper`, 중국어는 `qwen3-asr-transformers`를 운영 기본값으로 둔다. |
| raw STT window 결과 | 구현됨 | 원문창은 문장 경계/확정 전 raw STT window만 표시한다. |
| 정규화 및 접합 | 구현 중 | pending tail과 새 raw의 overlap, CJK no-space 내부 prefix overlap, 최근 final echo 억제를 적용한다. |
| Stable Token Detection | 지표 구현됨 | 이전/현재 raw window의 안정 prefix, 불안정 tail, 안정 token ratio를 별도 계층에서 계산한다. final 승격 정책 반영은 후속 튜닝으로 둔다. |
| Semantic Boundary Detection | 부분 구현 | SaT/SBD 후보 생성과 pending 보수 처리, stable confidence 보정은 구현되어 있다. streaming punctuation/end probability, right-context score, VAD 보조 feature는 후속 단계다. |
| 세그먼트 상태관리 | 구현됨 | `pending`, `staged`, `final`, `suppressed`, `revised` 의미를 분리하고 final은 append-only로 유지한다. |
| 실시간 번역 | 구현됨 | 번역 큐에는 품질 게이트를 통과한 final transcript만 넣는다. staged/partial 번역은 운영 경로에서 제거한다. |

### 구현 우선순위

1. Stable Token Detection 지표를 운영 로그에서 1~2일 누적해 `finalization_rate_per_1000`, `raw_without_final`, `stage_replaced_unconfirmed`와 상관관계를 본다.
2. 안정 prefix가 높고 불안정 tail이 짧은 후보만 boundary confidence를 높이는 방향으로 튜닝한다.
3. CJK는 공백 기반 token보다 문자 n-gram, prefix/suffix overlap, 내부 prefix overlap을 우선한다.
4. Semantic Boundary Detection은 SaT 결과에 right-context와 punctuation/end score를 더하는 방식으로 확장한다.
5. VAD/silence는 final trigger가 아니라 boundary confidence 보조 feature로만 넣는다.
6. 각 단계의 출력과 지표를 로그에 분리해 STT 품질, stable detection 품질, boundary 품질, lifecycle 품질, 번역 품질을 따로 비교한다.

## 문헌 구현 정렬

문헌과 구현 판단은 [받아쓰기 AI 참조 레퍼런스 모음](2026-06-16-dictation-ai-reference-index.md)에 둔 레퍼런스를 기준으로 다음처럼 정렬한다.

| 문헌/개념 | 구현 반영 |
| --- | --- |
| Whisper streaming/local agreement | raw STT window를 final로 직접 쓰지 않고, stable token/revision lifecycle을 통해 final을 확정한다. |
| Streaming ASR Stability | `UPWR`, `UPSR`, revision, replacement, stability 지표로 partial 흔들림을 관찰한다. |
| Simul-Whisper / latency-stability tradeoff | `stt_rtf`, `total_rtf`, finalization latency, pending overrun을 함께 본다. |
| SaT/wtpsplit | 다국어 SBD 후보 생성기로 사용하되 final 결정자는 아니라고 명시한다. |
| Streaming punctuation | boundary score 보조 신호로만 본다. free-form rewrite는 alignment 위험 때문에 기본 경로에서 제외한다. |
| Speech translation segmentation | VAD/pause threshold는 translation trigger의 주 신호가 아니라 SBD confidence 보조 feature로 둔다. |
| Chinese ASR/domain candidates | Qwen3-ASR, Dolphin-CN-Dialect, WeNet은 STT backend 후보로 추적하고, FunASR는 과거 기준선으로 남긴다. |

## 흐름별 적합 AI 모델

이 섹션은 받아쓰기 AI 파이프라인의 각 흐름에 어떤 AI 모델이 적합한지 정리한다. 운영 기본값은 실시간성, 로컬 실행 가능성, Fail-Fast 정책, 언어별 품질을 함께 만족해야 한다. 후보 모델은 바로 기본값으로 편입하지 않고, 동일 입력 replay와 추적 지표로 검증한 뒤 승격한다.

| 흐름 | 기본/우선 모델 | 후보 모델 | 판단 |
| --- | --- | --- | --- |
| 영어/한국어 STT | `faster-whisper` + `large-v3` | Whisper streaming 계열, WhisperKit | 현재 한글/영어 운영 경로에서 사용 중이며 준수한 성능으로 판단한다. 다만 Whisper는 원래 streaming 모델이 아니므로 local agreement와 확정 생명주기가 필수다. |
| 중국어 STT | `qwen3-asr-transformers` + `Qwen3-ASR-0.6B` | `Qwen3-ASR-1.7B`, Dolphin-CN-Dialect, WeNet | 현재 중국어 운영 경로에서 사용 중이며 준수한 성능으로 판단한다. 중국어 의미 보존과 문장 구조 품질을 우선한다. |
| STT 기준선 | `faster-whisper` | Whisper large-v3 | 중국어에서는 품질 후보보다 baseline에 가깝다. 영어/한국어와 중국어의 판단을 분리한다. |
| 문장 경계 처리 | SaT / `wtpsplit` | punctuation restoration 모델, PySBD 비교군 | regex는 운영 경로에서 폐기한다. SBD 모델은 final 결정자가 아니라 staged 후보 생성기다. |
| Streaming punctuation | bounded lookahead punctuation 모델 | ELECTRA/BERT 기반 punctuation restoration | 문장부호와 end probability를 boundary score 보조 신호로 사용한다. 원문 rewrite를 수행하는 LLM은 기본 경로로 쓰지 않는다. |
| Stable token detection | 모델보다 결정론적 비교 계층 | token similarity, char n-gram, prefix/suffix overlap | 여러 STT window에서 유지되는 구간을 찾는 계층이다. 언어별 텍스트 비교 정책이 중요하며 별도 생성 모델을 두지 않는다. |
| 세그먼트 final 결정 | revision lifecycle | local agreement, echo suppression, staged confirmation | final 여부는 단일 모델 출력이 아니라 재관측 횟수, 중복 억제, right context, SBD 후보를 결합해 결정한다. |
| 번역 | `nllb-transformers` + `facebook/nllb-200-distilled-600M` | NLLB 1.3B/3.3B, M2M100, SeamlessM4T, TowerInstruct, X-ALMA | 기본값은 실시간성을 우선한다. 중한 품질 개선은 모델/백엔드 비교와 회귀 샘플 확장으로 진행한다. |
| 중국어 ASR 오류 보정 | 기본 경로 없음 | pinyin-aware LLM 보정, ASR-EC 계열 | 운영 기본 경로에는 넣지 않는다. raw STT 오류와 후처리 오류를 먼저 분리 계측한 뒤 후보로 검토한다. |
| 발화 종료 보조 신호 | 기본 경로 없음 | VAP, TurnGPT | 프레젠테이션 긴 발화에서는 주 결정 기준으로 쓰지 않는다. 무음/turn score는 boundary confidence 보조 feature로만 둔다. |

### STT 모델

영어/한국어 STT는 현재 `faster-whisper`와 Whisper `large-v3`를 사용한다. 운영 관측 기준 준수한 성능으로 판단하고 있으며, 품질과 로컬 실행 안정성이 검증되어 있고 CUDA/float16 경로에서 실시간 처리량을 맞추기 쉽다. 단 Whisper는 원래 저지연 streaming 모델이 아니므로 raw STT window를 바로 final로 쓰면 중복, revision, tail echo가 발생한다. 따라서 Whisper-Streaming 계열의 local agreement 아이디어를 후처리 계층에서 구현한다.

중국어 STT는 현재 `Qwen3-ASR-0.6B`를 사용한다. 운영 관측 기준 준수한 성능으로 판단하고 있으며, 중국어는 공백 기반 단어 경계가 약하고 동음 후보가 많아 빠른 모델보다 의미 보존과 문장 구조 안정성이 더 중요할 수 있다. `Qwen3-ASR-1.7B`는 품질 비교 후보지만 VRAM과 지연 비용을 별도로 검증해야 한다.

FunASR 계열은 과거 실험에서 처리 속도는 빨랐지만 의미 보존, stage churn, 확정률에서 불리했다. 따라서 운영 후보가 아니라 과거 기준선 기록으로 남긴다.

### 문장 경계 모델

문장 경계 처리에는 SaT/wtpsplit을 기본 후보로 둔다. SaT는 문장부호가 없거나 noisy한 텍스트에서도 다국어 문장 분절을 목표로 하므로, 받아쓰기 AI의 한국어/영어/중국어 공통 경계 후보 생성에 적합하다.

중요한 점은 SBD 모델이 final을 직접 결정하지 않는다는 것이다. SBD는 completed/pending 후보를 제안하고, final 승격은 staged confirmation과 revision lifecycle이 담당한다. 이 구조가 없으면 SBD가 맞는 경계를 잡아도 STT 후보 자체가 뒤 window에서 바뀌며 중복 final이나 premature translation을 만들 수 있다.

Streaming punctuation 모델은 SaT와 별도의 보조 계층이다. punctuation end probability는 boundary score에 도움을 주지만, free-form 문장 재작성은 alignment를 깨뜨릴 수 있으므로 기본 경로에서 제외한다.

### 번역 모델

실시간 번역 기본 후보는 `nllb-transformers`와 `facebook/nllb-200-distilled-600M`이다. 작고 빠르며 한국어/영어/중국어 대상 번역을 하나의 경로로 다룰 수 있다. 대신 중국어 고유명사, 서비스명, 구어체 표현에서 품질 한계가 관측되었으므로 `translation_quality` 샘플로 별도 추적한다.

NLLB 1.3B/3.3B는 같은 계열에서 품질을 올리는 가장 낮은 위험의 비교군이다. M2M100은 영어 중심 우회가 아닌 many-to-many 번역 비교군이며, SeamlessM4T는 speech/text translation을 함께 다룰 수 있지만 구현과 메모리 비용이 크다. TowerInstruct와 X-ALMA 같은 LLM 번역 모델은 고품질 후보지만 지연과 VRAM 비용이 커서 실시간 기본값과 분리한다.

번역은 final transcript만 입력으로 받는다. STT 모델이나 SBD 모델이 생성한 staged/partial 후보를 번역하면 원문 revision이 번역 중복과 오역으로 전파된다.

### 오류 보정 모델

중국어 ASR error correction, pinyin-aware LLM 보정, contextual ASR 모델은 후속 후보로만 둔다. 현재 운영 우선순위는 오류 보정 모델을 덧붙이는 것이 아니라 raw STT 품질, pending 접합, staged revision, final 확정의 실패 원인을 분리 계측하는 것이다.

오류 보정 모델을 도입하려면 다음 조건이 필요하다.

- raw STT 오류와 후처리 오류가 로그 지표에서 분리되어야 한다.
- 보정 모델이 원문 의미를 rewrite하거나 삭제하지 않는지 평가해야 한다.
- finalization latency와 VRAM 비용이 실시간 기준을 넘지 않아야 한다.
- 언어별 ad-hoc 정규식 보정으로 회귀를 숨기지 않아야 한다.

### 발화 종료 모델

VAP, TurnGPT 같은 turn-taking 모델은 회의 대화의 turn end 예측에는 유용할 수 있다. 하지만 프레젠테이션 긴 발화에서는 발화자가 문장을 멈추지 않고 이어가거나, 짧은 pause가 의미 경계와 맞지 않을 수 있다.

따라서 발화 종료 모델은 translation trigger의 직접 결정자가 아니라 Semantic Boundary Detection의 confidence를 보정하는 보조 feature 후보로 둔다. 운영 기본 경로는 텍스트 안정성, SBD, punctuation, right context, staged confirmation을 우선한다.

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
| `staged_age` | 후보가 staged 상태로 남은 chunk 수 | 장기 보류 진단 신호다. 단독 확정/폐기 기준으로 쓰지 않는다. |
| `staged_forced` | forced 후보 여부 | forced 후보도 별도 재확인과 품질 게이트를 통과해야 한다. |
| `replacement_decision` | staged 교체 판단 사유 | `unconfirmed`, `open_korean_clause`, `partial_revision`, `partial_preserve`, `duplicate_or_suffix`, `aged` 같은 이유를 로그로 남긴다. |
| `lifecycle_metrics` | 세션 누적 생명주기 카운터 | 장기 품질 추세와 회귀 판단에 사용한다. |
| `chunk_metrics` | 현재 chunk 생명주기 카운터 | 특정 chunk에서 stage/revision/final 이벤트가 폭증하는지 본다. |

출력 계층 용어는 다음처럼 정리한다.

| 계층 | 의미 | 정책 |
| --- | --- | --- |
| `hypothesis_text` | 가장 최근 STT window 디코딩 결과 | 내부 비교용이다. 사용자 final로 직접 쓰지 않는다. |
| `pending_text` | 재작성 가능한 후보 구간 | 경계/접합/재확인을 기다린다. |
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

### VAD와 무음 구간의 역할

VAD는 음성/비음성 구간을 찾는 데 유용하지만 프레젠테이션 긴 발화에서 번역 단위나 문장 경계를 직접 결정하는 주 신호로 쓰지 않는다.

근거:

- pause가 sentence boundary와 반드시 일치하지 않는다.
- lecture/presentation 같은 long speech에서는 명확한 silence가 드물다.
- 짧은 pause로 연결된 문장은 VAD가 안정적으로 탐지하기 어렵다.
- sentence end detection은 domain, punctuation, lexical cue, right context를 함께 봐야 한다.

따라서 VAD/무음 길이/발화 종료 예측은 Semantic Boundary Detection confidence를 보정하는 보조 feature로만 사용한다.

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
- 시작값: `windowSeconds=12.0`, `stepSeconds=1.0`, `sentenceFinalizeAge=3`
- 문장이 여전히 흔들리면 `windowSeconds`를 16, 20, 24, 최대 30초까지 단계적으로 비교한다.

중국어는 현재 Qwen 경로에서 준수한 성능으로 판단한다. 공백 기반 단어 경계가 약하고 동음 후보가 많아 긴 문맥이 raw STT 안정성에 도움이 될 수 있다. 하지만 긴 window는 final transcript 갱신 지연과 긴 문장 확정을 증가시킨다. 따라서 STT context와 final commit unit을 분리해서 본다.

### 폐기/보류 후보

- FunASR STT 계열은 처리 속도는 빠르지만 의미 보존, stage churn, 확정률에서 불리해 운영 후보에서 제외한다.
- Qwen3-ASR vLLM streaming은 vLLM 의존성이 `mediapipe`/`protobuf`와 충돌해 공유 `.venv`에서는 지원하지 않는다. 별도 격리 런타임 설계가 필요하다.
- Dolphin-CN-Dialect와 WeNet은 후속 streaming 후보로 추적한다.

### 중국어 STT 후보 상세

중국어 운영 우선값은 `qwen3-asr-transformers`와 `qwen3-asr-0.6b`다. `qwen3-asr-1.7b`는 품질 상향 비교 후보이고, `qwen3-asr-vllm-streaming`, Dolphin-CN-Dialect, WeNet은 후속 streaming 또는 방언/구조 비교 후보다. FunASR Paraformer/SenseVoice는 처리 속도는 빨랐지만 의미 보존, stage churn, 확정률에서 불리해 운영 후보에서 제외하고 과거 기준선으로만 남긴다. Whisper/faster-whisper 중국어 경로는 baseline으로만 둔다.

Qwen3-ASR vLLM streaming, Dolphin-CN-Dialect, WeNet의 세부 판단은 [받아쓰기 AI 중국어 STT 후보 세부검증 리포트](2026-06-16-dictation-ai-chinese-stt-candidate-validation.md)에 둔다. 후속 streaming backend가 필요해지면 partial/final 이벤트, session id, stream reset, backpressure, model-ready/download-ready 상태를 명시 계약으로 추가한다.

## 런타임 의존성과 모델 캐시 제약

받아쓰기 AI는 CUDA/float16 중심의 Fail-Fast 정책을 따른다. 모델과 의존성은 실행 중 암묵 변경하지 않는다.

| 항목 | 현재 판단 |
| --- | --- |
| `faster-whisper`, SaT, NLLB/M2M100 | Serve 런타임에서 로컬 캐시만 사용한다. 캐시가 없거나 부분 다운로드 상태면 다운로드하지 않고 실패한다. |
| 모델 다운로드 | `scripts/setup/download-dictation-ai-models.py`와 config GUI 모델 다운로드 매니저 경로로 제한한다. `serve`는 다운로드를 수행하지 않는다. |
| `qwen-asr` | `qwen-asr==0.0.6`은 `transformers==4.57.6` 요구와 함께 고정한다. |
| `gradio` | qwen-asr 의존성 범위가 넓어 resolver 역추적을 만들 수 있으므로 dry-run에서 확인한 호환 버전을 고정한다. |
| `wtpsplit` | Hugging Face Hub 메타데이터 제약이 Qwen3-ASR/transformers와 충돌할 수 있어 setup/env sync에서 `--no-deps` 설치를 전제로 한다. 필요한 런타임 의존성은 별도 명시한다. |
| vLLM | 공유 `.venv`에 넣지 않는다. 필요 시 별도 프로세스/격리 런타임으로 설계한다. |
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

## 중국어 번역 백엔드 확장 정책

중국어 STT가 안정화된 뒤 관측한 로그에서는 STT보다 `zh->ko` 번역 품질이 병목으로 나타났다. 특히 지명, 서비스명, 구어체 표현에서 NLLB 600M의 오역이 반복되었다.

이 문제는 언어별 문자열 휴리스틱보다 번역 backend/model 선택지를 계약 데이터로 관리하고, 동일 테스트 케이스에서 모델별 품질 지표를 비교하는 방식으로 접근한다.

후보:

| 백엔드 | 모델 | 판단 |
| --- | --- | --- |
| `nllb-transformers` | `facebook/nllb-200-distilled-600M` | 빠르고 현재 기준선이다. |
| `nllb-transformers` | `facebook/nllb-200-distilled-1.3B`, `facebook/nllb-200-1.3B`, `facebook/nllb-200-3.3B` | 같은 백엔드에서 모델 크기만 바꾸는 낮은 위험의 품질 개선 후보다. |
| `m2m100-transformers` | `facebook/m2m100_1.2B` | 영어 중심 우회가 아닌 many-to-many 번역 비교군이다. |
| `seamless-m4t-v2` | `facebook/seamless-m4t-v2-large` | 구현/메모리 비용이 커서 후속 후보로 둔다. |
| LLM 번역 | TowerInstruct, X-ALMA Group6 | 지연/VRAM 비용이 커서 고품질 실험군으로 분리한다. |

## 운영 파라미터 기준

| 항목 | 영어/한국어 시작값 | 중국어 시작값 | 판단 기준 |
| --- | ---: | ---: | --- |
| `windowSeconds` | 7.0 | 12.0 | raw STT 안정성과 final 지연의 균형 |
| `stepSeconds` | 1.0 | 1.0 | 화면 갱신과 반복 처리량의 균형 |
| `sentenceFinalizeAge` | 3 | 3 | staged 후보 재관측 횟수 |
| `beamSize` | 3 | 3 | 정확도/지연 비교 시작점 |
| `temperature` | 0.0 | 0.0 | 재현성과 안정성 |
| `maxNewTokens` | 192 | 192 | 긴 문장 절단 방지 |
| `translationBeamSize` | 1 | 1 | 실시간 번역 시작점 |
| `translationMaxNewTokens` | 128 | 128 | 번역 지연 제어 |

성능 로그의 `stt_step_load` 또는 `total_step_load`가 1.0을 넘거나 `input_queue_drops`가 1 이상이면 실시간 처리량을 초과한 상태다.

## 품질 지표

받아쓰기 AI 실시간 전사/번역 경로의 품질은 unittest 성공/실패만으로 판단하지 않는다. 테스트는 누적 운영 로그에서 관측한 실패 사례를 실행해 현재 로직의 성능 추이를 출력하는 추적 하네스다.

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
| `coalesce` | 중국어 multi-completed 후보를 하나의 관찰 단위로 병합하는지 | 100% |
| `duplicate_suppression` | 이미 확정/관측된 후보가 중복 출력되지 않도록 억제되는지 | 100% |
| `runtime_metrics` | 런타임 누적 지표가 안정성 요약으로 올바르게 집계되는지 | 100% |
| `translation_quality` | 번역 출력의 고유명사/도메인 용어/환각 회귀를 추적하는지 | 80% 이상 |

향후 정답 전사 코퍼스가 준비되면 `WER`, 한국어/중국어 `CER`, deletion rate, duplicate insertion rate, finalization latency, revokes per second를 추가한다.

## KPI 리포트 프레임

운영 판단은 "지표가 좋아졌는가"가 아니라 "중복 감소, 지연 제어, 번역 안정성이 달성되었는지"를 본다.

3개 축:

1. 안정성 축: 리비전 빈도와 규모 감소 (`UPWR`, `UPSR`, `replaced ratio`, `rollback_rate`)
2. 경계 축: 문장 경계 추정 품질 (`pending_chars`, `forced_by`, `boundary_latency`, `end_marks_stable`)
3. 지연/번역 축: 실시간성 (`stt_rtf`, `total_rtf`), 번역 부하 (`confirmed_only_delta`, `translation_redundant_ratio`)

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

필수 로그 입력:

| 이벤트 | 필수 필드 |
| --- | --- |
| split event | `chunk`, `completed`, `final`, `pending_text`, `forced_by`, `pending_overrun`, `boundary_backend`, `pending_chars`, `pending_chunks`, `pending_chars_per_chunk` |
| commit event | `step`, `window`, `stt_elapsed`, `stt_rtf`, `translation_elapsed`, `total_elapsed`, `total_rtf`, `beam`, `max_tokens`, `text_chars` |
| transcript fragment | `delta_text`, `state`, `revision_id` |

판정 규칙:

| 판정 | 조건 |
| --- | --- |
| Go | `UPWR`, `UPSR`가 baseline 대비 각각 15% 이상 개선되고, `pending_chars_p90`이 10% 이상 개선되며, `confirmed_only_ratio >= 0.9`이고 `p95(total_rtf)`가 목표값 안에 있다. |
| No-Go | `p95(total_rtf)`가 baseline 대비 20% 이상 악화되거나, `UPWR`/`UPSR`이 15% 이상 악화되거나, `DupAmplification > 1.3`이 지속된다. |
| Ramp | Go/No-Go 임계에는 못 미치지만 `pending_chars`와 `forced_by`가 개선되고 `rtf` 악화가 5% 이하인 경우다. |

KPI 리포트 산출물은 `docs/reports/dictation-ai-kpi-{{date}}.md` 형태를 권장한다. 최소 항목은 실행 식별자, 실험군, 조건, 언어별 KPI 표, 회귀 Top 5 로그 예시, 다음 액션 체크리스트다.

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

이 케이스는 SBD 구두점 결정 문제가 아니라 pending/new 접합 단계에서 내부 재시작을 새 continuation으로 오인한 문제다.

반영 판단:

- `pending_new_text_combined()`는 CJK no-space 텍스트에 한해 긴 내부 prefix overlap이 확인되면 `pending prefix + new_text`로 병합한다.
- 서로 다른 중국어 continuation은 인위적 공백을 넣지 않고 그대로 이어붙인다.
- STT 원문창은 staged 후보가 아니라 raw STT window만 표시해야 한다.

### 2026-06-16 원문창 의미 재정의

전사 품질을 볼 때는 세 창/로그의 의미를 구분한다.

- STT 원문창: raw STT window 결과
- 전사 창: revision lifecycle과 final 확정을 거친 사용자 출력
- stdout 진단 로그: `stable_tail`, `delta_tail`, `pending_tail`, `staged_tail` 같은 내부 상태

원문창이 staged 후보를 표시하던 시기의 로그 해석은 raw STT 품질 판단 근거로 쓰지 않는다.

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

구현 우선순위:

1. 문자열 LCP와 재확인 카운트 기반 stable 확정.
2. 문장 경계 detector 분리와 `sat` backend 운영 정합화.
3. `UPWR`, `UPSR`, `forced_by` 지표 수집.
4. 안정성 기준 통과 후 replacements trimming 계층 검토.
5. Two-Pass/causal fine-tune 같은 모델 계층 변경 검토.

실패 대응:

- 백엔드 초기화/로딩/분절 실패는 조건부 CPU fallback 또는 legacy regex fallback 대신 즉시 실패한다.
- 모델 다운로드가 필요한 경로는 다운로드 가능성을 사전에 로그로 출력한다.
- 다운로드/로딩 단계가 끝나기 전에는 오디오 입력 장치를 열지 않고 전사/번역 job을 시작하지 않는다.
- 임계 지표가 악화되면 자동 rollback보다 운영자 개입과 원인 로그 수집을 우선한다.
- 배포 직후 24시간은 `pending`, `confirmed`, `stage_replaced_unconfirmed`, `raw_without_final`, `translation_quality`를 짧은 주기로 확인한다.
- 회귀가 누적되면 원본 배포 채널로 되돌리고 원인 로그를 묶어 1페이지 인시던트 노트를 작성한다.

## 현재 미해결 과제

- 동일 오디오 replay 기반 통제 실험이 부족하다.
- 정답 전사 코퍼스가 없어 CER/WER 기반 정량 평가는 제한적이다.
- 중국어 STT의 장문 안정성과 final 갱신 지연 사이의 최적점을 더 좁혀야 한다.
- 중한 번역은 STT/확정 품질과 분리된 별도 평가셋으로 비교해야 한다.
- Qwen3-ASR vLLM streaming은 별도 격리 런타임 설계 없이는 공유 `.venv`에 넣지 않는다.
- LLM 번역 후보는 품질은 기대되지만 VRAM/지연 비용 때문에 실시간 기본값과 분리한다.
