# 받아쓰기 AI 실험일지

## 문서 상태

이 문서는 폐기된 원본 문서 `docs/2026-06-13-dictation-ai-feature-design.md`의 Git 커밋 기록을 기준으로 재구성한 실험일지다. 이 파일은 이전에 다른 이름의 설계 문서로 존재했으므로 rename 이전 문서의 변경 이력까지 추적 대상에 포함한다. 또한 받아쓰기 AI의 실험 판단이 README, 논문 초안, 발표용 세그먼트 레퍼런스 문서에 분산되어 기록된 경우 해당 문서 업데이트 히스토리도 보조 근거로 포함한다. 실시간 파이프라인 기준은 [받아쓰기 AI 실시간 처리 파이프라인 기준](2026-06-16-dictation-ai-realtime-pipeline.md), 설정 계약과 기본값은 [받아쓰기 AI 계약과 기본값](2026-06-16-dictation-ai-contract-defaults.md)을 따른다. Qwen3-ASR vLLM streaming, Dolphin-CN-Dialect, WeNet의 세부검증 판단은 [받아쓰기 AI 중국어 STT 후보 세부검증 리포트](2026-06-16-dictation-ai-chinese-stt-candidate-validation.md)에 둔다.

작성 기준:

- 기준 파일: `docs/2026-06-13-dictation-ai-feature-design.md` Git 이력
- 최초 추적 파일: `docs/2026-06-13-whisper-sliding-window-design.md`
- 주 추적 명령: `git log --follow --date=short --name-status -- docs/2026-06-13-dictation-ai-feature-design.md`
- 보조 추적 명령: `git log --date=short --name-status -- README.md docs/2026-06-15-presentation-dictation-segmentation-references.md docs/paper/ko-revision-aware-realtime-stt.md`
- 범위: 2026-06-12부터 2026-06-16까지 받아쓰기 AI 관련 문서와 rename 이전 설계 문서의 변경 이력

추적 원칙:

- 실험일지는 현재 파일명만 기준으로 보지 않는다.
- 최초 실험 문서인 `2026-06-13-whisper-sliding-window-design.md` 생성 시점부터 모든 rename 이후 변경을 하나의 실험 기록으로 본다.
- `README.md`, `docs/paper/ko-revision-aware-realtime-stt.md`, `2026-06-15-presentation-dictation-segmentation-references.md`에만 남은 받아쓰기 AI 실험 판단도 누락 없이 반영한다.
- `whisper`, `오디오 AI`, `받아쓰기 AI` 명칭 변경은 기능 범위와 사용자 노출명 정리 과정으로 해석하고, 별도 실험 계열로 분리하지 않는다.
- 커밋 제목이 `docs`, `feat`, `fix`, `refactor`, `test` 중 무엇이든 해당 문서에 실험 관측, 기준, 모델 선택, 기본값, 검증 결과를 바꾼 경우 실험일지 추적 대상이다.

## 문서 계보

`git log --follow --name-status` 기준 문서 이름은 다음 흐름으로 변경되었다.

| 시점 | 커밋 | 변경 | 의미 |
| --- | --- | --- | --- |
| 2026-06-13 | `cc3fbe0` | `docs/2026-06-13-whisper-sliding-window-design.md` 신규 작성 | Whisper sliding window와 문장 확정 문제를 문헌 기반 설계로 정리하기 시작했다. |
| 2026-06-13 | `d6072e7` | `whisper-sliding-window-design` → `whisper-feature-design` | 슬라이딩 윈도우 설계에서 Whisper 기능 설계 문서로 범위를 넓혔다. |
| 2026-06-14 | `9efb27b` | `whisper-feature-design` → `audio-ai-feature-design` | Whisper라는 기술명보다 오디오 AI 기능 도메인으로 문서명을 확장했다. |
| 2026-06-15 | `b3f1b89` | `audio-ai-feature-design` → `dictation-ai-feature-design` | 사용자 기능명을 받아쓰기 AI로 정리하고, STT/문장 추적/번역 기능을 이 도메인 아래로 묶었다. |
| 2026-06-16 | `9f1d051` | `dictation-ai-feature-design` 폐기 예정 원본 기록으로 분류 | 새 설계/실험 노트와 계약 문서가 기준 문서 역할을 맡도록 문서 체계를 분리했다. |

## 요약

받아쓰기 AI 실험은 Whisper 슬라이딩 윈도우 후처리에서 시작해 다국어 STT, 문장 경계 처리, 중국어 STT 품질, 번역 품질, 설정 계약 정리로 확장되었다.

핵심 결론:

- 영어/한국어 STT는 `faster-whisper + large-v3`가 현재 준수한 성능으로 판단된다.
- 중국어 STT는 `qwen3-asr-transformers + qwen3-asr-0.6b`가 현재 준수한 성능으로 판단된다.
- 중국어에서 `faster-whisper`는 품질 후보가 아니라 baseline이다.
- FunASR 계열은 처리 속도는 빠르지만 의미 보존, stage churn, 확정률에서 불리해 운영 후보에서 제외했다.
- 문장 경계는 regex가 아니라 SaT/wtpsplit 기반 SBD를 후보 생성기로 사용한다.
- final 확정은 단일 모델 출력이 아니라 staged confirmation, `sentenceFinalizeAge`, 중복 억제, revision lifecycle로 결정한다.
- 번역은 final transcript만 대상으로 한다.

모델 선정 기준:

| 흐름 | 선정 모델 | 탈락/보류 모델 | 선정 이유 |
| --- | --- | --- | --- |
| 영어/한국어 STT | `faster-whisper + large-v3` | Whisper streaming 계열, WhisperKit | CUDA/float16 로컬 실행에서 실시간 처리량과 품질이 준수했다. streaming 전용 모델이 아니므로 후처리 생명주기를 결합한다. |
| 중국어 STT | `qwen3-asr-transformers + qwen3-asr-0.6b` | `faster-whisper`, FunASR Paraformer | Qwen3-ASR가 FunASR보다 느리지만 의미 보존, 문장 구조, 확정률이 좋았다. `faster-whisper` 중국어는 baseline으로만 둔다. |
| 문장 경계 처리 | SaT/wtpsplit | regex, 언어별 ad-hoc 규칙 | 다국어 문장 경계 후보 생성에 적합하고, 운영 정책상 regex 경로를 폐기하기로 했다. |
| 번역 | `nllb-transformers + facebook/nllb-200-distilled-600M` | Whisper translate, NLLB 1.3B/3.3B, M2M100, SeamlessM4T, LLM 번역 모델 | 현재 기본값은 실시간성을 우선한다. 더 큰 모델과 다른 backend는 품질 비교 후보로 남긴다. |

로직 변경 아이데이션 기준:

| 축 | 아이디어 방향 | 채택 기준 |
| --- | --- | --- |
| raw/final 분리 | raw STT window를 사용자 출력으로 쓰지 않고 staged/final 생명주기를 둔다. | 중복 출력, tail echo, partial revision이 사용자 결과로 새지 않아야 한다. |
| stable token | 같은 window에서 반복 유지되는 prefix/tail을 결정론적으로 비교한다. | 모델 출력을 다시 생성하지 않고 STT window 간 안정 구간을 찾아야 한다. |
| revision lifecycle | `pending`, `staged`, `final`, `suppressed`, `revised` 상태로 후보를 관리한다. | final은 append-only이고, 미확정 후보만 교체/수정 가능해야 한다. |
| CJK 접합 | 폐기 | 공백 없는 중국어의 문자 n-gram, prefix/suffix, 내부 prefix overlap 기반 접합 보정은 학술적 근거가 부족해 운영 요구사항에서 제외한다. |
| final-only 번역 | staged/partial 후보를 번역하지 않는다. | 원문 revision이 번역 중복과 premature translation으로 전파되지 않아야 한다. |

## 사전 이력: 2026-06-12 위스퍼 GUI, 번역, 성능 설정 준비

### 관련 커밋

| 커밋 | 제목 |
| --- | --- |
| `46fcf9e` | feat: config GUI 상태 저장 및 Whisper 설정 추가 |
| `2d8f751` | feat: 위스퍼 응답속도와 문서 개선 |
| `c48e390` | feat: 위스퍼 번역 창 분리 |
| `d3c9de3` | feat: 위스퍼 번역 모델 옵션 추가 |
| `a8d602d` | refactor: 설정 탭 분리와 위스퍼 번역 정책 정리 |
| `37b82cf` | refactor: 위스퍼 설정 UI와 모달 다국어 정리 |
| `524dd0e` | fix: NLLB 번역 설정과 위스퍼 전사 경로 분리 |
| `1138c31` | feat: 위스퍼 GUI 성능 설정과 측정 로그 추가 |
| `074f01c` | fix: 위스퍼 기본값과 반복 전사 필터 개선 |
| `dd2505f` | fix: 위스퍼 저장 설정 기본값과 번역 반복 억제 반영 |
| `7591cfe` | fix: 위스퍼 문장 확정과 창 상태 저장 개선 |
| `bbfc11e` | feat: 위스퍼 문장 경계와 출력 창 개선 |

### 실험 질문

- 받아쓰기 AI를 config GUI의 설정값으로 통제하고, Serve 실행은 저장된 설정만 따르게 만들 수 있는가?
- 전사 결과와 번역 결과를 같은 출력 흐름으로 다루면 반복 출력과 상태 복원이 꼬이는가?
- NLLB 번역을 사용할 때 Whisper의 `task=translate`와 외부 번역 경로를 섞으면 계약이 불명확해지는가?
- 실시간 품질 문제를 사용자 체감만으로 판단하지 않고 성능 로그로 관측할 수 있는가?

### 관측

이 시점의 기록은 `2026-06-13-whisper-sliding-window-design.md` 생성 전 README 중심 업데이트에 남아 있다. 따라서 원 설계 문서의 직접 rename 체인은 아니지만, 이후 받아쓰기 AI 실험의 전제 조건으로 보아야 한다.

확인된 흐름:

- config GUI에 Whisper 설정과 창 상태 저장이 추가되면서 받아쓰기 AI가 카메라/오디오 설정 GUI의 하위 기능으로 들어왔다.
- 전사 창과 번역 창을 분리하면서 raw STT, final transcript, translated output의 책임이 갈라지기 시작했다.
- NLLB 번역 설정은 Whisper 전사 경로와 분리되었고, Whisper 백엔드는 전사만 담당하는 방향으로 정리되었다.
- 응답속도와 측정 로그가 추가되면서 이후 `stt_rtf`, `total_rtf`, queue drop, finalization count를 기준으로 비교할 수 있는 기반이 생겼다.
- 반복 전사 필터와 저장 기본값 보정은 sliding window STT가 같은 구간을 반복 관측한다는 문제를 드러냈다.

### 반영 판단

- 받아쓰기 AI는 GUI 설정 계약을 먼저 정하고, Serve는 저장값을 그대로 실행하는 구조가 맞다.
- STT 원문, final transcript, 번역 결과는 출력 창과 내부 생명주기에서 분리해야 한다.
- 번역은 전사 backend의 부가 모드가 아니라 별도 backend 계약으로 다룬다.
- 2026-06-13 이후의 실험은 이 사전 이력을 바탕으로 문장 경계, revision lifecycle, final-only translation을 정교화한 흐름으로 본다.

### 모델 성능 비교와 선정

| 흐름 | 비교 모델 | 판단 |
| --- | --- | --- |
| STT | Whisper/faster-whisper | 초기 운영 경로로 채택했다. 실시간성은 이후 `stt_rtf`, `total_rtf` 로그로 관측하도록 했다. |
| 번역 | Whisper translate vs NLLB | Whisper translate는 영어 대상 내장 번역으로 제한하고, 한국어/중국어 대상 번역은 외부 번역 backend로 분리하는 쪽이 계약이 명확했다. |
| 번역 | NLLB | Whisper STT와 분리 가능한 번역 모델로 채택했다. 이후 품질 비교는 NLLB 크기 확장, M2M100, LLM 번역 후보로 이어진다. |

### 로직 변경 아이데이션

| 관측 | 아이디어 | 결과 |
| --- | --- | --- |
| 같은 음성 구간이 sliding window에 반복 포함됨 | raw STT를 바로 append하지 않고, 사용자 출력 전에 중복 억제 계층을 둔다. | 반복 전사 필터와 final-only 출력 생명주기 실험으로 이어졌다. |
| 전사와 번역이 같은 흐름에 섞이면 반복 번역이 발생함 | 전사 창, 번역 창, 원문창을 다른 의미의 출력으로 분리한다. | raw STT, final transcript, translated output을 별도 상태로 다루는 설계가 시작됐다. |
| Whisper `translate`와 외부 번역 backend가 섞이면 계약이 흐림 | STT는 `transcribe`, 번역은 별도 backend가 담당하게 한다. | 이후 NLLB/M2M100 같은 번역 모델 비교가 STT 품질 실험과 분리됐다. |
| GUI 설정과 Serve 실행 사이의 상태가 어긋날 수 있음 | GUI에서 저장한 설정을 Serve가 그대로 실행하고, 실행 중 자동 의미 전환을 막는다. | 설정 계약/기본값 문서화의 전제가 됐다. |

### 주요 기본값 변경

| 축 | 기본값/정책 변화 | 사유 |
| --- | --- | --- |
| 설정 저장 | Whisper 설정과 창 위치를 설정 파일에 저장 | Serve 실행 시 GUI에서 검증한 설정을 재사용하기 위해서다. |
| 출력 창 | 전사 창과 번역 창을 분리 | raw STT와 번역 결과가 서로 다른 생명주기를 갖기 때문이다. |
| 번역 task | 외부 번역 사용 시 Whisper는 `transcribe` 경로로 제한 | Whisper `translate`와 NLLB 번역을 섞으면 source/target 계약과 중복 번역 억제가 불명확해진다. |
| 번역 backend | NLLB 번역 설정을 Whisper STT 설정과 분리 | 전사 품질과 번역 품질을 독립적으로 실험하기 위해서다. |
| 반복 억제 | 반복 전사 필터와 저장 기본값을 보정 | sliding window가 같은 음성 구간을 반복 관측해 중복 출력이 발생했기 때문이다. |

## 2026-06-13: Whisper 슬라이딩 윈도우와 확정 생명주기 정립

### 관련 커밋

| 커밋 | 제목 |
| --- | --- |
| `cc3fbe0` | docs: Whisper 슬라이딩 윈도우 개정판 누락 항목 반영 |
| `abcdf27` | docs: 문헌 기반 설계 문서 누락 절차 복구 |
| `6c6243e` | fix: 위스퍼 문장 경계 리비전 개선 |
| `d6072e7` | test: 위스퍼 서비스 기준 테스트 추가 |
| `9faff69` | refactor: 위스퍼 전사 로직 분리 |
| `7f94664` | fix: 위스퍼 문장 교체 확정 기준 보정 |
| `6b958d4` | feat: setup 위스퍼 모델 사전 다운로드 추가 |
| `997350b` | fix: 위스퍼 문장 교체 판단 개선 |
| `e96ec13` | docs: 위스퍼 설계 문서 구현 정합성 갱신 |
| `f0199eb` | feat: 위스퍼 pending 진단 지표 추가 |
| `ff9a16a` | feat: 위스퍼 언어별 후처리 모델 선택 추가 |
| `32a651a` | docs: 위스퍼 모델 준비 정책 문서화 |
| `12cc028` | docs: 중국어 STT 교체 검토 문서화 |
| `17a4391` | feat: 중국어 STT 모델 교체 설정 추가 |

### 실험 질문

- Whisper raw STT window를 그대로 화면에 append하면 왜 중복/누락/revision 문제가 생기는가?
- final transcript와 hypothesis/pending/staged 상태를 어떻게 분리해야 하는가?
- 문장 교체 시 기존 staged 후보를 보존해야 하는 경우와 폐기해야 하는 경우를 어떻게 구분할 것인가?
- 중국어 STT 품질이 `faster-whisper`로 충분한가?

### 관측

30분 운영 로그 기반으로 계산 성능은 충분했지만 문장 확정 생명주기와 staged 교체 판단이 품질 병목으로 나타났다.

기록된 관측값:

```text
1차 관측: 30분, 18,158개 이벤트, avg stt_rtf≈0.088, max stt_rtf≈0.13
2차 관측: 30분, 6,892개 이벤트, 1,124개 chunk, 2,412개 transcript
2차 성능: avg stt_rtf≈0.096, max stt_rtf≈0.13, avg total_rtf≈0.097
```

대표 회귀:

- `이 두 직업은`이 반복 관측되어 확정됐지만 실제로는 다음 문장의 열린 절이었다.
- 긴 금액 설명 문장은 여러 번 관측됐지만 열린 절이므로 교체 시 확정하면 안 됐다.
- 다음 문장 머리와 기존 staged tail overlap이 섞이는 경우 staged 보존이 필요했다.

### 반영 판단

- final transcript는 append-only로 유지한다.
- raw STT window는 원문창/진단용이고 final 출력으로 직접 사용하지 않는다.
- 일반 후보 확정 기준을 2회에서 3회 재확인으로 올린다.
- forced 후보는 더 보수적으로 본다.
- 열린 한글 절은 반복 관측만으로 확정하지 않는다.
- pending, replacement, revision 지표를 별도로 추적한다.
- 중국어 STT는 별도 backend 교체 검토가 필요하다.
- 모델 준비는 첫 실행 중 암묵 다운로드가 아니라 사용자가 이해할 수 있는 준비 단계로 분리해야 한다.

### 모델 성능 비교와 선정

| 흐름 | 비교 모델 | 관측/선정 |
| --- | --- | --- |
| 영어/한국어 STT | `faster-whisper + large-v3` | 30분 운영 로그에서 평균 `stt_rtf≈0.088~0.096`, 최대 `stt_rtf≈0.13`, 평균 `total_rtf≈0.097`로 계산 성능은 충분했다. 품질 병목은 모델 처리량보다 sliding window 확정 생명주기였다. |
| 중국어 STT | `faster-whisper` | 중국어 정확도와 문장 구조 안정성이 부족해 운영 품질 후보가 아니라 baseline으로 분리했다. |
| 문장 경계 | SaT/wtpsplit vs regex/ad-hoc | regex는 다국어 운영 기본값으로 부적합하다고 보고, SBD 모델을 후보 생성기로 쓰는 방향을 채택했다. |

### 로직 변경 아이데이션

| 관측 | 아이디어 | 결과 |
| --- | --- | --- |
| `이 두 직업은` 같은 열린 절이 반복 관측만으로 확정됨 | 단순 반복 횟수보다 열린 절 여부와 right context를 먼저 본다. | `open_korean_clause`가 재확인 횟수보다 우선하는 방향으로 조정했다. |
| 긴 금액 설명 문장이 여러 번 관측됐지만 뒤 문장으로 이어짐 | 일반 후보 확정 기준을 높이고, forced 후보는 더 보수적으로 다룬다. | 일반 후보는 3회 재확인, forced 후보는 더 높은 보수 기준을 유지했다. |
| 다음 문장 머리와 기존 staged tail이 겹쳐 기존 후보가 폐기될 위험이 있음 | partial replacement에서 기존 staged가 닫힌 문장형이거나 tail overlap이 충분하면 보존한다. | staged 교체 판단을 보존/폐기/확정 케이스로 분리했다. |
| tail 확정 지연, VAD 필터, 반복 확인 규칙이 서로 충돌함 | tail 지연류 설정을 줄이고 `sentenceFinalizeAge`와 staged confirmation으로 일원화한다. | 확정 로직을 단일 생명주기 중심으로 정리했다. |
| 문제 원인이 모델 처리량인지 확정 로직인지 분리하기 어려움 | `chunk_metrics`, `pending_overrun`, `replacement` 추적 지표를 추가한다. | 품질 회귀를 로그와 추적 테스트에서 직접 확인하는 흐름이 생겼다. |

### 주요 기본값 변경

| 축 | 기본값/정책 변화 | 사유 |
| --- | --- | --- |
| 확정 재확인 | 일반 후보 확정 기준을 `2`회 관측에서 `3`회 관측으로 상향 | 열린 절과 tail echo가 반복 관측만으로 premature final이 되는 문제를 줄이기 위해서다. |
| forced 후보 | forced boundary 후보를 일반 후보보다 보수적으로 처리 | 모델이 경계를 강하게 제안해도 뒤 window에서 문장이 이어질 수 있기 때문이다. |
| 문장 경계 | regex/ad-hoc 규칙이 아니라 SaT/wtpsplit 계열 SBD를 후처리 후보 생성기로 채택 | 언어별 정규식 누적 대신 다국어 모델 기반 경계 판단으로 전환하기 위해서다. |
| 모델 준비 | setup/GUI에서 모델 캐시를 준비하고 Serve 전 검사하는 흐름으로 이동 | 첫 실행 중 다운로드 지연과 실패를 런타임 품질 문제와 분리하기 위해서다. |
| 중국어 STT | `faster-whisper`를 중국어 품질 후보가 아니라 baseline으로 분리하기 시작 | 중국어 문장 구조와 의미 보존에서 별도 STT 후보 검토가 필요했기 때문이다. |

## 2026-06-14: 중국어 STT 후보와 모델 준비 흐름 확장

### 관련 커밋

| 커밋 | 제목 |
| --- | --- |
| `855abf8` | feat: 위스퍼 언어별 설정 화면 정리 |
| `6c3b90f` | fix: 위스퍼 FunASR 로그와 문서 안정화 |
| `aa3eccf` | feat: 위스퍼 언어별 STT 모델 선택 정리 |
| `0741d4a` | refactor: 위스퍼 설정 화면 그룹 정리 |
| `cec326c` | feat: 위스퍼 번역 백엔드와 모델 다운로드 진행 표시 추가 |
| `43ebef0` | feat: 위스퍼 모델 준비와 중국어 문장 추적 개선 |
| `9efb27b` | refactor: 오디오 AI 도메인 명칭 정리 |
| `8a48410` | fix: 오디오 AI 전사 안정화와 다운로드 창 정리 |
| `61defdb` | test: 번역 품질 관측 케이스 정리 |
| `008cec1` | fix: 중국어 오디오 AI stage 후보 전환 개선 |
| `e564dab` | feat: 중국어 STT 대안 백엔드 추가 |
| `b11ec0e` | fix: 모델 다운로드 경로 개선 |
| `19c98c4` | fix: 중국어 STT 기본값과 의존성 충돌 수정 |
| `b922231` | fix: Qwen ASR 의존성 버전 고정 |
| `9f12da4` | feat: 중국어 STT 스트리밍 옵션 추가 |
| `9d120cf` | feat: 오디오 AI 컨텍스트 윈도우 상한 확대 |
| `7983d72` | refactor: FunASR 모델 관리 코드 제거 |
| `1541a52` | feat: 오디오 AI 스트리밍 STT 선택 추가 |
| `1d400d7` | fix: vLLM 공유 런타임 충돌 차단 |

### 실험 질문

- 중국어 STT에서 `faster-whisper`를 계속 사용할 수 있는가?
- Qwen3-ASR, FunASR, WeNet, Dolphin-CN-Dialect 중 어떤 방향이 운영 후보인가?
- 긴 context window가 중국어 raw STT 안정성에 도움이 되는가?
- 모델 다운로드와 Serve 시작 사이의 책임을 어떻게 나눌 것인가?
- vLLM streaming 후보를 공유 `.venv`에 넣을 수 있는가?

### 관측

중국어 운영 로그에서 `boundary_complete=2~4`가 같은 chunk 안에서 반복 관측되었다. 기존 생명주기는 completed 후보를 순서대로 staging에 넣었고, 같은 STT window의 첫 후보가 다음 후보에 의해 확정 전 폐기되는 문제가 있었다.

30분 중국어 STT 모니터링:

```text
replace=570 discard=568 suppressed=266 revision=327 finalized=137 no_result=20
perf_samples=1064 max_stt=0.350s max_total=0.370s avg_total_rtf=0.010 translation=0
```

backend 비교 관측:

- FunASR Paraformer는 인접 전사 유사도와 처리시간은 좋았지만 stage 교체/폐기가 많고 확정률이 낮았다.
- Qwen3-ASR 0.6B는 처리시간이 더 길지만 의미 보존과 문장 구조가 더 자연스러웠고 확정률도 높았다.
- Whisper/faster-whisper는 중국어 정확도가 부족해 baseline으로 분리했다.

대표 지표:

```text
qwen3-asr-0.6b, window=30: replace/chunk=0.55 discard/chunk=0.55 finalized/chunk=0.11 STT avg=1.109s
funasr-paraformer, window=30: replace/chunk=0.74 discard/chunk=0.74 finalized/chunk=0.04 STT avg=0.290s
funasr-paraformer, window=15: replace/chunk=0.25 discard/chunk=0.25 finalized/chunk=0.22 STT avg=0.129s
```

### 모델 성능 비교와 선정

| 흐름 | 비교 모델 | 관측/선정 |
| --- | --- | --- |
| 중국어 STT | `qwen3-asr-0.6b`, `window=30` | STT 평균은 약 `1.109s`로 FunASR보다 느렸지만 의미 보존과 문장 구조가 더 자연스러웠고 확정률도 상대적으로 높았다. 중국어 품질 우선 후보로 선정했다. |
| 중국어 STT | FunASR Paraformer, `window=30` | STT 평균은 약 `0.290s`로 빨랐지만 `replace/chunk=0.74`, `discard/chunk=0.74`, `finalized/chunk=0.04`로 stage churn과 낮은 확정률이 문제였다. 운영 후보에서 제외했다. |
| 중국어 STT | FunASR Paraformer, `window=15` | STT 평균은 약 `0.129s`로 가장 빨랐고 확정률은 개선됐지만 의미 보존과 품질 우선 기준에는 부족했다. 과거 기준선으로만 남긴다. |
| 중국어 STT | `faster-whisper` | 중국어 품질 비교에서는 baseline으로만 유지한다. 영어/한국어의 판단과 분리한다. |
| streaming STT | `qwen3-asr-vllm-streaming` | 지연 개선 후보지만 공유 `.venv`에서 vLLM 의존성 충돌이 있어 운영 후보가 아니라 격리 런타임 후속 실험으로 보류했다. |

### 로직 변경 아이데이션

| 관측 | 아이디어 | 결과 |
| --- | --- | --- |
| 중국어 SBD가 한 STT window에서 completed 후보를 2~4개 반환함 | 중국어 completed 후보는 같은 STT window의 하나의 관찰 단위로 병합한다. | `coalesce` 추적 지표와 중국어 multi-completed 병합 정책이 생겼다. |
| 같은 chunk 안 후속 completed 후보가 첫 후보를 확정 전 폐기함 | staged 후보가 재확인 기준을 통과하지 못하면 교체 직전 확정하지 않는다. | `stage_replaced_unconfirmed`, `stage_finalize_before_replace`를 구분해 관측했다. |
| 짧은 CJK 후보는 노이즈일 수 있지만 오래 보류하면 final이 막힘 | 명백한 오류만 차단하고, 나머지는 stage 교체/재확인으로 처리한다. | 보류 규칙을 늘리기보다 final 생성률과 품질 게이트를 같이 보는 방향으로 정리했다. |
| FunASR는 빠르지만 stage churn이 큼 | 모델 처리시간보다 stage lifecycle 안정성 지표를 함께 본다. | `replace/chunk`, `discard/chunk`, `finalized/chunk`를 모델 비교 지표로 사용했다. |
| vLLM streaming은 지연 후보지만 의존성 충돌 위험이 큼 | 공유 런타임에 넣지 않고 격리 런타임 실험으로 분리한다. | Fail-Fast 정책과 모델 실행 경로 분리 아이디어로 이어졌다. |

### 반영 판단

- 중국어 completed 후보는 같은 STT window의 하나의 관찰 단위로 병합한다.
- 영어/한국어 completed 후보는 경계 모델 출력 단위를 보존한다.
- Qwen3-ASR를 중국어 품질 우선 후보로 올린다.
- FunASR STT는 운영 후보에서 제외하고 과거 기준선 기록으로만 남긴다.
- `qwen3-asr-vllm-streaming`은 vLLM 의존성이 `mediapipe`/`protobuf`와 충돌하므로 공유 `.venv`에서는 차단한다.
- 모델 다운로드는 setup이 아니라 config GUI 모델 다운로드 매니저와 Serve 시작 전 캐시 검사 흐름으로 분리한다.
- 중한 번역 품질 병목은 STT/staging 병목과 분리해 추적한다.

### 주요 기본값 변경

| 축 | 기본값/정책 변화 | 사유 |
| --- | --- | --- |
| 중국어 STT backend | 중국어 후보에 `qwen3-asr-transformers`를 추가하고 운영 우선 후보로 승격 | `faster-whisper` 중국어 품질 한계와 FunASR의 stage churn이 관측됐기 때문이다. |
| 중국어 STT model | 중국어 기본 후보를 `qwen3-asr-0.6b`로 수렴 | 처리시간은 늘지만 의미 보존과 문장 구조가 더 안정적이었다. |
| 중국어 streaming 후보 | `qwen3-asr-vllm-streaming`은 공유 `.venv` 기본값에서 제외 | vLLM 의존성이 `mediapipe`/`protobuf`와 충돌해 Fail-Fast 대상이기 때문이다. |
| 중국어 context | `windowSeconds=30`까지 실험 범위를 확장 | 긴 중국어 문장에서 raw STT 안정성은 좋아질 수 있지만 final 지연 비용을 같이 봐야 했기 때문이다. |
| 모델 다운로드 | config GUI 다운로드 모달과 Serve 전 캐시 검사로 분리 | STT/번역/문장 경계 모델 준비 상태를 실행 전 명확히 보여주기 위해서다. |
| FunASR | FunASR 모델 관리 경로를 기본 운영 후보에서 제거 | 빠르지만 의미 보존, 폐기율, 확정률이 운영 기준에 못 미쳤기 때문이다. |

## 2026-06-15: 중국어 pending 접합, 원문창 의미, 언어별 기본값 정리

### 관련 커밋

| 커밋 | 제목 |
| --- | --- |
| `4d8f177` | fix: 중국어 pending 내부 재시작 병합 보정 |
| `574e6dd` | fix: 오디오 AI 중국어 기본값과 추적 지표 보강 |
| `716713f` | fix: 오디오 AI 원문 출력과 중국어 리비전 안정화 |
| `3f5315d` | feat: 오디오 AI 언어별 전사 튜닝 개선 |
| `978ce7b` | fix: 오디오 AI 문장 생명주기와 갱신 기본값 개선 |
| `6d20b63` | fix: 오디오 AI 문장 확정 빈도 개선 |
| `b3f1b89` | docs: 받아쓰기 AI 문서와 표시명 정리 |
| `5717b56` | refactor: 받아쓰기 AI 설정 스키마 정리 |
| `ba2818a` | refactor: 받아쓰기 문장 확정 규칙 단순화 |

### 실험 질문

- 중국어 pending이 길어진 상태에서 다음 raw STT가 내부 중간부터 다시 시작하면 어떻게 병합해야 하는가?
- STT 원문창은 raw STT를 보여야 하는가, staged 후보를 보여야 하는가?
- 중국어 `windowSeconds=30`이 항상 좋은가?
- 언어별 runtime 기본값을 어떻게 분리해야 하는가?

### 관측

최근 회전 로그 집계에서 계산 성능은 병목이 아니었다.

```text
diag=2494 duplicate=491 final=271 replace=160 discard=155 suppressed=29
avg_stt_rtf=0.035 avg_total_rtf=0.035 avg_text_chars=101.5
quality: cjk_internal_gap=194 mixed_latin_zh=37 latin_only_for_zh=6 no_end_marker=3
```

대표 pending 내부 재시작:

```text
pending_tail=...喷枪
new_text=条，然后把这米再切断了，摆成四个墩儿墩儿，然后就是火山的底座，然后上面这个洒的就更像熔岩一样，然后用喷枪
old_result=...喷枪 条，然后把这米再切断了...
```

중국어 12초/1초 모니터링에서는 `stt_step_load`가 대체로 0.4~0.7이고 `input_queue_drops=0`이라 처리량은 충분했다. 다만 복잡한 stage 보류/폐기 규칙이 누적되면서 `raw_without_final`이 증가했다.

### 모델 성능 비교와 선정

| 흐름 | 비교 모델/조건 | 관측/선정 |
| --- | --- | --- |
| 영어/한국어 STT | `faster-whisper + large-v3`, `windowSeconds=7`, `stepSeconds=1` | 실시간성과 문장 안정성의 균형점으로 판단했다. 현재 한국어/영어 기본 모델로 유지한다. |
| 중국어 STT | `qwen3-asr-0.6b`, `windowSeconds=12`, `stepSeconds=1` | `stt_step_load≈0.4~0.7`, `input_queue_drops=0`으로 처리량은 충분했다. 30초 window보다 final 갱신 지연이 낮아 운영 시작점으로 선정했다. |
| 중국어 STT | `qwen3-asr-0.6b`, `windowSeconds=30` | 장문 raw STT 안정성은 나아질 수 있지만 final script 갱신이 늦고 긴 문장 확정 비용이 컸다. 비교 실험값으로 유지한다. |
| 번역 | `nllb-200-distilled-600M` | 중국어 안정화 이후 지명, 서비스명, 구어체 표현에서 중한 오역이 관측됐다. 실시간 기본값으로는 유지하되 품질 개선 비교가 필요하다. |
| 번역 후보 | NLLB 1.3B/3.3B, M2M100, SeamlessM4T, LLM 번역 모델 | 기본값으로 바로 승격하지 않고 `translation_quality` 샘플 기반 비교 후보로 남긴다. |

### 로직 변경 아이데이션

| 관측 | 아이디어 | 결과 |
| --- | --- | --- |
| pending tail 뒤에 새 STT가 같은 CJK 구간 중간부터 다시 시작함 | 당시에는 CJK no-space 내부 prefix overlap 접합으로 분류했다. | 현재는 학술적 근거 부족으로 접합 보정을 폐기하고 STT/backend 품질과 revision lifecycle 관측으로 돌린다. |
| 서로 다른 중국어 continuation 사이에 공백이 삽입됨 | 당시에는 CJK continuation을 인위적 공백 없이 이어붙였다. | 현재는 언어별 접합 보정을 폐기하고 detector 입력 생성을 위한 단순 결합만 수행한다. |
| 원문창이 staged 후보를 보여주던 시기의 로그가 raw STT 품질 판단을 흐림 | 원문창은 `stt_raw` 이벤트만 표시하고, staged/partial은 진단 로그로만 둔다. | raw STT 품질, revision lifecycle, final 출력의 관측 위치를 분리했다. |
| `raw_without_final`이 증가했지만 입력 큐 드롭은 없었음 | 후보 차단/보류 규칙을 늘리기보다 final 생성률 회복을 우선한다. | 명백한 오류만 차단하고 나머지는 staged 교체와 재확인으로 처리하는 방향을 채택했다. |
| CJK revision 내용이 바뀌어도 기존 confirmations가 남을 수 있음 | 실제 내용이 바뀐 revision은 confirmations를 1부터 다시 센다. | 흔들리는 후보가 누적 확인만으로 final이 되는 문제를 줄였다. |

### 반영 판단

- CJK no-space 텍스트의 내부 prefix overlap 기반 접합 보정은 운영 요구사항에서 제외한다.
- 서로 다른 중국어 continuation은 인위적 공백 없이 이어붙인다.
- 원문창은 `stt_raw` 이벤트만 표시한다.
- staged/partial 후보는 final 확정 전 내부 상태이므로 원문창에 표시하지 않는다.
- 영어/한국어 기본 시작점은 `windowSeconds=7`, `stepSeconds=1`, `sentenceFinalizeAge=3`이다.
- 중국어/Qwen3-ASR 기본 시작점은 `windowSeconds=12`, `stepSeconds=1`, `sentenceFinalizeAge=2`이다.
- 30초 window는 장문 안정성에는 유리할 수 있지만 final script 갱신 지연과 긴 문장 확정 비용이 커질 수 있다.

### 주요 기본값 변경

| 축 | 기본값/정책 변화 | 사유 |
| --- | --- | --- |
| 언어별 runtime | active/global 값보다 `stepSeconds{Lang}`, `windowSeconds{Lang}`, `sentenceFinalizeAge{Lang}`를 기준으로 정리 | 영어/한국어와 중국어의 적정 window가 달라 단일 기본값으로 품질을 맞추기 어려웠기 때문이다. |
| 영어/한국어 window | `windowSecondsEn=7`, `windowSecondsKo=7` | `faster-whisper + large-v3`에서 실시간성과 문장 안정성의 균형점으로 판단했다. |
| 중국어 window | `windowSecondsZh=12`를 시작점으로 설정 | 30초 window의 안정성은 인정하되 final 갱신 지연이 커서 운영 시작점은 낮췄다. |
| step | `stepSecondsEn/Ko/Zh=1` | 화면 갱신성과 STT 처리량이 모두 감당 가능한 범위로 관측됐다. |
| 확정 age | `sentenceFinalizeAgeEn/Ko=3`, `sentenceFinalizeAgeZh=2` | 2026-06-17 SaT 벤치에서 중국어 age 2가 `no_end_marker` final을 0으로 유지하면서 age 3보다 확정 수와 `finalized_per_stage_start`를 개선했다. |
| STT 디코딩 | `beamSize=3`, `maxNewTokens=192`, `temperature=0.0`를 언어별 시작점으로 정리 | 빠른 발화와 긴 문장 절단을 줄이되 실시간 지연을 통제하기 위한 기준선이다. |

## 2026-06-16: 확정 절차 단순화, 계약 문서화, 문서 체계 분리

### 관련 커밋

| 커밋 | 제목 |
| --- | --- |
| `b9e6e78` | refactor: 받아쓰기 문장 확정 절차 단순화 |
| `a816ea9` | feat: 받아쓰기 문장 확정 관찰값 추가 |
| `01abc92` | docs: 받아쓰기 확정 관찰 기준 문서화 |
| `f89e05c` | docs: 전사 번역 운영 흐름 추가 |
| `623182f` | docs: 받아쓰기 AI 레퍼런스 문서 통합 |
| `9f1d051` | docs: 받아쓰기 AI 설계 노트와 계약 문서 정리 |

### 실험 질문

- 후보 보류/폐기 규칙이 너무 많아 final 생성률을 낮추는가?
- 같은 STT chunk 안 여러 중국어 completed 후보가 첫 후보를 즉시 final로 밀어내는가?
- 발표/회의용 실시간 번역에서 침묵 구간과 VAD를 문장 경계의 주 신호로 사용해도 되는가?
- 문서가 설계, 실험, 계약, 레퍼런스 역할을 분리하고 있는가?

### 관측

2026-06-16 로그에서 같은 STT chunk 안의 여러 중국어 completed 후보가 첫 관찰 후보를 `next_completed`로 즉시 final 확정시키는 문제가 관측되었다. 또한 Qwen3-ASR가 빈 `ASRTranscription` 객체를 반환했을 때 객체 표현 문자열이 raw STT로 유입되는 경로가 확인되었다.

발표용 전사/번역 운영 흐름 문서에서는 VAD와 pause threshold만으로 문장 경계를 확정하는 방식이 발표 말투, 긴 설명, 화면 공유 중 발화 지연에서 불안정하다고 정리되었다. 운영 흐름은 `Streaming ASR → Stable Token Detection → Semantic Boundary Detection → Translation Trigger`로 잡고, 번역은 안정화된 final segment만 대상으로 삼는 방향이 문서화되었다.

### 모델 성능 비교와 선정

| 흐름 | 비교 모델 | 관측/선정 |
| --- | --- | --- |
| STT 최종 기준 | `ko/en=faster-whisper + large-v3`, `zh=qwen3-asr-transformers + qwen3-asr-0.6b` | 언어별 운영 관측에서 준수한 성능으로 판단한 조합을 계약 기본값으로 문서화했다. |
| 문장 경계 | SaT/wtpsplit vs VAD/pause threshold | VAD와 침묵 길이는 발표 말투에서 경계 신호로 불안정했다. SaT/wtpsplit 기반 SBD와 stable token을 주 경로로 선정하고 VAD는 보조 신호로 낮췄다. |
| 번역 | `nllb-transformers + facebook/nllb-200-distilled-600M` | 실시간 기본값으로 유지한다. 품질 개선은 NLLB 대형 모델, M2M100, SeamlessM4T, LLM 번역 후보의 후속 비교로 분리했다. |
| ASR 오류 보정 | pinyin-aware LLM 보정, ASR-EC 계열 | raw STT 오류와 후처리 오류가 아직 충분히 분리 계측되지 않았으므로 운영 기본값에는 넣지 않았다. |

### 로직 변경 아이데이션

| 관측 | 아이디어 | 결과 |
| --- | --- | --- |
| 같은 STT chunk 안 여러 중국어 completed 후보가 첫 후보를 `next_completed`로 즉시 final 확정함 | 중국어 multi-completed 후보를 먼저 병합하고, 교체 직전 확정은 재확인 기준을 통과한 staged에만 허용한다. | 즉시 final로 밀어내는 경로를 줄이고 관찰 단위를 먼저 정규화했다. |
| Qwen3-ASR가 빈 `ASRTranscription` 객체를 반환할 수 있음 | `.text` 속성이 있으면 빈 문자열도 명시 결과로 보고 객체 문자열화를 금지한다. | 객체 표현 문자열이 raw STT로 유입되는 경로를 차단했다. |
| 발표 말투에서는 VAD/pause가 문장 경계와 맞지 않음 | VAD는 주 결정자가 아니라 SBD confidence 보조 feature로 둔다. | `Streaming ASR -> Stable Token Detection -> Semantic Boundary Detection -> Translation Trigger` 흐름을 채택했다. |
| partial 번역이 원문 revision을 오역/중복 번역으로 전파함 | 번역 트리거를 final segment 확정 이후로 제한한다. | final-only translation 계약으로 정리했다. |
| 오류 보정 모델을 먼저 붙이면 raw STT 오류와 후처리 오류가 섞임 | ASR-EC/LLM 보정은 후속 후보로 미루고, 먼저 로그 지표에서 실패 원인을 분리한다. | 운영 기본 경로에는 오류 보정 모델을 넣지 않았다. |

### 반영 판단

- 중국어 multi-completed 후보는 하나의 관찰 단위로 병합한다.
- 교체 직전 확정은 `sentenceFinalizeAge` 또는 재확인 횟수 기준을 통과한 후보에만 허용한다.
- CJK revision 내용이 실제로 바뀌면 confirmations를 1부터 다시 센다.
- STT 어댑터는 `.text` 속성이 존재하면 빈 값도 명시 결과로 처리하고 객체를 문자열화하지 않는다.
- 후보 차단/폐기 규칙은 명백한 오류로 제한한다.
- VAD와 침묵 길이는 보조 신호로만 사용하고, 문장 경계의 주 신호는 안정 토큰과 모델 기반 semantic boundary detector로 둔다.
- 실시간 번역은 partial을 매번 번역하지 않고 final segment 확정 이후에만 트리거한다.
- 새 기준 문서는 설계/실험 노트, 계약/기본값 문서, 레퍼런스 인덱스로 분리한다.
- 기존 기능 설계 문서와 프레젠테이션 세그먼트 문서는 폐기 예정 원본 기록으로 분류한다.

### 주요 기본값 변경

| 축 | 기본값/정책 변화 | 사유 |
| --- | --- | --- |
| 저장 스키마 | `dictationAi` 계약을 기준으로 하고 과거 `whisper` 명칭은 호환 맥락으로 축소 | 사용자 기능명과 기술 backend명을 분리하기 위해서다. |
| STT 기본값 | `ko/en=faster-whisper + large-v3`, `zh=qwen3-asr-transformers + qwen3-asr-0.6b` | 현재 운영 관측에서 각 언어별 준수한 성능으로 판단한 조합이다. |
| legacy projection | active 키는 현재 선택 언어의 언어별 기본값 projection으로 유지 | 기존 설정 호환성과 언어별 기본값을 동시에 유지하기 위해서다. |
| 번역 기본값 | `translationEnabled=false`, `translationBackend=nllb-transformers`, `translationModel=facebook/nllb-200-distilled-600M`, `translationBeamSize=1`, `translationMaxNewTokens=128` | 번역은 선택 기능이며, 켰을 때는 실시간성을 우선하는 시작점을 제공하기 위해서다. |
| 문장 경계 기본값 | `sentenceBoundaryBackend=sat`, `sentenceBoundaryModel=sat-3l-sm`, `sentenceBoundaryDevice=cuda`, `sentenceBoundaryComputeType=float16` | regex 운영 경로를 폐기하고 모델 기반 SBD를 기본 후보 생성기로 쓰기 위해서다. |
| 확정 정책 | tail 확정 지연류의 별도 조정값을 줄이고 `sentenceFinalizeAge=3`과 staged confirmation으로 일원화 | 규칙 수가 늘수록 final 생성률과 디버깅 가능성이 떨어졌기 때문이다. |
| 번역 트리거 | 번역 입력을 final transcript only로 고정 | partial 번역 중복과 premature translation을 막기 위해서다. |

## 2026-06-16~17: 중국어 운영 모니터링과 CJK replacement 튜닝

이 섹션은 `653e7b08c4f98750a7220976b276223141323332` 커밋 당시 기준 문서에 기록됐으나 실험일지로 옮겨지지 않았던 운영 모니터링과 벤치 튜닝 이력을 반영한다.

### 2026-06-16 stable 지표 적용 후 5분 운영 모니터링

stable token 지표를 추가한 뒤 중국어 실시간 경로를 약 5분 더 관측했다. 처리량은 충분했고, `stt_step_load`는 대체로 `0.3~0.7` 구간에 있었으며 queue drop은 관측되지 않았다.

관측된 병목:

- `stable_token_ratio`가 높은 chunk에서도 후보 자체가 글자 단위 공백 CJK로 변환되면 staged 교체와 confirmation reset을 유발했다.
- `raw_without_final`과 `stage_revision_confirmation_reset`은 계속 누적됐다.
- `stage_replace_decision_unconfirmed_cjk`와 `stage_replaced_unconfirmed`가 누적되어, 불안정 후보를 stage에 올리기 전에 차단할 필요가 있었다.
- `stable_overlap_source=suffix_prefix`는 정상 final 직전에도 관측되어 sliding overlap 지표가 유효한 진단 신호임을 확인했다.

당시 반영:

- `spaced_cjk`, `cjk_repeated_ngram`, `latin_only_for_zh`, `empty` 후보는 stage 진입 전에 차단한다.
- `short_cjk`, `no_end_marker`, `mixed_latin_zh`는 stage 진입 차단 대상에 넣지 않고 final/translation 품질 게이트에서만 다룬다.
- 안정성 요약 로그에 `stage_candidate_quality_blocked`, `stage_candidate_quality`를 추가한다.
- 추적 테스트에 `stage_candidate_quality_blocked`, `stage_candidate_quality`, `stage_candidate_quality_spaced_cjk`, `stage_candidate_quality_no_end_marker`를 추가한다.

추가 5분 모니터링에서는 stage 후보 품질 차단이 실제 운영 로그에서 반복적으로 동작했다. 그러나 `stage_candidate_quality_blocked` 증가에도 `raw_without_final`과 `stage_revision_confirmation_reset`은 여전히 높았다. 여러 chunk에서 Qwen window가 같은 의미 구간을 내부에 유지하면서도 prefix 또는 suffix-prefix로 맞지 않아 `stable_token_ratio=0`, `stable_overlap_source=none`으로 기록됐다.

추가 반영:

- `stable_internal_chars`, `stable_internal_ratio`를 진단 지표로 추가한다.
- `stable_overlap_source=none`이면서 `stable_internal_ratio`가 높은 케이스를 추적 테스트에 추가한다.
- 안정성 요약 로그에 `stage_candidate_quality_cjk_internal_gap`, `stage_candidate_quality_mixed_latin_zh`를 추가한다.
- `segment_state_pending/staged/final/suppressed/revised`를 안정성 요약 로그와 runtime tracking에 추가한다.

현재 재정리 판단:

- stable token/char 지표와 상태 전환 metric은 최소 파이프라인의 관측 지표로 유지한다.
- 내부 overlap을 이용한 delta 재작성 또는 pending/new 접합 보정은 2026-06-17~18 재정리에서 폐기했다.

### 2026-06-16 내부 overlap 적용 후 5분 운영 모니터링

내부 overlap 보조 신호를 적용한 뒤 중국어 실시간 경로를 약 5분 더 관측했다.

관측값:

- chunk 320 누적 기준 `finalized=19`, `raw_without_final=300`, `stage_replaced_unconfirmed=63`, `stage_revision_confirmation_preserved_internal=30`, `stage_revision_confirmation_reset=109`였다.
- `stable_internal_ratio>=0.75` 케이스는 `revision_preserved_internal`로 분리되어 reset을 줄였지만, 0.60대 내부 overlap을 가진 같은 문맥 확장 리비전은 여전히 reset됐다.
- `stable_internal_chars=65`, `stable_internal_ratio=0.619`, `stable_overlap_source=none`인 chunk는 같은 문맥 확장인데 reset됐다.
- `stable_internal_chars=39`, `stable_internal_ratio=0.867`처럼 ratio는 높지만 내부 공통 구간이 짧은 케이스도 있어 ratio 단독 완화는 위험했다.
- `stage_candidate_quality_blocked`는 32까지 누적되어 `spaced_cjk`, `cjk_internal_gap`, `cjk_repeated_ngram` 차단이 계속 동작했다.
- 후반 일부 구간에서 `stt_step_load`가 2.9 내외로 올라가고 queue가 30대까지 쌓였지만 drop은 없었다.

당시 튜닝:

- CJK revision confirmation 보존 기준을 `stable_internal_ratio>=0.60`과 `stable_internal_chars>=40`의 동시 조건으로 조정한다.
- final 확정 기준은 그대로 유지한다. 이 튜닝은 reset 완화만 수행하며 확정/번역 큐 진입을 직접 앞당기지 않는다.
- 안정성 요약 로그에 `revision_internal_high`, `revision_internal_mid`, `revision_internal_low`를 추가한다.
- 추적 테스트에 high bucket 보존 케이스와 mid bucket reset 케이스를 추가한다.

현재 재정리 판단:

- 내부 overlap은 안정성 관측 지표로는 남길 수 있다.
- 내부 overlap을 근거로 문자열 delta를 재작성하는 로직은 의미 단위 재작성 위험이 있어 폐기했다.

### 2026-06-17 중국어 30분 운영 모니터링

중국어 실시간 경로를 약 30분 모니터링했다. 실행 조건은 로그 기준 `qwen3-asr-0.6b`, `window=15.0`, `step=1.0`, `beam=3`, `maxNewTokens=192`다.

관측값:

- `stt_step_load`와 `total_step_load`는 대부분 1.0 미만이고 `input_queue_drops=0`으로 유지되어 계산 성능은 주 병목으로 보지 않았다.
- 일부 구간에서 queue가 순간적으로 50까지 쌓였다. drop은 없었지만 queue peak/backlog는 별도 추적 지표가 필요했다.
- chunk 656 누적 스냅샷 기준 `finalized=36`, `stage_start=141`, `stage_replaced_unconfirmed=104`, `stage_revision_confirmation_preserved_internal=121`, `stage_revision_confirmation_reset=192`였다.
- 해당 스냅샷의 `finalized_per_stage_start`는 약 `0.255`, `stage_replaced_unconfirmed_per_stage_start`는 약 `0.738`, `revision_preserve_rate`는 약 `0.387`이었다.
- `stage_candidate_quality_blocked`, `raw_without_final`, `segment_state_revised/suppressed`가 계속 누적되어 품질 병목은 처리량보다 staged 생명주기 churn에 가까웠다.
- 문장형 후보가 보이더라도 `staged_confirmations=1/3` 또는 `2/3` 상태에서 다음 window 재표현으로 reset/교체되어 final까지 도달하지 않는 사례가 반복됐다.
- 기존 구현은 revision 처리 때 `staged_age`를 0으로 되돌려, completed 후보가 매 chunk 나오는 중국어 경로에서 age 기반 확정이 사실상 누적되기 어려웠다.

당시 반영:

- 기본 런타임 파라미터는 유지한다.
- `input_queue_size_peak`, `input_queue_backlog_chunk`를 런타임 지표에 추가한다.
- `finalized_per_stage_start`, `stage_replaced_unconfirmed_per_stage_start`, `revision_preserve_rate`를 tracking metric으로 추가한다.
- revision으로 같은 staged lifecycle이 유지될 때 `staged_age`를 누적한다.
- CJK 후보는 첫 관측 확정을 계속 막되, 짧은 조각/글자 단위 공백/반복 n-gram/내부 공백 오염이 없는 후보가 2회 이상 관측되거나 age 기준을 채우면 `stable_cjk`/`aged` 사유로 final 승격할 수 있게 한다.
- `stage_finalize_stable_cjk`, `stage_age_finalize`, `stage_age_quality_blocked` 지표를 추가한다.
- age 기준 확정도 `short_cjk`, `spaced_cjk`, `cjk_internal_gap`, `cjk_repeated_ngram`, `latin_only_for_zh` 품질 게이트를 통과해야 한다.

패치 반영 후 새 실행 초반 chunk 431 누적 기준 `finalized=70`, `stage_start=115`, `stage_replaced_unconfirmed=44`, `stage_age_finalize=41`, `stage_finalize_stable_cjk=25`가 관측됐다. 30분 모니터링 종료 직전 chunk 761 누적 기준은 `finalized=120`, `stage_start=195`, `stage_replaced_unconfirmed=72`, `input_queue_drops=0`, `input_queue_size_peak=10`이었다.

현재 재정리 판단:

- age 누적과 상태/지표 추가는 생명주기 관측과 확정 지연 분석에 필요한 이력으로 유지한다.
- 학술적 근거가 부족한 pending/new 접합 보정은 재도입하지 않는다.

### 2026-06-17 후속 30분 운영 모니터링

로그 회전 보존 개수를 1000개로 늘린 뒤 중국어 실시간 경로를 다시 관측했다. 분석 범위는 `.tmp/logs/avc-whisper.log*`의 `2026-06-17 00:11:59`부터 `00:41:59`까지 약 30분이다. 실행 조건은 로그 기준 `qwen3-asr-0.6b`, `window=15.0`, `step=1.0`, `beam=3`, `maxNewTokens=192`, 번역 OFF 구간 중심이다.

관측값:

- `perf` 로그 1039개 기준 평균 `total_step_load≈0.63`, 최대 `1.39`, `input_queue_drops_total=0`, 최대 `queue_peak=10`이었다.
- `completed=1 final=0` 진단은 863회, `final=1` 진단은 651회 관측됐다.
- 주요 이벤트는 `stage_candidate_quality_blocked=184`, `stage_replaced_unconfirmed=84`, `stage_revision_reset=379`, `stage_age_finalize=108`, `stage_finalize_stable_cjk=44`, `confirmed_finalize=11`, `translation_skip_final_quality=104`였다.
- 대표 품질 차단은 글자 단위 공백 CJK였다. 예: `顶 级 的 夏 威 夷 对 品 质 之 上 的 很 好 吃 好 看 这 个 哇 好 吃`.
- 대표 final 품질 관측은 `no_end_marker` 또는 `short_cjk,no_end_marker`였다. 예: `好乖好棒好棒怎么那么棒你看他还去当指挥交通的`, `拍照那我们就进去耶`.
- 안정 신호가 높아도 첫 관측 또는 단일 교체 후보인 경우에는 final로 보내지 않는 현재 정책이 유지됐다. 예: chunk 80의 긴 CJK 후보는 `stable_token_ratio=0.924`였지만 `staged_confirmations=1`, `staged_age=0`이라 `unconfirmed_cjk` 교체로 남았다.

튜닝 판단:

- 계산 처리량은 병목이 아니므로 `stepSecondsZh=1.0`, `beamSizeZh=3`, `maxNewTokensZh=192`는 유지한다.
- 2026-06-17 SaT 벤치 기준 `sentenceFinalizeAgeZh=2`가 현재 기본 후보 중 가장 낫다. `no_end_marker` final은 0으로 유지하면서 `finalized=20`, `stage_start=34`, `finalized_per_stage_start=0.588`로 age 3의 `finalized=19`, `stage_start=35`, `finalized_per_stage_start=0.543`보다 확정 지표가 개선됐다. 4 이상은 `finalized=18`, `finalized_per_stage_start=0.514`로 누락 쪽으로 기울었다.
- `windowSecondsZh=15.0`은 현재 STT 안정성과 확정 지연의 균형점으로 유지한다. 이번 구간에서 queue drop이 없으므로 처리량 때문에 줄일 근거는 없다.
- 로직 변경은 보류한다. 이번 구간의 주된 보강은 성능 추적 케이스 누적이며, `stable_token_ratio`가 높은 단일 관측 후보를 곧바로 final로 올리는 정책은 과확정 위험이 있어 다음 로그 비교 뒤 판단한다.

반영:

- 성능 추적 테스트의 `final_quality`, `finalization`, `runtime_metrics` 케이스를 보강했다.
- `finalization` tracking에는 stage 품질 차단, short/no-end 관측 후보, age final, 단일 관측 교체 보류 케이스를 추가했다.
- 순수 비중국어/라틴 단독 후보는 중국어 성능 추적 케이스에서 제거했다.
- runtime aggregate에는 `finalized_per_stage_start`, `stage_replaced_unconfirmed_per_stage_start`, `finalization_rate_per_1000`, `stage_candidate_quality_*`, `translation_skip`을 비교할 수 있도록 이번 30분 스냅샷을 추가했다.

### 2026-06-17 실제 SaT 벤치 기반 CJK replacement 튜닝

벤치 조건:

- `tests/eval/dictation_ai/sbd_text_cases.sample.jsonl` 24건
- `sat-3l-sm`, CUDA, `float16`
- `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`
- mock/smoke 경로는 성능 벤치 CLI에 두지 않는다.

기준선:

- `cases=24`, `pass_rate=0.083`
- `finalized=34`, `stage_start=54`, `finalized_per_stage_start=0.630`
- `stage_revision=109`, `stage_replace=6`, `stage_replaced_unconfirmed=6`
- `stage_candidate_quality_blocked=17`

튜닝:

- CJK staged 후보가 다음 completed 후보로 교체될 때, 후보에 문장 종료 신호가 있고 `short_cjk`, `spaced_cjk`, `cjk_internal_gap`, `cjk_repeated_ngram`, `latin_only_for_zh`, `no_end_marker` 차단 flag가 없으면 첫 관측 이후에도 교체 직전 확정을 허용한다.
- 이 값은 `CJK_REPLACEMENT_CONFIRM_CHUNKS=1`로 분리한다.
- 목적은 케이스별 보정이 아니라 sliding window 재표현으로 인해 문장형 CJK 후보가 `unconfirmed_cjk`로 suppress되는 비율을 줄이는 것이다.

튜닝 후:

- `cases=24`, `pass_rate=0.083`
- `finalized=38`, `stage_start=58`, `finalized_per_stage_start=0.655`
- `stage_revision=120`, `stage_replace=6`, `stage_replaced_unconfirmed=6`
- `stage_candidate_quality_blocked=12`

판단:

- pass rate는 그대로지만 이 벤치는 품질 게이트가 아니라 누락/중복 추적용이다.
- 실제 모델 기준으로 final 확정 수가 34에서 38로 늘고, 품질 차단 후보가 17에서 12로 줄어 개선 방향이다.
- `stage_replaced_unconfirmed`은 줄지 않았으므로 다음 튜닝은 replacement suppress 자체보다 spaced CJK 후보 품질 차단과 revision granularity를 분리해 관측한다.
- 중국어 문장 경계 문제는 정규식 또는 케이스별 규칙으로 해결하지 않는다.

현재 재정리 판단:

- 이 튜닝은 653e7b 커밋의 직접 실험 이력으로 보존한다.
- 이후 반복 벤치와 재설계 정리에서 기준 문서는 최소 파이프라인만 유지하고, 튜닝/폐기 후보는 실험일지에서만 관리한다.

## 2026-06-17~18: 재설계 기준 재정리와 과거 보정 폐기

### 실험 질문

- 2026-06-16 재설계 이후에도 이전 FunASR/Whisper 시절 보정 로직이 남아 있는가?
- 파라미터 튜닝으로 확정률 개선이 보이지 않는다면 로직 구조 문제로 볼 수 있는가?
- 기준 문서에 실험 기록과 폐기 후보가 섞이면 필수 구현처럼 오해되는가?
- 벤치/성능 추적 테스트가 품질 게이트가 아니라 성능 추세 관측 도구로 동작하는가?

### 관측

반복 벤치와 로그 모니터링에서 중국어 STT 결과 중 final로 넘어가지 못하는 문장과 중복 출력 후보가 계속 관측되었다. 수치 조정만으로 개선 폭이 뚜렷하지 않아, 파라미터보다 생명주기 구조와 과거 보정 잔존 여부를 우선 검토했다.

확인된 과거 로직:

- 2026-06-14 계열에서 들어온 completed 후보 재구성 로직
- staged 후보 교체 전 suffix/overlap 판단으로 기존 후보를 확정하는 보정
- pending/new 내부 overlap을 continuation처럼 잘라내는 delta 보정
- CJK no-space 내부 재시작 접합 아이디어
- 실험 후보였던 최근 문장 수 제한, 글자 수 cap, no-end-marker age 확정 완화

실제 SaT/CUDA 벤치 조건:

```text
cases=24
backend=sat
device=cuda
compute_type=float16
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

최소 파이프라인 기준으로 정리한 뒤 기준선:

```text
pass_rate=0.083
finalized=100
stage_start=557
finalized_per_stage_start=0.180
final_f1_avg=0.112
```

### 반영 판단

- 기준 파이프라인은 다음 최소 구조로 고정한다.

```text
오디오 입력
  ↓
슬라이딩 윈도우 STT
  ↓
안정성/경계 판단
  ↓
세그먼트 생명주기
  ↓
final-only 번역
```

- 기준 문서는 실험 기록을 포함하지 않는다.
- 실험 기록은 이 파일에서 관리한다.
- 기준 문서는 `docs/2026-06-16-dictation-ai-realtime-pipeline.md`로 분리한다.
- completed 후보 재구성 또는 합성은 재설계 기준에서 제외한다.
- pending/new overlap 접합 보정과 CJK no-space 내부 재시작 접합 보정은 폐기한다.
- internal overlap 기반 delta 보정은 의미 단위 재작성에 가까워 제거한다.
- 여러 completed 후보가 한 window에서 나와도 SBD 모델 경계 단위를 보존한다.
- VAD/silence는 final trigger나 boundary confidence 보정에 넣지 않는다.
- 벤치 실행은 실제 모델 기준인 `sat + cuda + float16`만 성능 판단 근거로 삼는다. mock/smoke/CPU 실행 경로는 벤치 CLI에 두지 않는다.
- 성능 추적 테스트는 품질 게이트가 아니라 누락/중복/확정 지연의 추세 관측 도구로 유지한다.

### 로직 변경 아이데이션

| 관측 | 판단 | 결과 |
| --- | --- | --- |
| 같은 chunk 안 여러 completed 후보가 단일 staged slot에서 서로 밀어냄 | 후보를 합치기보다 문장 단위 lifecycle 구조 문제로 본다. | completed 재구성 로직과 관련 테스트를 제거했다. |
| internal overlap delta가 일부 중복을 줄일 수 있음 | pending/new 접합 보정과 유사한 의미 재작성 위험이 있다. | 내부 overlap delta 보정과 품질 게이트 테스트를 제거했다. |
| 수치 튜닝 후보가 일부 지표를 개선함 | 기준 파이프라인을 흐리면 필수 구현처럼 오해된다. | 기준 문서에서 튜닝 후보와 폐기 후보 표를 제거하고 실험일지로 이동했다. |
| 성능 벤치를 mock/smoke/CPU로 돌릴 수 있음 | 실제 운영 품질 판단과 무관한 결과가 된다. | 벤치 CLI에서 mock/smoke 경로를 폐기하고 `sat + cuda + float16`만 허용하도록 했다. |

### 문서 정리

| 문서 | 역할 |
| --- | --- |
| `2026-06-16-dictation-ai-realtime-pipeline.md` | 현재 실시간 파이프라인 기준 |
| `2026-06-16-dictation-ai-experiment-log.md` | 실험 관측, 폐기 판단, 벤치 이력 |
| `2026-06-16-dictation-ai-contract-defaults.md` | 설정 계약, 허용값, 기본값 |
| `2026-06-16-dictation-ai-reference-index.md` | 외부 레퍼런스 인덱스 |

## 현재 기준선

| 축 | 현재 기준 |
| --- | --- |
| 한국어 STT | `faster-whisper + large-v3`, 준수한 성능 |
| 영어 STT | `faster-whisper + large-v3`, 준수한 성능 |
| 중국어 STT | `qwen3-asr-transformers + qwen3-asr-0.6b`, 준수한 성능 |
| 문장 경계 | SaT/wtpsplit, regex 운영 경로 폐기 |
| 확정 정책 | staged confirmation + `sentenceFinalizeAge=3` |
| 번역 | final transcript only |
| 중국어 window 시작점 | `windowSecondsZh=12`, `stepSecondsZh=1` |
| 영어/한국어 window 시작점 | `windowSecondsEn/Ko=7`, `stepSecondsEn/Ko=1` |

## 2026-06-17 재설계 기준 코드 정리

### 목적

`2026-06-16-dictation-ai-realtime-pipeline.md`를 기준으로 과거 실험에서 추가된 보정 경로가 운영 파이프라인과 벤치 하네스에 남아 있는지 검토했다.

### 제거한 경로

- raw/window, completed, pending 텍스트에 적용하던 반복 phrase collapse 재작성
- pending overrun을 completed 후보로 강제 승격하던 final trigger
- CJK staged 후보를 replacement 전에 1회 관측만으로 확정하던 `stable_cjk` 조기 확정 경로
- collapse 전용 성능 추적 bucket과 단위 테스트
- internal overlap 기반 delta 보정을 고정하던 legacy 품질 게이트 테스트

### 판단

- 반복 collapse와 pending 강제 승격은 SBD 모델 경계와 staged lifecycle을 우회한다.
- CJK 조기 replacement 확정은 `staged_confirmations`와 `sentenceFinalizeAge` 기준을 흐린다.
- 해당 경로들은 실제 로그에서 보였던 일부 중복을 줄이는 실험 흔적이지만, 재설계 기준의 최소 파이프라인 필수요소가 아니다.

### 검증

```text
./.venv/bin/python -m unittest \
  tests.unit.test_transcript_revision

./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py \
  --device cuda \
  --compute-type float16 \
  --output .tmp/eval/dictation-ai-sbd/latest.json
```

단위 테스트는 deterministic helper 회귀 검증으로 통과했다.
성능 추적 케이스는 SBD 벤치 리포트로 final/staged/pending lifecycle 지표를 출력한다.

```text
./.venv/bin/python -m py_compile \
  src/app/dictation_transcript_logic.py \
  src/app/dictation_window.py \
  tests/eval/dictation_ai/sbd_benchmark.py
```

이번 검증은 코드 정리 검증이다. 성능 판단용 CUDA/SaT 벤치 수치는 별도 실행 결과만 기준으로 삼는다.

후속 정리에서 `tests.unit.test_dictation_ai_sbd_benchmark`는 제거했다. 해당 테스트는 eval 벤치의 private lifecycle 함수를 다시 호출해 작은 벤치 하네스를 별도로 유지하는 구조였으므로, SBD 생명주기 성능 판단은 `tests/eval/dictation_ai/sbd_benchmark.py` 한 곳에서만 관리한다.

## 2026-06-17 CJK staged 교체 보류 최소 개선

### 문제

로그와 벤치에서 중국어 completed 후보가 한 chunk 안에 여러 개 나올 때 단일 `staged_sentence` 슬롯이 계속 교체됐다. 기존 staged 후보는 대부분 `unconfirmed_cjk`로 suppress되어 final까지 도달하지 못했다.

### 최소 변경

- `unconfirmed_cjk` replacement는 즉시 suppress/replace하지 않고 `stage_replace_deferred`로 보류한다.
- 보류는 chunk당 한 번만 `staged_age`를 증가시킨다.
- staged 후보가 age 기준을 채우면 기존 append-only final 경로로 확정한다.
- completed 후보 합성, overlap 접합, collapse 재작성은 다시 도입하지 않는다.

### CUDA/SaT 벤치 결과

조건:

```text
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
backend=sat
device=cuda
compute_type=float16
cases=24
```

변경 전:

```text
pass_rate=0.083
finalized=8
stage_start=809
finalized_per_stage_start=0.010
stage_replace=781
stage_replaced_unconfirmed=781
final_f1_avg=0.083
```

변경 후:

```text
pass_rate=0.083
finalized=63
stage_start=164
finalized_per_stage_start=0.384
stage_replace=532
stage_replace_deferred=451
stage_replaced_unconfirmed=81
final_f1_avg=0.106
```

판단:

- 실행은 정상이다.
- final 확정 수와 staged 대비 final 비율이 크게 개선됐다.
- pass rate는 그대로라 정답 기대치와 실제 final granularity는 추가 검토가 필요하다.
- 현재 개선은 구조적 최소 보완으로 유지하고, 다음 단계는 다중 staged lifecycle 설계 여부를 별도로 판단한다.

## 2026-06-17 최근 final 기반 중복 확정 억제 최소 개선

### 로그 관측

최근 `avc-whisper.log`에서 `Dictation AI transcript` 라인은 staged 표시도 포함하므로 final 중복 판단 기준으로 쓰면 안 된다. 실제 final 기준인 `받아쓰기 AI 문장 확정` 로그를 보면, 짧게 확정된 문장이 뒤 window에서 더 긴 문장으로 다시 등장하는 케이스가 있었다.

대표 케이스:

```text
최근 final: 对，经过了无数的龟毛，然后又怕发生跟外婆。
후속 후보: 对，经过了无数的规毛，然后又怕发生跟外婆家一样的事件，就不要点太多。
```

### 최소 변경

- 확정 직전에만 최근 final 저장소를 조회한다.
- 최근 final과 같은 후보는 final/translation 대상에서 제외한다.
- 최근 final의 확장 후보는 이미 확정된 prefix를 다시 내보내지 않고 suffix만 final로 확정한다.
- 후보 생성, SBD 경계, staged lifecycle에는 새 병합 규칙을 추가하지 않는다.

### CUDA/SaT 벤치 결과

조건:

```text
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
backend=sat
device=cuda
compute_type=float16
cases=24
```

직전 기준:

```text
pass_rate=0.083
finalized=63
stage_start=164
finalized_per_stage_start=0.384
final_f1_avg=0.106
finalize_recent_delta_trimmed=0
finalize_duplicate_suppressed=0
```

변경 후:

```text
pass_rate=0.083
finalized=62
stage_start=164
finalized_per_stage_start=0.378
final_f1_avg=0.118
finalize_recent_delta_trimmed=2
finalize_duplicate_suppressed=1
```

판단:

- 중복 final 후보를 줄이면서 final F1이 소폭 개선됐다.
- final 수는 1개 줄었지만 staged 대비 final 비율은 거의 유지됐다.
- 번역은 final sentence만 대상으로 하므로, 이 조정은 중복 번역 요청도 함께 줄인다.
- 과도한 생명주기 확장은 하지 않고 최근 final 저장소를 확정 직전 비교에만 사용한다.

### 의심 케이스 벤치 추가와 후보 단계 보완

추가 케이스:

```text
tests/eval/dictation_ai/sbd_text_cases.sample.jsonl
id=zh_log_recent_final_extension_delta_20260617_001
```

의도:

- 최근 final이 뒤 window에서 더 긴 문장으로 다시 등장할 때 기존 final prefix를 중복 확정하지 않는다.
- 확장 suffix는 문장 종결부호를 유지해 final-only 번역 대상이 될 수 있어야 한다.
- 의심 상황은 품질 게이트가 아니라 벤치 지표로 유지한다.

중간 결과:

```text
pass_rate=0.080
finalized=63
stage_start=166
finalized_per_stage_start=0.380
final_f1_avg=0.130
candidate_recent_final_delta_trimmed=0
```

관측:

- suffix 후보가 stage에 들어가기 전에 `committed_text` 기반 delta로 먼저 잘리면서 종결부호가 사라졌다.
- 결과적으로 `no_end_marker` 상태가 되어 final/translation 대상까지 가지 못했다.

보완:

- recent final 확장 후보의 suffix는 원 후보의 종결부호를 보존한다.
- stage 후보 생성 직전에도 최근 final 저장소를 한 번 조회해 suffix-only 후보를 만든다.
- SBD 경계나 completed 후보 합성은 추가하지 않는다.

보완 후 CUDA/SaT 벤치:

```text
pass_rate=0.120
finalized=68
stage_start=169
finalized_per_stage_start=0.402
stage_replace=511
stage_replace_deferred=432
stage_replaced_unconfirmed=79
final_f1_avg=0.141
candidate_recent_final_delta_trimmed=44
finalize_recent_delta_trimmed=2
finalize_duplicate_suppressed=1
```

추가 케이스 결과:

```text
case_pass=True
actual_final=[
  "对，经过了无数的龟毛，然后又怕发生跟外婆。",
  "家一样的事件就不要点太多。"
]
candidate_recent_final_delta_trimmed=3
```

판단:

- 문장 순서를 유지하면서 이미 확정된 prefix의 중복 final을 줄였다.
- 확장 suffix가 종결부호를 유지해 번역 대상 확정 조건을 만족할 수 있게 됐다.
- 변경은 최근 final 저장소를 이용한 후보 delta 산출에 한정되며, 과거의 pending/new 접합 또는 completed 합성 로직은 재도입하지 않았다.

### 추가 관측: 빵/계란 설명 중복 후보

사용자 관측:

```text
哎，很Q哎，风味面包，哇好可爱。
哎，粉丝啊，超级松软，蛋超级多，蛋是超多，有没有选？
哦，它蛋超多哎，煮丝啊，超级松软，蛋超级多，特别超多。

再点一颗
然后蛋煎很好，大蒜土司，然后蛋。
超级松软，但超级多，特别超多，有没有觉得？
再点一颗
红蒜煎很好，大蒜土司，然后蛋，然后加上脆皮根，然后再加上它上面又有那个蒜香美奶汁，就是叫蒜头组合。
```

추가 케이스:

```text
tests/eval/dictation_ai/sbd_text_cases.sample.jsonl
id=zh_log_duplicate_bread_egg_fragment_20260617_001
```

보완:

- 최근 final과 후보의 CJK 공통 구간이 prefix가 아니라 내부에 있어도, matching block 누적 coverage가 충분하면 중복 후보로 본다.
- 후보가 이미 확정된 recent final의 반복 변형이면 stage 진입 전에 suppress한다.
- 짧은 fragment 자체를 final로 강제하지 않는다.

CUDA/SaT 벤치:

```text
cases=26
pass_rate=0.115
finalized=68
stage_start=172
finalized_per_stage_start=0.395
stage_replace=513
stage_replace_deferred=429
stage_replaced_unconfirmed=84
final_f1_avg=0.153
candidate_recent_final_delta_trimmed=65
candidate_duplicate_suppressed=146
```

추가 케이스 결과:

```text
case_pass=False
final_score_f1=0.444
candidate_recent_final_delta_trimmed=2
candidate_duplicate_suppressed=3
actual_final=[
  "哎，很Q哎，风味面包，哇好可爱。",
  "哎，粉丝啊，超级松软，蛋超级多，蛋是超多，有没有选？",
  "红蒜煎很好，大蒜土司，然后蛋，然后加上脆皮根，然后再加上它上面又有那个蒜香美奶汁，就是叫蒜头组合。"
]
```

판단:

- `蛋超级多...` 계열의 유사 중복 후보는 recent final 저장소로 억제됐다.
- `大蒜土司...` 계열은 앞 문장이 final까지 가지 않고 staged에 머문 상태라 recent final 저장소로는 trim되지 않는다.
- staged 후보까지 별도 순서 버퍼로 확장하면 과거 병합/재구성 로직으로 되돌아갈 위험이 있으므로 이번 패치에서는 추가하지 않는다.
- 이 케이스는 중복 후보 억제와 확정 누락이 함께 있는 성능 벤치 케이스로 유지한다.

### 추가 관측: 종로/광장시장 이동 설명 확정 누락

사용자 관측:

```text
喝完咖啡，准备前往中路三街。
我们要坐紫色，也就是从马步站坐到中路三街之后，走到中路街去广场市场拜。
...
好，我们现在在中路五街了。
对，人好多哦。
人超多。
街上蛮多人下车的。
我的Tmoney。
现在寻找出口中。
```

추가 케이스:

```text
tests/eval/dictation_ai/sbd_text_cases.sample.jsonl
id=zh_log_missing_jongno_market_transfer_20260617_001
```

관측:

- `对，人好多哦。`, `人超多。`, `街上蛮多人下车的。`, `我的Tmoney。` 같은 짧은 CJK 후보가 다음 completed 후보에 밀리면서 confirmation을 채우기 전에 교체됐다.
- `short_cjk` 후보는 age 기준 replacement에서 final 품질 게이트에 막히므로, 너무 빨리 `aged` replacement로 넘어가면 확정 누락이 늘어난다.

보완:

- 종결부호가 있는 `short_cjk` 후보는 replacement 직전 제한된 추가 chunk 동안 `unconfirmed_cjk`로 보류한다.
- 같은 후보가 반복 관측되면 confirmation으로 final될 수 있게 한다.
- `no_end_marker`가 있는 짧은 CJK 후보는 추가 보류 대상이 아니다.
- 별도 ordered staged queue는 도입하지 않는다.

CUDA/SaT 벤치 비교:

```text
변경 전:
cases=27
pass_rate=0.111
finalized=71
stage_start=184
finalized_per_stage_start=0.386
stage_replaced_unconfirmed=92
final_f1_avg=0.154

변경 후:
cases=27
pass_rate=0.111
finalized=86
stage_start=130
finalized_per_stage_start=0.662
stage_replaced_unconfirmed=21
final_f1_avg=0.216
```

추가 케이스 결과:

```text
actual_final=[
  "开完咖啡，准备前往中路三街。",
  "三街，我们要坐紫色，也就是从马步站坐到中路三街之后，走到中路街去广场市场摆。",
  "好，我们现在在中路五街了。",
  "人超多。",
  "街上蛮多人下车的。"
]
actual_staged="我的T-money。"
```

판단:

- 짧은 CJK 후보의 확정 누락은 일부 개선됐다.
- 전체 벤치에서 final 수, staged 대비 final 비율, final F1이 모두 개선됐다.
- `我的Tmoney。`, `现在寻找出口中。`처럼 뒤 문장 순서를 더 잘 살리려면 단일 staged slot 한계를 다뤄야 한다.
- ordered staged queue는 설계 변경 폭이 크므로 이번 패치에서는 도입하지 않고, 벤치 케이스로 남겨 추후 근거로 삼는다.

### 추가 관측: 팬케이크 설명 확정 누락과 유사도 기반 age

사용자 관측:

```text
一来了，其实每一餐都蛮多人哎。煎饼。好多。
好好大饭，好大。
之前一来看到最多菜的就是煎饼，各种煎饼。
我的菜，等一下就可以吃煎饼了。现在人潮反而汹涌。真的。
```

추가 케이스:

```text
tests/eval/dictation_ai/sbd_text_cases.sample.jsonl
id=zh_log_missing_pancake_crowd_fragment_20260617_001
```

원인 판단:

- 기존 age/confirmation은 일부 짧은 CJK correction을 같은 token-sentence로 보지 못했다.
- 예: `对的，还超多。` ↔ `超多！`, `好好大饭，好大。` ↔ `好好大，好大。`, `现在人潮反而凶。` ↔ `现在人潮反而汹涌。`
- 유사 후보가 revision으로 인정되지 않으면 staged 후보는 갱신되지 않고, age만 오르다가 다른 completed 후보에 밀린다.

보완:

- CJK token-sentence 유사도 기준을 추가했다.
- 짧은 CJK containment, 소폭 글자 교정, 짧은 mixed CJK/Latin correction은 같은 revision 후보로 본다.
- preferred 문장이 소폭 교정된 수준이면 confirmation을 리셋하지 않고 누적한다.
- 큰 확장 후보는 기존처럼 confirmation을 리셋해 과확정을 막는다.

CUDA/SaT 벤치 비교:

```text
변경 전:
cases=28
pass_rate=0.107
finalized=86
stage_start=132
finalized_per_stage_start=0.652
stage_replaced_unconfirmed=22
final_f1_avg=0.209

변경 후:
cases=28
pass_rate=0.107
finalized=92
stage_start=134
finalized_per_stage_start=0.687
stage_replaced_unconfirmed=18
final_f1_avg=0.219
```

관련 케이스 결과:

```text
zh_log_missing_jongno_market_transfer_20260617_001:
  추가 final: "对，人好多哦。"
  추가 final 유지: "人超多。", "街上蛮多人下车的。"
  actual_staged: "现在寻找出口中。"

zh_log_missing_pancake_crowd_fragment_20260617_001:
  actual_final: ["哎，煎饼。"]
  actual_staged: "好多。"
```

판단:

- 유사도 기반 age/confirmation은 전체 지표와 일부 누락 케이스를 개선했다.
- 팬케이크 케이스는 여러 completed 후보가 한 window에 반복 등장하는데 단일 staged slot이 하나만 붙잡기 때문에 대부분 누락된다.
- 이 문제는 유사도 기준만으로 완전 해결되지 않으며, ordered staged queue 또는 다중 staged 후보 관리가 필요한 별도 설계 이슈다.
- 이번 패치에서는 과도한 구조 변경을 피하고, 케이스를 벤치에 남겨 다음 설계 판단 근거로 사용한다.

### 추가 보완: ordered staged queue와 chunk aging guard

로그 판단:

- 한 chunk에서 SaT/SBD가 여러 completed 후보를 순서대로 생성한다.
- 기존 단일 staged slot은 active 후보와 다른 CJK 후보를 `unconfirmed_cjk`로 보류하면서도 실제로는 후보를 보존하지 못해 누락을 만들었다.
- 확정된 final은 append-only로 유지해야 하므로, final 이후 재병합이 아니라 final 전 staged 후보만 순서대로 관리해야 한다.

보완:

- active staged 뒤에 제한된 `staged_sentence_queue`를 둔다.
- active와 다른 CJK completed 후보는 폐기하지 않고 queue에 저장한다.
- queue 안의 같은 token-sentence revision은 confirmation/age를 누적한다.
- active staged가 final/suppressed 되면 queue에서 다음 후보를 순서대로 승격한다.
- 같은 chunk에서 이미 revision/replacement로 age가 오른 후보는 chunk 말미 aging에서 제외한다.

CUDA/SaT 벤치 비교:

```text
유사도 기반 age 기준:
cases=28
pass_rate=0.107
finalized=92
stage_start=134
finalized_per_stage_start=0.687
final_f1_avg=0.219

ordered staged queue:
cases=28
pass_rate=0.143
finalized=106
stage_start=164
finalized_per_stage_start=0.646
final_f1_avg=0.231
stage_queue_enqueue=236
stage_queue_promote=123
stage_queue_revision=371
stage_queue_drop_oldest=27
```

주요 케이스:

```text
zh_log_missing_pancake_crowd_fragment_20260617_001:
  변경 전 actual_final: ["哎，煎饼。"]
  변경 후 actual_final:
    "一来了，其实每一餐都蛮多人哎。"
    "哎，煎饼。"
    "好多。"
    "好好大饭，好大。"
    "之前一来看到最多菜的就是煎饼，各种煎饼。"
    "我的菜，等一下就可以吃煎饼了。"

zh_log_missing_jongno_market_transfer_20260617_001:
  변경 후 actual_final:
    "开完咖啡，准备前往中路三街。"
    "我们要坐紫色，也就是从马步站坐到中路三街之后，走到中路街去广场市场拜。"
    "好，我们现在在中路五街了。"
    "对，人好多哦。"
    "人超多。"
    "街上蛮多人下车的。"
    "我的T蛮。"
    "我的Tmoney。"
```

판단:

- 확정 누락은 줄었다.
- `finalized`와 `final_f1_avg`는 개선됐다.
- queue 도입으로 `stage_start`가 증가하므로 `finalized_per_stage_start`는 단독 성공 지표로 쓰기 어렵다.
- `我的T蛮。`처럼 오인식/중간 fragment가 final로 올라오는 리스크가 남아 있어, 다음 튜닝은 queue final 품질과 recent final 유사 억제를 함께 봐야 한다.

### 추가 보완: 초단편 CJK stage 후보 차단

로그 판단:

- chunk 704~720 부근에서 `们`, `不 然 他`, `哎` 같은 CJK 초단편이 staged로 시작된 뒤 다음 completed 후보를 `unconfirmed_cjk`로 막는 패턴이 반복됐다.
- chunk 201~214 부근에서도 staged queue가 동작하더라도 `好去。`, `八`, `等 一 下 等 等` 같은 저가치 fragment가 active staged나 queue를 점유하면서 `raw_without_final`이 증가했다.
- 현재 실행은 `translation_enabled=False`였으므로 번역 누락이 아니라 final-only 번역 대상으로 넘길 final 문장 생성 단계의 병목이다.

보완:

- 문장 종료 부호가 없고 CJK 단위가 3개 이하인 후보를 `low_value_cjk_fragment`로 진단한다.
- 이 flag는 stage 후보 진입과 final 번역 대상을 차단한다.
- 케이스별 문구 규칙은 추가하지 않고 기존 품질 flag/metric 경로에 통합했다.
- `zh_log_low_value_cjk_stage_blocks_queue_20260617_001`을 SBD 벤치 케이스로 추가했다.

기대 관측:

- `stage_candidate_quality_low_value_cjk_fragment` 증가가 보이면 초단편 후보가 stage/queue 점유 전에 제거된 것이다.
- `raw_without_final`과 `stage_queue_drop_oldest`가 함께 줄어드는지 CUDA/SaT 벤치로 확인한다.

CUDA/SaT 벤치 결과:

```text
cases=29
pass_rate=0.138
finalized=109
stage_start=165
finalized_per_stage_start=0.661
final_f1_avg=0.223
stage_candidate_quality_low_value_cjk_fragment=15
stage_queue_enqueue=230
stage_queue_promote=122
stage_queue_revision=377
stage_queue_drop_oldest=23
```

판단:

- 초단편 CJK 후보는 실제로 15회 차단되어 stage/queue 오염을 줄이는 근거가 생겼다.
- 새로 추가한 `zh_log_low_value_cjk_stage_blocks_queue_20260617_001` 케이스는 여전히 final 1개만 생성했고, active staged 뒤에 queue가 쌓였다.
- 남은 병목은 초단편 후보보다 active staged 확정/교체 소비 지연에 가깝다. 추가 로직을 늘리기 전, 이 병목을 별도 벤치 케이스로 추적한다.

### 추가 보완: CJK revision 변경 시 age 재시작

로그 판단:

- GS25 구간에서 `那个咖啡二十五是做咖啡。`가 `那个咖啡二十五是做咖啡的然后这边。`으로 바뀌었다.
- 이때 confirmation은 1로 리셋됐지만 age는 누적되어 `aged` final이 발생했다.
- 결과적으로 아직 이어지는 열린 꼬리 문장이 final-only 번역 대상으로 넘어갈 수 있었다.

보완:

- CJK revision 내용이 바뀌고 similarity/internal stability 기준으로 confirmation 보존이 되지 않는 경우 staged age도 0으로 되돌린다.
- queue 안의 revision도 같은 기준으로 age를 재시작한다.
- 관측 지표로 `stage_revision_age_reset`, `stage_queue_revision_age_reset`을 추가했다.
- `zh_log_revision_age_reset_gs25_20260617_001`을 SBD 벤치 케이스로 추가했다.

CUDA/SaT 벤치 결과:

```text
cases=30
pass_rate=0.133
finalized=103
stage_start=159
finalized_per_stage_start=0.648
final_f1_avg=0.239
stage_revision_age_reset=23
stage_queue_revision_age_reset=45
```

주요 케이스:

```text
zh_log_revision_age_reset_gs25_20260617_001:
  actual_final:
    "我们现在进来了一间GS二十五，就是这边的便利超商。"
    "但这件很特别的是，它有非常多全自动的。"
  actual_staged:
    "那边那个是做披萨的，然后那边那个咖啡二十五是做咖啡的，然后这边这一个它。"
```

판단:

- 전체 final 수는 109에서 103으로 줄었지만 `final_f1_avg`는 0.223에서 0.239로 올랐다.
- 이는 확정 누락 개선이 아니라 잘못된 조기 확정과 번역 대상 오염을 줄인 개선이다.
- active staged 뒤에 queue가 쌓이는 문제는 여전히 남아 있으므로 다음 튜닝은 queue 소비 조건을 별도 벤치로 확인한다.

### 반복 튜닝: staged queue 크기와 승격 직후 확정

검토한 변경:

- queue에서 승격된 후보가 이미 확정 조건을 만족하면 즉시 final로 소비하는 로직을 시험했다.
- `finalized`는 106으로 늘었지만 `final_f1_avg`가 0.239에서 0.236으로 낮아져 폐기했다.

채택한 변경:

- `MAX_STAGED_SENTENCE_QUEUE`를 8에서 12로 늘렸다.
- 16도 시험했지만 12와 `final_f1_avg`가 같아 더 보수적인 12를 채택했다.

CUDA/SaT 벤치 비교:

```text
revision age reset:
finalized=103
final_f1_avg=0.239
stage_queue_drop_oldest=23

queue immediate finalize trial:
finalized=106
final_f1_avg=0.236
stage_queue_ready_finalize=24

queue size 12:
finalized=107
final_f1_avg=0.256
stage_queue_drop_oldest=2

queue size 16:
finalized=108
final_f1_avg=0.256
stage_queue_drop_oldest=0

benchmark expectation fix:
pass_rate=0.200
final_f1_avg=0.263

confirm chunks 2 trial:
pass_rate=0.133
finalized=129
final_f1_avg=0.277
```

판단:

- 승격 직후 확정은 final 수만 늘리고 품질 지표를 낮춰 폐기했다.
- queue 크기 12는 drop_oldest를 크게 줄이고 `final_f1_avg`를 올렸다.
- 16은 지표상 추가 이점이 없어 운영 지연과 메모리 증가를 피하기 위해 채택하지 않았다.
- `orange_juice`와 `gs25` 케이스는 final 결과가 의도와 맞는데 staged/pending 기대값이 파이프라인 정의와 달라 pass를 깨고 있어 벤치 기대값을 정정했다.
- confirmation 기준 2는 final 수와 F1은 올렸지만 pass_rate를 낮추고 `supper`, `gs25` 케이스를 실패로 바꿔 폐기했다.

### 정리: token-sentence 유사도 임계값 policy화

검토:

- CJK token-sentence revision 판정과 confirmation 보존 기준에는 ratio, common-run, coverage, length-delta 임계값이 함수 안에 직접 들어 있었다.
- 반복 벤치로 튜닝하려면 어떤 임계값으로 나온 결과인지 리포트에 남아야 한다.

보완:

- CJK revision similarity, confirmation preserve, 일반 revision fallback 임계값을 `dictation_transcript_logic.py` 상단 상수로 분리했다.
- 값 자체는 변경하지 않았다.
- SBD 벤치 리포트에 `revision_similarity_policy`를 기록한다.
- 이 값들은 아직 GUI/사용자 설정으로 노출하지 않고 내부 튜닝 policy로 관리한다.

### 반복 튜닝: revision similarity 상수 조합 비교

목적:

- 중복 확정과 확정 누락이 리비전 유사도 상수 변경만으로 개선되는지 확인한다.
- 기본 운영값을 직접 바꾸지 않고 `AVC_DICTATION_*` 환경변수로 동일 벤치에서 조합을 비교한다.

CUDA/SaT 벤치 비교:

```text
baseline:
pass_rate=0.200
final_f1_avg=0.263
final_precision_avg=0.279
final_recall_avg=0.255
finalized=107
false_positive=82
false_negative=110

permissive:
pass_rate=0.200
final_f1_avg=0.257
final_precision_avg=0.272
final_recall_avg=0.250
finalized=112
false_positive=88
false_negative=111

strict:
pass_rate=0.200
final_f1_avg=0.260
final_precision_avg=0.278
final_recall_avg=0.251
finalized=106
false_positive=82
false_negative=111

tail/prefix relaxed:
pass_rate=0.200
final_f1_avg=0.263
final_precision_avg=0.279
final_recall_avg=0.255
finalized=109
false_positive=84
false_negative=110

confirm preserve strict:
pass_rate=0.200
final_f1_avg=0.263
final_precision_avg=0.279
final_recall_avg=0.255
finalized=107
false_positive=82
false_negative=110

CJK length delta/tail position relaxed:
pass_rate=0.167
final_f1_avg=0.256
final_precision_avg=0.267
final_recall_avg=0.256
finalized=113
false_positive=88
false_negative=110

CJK length delta strict:
pass_rate=0.200
final_f1_avg=0.263
final_precision_avg=0.279
final_recall_avg=0.255
finalized=107
false_positive=82
false_negative=110
```

판단:

- permissive 조합은 final 수를 늘렸지만 false positive와 false negative가 모두 악화되어 폐기한다.
- strict 조합은 확정 수를 줄였지만 false negative를 줄이지 못해 폐기한다.
- tail/prefix 완화는 F1은 유지했지만 false positive가 늘어 기본값 대비 이점이 없다.
- confirmation 보존 강화와 CJK length delta 강화는 기준값과 동등해 채택 근거가 없다.
- CJK length delta/tail position 완화는 pass rate와 precision을 낮춰 폐기한다.
- 결론적으로 현재 벤치에서는 리비전 관리 상수 변경만으로 중복 확정과 확정 누락이 개선되지 않았다. 기본 상수는 유지하고, 다음 개선은 상수 튜닝보다 final 전 최근 확정 문장 유사도 비교와 staged queue 소비 설계 검토가 우선이다.

### 추가 관측: 한국어 주행 로그 중복 확정

관측 입력:

```text
오 주행하죠?
지금 3배속이니까 1분의 1 속도로 보시면 요게 정...
이게 정상속도입니다
지금 3배속 이니까 1분의 1 속도로 보시면 요게 정상 속도입니다
뭐 그렇게 빠른 건 아니에요
일단 도심도로 지금 3배속이니까 1분의 1속도로 보시면 이게 정상속도입니다
그렇게 빠른건 아니에요
일단 도심도로 이런식으로 가고요
이게 정상 속도입니다
일단 도심도로 이런 식으로 가고요
```

보완:

- `ko_log_duplicate_driving_speed_fragment_20260617_001`을 SBD 벤치 케이스로 추가했다.
- 문장 확정 규칙은 언어 코드별 예외로 만들지 않는다.
- 최근 final 후보 비교는 token-sentence compact 유사도 기반 공통 규칙으로 정리했다.

CUDA/SaT 벤치 결과:

```text
cases=31
pass_rate=0.194
finalized=112
stage_start=169
finalized_per_stage_start=0.663
final_f1_avg=0.257

ko_log_duplicate_driving_speed_fragment_20260617_001:
case_pass=false
precision=0.200
recall=0.250
f1=0.222
candidate_duplicate_suppressed=4
final_quality_no_end_marker=3
```

판단:

- 추가한 공통 recent-final compact 유사도 규칙으로 중복 후보 4개는 억제됐다.
- 하지만 `요게 정...`, `이게 정상속도입니다`, `일단 도심도로 지금 3배속이니까` 같은 미완성 후보가 먼저 final로 나가 케이스는 아직 실패한다.
- 다음 개선은 언어별 suffix 예외가 아니라 종결 신호 없는 staged 후보의 replacement-before-final 조건을 공통 규칙으로 재검토하는 방향이다.

### 추가 관측: 한국어 경로 기억 로그의 누락+중복 복합 실패

로그 근거:

```text
.tmp/logs/avc-whisper.log.1
23:18:01 chunk=4 pending='...내가 갔던 길을 또 가야 되는'
23:18:02 chunk=5 pending='...내가 갔던 길을 또 가야 되는 경우 많잖아요'
23:18:03 chunk=6 final reason=confirmed quality_flags=no_end_marker
23:18:05 chunk=8 stage_start='대부분 운전자들은 갔던 길'
23:18:06 chunk=9 stage_replace decision=open_korean_clause
23:18:06 chunk=9 final reason=next_completed quality_flags=no_end_marker
23:18:11 chunk=14 stage_replace decision=open_korean_clause
23:18:11 chunk=14 final reason=next_completed
23:18:13 chunk=16 final reason=next_completed
23:18:14 chunk=17 final reason=next_completed quality_flags=no_end_marker
```

보완:

- `ko_log_duplicate_missing_route_memory_fragment_20260617_001`을 SBD 벤치 케이스로 추가했다.
- 이 케이스는 단순 중복이 아니라 누락, 조각 final, 최근 final 억제가 동시에 나타나는 복합 실패로 분류한다.

CUDA/SaT 벤치 결과:

```text
cases=32
pass_rate=0.188
finalized=116
stage_start=174
finalized_per_stage_start=0.667
final_f1_avg=0.249

ko_log_duplicate_missing_route_memory_fragment_20260617_001:
case_pass=false
precision=0.000
recall=0.000
f1=0.000
false_positive=4
false_negative=4
finalized=4
stage_finalize_before_replace=4
stage_replace_decision_open_korean_clause=1
stage_replaced_unconfirmed=1
stage_revision=7
stage_revision_changed=4
candidate_duplicate_suppressed=4
final_quality_no_end_marker=1
```

실제 final:

```text
이런 것들을 위주로 하는데 그런데 만약에 내가 갔던 길을 또 가야 되는 경우 많잖아요.
대부분 운전자들은 갔던 길 또 가니까 집회사 집회사입니다
아니 무슨 놀이공원 집회사 집회사입니다.
그래서 갔던 길을 기억하고 있다가 그 길을 똑같이 가는 거 이게 되게 중요하거든요.
```

판단:

- 최근 final 억제는 일부 동작해 `candidate_duplicate_suppressed=4`를 만들지만, 이미 잘못 final된 조각을 되돌릴 수 없다.
- 핵심 원인은 `stage_finalize_before_replace=4`다. 다음 completed 후보가 들어올 때 기존 staged를 final로 밀어내는 규칙이 open clause와 no-end-marker 후보를 충분히 보류하지 못한다.
- `stage_replace_decision_open_korean_clause=1`과 `stage_replaced_unconfirmed=1`은 일부 조각이 final 대신 교체 폐기됐음을 보여준다. 하지만 다른 후보들은 `next_completed`로 final되어 중복과 누락이 동시에 생겼다.
- 따라서 다음 개선은 언어별 예외가 아니라 공통 규칙으로 `no_end_marker`/open-clause 성격의 staged 후보가 replacement-before-final을 통과하지 못하게 하는 방향이어야 한다.

### 2026-06-17 추가 관측: `next_completed`와 짧은 delta 조각 final

로그 근거:

```text
.tmp/logs/avc-whisper.log.1
23:25:10 chunk=32 final reason=next_completed quality_flags=no_end_marker
23:25:13 chunk=35 final reason=next_completed quality_flags=no_end_marker
23:26:33 chunk=115 final reason=next_completed
23:26:36 chunk=118 final reason=next_completed
23:28:09 chunk=11 final reason=next_completed quality_flags=no_end_marker
23:28:12 chunk=14 final reason=next_completed quality_flags=no_end_marker
23:30:51 chunk=174 final reason=next_completed text='들죠'
23:30:52 chunk=175 final reason=next_completed text='들죠'
23:30:53 chunk=176 final reason=next_completed quality_flags=no_end_marker
23:39:43 chunk=707 final reason=next_completed quality_flags=no_end_marker
23:40:27 chunk=750 final reason=next_completed quality_flags=no_end_marker
```

보강한 SBD 벤치 케이스:

- `ko_log_missing_ultrasonic_reinsert_fragment_20260617_001`
- `ko_log_duplicate_li_auto_xiaomi_fragment_20260617_001`
- `ko_log_duplicate_tesla_global_direction_fragment_20260617_001`
- `ko_log_duplicate_short_delta_rear_camera_view_20260617_001`
- `ko_log_duplicate_mobiline_breakup_fragment_20260617_001`
- `ko_log_mixed_fsd_chip_production_fragment_20260617_001`
- `ko_log_trailing_ellipsis_luminar_fragment_20260618_001`
- `ko_log_mixed_lidar_camera_sensor_fragment_20260618_001`
- `ko_log_alpha_mayo_no_end_fragment_20260618_001`
- `ko_log_distillation_context_reorder_fragment_20260618_001`

보수적 로직 변경:

- 종결 신호가 없는 staged 후보는 required confirmation 전에는 `next_completed`로 final 확정하지 않는다.
- final 직전 committed prefix 제거 결과가 원 staged보다 크게 짧아진 조각이고 종결 신호가 없으면 `finalize_short_delta_suppressed`로 계측하고 final 출력하지 않는다.
- `duplicate_or_suffix`, `partial_preserve`, `aged` replacement 경로도 종결 신호 없는 미확인 staged 후보를 final로 확정하지 않는다.
- 이 규칙은 한국어/중국어/영어 예외가 아니라 공통 sentence lifecycle 규칙이다.

CUDA/SaT 벤치 결과:

```text
cases=36
pass_rate=0.167
finalized=121
stage_start=215
finalized_per_stage_start=0.563
final_f1_avg=0.224
```

추가 실험:

- `ko_log_duplicate_mobiline_breakup_fragment_20260617_001`를 추가해 케이스 수가 37개가 되었다.
- replacement-before-final 전체에 반복 confirmation 또는 age 누적을 요구하는 강한 게이트를 시험했다.
- 결과는 `cases=37`, `finalized=114`, `finalized_per_stage_start=0.451`, `final_f1_avg=0.209`로 악화되었다.
- 특히 `ko_log_duplicate_mobiline_breakup_fragment_20260617_001`에서 final이 전부 막혀 확정 누락이 커졌다.
- 따라서 강한 confirmation/age 게이트는 폐기하고, replacement 경로의 `no_end_marker` 미확정 final 차단만 유지한다.
- `ko_log_mixed_fsd_chip_production_fragment_20260617_001`를 추가해 케이스 수가 38개가 되었다.
- 이 케이스에서는 최근 final이 후보 suffix로 다시 붙어 `... 하는 건데 왜냐하면 삼성전자 있죠?`처럼 중복 확정되는 현상이 관측되었다.
- token-sentence suffix 유사도 기반으로 최근 final suffix를 제거하도록 보정했다.
- CUDA/SaT 벤치 결과는 `cases=38`, `pass_rate=0.158`, `finalized=127`, `finalized_per_stage_start=0.479`, `final_f1_avg=0.217`이다.
- 신규 케이스에서 잘못된 suffix 반복 final은 제거됐지만, 기대 문장으로 확정되지는 않아 확정 누락은 남았다.
- 2026-06-18 00:01 로그에서 `야 너 뭐 또 모르면서 루미나...`가 `next_completed`로 final되는 현상을 관측했다.
- `...`/`…`로 끝나는 STT 후보는 실제 문장 종료가 아니라 다음 window에서 확장되는 미완성 후보로 다루도록 `trailing_ellipsis` 품질 flag를 추가했다.
- `ko_log_trailing_ellipsis_luminar_fragment_20260618_001`는 final F1 1.0으로 개선됐고, 39케이스 CUDA/SaT 벤치는 `pass_rate=0.154`, `finalized=130`, `finalized_per_stage_start=0.478`, `final_f1_avg=0.239`를 기록했다.
- 같은 모니터링 구간에서 `ko_log_mixed_lidar_camera_sensor_fragment_20260618_001`도 추가했다. 이 케이스는 뒤 문장들이 먼저 final되고, 첫 문장이 `를 막 찍고...`처럼 앞부분이 잘린 채 나중에 확정되는 순서 뒤집힘 계열이다.
- 40케이스 CUDA/SaT 벤치는 `pass_rate=0.150`, `finalized=133`, `finalized_per_stage_start=0.477`, `final_f1_avg=0.233`이다. `lidar` 케이스는 아직 final F1 0.0이므로 다음 순서 관리 개선 근거로 남긴다.
- 2026-06-18 00:06 로그에서 `ko_log_alpha_mayo_no_end_fragment_20260618_001`, `ko_log_distillation_context_reorder_fragment_20260618_001`를 추가했다.
- `alpha_mayo`는 짧은 no-end-marker 후보가 `next_completed`로 final되고 뒤 문장이 pending/staged로 밀리는 유형이다.
- `distillation`은 여러 completed 후보가 한 window 안에서 순서가 재배치되며 핵심 문장과 문맥 fragment가 뒤섞이는 유형이다.
- 42케이스 CUDA/SaT 벤치는 `pass_rate=0.143`, `finalized=136`, `finalized_per_stage_start=0.458`, `final_f1_avg=0.222`이다.
- 현재 코드 기준 `alpha_mayo`는 no-end-marker 중복 final은 막히지만 기대 문장까지 확정하지 못해 누락으로 남는다.
- 현재 코드 기준 `distillation`은 질문 문장들은 확정하지만 `디스트릴레이션이라고 해서 증류라는 걸 하죠`가 staged에 남아 final 누락으로 남는다.
- 2026-06-18 00:10 로그에서 `ko_log_repeated_overrun_level4_fragment_20260618_001`를 추가했다. 과거 실행에서는 `pending_overrun=long_no_boundary` 뒤 700자 이상의 반복 후보가 final됐지만, 현재 코드 기준 벤치에서는 거대 반복 final은 막히고 긴 staged가 확정되지 않는 누락으로 남는다.
- 43케이스 CUDA/SaT 벤치는 `pass_rate=0.140`, `finalized=136`, `finalized_per_stage_start=0.453`, `final_f1_avg=0.217`이다.
- 같은 로그 구간에서 `ko_log_mixed_ai_stock_allocation_fragment_20260618_001`를 추가했다. 이 케이스는 `AI발 주식시장` 문장이 앞선 `채권도 투자하고...` 조각과 뒤섞여 final되고, 이후 `실제로 최근에 다른 투자처의 자금들을...`처럼 최근 final suffix가 다른 문맥과 결합되는 유형이다.
- 44케이스 CUDA/SaT 벤치는 `pass_rate=0.136`, `finalized=140`, `finalized_per_stage_start=0.459`, `final_f1_avg=0.212`이다. 신규 케이스는 final F1 0.0이며, `candidate_recent_final_delta_trimmed=2`, `candidate_duplicate_suppressed=4`가 관측됐지만 순서가 섞인 긴 `next_completed` final은 아직 남는다.
- terminal-tail revision split을 추가해 종결부호가 있는 staged 문장의 tail이 다음 후보 뒤쪽에 재삽입되는 경우를 같은 문장의 revision으로 병합하지 않도록 했다. 이 변경은 `ko_log_mixed_ai_stock_allocation_fragment_20260618_001`에서 첫 문장 `우리가 채권도 투자하고 금도 투자하고 여러 투자처들이 있잖아요.`를 보존한다.
- 같은 패치에서 committed prefix 제거 뒤 남는 짧은 no-end 조각 억제를 `confirmed` 계열 final에도 적용했다. 단, age 기반 확정까지 억제하면 중국어 `zh_log_missing_jongno_market_transfer_20260617_001` F1이 `0.353 -> 0.125`로 악화되어 age 경로는 제외했다.
- 채택한 조합의 44케이스 CUDA/SaT 벤치는 `pass_rate=0.136`, `finalized=141`, `finalized_per_stage_start=0.461`, `final_f1_avg=0.224`이다.
- 개선된 케이스는 `zh_log_missing_restroom_fragment_20260617_001` F1 `0.000 -> 0.250`, `ko_log_mixed_ai_stock_allocation_fragment_20260618_001` F1 `0.000 -> 0.286`이다. `stage_revision_terminal_tail_split=3`, `finalize_short_delta_suppressed=1`이 관측됐다.
- 2026-06-18 00:22 로그에서 `ko_log_short_delta_treasury_investor_fragment_20260618_001`를 추가했다. `기관이에요`, `문제는` 같은 짧은 no-end 조각과 이전 pending 접두어 `근데`가 앞 문장에 붙는 순서 혼입이 함께 관측된 케이스다.
- 45케이스 CUDA/SaT 벤치는 `pass_rate=0.133`, `finalized=146`, `finalized_per_stage_start=0.465`, `final_f1_avg=0.219`이다.
- 신규 케이스는 final F1 0.0이며, 실제 출력은 `근데 의미는 중앙은행은...`처럼 pending 접두어가 앞 문장에 섞였다. 이 문제는 short-delta 억제만으로 해결되지 않고, pending/staged 순서 일관성 판단이 필요하다.
- 2026-06-18 00:24 로그에서 `ko_log_short_terminal_overseas_demand_fragment_20260618_001`를 추가했다. `아까 해외.` 같은 짧은 terminal fragment가 긴 staged 후보를 밀어내고, 뒤이어 `해외 쪽의 수요가... 아까 해외 중앙은행...`처럼 문맥이 결합되는 유형이다.
- 46케이스 CUDA/SaT 벤치는 `pass_rate=0.130`, `finalized=150`, `finalized_per_stage_start=0.469`, `final_f1_avg=0.214`이다.
- 짧은 terminal fragment가 긴 staged를 교체하지 못하게 queue로 보류하는 실험을 했다. 결과는 `final_f1_avg=0.215`로 소폭 상승했지만 `stage_replace_deferred_short_terminal=65`로 너무 넓게 발동했고, 신규 `overseas_demand` 케이스 자체는 final F1 0.0으로 남았다.
- 따라서 short-terminal defer 실험은 폐기하고, 케이스만 벤치 근거로 남긴다. 다음 개선은 단순 길이/종결부호 조건이 아니라 pending/staged 순서 혼입을 직접 식별하는 방향이어야 한다.
- 2026-06-18 00:31 로그에서 `ko_log_mixed_bond_manager_fragment_20260618_001`를 추가했다. `좋은 재료가 없습니다.`가 이미 final된 뒤, 다음 후보 suffix에 `좋은 재료 없습니다.` tail이 다시 붙어 `그래서 채권 매니저들 사이에서는 당연히 좋은 재료 없습니다.`로 확정되는 유형이다.
- 47케이스 CUDA/SaT 벤치는 `pass_rate=0.128`, `finalized=153`, `finalized_per_stage_start=0.472`, `final_f1_avg=0.222`이다.
- 최근 final 전체가 아니라 최근 final의 짧은 tail이 후보 suffix로 재삽입되는 경우도 앞쪽 delta만 남기도록 보완했다.
- 보완 후 47케이스 CUDA/SaT 벤치는 `pass_rate=0.128`, `finalized=153`, `finalized_per_stage_start=0.474`, `final_f1_avg=0.228`이다.
- 개선된 케이스는 `ko_log_mixed_bond_manager_fragment_20260618_001` 하나로, final F1이 `0.571 -> 0.857`로 올랐다. 다른 케이스의 F1 하락은 관측되지 않았다.
- 2026-06-18 00:35 로그에서 `ko_log_mixed_goods_economy_fragment_20260618_001`를 추가했다. `굉장히 힘들어지죠.`, `물건을 파는 게 굉장히 어려워집니다.`가 이미 final된 뒤 뒤 후보 suffix에 다시 붙어 `... 일본 정부가 제일 먼저 굉장히 어려워집니다.`처럼 섞이는 유형이다.
- 48케이스 CUDA/SaT 벤치는 `pass_rate=0.125`, `finalized=156`, `finalized_per_stage_start=0.477`, `final_f1_avg=0.241`이다.
- 신규 `goods_economy` 케이스는 최근 final tail trimming으로 final F1 0.857을 기록했다. 기대 final 중 `금리를 인하하겠죠.`는 staged에 남아 확정 누락이 남지만, 앞선 mixed-context final은 억제됐다.
- 2026-06-18 00:40 로그에서 `ko_log_mixed_lost_decades_abe_fragment_20260618_001`를 추가했다. `이러다가 2013년에`와 `그래서 우리가 그거를 잃어버린 20년이라고 부릅니다.`가 window 순서에 따라 섞여 final될 수 있는 유형이다.
- 49케이스 CUDA/SaT 벤치는 `pass_rate=0.143`, `finalized=159`, `finalized_per_stage_start=0.479`, `final_f1_avg=0.257`이다.
- 신규 `lost_decades_abe` 케이스는 현재 recent-final delta trimming과 duplicate suppression으로 final F1 1.0을 기록했다. 별도 로직 증가는 필요하지 않다.
- 같은 로그 구간에서 `ko_log_premature_no_end_ycc_fragment_20260618_001`를 추가했다. 운영 로그에서는 `... 국채금리를 0%`가 `no_end_marker`인데 confirmed final되고, 바로 뒤의 `... 0%에 고정시키게 됩니다.`가 중복 억제되는 조기 확정/확정 누락 유형이 관측됐다.
- 같은 boundary 결과 안에 현재 staged 후보를 prefix로 갖는 더 긴 완료 후보가 뒤에 있으면, 종결 신호 없는 staged의 confirmed/next_completed 확정을 한 번 보류하도록 최소 정책을 추가했다.
- 50케이스 CUDA/SaT 벤치는 `pass_rate=0.160`, `finalized=160`, `finalized_per_stage_start=0.476`, `final_f1_avg=0.272`이다.
- 신규 `ycc` 케이스는 final F1 1.0을 기록했다. `stage_confirm_deferred_later_extension`은 전체 50케이스 중 1회만 발동해 과도한 발동은 관측되지 않았지만, 실제 로그 재현성과 함께 계속 관찰한다.
- 2026-06-18 00:45 로그에서 `ko_log_mixed_yen_exchange_rate_fragment_20260618_001`, `ko_log_trailing_ellipsis_japan_bond_fragment_20260618_001`를 추가했다.
- `yen_exchange_rate`는 pending tail `그래서 하려고 했는데 일본 N하고 달러하고의`가 앞 문장 `딱 봤는데 5% 수익률을 줘요.`와 섞여 final되는 유형이다. 현재 벤치에서는 mixed final은 억제되지만 `환율.`에서 먼저 final되어 다음 window의 `환율, 비용이 있어요.` 확장을 반영하지 못한다.
- `trailing_ellipsis_japan_bond`는 `일본이 갖고 있었던 일본...`이 교체 과정에서 final될 수 있는 유형이다. 현재 벤치에서는 ellipsis final은 억제되지만 마지막 완료 문장 `미국의 국채를 팔기 시작합니다.`가 staged에 남아 final 누락으로 남는다.
- 52케이스 CUDA/SaT 벤치는 `pass_rate=0.154`, `finalized=165`, `finalized_per_stage_start=0.481`, `final_f1_avg=0.289`이다.
- 신규 케이스 점수는 `yen_exchange_rate` final F1 0.667, `trailing_ellipsis_japan_bond` final F1 0.800이다. 이번 반복에서는 미래 window 확장을 예측하는 넓은 지연 정책을 추가하지 않고 케이스만 누적한다.
- 2026-06-18 00:47 로그에서 `ko_log_mixed_inflation_rate_cut_fragment_20260618_001`, `ko_log_mixed_samsung_foreign_selloff_fragment_20260618_001`를 추가했다.
- `inflation_rate_cut`는 current pending tail `물가가 계속 올라가고 있다 보니까...`가 이전 completed 문장 `굉장히 민감한 이슈심이 하나입니다.` 앞에 붙어 final되는 유형이다.
- `samsung_foreign_selloff`는 pending tail `삼성전자가 싫어서...`가 이전 문장 `조심하셔야 된다라는 얘기를 드리고 싶어요.` 앞에 붙는 유형이다. 현재 recent-final delta trimming으로 이 케이스는 final F1 1.0을 기록한다.
- 54케이스 CUDA/SaT 벤치는 변경 전 `pass_rate=0.167`, `finalized=170`, `finalized_per_stage_start=0.484`, `final_f1_avg=0.297`이다.
- completed 후보가 현재 pending tail과 같은 prefix로 시작하지만 서로 다른 suffix로 갈라지는 경우를 pending-prefix 혼합 후보로 보고 stage 전에 suppress하는 최소 정책을 추가했다.
- 변경 후 54케이스 CUDA/SaT 벤치는 `pass_rate=0.167`, `finalized=170`, `finalized_per_stage_start=0.486`, `final_f1_avg=0.305`이다.
- `candidate_pending_prefix_mixed_suppressed`는 전체 54케이스 중 1회만 발동했고, `inflation_rate_cut` final F1이 `0.000 -> 0.400`으로 개선됐다. 하락 케이스는 관측되지 않았다.
- 2026-06-18 00:50 로그에서 `ko_log_mixed_inflation_transition_fragment_20260618_001`, `ko_log_mixed_global_supply_chain_fragment_20260618_001`를 추가했다.
- `inflation_transition`은 짧은 pending prefix `인플레이션으로 전환되는`이 이전 문맥 `팔고 물가를...` 앞에 붙어 final되는 유형이다.
- `global_supply_chain`은 `싼 곳에서 부품을 만들고 그 다음에 미국이...` 같은 no-end 조각이 final될 수 있는 유형이다. 현재 pending-prefix 혼합 후보 억제로 final F1 1.0을 기록한다.
- 56케이스 CUDA/SaT 벤치는 `pass_rate=0.161`, `finalized=173`, `finalized_per_stage_start=0.489`, `final_f1_avg=0.312`이다.
- `inflation_transition`은 아직 final F1 0.0이다. 원인은 pending prefix가 2 token으로 짧아 현재 4 token 기준 pending-prefix 혼합 후보 억제에 걸리지 않기 때문이다.
- 짧은 pending prefix도 글자 길이가 충분하면 억제하는 실험을 했지만, 전체 지표와 발동 카운터가 변하지 않았다. 근거 없는 범위 확장이므로 폐기하고 기존 4 token 기준을 유지한다.
- 2026-06-18 00:54 로그에서 `ko_log_mixed_corporate_bond_cost_fragment_20260618_001`, `ko_log_missing_stock_market_impact_fragment_20260618_001`를 추가했다.
- `corporate_bond_cost`는 `결국은... 회사 채급...` no-end 후보가 final되고 뒤의 `기업 비용` 문맥과 섞일 수 있는 유형이다.
- `stock_market_impact`는 aged final 뒤에 이어지는 `주식시장이 집착적으로 영향을 받아요.`가 중복 억제로 누락될 수 있는 유형이다.
- 58케이스 CUDA/SaT 벤치는 `pass_rate=0.172`, `finalized=179`, `finalized_per_stage_start=0.496`, `final_f1_avg=0.335`이다.
- 신규 두 케이스는 현재 로직에서 모두 final F1 1.0을 기록했다. 추가 로직은 적용하지 않는다.
- 2026-06-18 00:56 로그에서 `ko_log_mixed_bond_rate_foreign_selloff_fragment_20260618_001`, `ko_log_trailing_ellipsis_korean_semiconductor_fragment_20260618_001`를 추가했다.
- `bond_rate_foreign_selloff`는 `그런데 이때 사람들은...` pending tail이 이전 문맥 `주식시장의 내관으로 작동하는...`과 섞여 final될 수 있는 유형이다.
- `korean_semiconductor`는 `한국의 반도체 주식이나 아니면 한국의...` ellipsis 후보가 final될 수 있는 유형이다.
- 60케이스 CUDA/SaT 벤치는 `pass_rate=0.183`, `finalized=183`, `finalized_per_stage_start=0.499`, `final_f1_avg=0.357`이다.
- 신규 두 케이스는 현재 로직에서 모두 final F1 1.0을 기록했다. ellipsis 후보는 staged/pending에 남고 final로 나가지 않는다. 추가 로직은 적용하지 않는다.
- 2026-06-18 00:59 로그에서 `ko_log_mixed_macro_trend_fragment_20260618_001`, `ko_log_mixed_interest_parity_dollar_fragment_20260618_001`를 추가했다.
- `macro_trend`는 `우리가 예전에 거시경제에서 배웠던 추세?`가 final되고 기대 문장 `이런 것 같이 잘 안 맞고 있어요.`가 누락되는 유형이다. 현재 final F1 0.0으로 남아 있다.
- `interest_parity_dollar`는 이미 final된 `이게 이제 금리 평형 이론의 가장 기본이에요.` 뒤에 STT 오인식 후보 `성형이론의 가장 기본이에요.`가 다시 final되는 짧은 recent-final tail echo 유형이다.
- 62케이스 CUDA/SaT 벤치는 변경 전 `pass_rate=0.177`, `finalized=187`, `finalized_per_stage_start=0.490`, `final_f1_avg=0.359`이다.
- 짧은 후보가 최근 final의 tail과만 유사하면 recent-final echo로 suppress하도록 최소 정책을 추가했다.
- 변경 후 62케이스 CUDA/SaT 벤치는 `pass_rate=0.194`, `finalized=185`, `finalized_per_stage_start=0.487`, `final_f1_avg=0.374`이다.
- 개선된 케이스는 `ko_log_mixed_interest_parity_dollar_fragment_20260618_001` F1 `0.800 -> 1.000`, `ko_log_mixed_ai_stock_allocation_fragment_20260618_001` F1 `0.286 -> 1.000`이다. 하락 케이스는 관측되지 않았다.
- 2026-06-18 01:03 로그에서 `ko_log_mixed_exchange_rate_prediction_fragment_20260618_001`를 추가했다. `몇 년인지 정확하게...` pending tail이 이미 final된 `제 느낌상 최소 3년은...` 문장과 결합될 수 있는 유형이다. 현재 코드는 final/pending F1 1.0을 기록하지만 stale staged가 남아 관찰 대상으로 둔다.
- 2026-06-18 01:05 로그에서 `ko_log_mixed_fomc_rate_decision_fragment_20260618_001`를 추가했다. `6월에 있을 FOMC` 같은 이전 pending prefix가 최근 final tail `이런 상황이 벌어졌다고...` 앞에 붙어 오염 final이 되는 유형이다.
- 64케이스 CUDA/SaT 벤치의 변경 전 기준은 `pass_rate=0.188`, `finalized=189`, `finalized_per_stage_start=0.480`, `final_f1_avg=0.388`이다.
- 이전 pending prefix 뒤에 최근 final tail이 재삽입된 completed 후보를 stage 전에 suppress하는 최소 정책을 추가했다. 이 규칙은 특정 문구나 언어별 정규식이 아니라 `prior pending prefix + recent final tail similarity`를 보는 token-sentence lifecycle 필터다.
- 변경 후 64케이스 CUDA/SaT 벤치는 `pass_rate=0.188`, `finalized=187`, `finalized_per_stage_start=0.475`, `final_f1_avg=0.393`이다.
- `candidate_prior_pending_recent_final_mixed_suppressed`는 전체 64케이스 중 3회 발동했다.
- 개선된 케이스는 `ko_log_mixed_fomc_rate_decision_fragment_20260618_001` F1 `0.667 -> 1.000`이다. `ko_log_duplicate_li_auto_xiaomi_fragment_20260617_001`와 `ko_log_duplicate_short_delta_rear_camera_view_20260617_001`에서도 오염 final이 각각 1개 줄었고, F1 하락은 관측되지 않았다.
- 2026-06-18 01:15-01:16 로그에서 `ko_log_mixed_household_debt_governor_fragment_20260618_001`, `ko_log_mixed_rate_hike_domestic_demand_fragment_20260618_001`, `ko_log_mixed_exchange_rate_defense_fragment_20260618_001`를 추가했다.
- `household_debt_governor`는 `GDP 대비 가계부채 비율이` pending이 최근 final tail `신임 총재가 오셨잖아요.`와 섞여 staged/final 후보가 되는 유형이다. 현재 벤치에서는 기대 final 중 핵심 문장 일부가 `staged`에 남고 final F1 0.500이다.
- `rate_hike_domestic_demand`는 `금리를 올리겠다는 거.`, `굉장히 중요하게 생각을 하고 있는 거죠.` 같은 중간 fragment가 final로 나가고 뒤의 더 완성된 문장이 다시 final되는 유형이다. 현재 final F1은 0.667이다.
- `exchange_rate_defense`는 이전 로그에서는 `환율이 지금 이슈가...` pending과 앞 문맥 `금리를 올리지는 않을 거다...`가 섞여 final됐지만, 현재 prior pending/recent final 혼합 억제와 terminal-tail split 조합으로 final F1 1.000을 기록한다.
- 67케이스 CUDA/SaT 벤치는 `pass_rate=0.194`, `finalized=195`, `finalized_per_stage_start=0.481`, `final_f1_avg=0.408`이다.
- 신규 샘플 추가 후 기존 64케이스의 final 결과 하락은 관측되지 않았다.
- 2026-06-18 01:24-01:30 로그에서 `ko_log_mixed_corporate_debt_cost_fragment_20260618_001`, `ko_log_mixed_nvidia_earnings_repeated_sales_fragment_20260618_001`, `ko_log_mixed_hbm_market_share_repeated_fragment_20260618_001`를 추가했다.
- `corporate_debt_cost`는 `금리가 굉장히...` trailing ellipsis 뒤에 회사채 비용 문장이 이어지는 유형이다. 현재 prior pending/recent final 혼합 억제와 recent-final delta trimming 조합으로 final F1 1.000을 기록한다.
- `nvidia_earnings_repeated_sales`는 `어닝/워닝 서프라이즈... 매출을 갖고 왔고` 구간이 긴 completed 후보 안에서 반복 삽입되어 final되는 유형이다.
- `hbm_market_share_repeated`는 `1차라고 보기에는... 왜냐하면 HBM 글로벌` 구간이 여러 번 재삽입되어 거대 final 후보가 되는 유형이다.
- 70케이스 CUDA/SaT 기준선은 변경 전 `pass_rate=0.200`, `finalized=203`, `finalized_per_stage_start=0.489`, `final_f1_avg=0.420`이다.
- 긴 후보 내부에서 동일한 token n-gram이 반복 삽입되는 경우 `repeated_word_ngram` 품질 플래그를 붙이고 stage/final/translation 후보에서 제외하도록 최소 정책을 추가했다. 이 규칙은 CJK 전용 반복 감지의 언어 예외 확장이 아니라 공백 기반 token-sentence에도 같은 반복 삽입 안전장치를 적용한 것이다.
- 변경 후 70케이스 CUDA/SaT 벤치는 `pass_rate=0.200`, `finalized=201`, `finalized_per_stage_start=0.484`, `final_f1_avg=0.423`이다.
- 개선된 케이스는 `ko_log_mixed_nvidia_earnings_repeated_sales_fragment_20260618_001` F1 `0.667 -> 0.800`, `ko_log_mixed_hbm_market_share_repeated_fragment_20260618_001` F1 `0.400 -> 0.500`이다. 기존 68케이스의 final 결과 변화는 관측되지 않았다.
- 반복 삽입 final은 억제됐지만 두 케이스 모두 기대 문장이 final까지 승격되지는 못하고 staged에 남았다. 따라서 이번 변경은 성공률 개선보다 오염 final 억제 근거로 기록한다.
- 2026-06-18 01:26-01:27 로그에서 `ko_log_mixed_productive_assets_fragment_20260618_001`, `ko_log_mixed_worker_product_price_fragment_20260618_001`를 추가했다.
- `productive_assets`는 첫 window에서 올바른 staged `... 마지막이 요게 관건입니다`가 생성됐지만, 다음 window에서 pending prefix `이게 뭐냐면은/마지막 이게 뭐냐면은 생산자...`가 기존 staged 앞에 끼어든 후보로 revision되어 오염 final되는 유형이다.
- `worker_product_price`는 `그러면 우리 같은 근로자들과 노동자들은...` 문장이 누락되고, `그리고 두 번째... 상품 가격...`과 `아니잖아요`가 no-end fragment로 나뉘어 확정되는 유형이다.
- 72케이스 CUDA/SaT 기준선은 `pass_rate=0.194`, `finalized=204`, `finalized_per_stage_start=0.483`, `final_f1_avg=0.416`이다.
- 종결 신호 없는 후보가 기존 staged 대부분을 suffix로 공유하면서 앞에 1-8 token prefix만 새로 끼워 넣은 형태이면 기존 staged를 보존하도록 revision 선호 규칙을 보강했다. 이 규칙은 특정 문구나 언어별 예외가 아니라 sliding window 순서 혼입을 막는 token-sentence lifecycle 규칙이다.
- 변경 후 72케이스 CUDA/SaT 벤치는 `pass_rate=0.194`, `finalized=205`, `finalized_per_stage_start=0.482`, `final_f1_avg=0.416`이다.
- `ko_log_mixed_productive_assets_fragment_20260618_001`는 오염 final `마지막 이게 뭐냐면은 생산자 ... 마지막이 요게 관건입니다`가 `예금쪽들도 ... 마지막이 요게 관건입니다`로 바뀌었다. 다만 punctuation 없는 final로 남아 F1은 아직 0.0이다.
- 기존 케이스 중 `ko_log_duplicate_short_delta_rear_camera_view_20260617_001`도 같은 규칙으로 문장이 더 분리됐지만, 기대 문장 exact 기준 F1은 0.0으로 유지됐다. F1 하락 케이스는 관측되지 않았다.
- 2026-06-18 01:31 로그에서 `ko_log_mixed_dollar_share_hegemony_fragment_20260618_001`, `ko_log_mixed_asset_pumping_repeat_fragment_20260618_001`, `ko_log_mixed_yuan_dollar_50years_fragment_20260618_001`를 추가했다.
- `dollar_share_hegemony`는 `근데 중요한 건 뭐냐면...` pending prefix가 앞 문맥 `60% 언더는... 떨어지고 있죠`와 섞여 staged/final 후보가 되는 유형이다.
- `asset_pumping_repeat`는 completed/final보다 pending tail 내부에서 `지금 미국이 하는 모든 정책들이... 자산 띄우기 작전인 것 같은데`가 반복 누적되는 유형이다.
- `yuan_dollar_50years`는 `아직은 앞으로 50년은 없을 거에요`가 no-end staged/final 후보로 남고, 뒤의 `근데 지키지 않으면...` 문맥이 pending으로 밀리는 유형이다.
- 75케이스 CUDA/SaT 벤치는 `pass_rate=0.187`, `finalized=205`, `finalized_per_stage_start=0.463`, `final_f1_avg=0.399`이다.
- 벤치 하네스가 운영 로그와 동일하게 pending 품질 플래그를 계측하도록 `pending_quality_*` 집계를 추가했다. 계측 추가는 동작을 바꾸지 않으며, 75케이스 지표는 동일하다.
- 변경 후 75케이스 CUDA/SaT 벤치에서 `pending_quality_repeated_word_ngram=8`이 관측됐다. 신규 `asset_pumping_repeat` 케이스에서는 2회 발생했다.
- pending 반복 누적은 확정 중복 이전 단계의 문제로 확인됐지만, 지금 바로 pending을 절단/접합하면 과거에 폐기한 정규화/접합 로직으로 되돌아갈 위험이 있다. 따라서 이번 반복에서는 성능 관측 지표와 벤치 샘플로만 고정하고, pending 절단 정책은 별도 근거가 쌓일 때까지 적용하지 않는다.
- 2026-06-18 01:35-01:36 로그에서 `ko_log_mixed_it_debt_liquidity_fragment_20260618_001`, `ko_log_mixed_money_function_fragment_20260618_001`를 추가했다.
- `it_debt_liquidity`는 `IT쪽 부실이 3조 달러 정도...`와 `근데 그거를 짓누를 정도로...`가 completion 후보로 반복 등장하지만, 현재 로직에서는 기대 final이 확정되지 않고 `근데 그걸 짓누를 정도로...`가 staged에 남는 유형이다.
- `money_function`은 `화폐 기능/화폐기능`, `가치척도/가치조정/가치저정`처럼 짧은 변형 반복이 이어지며, 현재 `repeated_word_ngram` 임계값에는 걸리지 않고 staged/pending 잔류로 남는 유형이다.
- 77케이스 CUDA/SaT 벤치는 `pass_rate=0.182`, `finalized=205`, `finalized_per_stage_start=0.451`, `final_f1_avg=0.389`이다.
- 신규 두 케이스 모두 final F1은 0.0이다. 다만 나쁜 final을 추가로 내보내는 형태보다는 no-end staged/pending 잔류가 주된 결과라서, 이번 반복에서는 token n-gram 임계값을 낮추거나 pending 절단 정책을 추가하지 않는다. 짧은 변형 반복까지 억제 범위를 넓히면 정상적인 짧은 문장 revision까지 막을 위험이 있으므로 벤치 근거로만 축적한다.
- 2026-06-18 01:39-01:40 로그에서 `ko_log_mixed_ai_industry_stablecoin_fragment_20260618_001`를 추가했다.
- 이 케이스는 `결국 AI 산업이죠.`가 먼저 확정된 뒤, `거기만 우승하면...` pending과 앞 문맥이 섞여 오염 후보가 만들어지고, 이어서 `그런 현상들의 모든 끝판왕이 뭐냐면 결국에는 이 스테이블 코인이죠.`가 중복/리비전 흐름 안에서 처리되는 유형이다.
- 실제 로그 문맥을 맞추기 위해 직전 final `나는 몰빵 경제를 통해서 시장과 통화에 대한 패권 그리고 산업에 대한 우승, 특정 산업이죠.`부터 샘플에 포함했다.
- 78케이스 CUDA/SaT 벤치는 `pass_rate=0.179`, `finalized=208`, `finalized_per_stage_start=0.449`, `final_f1_avg=0.391`이다.
- 신규 `ai_industry_stablecoin` 케이스는 final F1 0.571이며, 실제 final은 `나는 몰빵 경제... 특정 산업이죠.`, `결국 AI 산업이죠.`, `그런 현상들의 모든 끝판왕이 뭐냐면 결국에는 이 스테이블 코인이죠.`로 남았다. 기대 문장 중 `거기만 우승하면 모든 걸 다 갖게 된다는 로직으로...`는 아직 final 누락이며, `근데 트럼프가 끝나고 나서 이제 모든 끝판왕이 뭐냐면은` stale staged도 남는다.
- `짧은 pending prefix + 최근 final suffix` 억제 규칙을 검토했지만 최종 78케이스 벤치에서 별도 발동 근거를 만들지 못했다. 검증되지 않은 runtime 분기를 늘리지 않기 위해 이번 반복에서는 코드 반영 없이 벤치 샘플과 실험 기록만 남긴다.
- 2026-06-18 01:46-01:49 로그에서 `ko_log_mixed_stablecoin_collateral_leverage_fragment_20260618_001`, `ko_log_mixed_svb_ceo_warning_fragment_20260618_001`를 추가했다.
- `stablecoin_collateral_leverage`는 `스테이블콘/담보자산/미국 채권/레버리지` 구간이 window 안에서 반복 삽입되어 `여기서 미국 채권을 사든 뭘 새로운 아바타 돈을 만들 수 있고...` 같은 오염 final이 생성되는 유형이다. `candidate_prior_pending_recent_final_mixed_suppressed=1`, `pending_quality_repeated_word_ngram=1`, `stage_candidate_quality_repeated_word_ngram=1`이 관측됐지만 final F1은 0.0이다.
- `svb_ceo_warning`은 `어땠죠?`가 먼저 final되고, `SBB/SVB가 국채에 몽땅 투자돼 있었잖아요`, `근데 새벽 3시인가 2시에...` 구간은 staged/pending으로 갈라져 final 누락되는 유형이다. final F1은 0.0이고, `stage_replace_decision_unconfirmed=4`, `stage_replaced_unconfirmed=5`가 관측됐다.
- 80케이스 CUDA/SaT 벤치는 `pass_rate=0.175`, `finalized=210`, `finalized_per_stage_start=0.437`, `final_f1_avg=0.382`이다.
- 신규 케이스들은 기존 품질 플래그와 prior-pending/recent-final 억제가 일부 동작함에도 완전 복구되지 않는다. 다만 실패 원인이 서로 다르고, 짧은 의문문 또는 긴 반복 후보를 일괄 차단하면 정상 문장 확정까지 흔들릴 수 있으므로 이번 반복에서는 로직을 추가하지 않는다.
- 2026-06-18 01:52 로그에서 `ko_log_pending_overrun_follow_acquire_giveup_fragment_20260618_001`를 추가했다.
- 이 케이스는 `따라가거나 아니면 획득하거나 아니면 포기하거나` 구간이 pending 내부에서 반복 누적되어 260자 이상으로 커졌다가, 다음 window에서 `그런데 이 중간에 있는 따라가거나가 서서히 좌절될 수밖에 없는 이 시스템의 변화의 속도가 너무 빠르다는 거예요.`로 정리되는 유형이다.
- 81케이스 CUDA/SaT 벤치는 `pass_rate=0.173`, `finalized=211`, `finalized_per_stage_start=0.438`, `final_f1_avg=0.389`이다.
- 신규 `follow_acquire_giveup` 케이스는 final F1 1.0이며, `pending_quality_repeated_word_ngram=2`, `stage_candidate_quality_repeated_word_ngram=2`가 관측됐다. 현재 반복 삽입 안전장치가 중간 오염 후보를 막고 최종 문장 확정은 유지한 사례로 본다.
- 이 케이스는 실패 샘플이라기보다 pending 반복 누적을 계측하는 회귀 샘플이다. 현 시점에서는 pending 절단/접합 로직을 추가하지 않고, 반복 품질 지표가 최종 확정 품질을 해치지 않는지 계속 관찰한다.
- 2026-06-18 01:54-01:55 로그에서 `ko_log_mixed_stablecoin_authority_no_end_fragment_20260618_001`를 추가했다.
- 이 케이스는 `그렇게 되면 그 국가 존속의 경제 시스템은 기반은, 권위는 어떻게 되죠?`가 나중에 완성형으로 관측되지만, 직전 window에서 종결부호 없는 조각으로 먼저 확정되어 번역이 생략되고 후속 완성형은 중복 억제되는 유형이다. 이어서 `정부의 본래의 세금 권한과 전통화폐에 대한 지속성...` 구간은 긴 절이 후보 내부에 반복 삽입되어 오염 final이 된다.
- 82케이스 CUDA/SaT 기준선은 `pass_rate=0.171`, `finalized=216`, `finalized_per_stage_start=0.442`, `final_f1_avg=0.385`이다.
- 기준선에서 신규 케이스는 의미상 일부 문장을 final로 내보내지만, 마지막 final이 `정부의 본래의 세금 권한과 전통화폐에 대한 지속성...` 절을 두 번 포함한다. 이때 기존 `repeated_word_ngram`은 최소 24단어/8단어 n-gram 기준이라 6-7단어 길이의 절 반복을 잡지 못했다.
- `repeated_word_ngram` 적용 범위를 최소 16단어, 6단어 이상 n-gram 반복까지 낮췄다. 이는 특정 문구를 삭제하거나 후보를 재작성하지 않고, 반복 삽입 후보를 stage/final/translation 품질 게이트에서 제외하는 기존 안전장치의 범위 조정이다.
- 변경 후 82케이스 CUDA/SaT 벤치는 `pass_rate=0.171`, `finalized=215`, `finalized_per_stage_start=0.440`, `final_f1_avg=0.385`이다.
- 신규 케이스에서는 반복 절이 포함된 오염 final이 차단되어 `stage_candidate_quality_repeated_word_ngram=1`이 추가로 관측됐다. 대신 완성 문장 `정부의 본래의 세금 권한과 전통화폐에 대한 지속성...`은 아직 final로 회수되지 않고 `정부의 본래의 세금 권한과` staged 잔류로 남는다.
- 영향이 바뀐 기존 케이스는 3개였고 final 결과 하락은 관측되지 않았다. `zh_log_duplicate_myeongdong_departure_fragment_20260617_001`는 동일 final을 유지하면서 `stage_candidate_quality_repeated_word_ngram=1`만 추가됐고, `ko_log_duplicate_tesla_global_direction_fragment_20260617_001`, `ko_log_pending_overrun_follow_acquire_giveup_fragment_20260618_001`는 반복 품질 계측 횟수만 바뀌었다.
- 2026-06-18 07:12-07:13 로그에서 `ko_log_mixed_submarine_space_no_end_delta_fragment_20260618_001`를 추가했다.
- 운영 로그에서는 `무슨 말이냐면 만들어주면`, `빽빽합니다`, `우리가 이렇게 둥그러 선 채를 했다가 정말 빽빽합니다`처럼 종결 신호 없는 delta 조각이 final로 출력되고 번역은 `final_quality=no_end_marker`로 생략되는 흐름이 관측됐다. 같은 구간에서 더 완성된 window가 뒤따라와 확정 누락과 중복 억제가 섞인다.
- 현재 코드 기준 83케이스 CUDA/SaT 벤치는 `pass_rate=0.169`, `finalized=224`, `finalized_per_stage_start=0.445`, `final_f1_avg=0.384`이다.
- 신규 `submarine_space_no_end_delta` 케이스는 final F1 0.353이다. 실제 final은 `저 디자인이 더 스텔스라면...`, `그게 어렵나 봐요.`, `잠수함은 안에 여유 공간이 1cm도 없어요.`, `무슨 말이냐면 저는 이제 조선소에서 직접 배를 만들어 봤으니까`, `그 안에가 정말 빽빽합니다.` 등을 내보내고, `그러니까 틀리면 9번 세로 맞추기가 쉽지 않겠네.`가 staged에 남는다.
- 벤치에서는 운영 로그의 짧은 delta 단독 final이 그대로 재현되지는 않았다. 현재 `_should_suppress_short_delta_final`이 `무슨 말이냐면 만들어주면`, `빽빽합니다` 유형을 억제 대상으로 판단하기 때문이다. 따라서 이번 반복에서는 로직을 추가하지 않고, serve 프로세스가 최신 로직으로 재시작된 뒤 같은 유형이 계속 나오는지 관찰한다.
- 2026-06-18 07:15 로그에서 `ko_log_duplicate_submarine_full_speed_fragment_20260618_001`를 추가했다.
- 이 케이스는 `예를 들어서 중앙주의센터에서 수중 전속력 전진` 구간이 한 final 안에 두 번 삽입되는 짧은 반복 final 유형이다. 기준선에서는 `예를 들어서 중앙주의센터에서 수중 전속력 전진 이러면 예를 들어서 중앙주의센터에서 수중 전속력 전진!`가 final로 나갔다.
- 84케이스 CUDA/SaT 기준선은 `pass_rate=0.167`, `finalized=226`, `finalized_per_stage_start=0.448`, `final_f1_avg=0.380`이다.
- 기존 `repeated_word_ngram`은 16 token 미만 후보를 보지 않아 13 token 안에서 6 token 구가 반복되는 이 케이스를 잡지 못했다. 반복 품질 게이트의 최소 후보 길이를 16 token에서 12 token으로 낮췄다. n-gram 크기는 6 token 이상을 유지해 짧은 단어 반복이나 정상 짧은 문장까지 넓히지 않았다.
- 변경 후 84케이스 CUDA/SaT 벤치는 `pass_rate=0.167`, `finalized=226`, `finalized_per_stage_start=0.448`, `final_f1_avg=0.380`이다.
- 영향이 바뀐 케이스는 신규 `submarine_full_speed` 1개뿐이다. 해당 케이스에서 `stage_candidate_quality_repeated_word_ngram=1`이 관측되고, 중복 final은 `예를 들어서 중앙주의시센터에서 수중 전속력 전진!` 단일 final로 줄었다. 정확도 점수는 `센터/시센터` STT 표기 차이 때문에 변하지 않았지만, 중복 확정 억제 목적에는 부합한다.
- 2026-06-18 07:16 로그에서 `ko_log_pending_overrun_old_submarine_space_fragment_20260618_001`를 추가했다.
- 이 케이스는 `오래된 잠수함... 마티지 같은데... 점점점` 구간이 pending 내부에서 반복 누적되어 186자 pending과 218자 staged 오염 후보로 커지는 유형이다.
- 85케이스 CUDA/SaT 벤치는 `pass_rate=0.165`, `finalized=228`, `finalized_per_stage_start=0.448`, `final_f1_avg=0.385`이다.
- 신규 `old_submarine_space` 케이스는 final F1 0.800이다. 실제 final은 `여유공간을 그래도 좀 늘렸어요.`, `옛날 보다.`까지 회수했고, 기대했던 긴 문장 `그래서 정말 오래된 잠수함은... 공간 안에 좀 더 여유가 있는 거죠.`는 staged에 남았다.
- 이 케이스에서 `pending_quality_repeated_word_ngram=3`, `stage_candidate_quality_repeated_word_ngram=1`, `candidate_pending_prefix_mixed_suppressed=1`이 관측됐다. 반복 품질 게이트가 거대 오염 staged 후보를 차단한 근거는 생겼지만, final 회수는 아직 완성되지 않았다.
- 2026-06-18 07:20-07:21 로그에서 `ko_log_mixed_carney_middle_power_fragment_20260618_001`를 추가했다.
- 이 케이스는 `카니 총리입니다.`가 앞 문맥에 붙어 먼저 확정되고, 뒤이어 `카니 총리가 작년 말에 굉장히 의미심장한 연설을 했어요.`, `그게 뭐냐면 중견국 연합체를 만들죠.`가 stage 교체와 recent-final trimming 사이에서 흔들리는 유형이다.
- 같은 구간에서 `한마디로`가 `final_quality=no_end_marker`로 확정된 뒤 번역 생략되는 현상도 관측됐다. 이 샘플은 단순 중복 억제보다 조기 조각 확정과 완성 문장 누락을 함께 추적하기 위한 벤치 케이스로 둔다.
- 86케이스 CUDA/SaT 벤치는 `pass_rate=0.163`, `finalized=232`, `finalized_per_stage_start=0.449`, `final_f1_avg=0.380`이다.
- 신규 `carney_middle_power` 케이스에서 짧은 `한마디로` 단독 final은 `finalize_short_delta_suppressed=1`로 억제됐다. 실제 final은 `안보를 완전히 의존했던 걸 탈피를 해가지고 새로운 파트너를 잡아야 되는데 카니 총리입니다.`, `카니 총리가 작년 말에 굉장히 살피를 해가지고 새로운 파트너를 잡아야 되는데 칸의 총리가 작년 말에 굉장히 의미심장한 연설을 했어요.`, `그게 뭐냐면 중견국 연합체를 만들죠.`, `한마디로 그 전에 했던 대로 하자는 거죠.`이다.
- 아직 남은 문제는 두 번째 final처럼 앞 window의 open clause가 뒤 window의 완성 문장 앞에 섞이는 긴 후보다. 이 유형은 6 token 이상 반복 n-gram으로 항상 잡히지 않으므로, 반복 임계값을 더 낮추기보다 staged 순서 일관성과 조기 `next_completed` 확정 조건을 계속 관찰한다.
- 2026-06-18 07:21 로그에서 `ko_log_pending_overrun_canada_security_threat_fragment_20260618_001`를 추가했다.
- 운영 로그에서는 `최근에 캐나다에서 작년에 발표한 보고서가... 캐나다의 가장 큰 안보 위협` 구간이 pending 내부에서 40자, 73자, 140자, 196자로 누적된 뒤 260자 반복 final로 확정됐다.
- 87케이스 CUDA/SaT 벤치는 `pass_rate=0.161`, `finalized=234`, `finalized_per_stage_start=0.451`, `final_f1_avg=0.376`이다.
- 신규 `canada_security_threat` 케이스에서는 운영 로그의 260자 반복 final이 그대로 재현되지는 않았다. 현재 로직이 `pending_quality_repeated_word_ngram=3`, `stage_candidate_quality_repeated_word_ngram=1`로 반복 누적 후보를 차단했고, 실제 final은 `겉에 보면 그냥 트럼프 들으라고 하는 얘기예요.`, `캐나다에서 작년에 발표한 보고서가 나 있는데 그게 뭐냐면 캐나다의 가장 큰 안보 위협은 중국이다라는 거예요.`로 남았다.
- 이 결과는 반복 품질 게이트가 오염 final 억제에는 효과가 있지만, 앞 문맥 `그런데 이제 그 이면에는...`을 완성 문장으로 회수하지는 못한다는 근거다. 이번 반복에서는 pending 절단/재접합 로직을 추가하지 않고 샘플과 지표로 축적한다.
- 2026-06-18 07:50 로그에서 `ko_log_repeated_defense_weapon_technology_fragment_20260618_001`를 추가했다.
- 운영 로그에서는 `방산의 무기 만들 수 있는 나라가 매우 제한적인 걸 보면...` 구간이 323자 반복 final로 확정됐다. 벤치에서는 현재 로직이 기대 final `방산의 무기 만들 수 있는 나라가 매우 제한적인 걸 보면 쉬운 기술이 아니라는 거고 첨단 기술이죠.`, `그 말은 기술 차이나 성능 차이나 이런 것에서 차이가 날 수밖에 없다는 거죠.`를 회수하고 pending `근데 이제 국방 부기 도입이라는 게`를 유지했다.
- 2026-06-18 07:52-07:53 로그에서 `ko_log_mixed_consulting_company_control_system_fragment_20260618_001`를 추가했다.
- 이 케이스는 `이름 못 들어본 컨설팅 회사를 고용하자는 거예요.`, `컨트롤 시스템을 안 썼어요.`, `왜냐?`, `우리나라에서 그걸 거부했거든요.` 구간이 짧은 조각으로 분리되고, 운영 로그에서는 `컨트롤 시스템을 안 썼어요`가 `final_quality=no_end_marker`로 확정되어 번역 생략됐다.
- 89케이스 CUDA/SaT 벤치는 `pass_rate=0.169`, `finalized=247`, `finalized_per_stage_start=0.462`, `final_f1_avg=0.380`이다.
- 신규 `consulting_company_control_system` 케이스는 오염 반복 final보다는 과분리와 마지막 staged 잔류가 주된 실패다. 실제 final은 `더 노골적.`, `근데 더 노골적으로 기술적으로 해요.`, `그러니까 티 안나게.`, `예를 들어서 뭐 이런거죠.`, `티 안 나게.`, `이름 못 들어본 컨설팅 회사를 고용하자는 거예요.`, `그 컨설팅 회사가 뭘 하냐 그랬더니 그것은 좀 차이가 있구나.`, `그런 걸 경험했었는데 결국은 컨트롤 시스템을 안 썼어요.`, `왜냐?`, `우리나라에서 그걸 거부했거든요.`, `그런 거 쓰면 안 된다.`이며 `우리는 그거 못 쓴다.`가 staged에 남았다.
- 이번 반복에서는 조각 final을 더 강하게 억제하는 로직을 추가하지 않는다. 이미 `왜냐?` 같은 짧은 의문문은 정상 발화일 수 있고, 과분리 억제를 넓히면 final 누락이 커질 위험이 있다.
- 2026-06-19 22:32-22:39 로그에서 `ko_log_deferred_stage_stall_vehicle_safety_fragment_20260619_001`, `zh_log_short_cjk_false_positive_stage_delay_seongsu_food_20260619_001`를 추가했다.
- `vehicle_safety` 케이스는 미확정 open-clause stage가 뒤 후보를 계속 보류해 `stage_replace_deferred`가 누적되고 final이 거의 나오지 않던 유형이다. 미확정 replacement는 기존 후보를 삭제하지 않고 candidate buffer에 보류하되, active 후보가 age 한계까지 final 품질을 만족하지 못하면 suppressed 처리 후 다음 후보를 승격하도록 조정했다.
- `seongsu_food` 케이스는 `澳洲。` 같은 짧은 CJK 오인식 후보가 active stage를 잡고 있어 `吃完之后呢...`, `好，走，去吃饭。` 같은 뒤 후보 확정이 늦어지는 유형이다. 해당 조각은 final로 내보내지 않고 `stage_age_quality_blocked`로 정리되는지 관측한다.
- revision 경로에서도 age 한계에 도달했지만 final 품질을 만족하지 못하는 후보는 suppress 후 queue 후보를 승격하도록 운영 루프와 벤치 모델을 맞췄다. 이는 age-only 경로에 이미 있던 품질 차단을 completed/revision 후보가 계속 들어오는 경로에도 동일하게 적용한 것이다.
- 91케이스 CUDA/SaT 벤치는 `pass_rate=0.143`, `finalized=271`, `finalized_per_stage_start=0.585`, `final_f1_avg=0.347`이다. 신규 두 케이스는 아직 case pass가 아니며, 각각 `stage_age_quality_blocked=2`, `raw_without_final=0`을 기록했다. 현재 목적은 성공 케이스로 만들기보다 중복 확정/확정 누락 의심 흐름을 수치화해 후속 튜닝 기준으로 고정하는 것이다.

## 2026-06-19 22:58 KST - 짧은 no-end 조각과 오디오 잔류 의심 로그

- 2026-06-19 22:47-22:52 로그에서 `여러분 안녕하십니까 오늘 주식시장을...`, `기상캐스터 배혜지`, `이 시각 세계였습니다.`, `SBS 비즈 신성우입니다.` 같은 짧은 진행/클로징 조각이 raw STT에 반복 등장했다.
- `기상캐스터 배혜지` 반복 구간은 `stt_raw`에는 나오지만 `text_chars=0`, `completed=0`, `pending=0`으로 downstream 문장 후보에는 반영되지 않은 경우가 있었다. 이는 문장 lifecycle 오염이라기보다 10초 슬라이딩 윈도우에 직전 오디오가 남아 같은 짧은 구간이 반복 전사되는 현상으로 추정한다.
- 입력 음성이 없었다는 관측이 있어, 해당 케이스는 확정 누락/중복 벤치의 정답 샘플로 확대하지 않는다. 다만 `ko_log_weathercaster_stock_prefix_corruption_fragment_20260619_001`는 짧은 no-end 조각이 다음 문장 prefix로 결합될 때의 lifecycle 오염 관찰 샘플로 둔다.
- 짧은 no-end 조각이 stage/final 후보로 올라가지 않도록 `short_no_end_fragment` 품질 플래그를 추가했다. 이 규칙은 특정 문구나 언어별 예외가 아니라 종결표지 없는 4 token 이하 조각을 stage/final 품질에서 제외하는 일반 안전장치다.
- `trailing_ellipsis` 후보도 stage 시작 대상에서 제외했다. `...`가 붙은 후보는 이미 final/translation 품질에서 제외되므로 stage 진입도 같은 기준으로 맞춘다.
- 운영 로그에 `audio_rms_db`, `audio_peak_db`를 추가했다. 이 지표는 VAD/silence 기반 final 판단에 쓰지 않고, STT raw 반복이 실제 잔류 오디오인지 무음 hallucination인지 사후 분석하기 위한 관측값으로만 사용한다.
- 변경 후 94케이스 CUDA/SaT 벤치는 `pass_rate=0.181`, `finalized=269`, `stage_start=432`, `finalized_per_stage_start=0.623`, `final_f1_avg=0.386`이다. 직전 94케이스 기준 `stage_start`가 줄고 `finalized_per_stage_start`, `final_f1_avg`가 개선됐다.

판단:

- `들죠`처럼 committed prefix 제거 뒤 남는 짧은 no-end-marker 조각 final은 억제할 수 있는 근거가 생겼다.
- 최근 추가 케이스들은 조기 중복 확정이 줄어든 대신, 더 나은 미래 window revision을 기다리지 못한 확정 누락 또는 staged 잔류로 남는 경향이 있다.
- 남은 주요 실패는 짧은 조각이 아니라 문맥이 섞인 긴 후보가 `next_completed`로 final되는 경우다. 예: `디스플레이 크기... 후진할 때 보면... 들죠`처럼 앞뒤 window 문맥이 한 문장으로 합쳐지는 경우.
- 다음 개선은 문맥이 섞인 긴 후보를 케이스별 문구로 보정하지 않고, staged와 output delta의 순서 일관성, 최근 final suffix 결합, age/confirmation 누적을 함께 이용해 `next_completed`를 더 보수화하는 방향으로 검토한다.

## 2026-06-19 23:18 KST - 미확정 replacement와 오디오 잔류 후보의 age 확정 차단

- 2026-06-19 22:59-23:01 로그에서 `과연 적절한 탈모 지원을 확대할 수 있을지.`, `탈모지원 확대를 두고 감론을 받았습니다.`가 먼저 staged 된 뒤, 같은 시작부를 가진 더 긴 후보가 이어서 관측됐다.
- 기존 로직은 미확정 replacement를 queue에 보류하면서 active staged의 age를 증가시켰고, age 한계에 도달하면 이전 후보를 final로 확정했다. 그 결과 `과연 적절한 탈모 지원을 확대할 수 있을지.`와 `과연 적절한 지원야를 두고 찬반 논란이 커지고 있습니다.`가 함께 final로 나가는 문장 파괴/중복이 발생했다.
- `ko_log_unconfirmed_replacement_sentence_destruction_hair_support_20260619_001`, `ko_log_unconfirmed_replacement_sentence_destruction_public_hearing_20260619_001`를 벤치 샘플에 추가했다.
- 미확정 replacement와 충돌 중인 active staged는 age만으로 final 승격하지 않고 suppress 후 queue 후보를 승격하도록 조정했다. 이는 특정 문구 보정이 아니라, final append-only 계약에서 불확실한 앞 후보를 확정하지 않는 보수적 생명주기 규칙이다.
- 프로그램 재시작 뒤 `SBS 비즈 우형준입니다.`, `MBC 뉴스 우형준입니다.`, `다음 영상에서 만나요.`, `지금까지 생생지구촌이었습니다.` 같은 이전/무관 클로징 문구가 raw 또는 no_speech 후보로 관측됐다. `audio_rms_db`는 약 -26 dB, `audio_peak_db`는 약 -6 dB로 완전 무음이 아니라 입력 source 또는 장치 버퍼의 잔류 오디오 가능성이 크다.
- Python worker의 `_audio_queue`는 worker 생성마다 새 queue라 프로세스 내부 큐 재사용으로 보기는 어렵다. 캡처 시작 직후 Pulse/sounddevice 장치 버퍼를 1초 drain하고, drain block/sample 수를 status 로그에 기록하도록 했다.
- no_speech/empty STT chunk는 문장 후보 검증 근거가 아니므로 staged age를 증가시키지 않도록 했다. `ko_log_no_text_should_not_age_residual_reporter_20260619_001`를 추가해 `MBC 뉴스 우형준입니다.`가 empty chunk만으로 final되지 않는지 관측한다.
- 변경 후 97케이스 CUDA/SaT 벤치는 `pass_rate=0.144`, `finalized=214`, `stage_start=495`, `finalized_per_stage_start=0.432`, `final_f1_avg=0.208`이다.
- 신규 `no_text_should_not_age_residual_reporter` 케이스는 final 없이 staged 유지로 동작했다. 반면 미확정 replacement suppress는 파괴 final을 줄이는 대신 일부 케이스에서 확정 누락과 staged 잔류를 늘렸다. 다음 튜닝은 `stage_unconfirmed_replacement_suppressed`, `stage_age_no_text_skipped`, `finalized_per_stage_start`를 함께 보며 suppress 이후 queue 후보가 언제 final로 승격되어야 하는지에 집중한다.
- `기상캐스터 배혜지`가 입력되지 않았는데 반복 관측된 사례는 입력 장치가 `alsa_output...monitor`인 출력 monitor 캡처 경로에서 발생했다. 이는 문장 lifecycle만의 문제가 아니라 앱이 접근한 Pulse monitor source 또는 sink 버퍼/재생 상태의 영향일 수 있다. Pulse 직접 캡처 명령에 low-latency 요청을 추가하고, source kind/latency와 시작 drain 결과를 로그로 남겨 재현 시 캡처 계층과 문장 계층을 분리해 본다.
- 23:12:55-23:13:01 로그에서 `노동부는 올 하반기에도 기획 조사를 진행할 예정입니다.`가 staged 된 뒤 `기상캐스터 배혜지`, `노은지 기상캐스터`가 pending으로 누적됐고, 다음 completed 후보가 `기상캐스터 배혜지 노동부는...` 형태로 들어오며 staged revision으로 선호되어 prefix 오염 final이 발생했다.
- 이전 pending tail이 기존 staged 문장 앞에 붙은 revision으로 보이면 pending prefix를 제거한 뒤 staged 본문 기준으로 비교하도록 했다. `ko_log_prior_pending_prefix_weathercaster_labor_revision_20260619_001`를 벤치 샘플에 추가하고 `candidate_prior_pending_prefix_trimmed` 지표를 추가했다.
- 사용자가 관측한 `박살났다는 얘기 나와있죠` / `가스 시설이 많이 파괴...` / `불가항력 선언...` sliding-window 반복 케이스를 `ko_log_sliding_window_gas_facility_force_majeure_20260619_001`로 추가했다. 이 케이스는 문장 앞부분이 계속 밀리면서 뒤쪽 안정 문장이 누락/중복되는지 보는 성능 관측 샘플이다.
- 23:13 로그와 사용자가 추가 관측한 미국 투자 질문 구간에서, 한 window에 여러 completed 후보가 들어올 때 미확정 replacement suppress가 age 0에서도 즉시 발생해 staged가 계속 교체되고 final이 부족해지는 흐름을 확인했다.
- 미확정 replacement 충돌 후보는 age 한계에 도달했을 때만 suppress하도록 완화했다. 이는 과거처럼 age만으로 final하는 것이 아니라, 불확실한 앞 후보를 너무 일찍 폐기하지 않기 위한 보류 규칙이다.
- `ko_log_sliding_window_us_investment_questions_20260619_001`를 추가해 질문 시퀀스가 순서대로 final 후보에 반영되는지 추적한다.
- 변경 후 100케이스 CUDA/SaT 벤치는 `pass_rate=0.140`, `finalized=241`, `stage_start=441`, `finalized_per_stage_start=0.546`, `final_f1_avg=0.266`이다. 직전 99케이스 `final_f1_avg=0.204`, `finalized_per_stage_start=0.424` 대비 final 소비율은 개선됐다.
- `ko_log_sliding_window_gas_facility_force_majeure_20260619_001`는 final이 0개에서 6개로 늘어 누락이 줄었다. `ko_log_sliding_window_us_investment_questions_20260619_001`는 뒤쪽 문장 3개만 final되어 앞 질문 2개 누락이 남았다. 다음 후보는 age 한계에 도달한 미확정 후보를 suppress할지 final할지 판단하는 기준을 더 좁히는 것이다.

## 남은 실험 과제

- 동일 입력 replay 기반으로 `faster-whisper`, `qwen3-asr-0.6b`, 과거 FunASR 기준선을 비교한다.
- 중국어 `windowSeconds=12/16/20/24/30`의 raw STT 안정성과 final 지연을 같은 입력에서 비교한다.
- 중한 번역은 STT/확정 품질과 분리된 평가셋으로 NLLB, M2M100, 더 큰 NLLB 모델을 비교한다.
- `translation_quality` 회귀 샘플을 늘려 고유명사, 서비스명, 구어체 오역을 추적한다.
- 정답 전사 코퍼스가 준비되면 한국어/중국어는 CER, 영어는 WER를 추가한다.
- Qwen3-ASR vLLM streaming은 공유 `.venv`가 아니라 격리 런타임 설계가 준비된 뒤 다시 검토한다.
