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
- mock/smoke 경로는 성능 판단에 사용하지 않았다.

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
- 벤치 실행은 실제 모델 기준인 `sat + cuda + float16`만 성능 판단 근거로 삼는다. mock/smoke/CPU 결과는 성능 튜닝 근거로 사용하지 않는다.
- 성능 추적 테스트는 품질 게이트가 아니라 누락/중복/확정 지연의 추세 관측 도구로 유지한다.

### 로직 변경 아이데이션

| 관측 | 판단 | 결과 |
| --- | --- | --- |
| 같은 chunk 안 여러 completed 후보가 단일 staged slot에서 서로 밀어냄 | 후보를 합치기보다 문장 단위 lifecycle 구조 문제로 본다. | completed 재구성 로직과 관련 테스트를 제거했다. |
| internal overlap delta가 일부 중복을 줄일 수 있음 | pending/new 접합 보정과 유사한 의미 재작성 위험이 있다. | 내부 overlap delta 보정과 품질 게이트 테스트를 제거했다. |
| 수치 튜닝 후보가 일부 지표를 개선함 | 기준 파이프라인을 흐리면 필수 구현처럼 오해된다. | 기준 문서에서 튜닝 후보와 폐기 후보 표를 제거하고 실험일지로 이동했다. |
| 성능 벤치를 mock/CPU로 돌릴 수 있음 | 실제 운영 품질 판단과 무관한 결과가 된다. | 벤치 CLI에서 `sat + cuda + float16`만 허용하도록 했다. |

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
  tests.unit.test_dictation_ai_sentence_revision \
  tests.unit.test_dictation_ai_sbd_benchmark \
  tests.unit.test_dictation_ai_sentence_forcing \
  tests.unit.test_dictation_ai_performance_tracking \
  tests.unit.test_dictation_ai_transcript_delta \
  tests.unit.test_dictation_ai_sentence_boundary \
  tests.unit.test_transcript_revision

Ran 394 tests
OK
```

```text
./.venv/bin/python -m py_compile \
  src/app/dictation_transcript_logic.py \
  src/app/dictation_window.py \
  tests/eval/dictation_ai/sbd_benchmark.py
```

이번 검증은 코드 정리 검증이다. 성능 판단용 CUDA/SaT 벤치 수치는 별도 실행 결과만 기준으로 삼는다.

## 남은 실험 과제

- 동일 입력 replay 기반으로 `faster-whisper`, `qwen3-asr-0.6b`, 과거 FunASR 기준선을 비교한다.
- 중국어 `windowSeconds=12/16/20/24/30`의 raw STT 안정성과 final 지연을 같은 입력에서 비교한다.
- 중한 번역은 STT/확정 품질과 분리된 평가셋으로 NLLB, M2M100, 더 큰 NLLB 모델을 비교한다.
- `translation_quality` 회귀 샘플을 늘려 고유명사, 서비스명, 구어체 오역을 추적한다.
- 정답 전사 코퍼스가 준비되면 한국어/중국어는 CER, 영어는 WER를 추가한다.
- Qwen3-ASR vLLM streaming은 공유 `.venv`가 아니라 격리 런타임 설계가 준비된 뒤 다시 검토한다.
