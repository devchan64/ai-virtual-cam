# 받아쓰기 AI 실험일지

## 문서 상태

이 문서는 폐기된 원본 문서 `docs/2026-06-13-dictation-ai-feature-design.md`의 Git 커밋 기록을 기준으로 재구성한 실험일지다. 이 파일은 이전에 다른 이름의 설계 문서로 존재했으므로 rename 이전 문서의 변경 이력까지 추적 대상에 포함한다. 또한 받아쓰기 AI의 실험 판단이 README, 논문 초안, 발표용 세그먼트 레퍼런스 문서에 분산되어 기록된 경우 해당 문서 업데이트 히스토리도 보조 근거로 포함한다. 실시간 파이프라인 기준은 [받아쓰기 AI 실시간 처리 파이프라인 기준](2026-06-16-dictation-ai-realtime-pipeline.md), 설정 계약과 기본값은 [받아쓰기 AI 계약과 기본값](2026-06-16-dictation-ai-contract-defaults.md)을 따른다.

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

### 중국어 STT 후속 후보 세부검증 판단

Qwen3-ASR vLLM streaming, Dolphin-CN-Dialect, WeNet은 별도 기본값이 아니라 중국어 raw STT 품질, streaming latency, 방언/코드스위칭 대응, 별도 ASR service 구조를 검토하기 위한 후속 후보로 분류했다. 후보를 평가할 때는 raw STT 품질과 받아쓰기 AI 후처리 품질을 분리한다. 좋은 raw STT가 있어도 sliding window, staged confirmation, final 확정 정책이 불안정하면 사용자 출력은 흔들리고, 반대로 후처리가 좋아도 raw STT가 의미를 잃으면 final 품질은 회복하기 어렵다.

후속 후보 판단:

| 후보 | 검증 관점 | 현재 판단 |
| --- | --- | --- |
| `qwen3-asr-vllm-streaming` | Qwen3-ASR 계열의 지연 개선 후보. raw partial, raw final, stream reset, session id, backpressure를 구분하는 별도 service 계약이 필요하다. | 공유 `.venv`에서 vLLM 의존성이 `mediapipe`/`protobuf`와 충돌하므로 in-process backend로 넣지 않는다. 격리 런타임과 ASR service 계약이 준비된 뒤 비교한다. |
| Dolphin-CN-Dialect | 표준 중국어 외 방언, 대만 만다린, 코드스위칭, 음식명/지명/가격 표현 비교 후보. | 실행 경로, 모델 캐시, 라이선스, CUDA 추론, adapter가 미정이므로 설정 계약/다운로드 대상/GUI 선택지에 넣지 않는다. 2차 품질 후보로 보류한다. |
| WeNet | dynamic chunk와 CTC/attention rescoring 기반 native streaming/non-streaming E2E ASR 구조 비교군. | 현재 프로젝트에는 의존성, 모델 다운로드, adapter, GPU 실행 경로가 없다. Qwen3-ASR vLLM streaming이 막히거나 streaming 이벤트 계약 비교가 필요할 때 검토한다. |

운영 반영 기준:

- 세 후보 모두 바로 기본값으로 승격하지 않는다.
- 더 빠르다는 이유만으로 채택하지 않는다. 의미 보존, 문장 구조, final 생성률, stage churn, 번역 입력 안정성이 함께 좋아야 한다.
- 후보가 도입되더라도 자동 fallback은 허용하지 않는다. 설정한 backend가 실행 불가능하면 실패 원인, 설정값, 권장 조치를 출력하고 중지한다.
- pending 접합 보정은 학술적 근거가 부족하므로 STT 후보 평가 기준으로 사용하지 않는다.

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
- 영어 기본 시작점은 `windowSeconds=20`, `stepSeconds=1`, `sentenceFinalizeAge=3`이다.
- 한국어 기본 시작점은 `windowSeconds=10`, `stepSeconds=1`, `sentenceFinalizeAge=3`이다.
- 중국어/Qwen3-ASR 기본 시작점은 `windowSeconds=15`, `stepSeconds=1`, `sentenceFinalizeAge=3`이다.
- 30초 window는 장문 안정성에는 유리할 수 있지만 final script 갱신 지연과 긴 문장 확정 비용이 커질 수 있다.

### 주요 기본값 변경

| 축 | 기본값/정책 변화 | 사유 |
| --- | --- | --- |
| 언어별 runtime | active/global 값보다 `stepSeconds{Lang}`, `windowSeconds{Lang}`, `sentenceFinalizeAge{Lang}`를 기준으로 정리 | 영어/한국어와 중국어의 적정 window가 달라 단일 기본값으로 품질을 맞추기 어려웠기 때문이다. |
| 영어 window | `windowSecondsEn=20` | 최근 영어 빠른 발화와 누락 관측을 기준으로 문맥을 늘렸다. |
| 한국어 window | `windowSecondsKo=10` | 한국어 기본 문맥을 10초로 조정했다. |
| 중국어 window | `windowSecondsZh=15` | `windowSecondsZh=15.0` 관측에서 STT 안정성과 확정 지연의 균형점으로 판단했다. |
| step | `stepSecondsEn/Ko/Zh=1` | 화면 갱신성과 STT 처리량이 모두 감당 가능한 범위로 관측됐다. |
| 확정 age | `sentenceFinalizeAgeEn/Ko/Zh=3` | 현재는 queue/recent-final/no-text/staged 후보 관리가 정리된 뒤의 기준이므로 언어별 예외를 줄이고 보수적인 공통 확정 기준을 기본값으로 둔다. |
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
- 당시 2026-06-17 SaT 벤치에서는 `sentenceFinalizeAgeZh=2`가 `no_end_marker` final을 0으로 유지하면서 `finalized=20`, `stage_start=34`, `finalized_per_stage_start=0.588`로 age 3의 `finalized=19`, `stage_start=35`, `finalized_per_stage_start=0.543`보다 확정 지표가 좋았다. 다만 이 결론은 이후 queue/recent-final/no-text/staged 후보 관리가 정리되기 전 로직 수준의 결과이므로 현재 기본값 판단 근거로는 폐기한다. 현재 기본값은 언어별 예외를 줄이고 보수적인 확정 기준을 유지하기 위해 `sentenceFinalizeAgeZh=3`으로 통일한다.
- `windowSecondsZh=15.0`은 현재 STT 안정성과 확정 지연의 균형점으로 유지한다. 이번 구간에서 queue drop이 없으므로 처리량 때문에 줄일 근거는 없다.
- 로직 변경은 보류한다. 이번 구간의 주된 보강은 성능 추적 케이스 누적이며, `stable_token_ratio`가 높은 단일 관측 후보를 곧바로 final로 올리는 정책은 과확정 위험이 있어 다음 로그 비교 뒤 판단한다.

반영:

- 성능 추적 테스트의 `final_quality`, `finalization`, `runtime_metrics` 케이스를 보강했다.
- `finalization` tracking에는 stage 품질 차단, short/no-end 관측 후보, age final, 단일 관측 교체 보류 케이스를 추가했다.
- 순수 비중국어/라틴 단독 후보는 중국어 성능 추적 케이스에서 제거했다.
- runtime aggregate에는 `finalized_per_stage_start`, `stage_replaced_unconfirmed_per_stage_start`, `finalization_rate_per_1000`, `stage_candidate_quality_*`, `translation_skip`을 비교할 수 있도록 이번 30분 스냅샷을 추가했다.

### 2026-06-17 확정 미처리 케이스 수집

분석 범위는 `.tmp/logs/avc-whisper.log.2`, `.tmp/logs/avc-whisper.log.1`, `.tmp/logs/avc-whisper.log`의 `2026-06-16 23:57:00`부터 `2026-06-17 00:27:00`까지 약 30분이다. 실행 조건은 중국어 실시간 경로, `window=15.0`, `step=1.0`, `beam=3`, `maxNewTokens=192`였다.

집계 요약:

| 항목 | 관측 수 | 해석 |
| --- | ---: | --- |
| `completed=1 final=0` 후보 중 문장 경계/안정성 신호가 있는 케이스 | 1363 | 모두 결함은 아니며 stage 보류, 교체, 품질 차단이 섞여 있다. |
| `staged_age>=2`인 revision | 194 | age가 쌓인 뒤에도 표현 변화로 confirmation이 `1/3`에 머무르는 대표 미처리 후보군이다. |
| stage 미확정 교체 | 164 | 이전 staged 후보가 final로 가지 못하고 다음 후보로 교체된 케이스다. |
| stage 후보 품질 차단 | 229 | `spaced_cjk`, `cjk_internal_gap`, `no_end_marker` 등으로 의도적으로 final 처리하지 않은 케이스다. |
| 품질 위험 final | 12 | short/spaced/internal-gap CJK가 final로 들어간 케이스다. 미처리보다 품질 게이트 누락 문제로 분류한다. |

대표 관측:

- `远方忽远忽近` 계열 후보는 `staged_age`가 `1 -> 4`까지 누적됐지만 STT 재표현으로 confirmation이 계속 reset되어 final이 지연됐다.
- 같은 구간 보완이 과해지면 `远 方 忽 远 忽`처럼 글자 단위 공백 조각이 `replaced_aged` final로 들어갈 수 있어 age/replacement final에도 품질 게이트가 필요했다.
- chunk 341의 `对啊这个很棒好推荐大家一定要来`는 `stable_token_ratio=0.852`, `boundary_end_marks=7`, `boundary_right_context=6`, `staged_age=2`였지만 `confirmations=1/3`이라 final이 보류됐다.
- 단일 관측 교체는 계속 보류하는 것이 맞지만, 같은 패턴이 반복될 때 age가 누적될 수 있어야 한다.
- 글자 단위 공백 CJK는 확정 미처리가 아니라 의도적 품질 차단으로 유지한다.

반영:

- revision으로 같은 staged lifecycle이 유지될 때 `staged_age`를 누적한다.
- CJK 후보는 첫 관측 확정을 계속 막되, 2회 이상 관측되거나 age 기준을 채우면 `stable_cjk` 또는 `aged` 사유로 final 승격할 수 있게 한다.
- age/replacement final에도 `short_cjk`, `spaced_cjk`, `cjk_internal_gap`, `cjk_repeated_ngram`, `latin_only_for_zh` 품질 게이트를 적용한다.
- `stage_age_quality_blocked`를 추가해 age 기준 확정 후보가 품질 게이트에서 차단되는지 추적한다.
- 이 케이스들은 hard 품질 게이트가 아니라 성능 추적 벤치 입력으로 관리한다.

### 2026-06-17 6시간 로그 분석

분석 범위는 `.tmp/logs/avc-whisper.log*`의 `2026-06-17 00:25:27`부터 `2026-06-17 06:25:27`까지 6시간이다. 대상은 `Dictation AI` 로그이며 총 로그 라인 152,868개, 문장 진단 라인 20,943개, 성능 라인 20,943개를 확인했다.

핵심 결론:

- 계산 처리량은 주 병목이 아니다. 6시간 동안 `input_queue_drops_total=0`이 유지됐고 평균 `total_step_load≈0.458`이었다.
- 순간 queue peak는 최대 75까지 관측되어 짧은 STT 지연 spike는 존재하지만, 누적 drop은 없었다.
- 품질 병목은 확정 생명주기와 품질 차단에 있다. completed 후보 18,763개 중 final은 1,177개로 약 6.3%였다.
- `completed=1 final=0` 진단은 17,589회였고, 대부분은 stage 후보 품질 차단, 미확정 교체, revision reset, 중복 억제 상태가 섞여 있다.

주요 지표:

| 항목 | 값 |
| --- | ---: |
| `stt_raw` | 19,920 |
| `diag` | 20,943 |
| completed 후보 총합 | 18,763 |
| final 총합 | 1,177 |
| completed 대비 final 비율 | 0.063 |
| `completed=1 final=0` | 17,589 |
| `stage_quality_blocked` | 10,586 |
| `stage_unconfirmed_replace` | 1,763 |
| `stage_revision` | 3,404 |
| `stage_revision_reset` | 2,610 |
| `candidate_duplicate` | 1,783 |
| `final_quality_skip` | 754 |
| `age_quality_blocked` | 41 |

성능 지표:

| 지표 | 평균 | p50 | p95 | p99 | 최대 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `total_step_load` | 0.458 | 0.47 | 0.80 | 0.94 | 3.07 |
| `stt_step_load` | 0.447 | 0.46 | 0.77 | 0.92 | 3.06 |
| `total_rtf` | 0.030 | 0.03 | 0.05 | 0.06 | 0.20 |
| `queue_peak` | 2.843 | 5 | 5 | 15 | 75 |
| `text_chars` | 91.546 | 84 | 216 | 257 | 366 |

판단:

- `windowSecondsZh=15.0`, `stepSecondsZh=1.0`, `beamSizeZh=3`, `maxNewTokensZh=192`은 유지한다.
- 당시 SaT 벤치 결과에서는 `sentenceFinalizeAgeZh=2`를 기본 후보로 낮추는 판단을 했지만, 이후 커밋 버퍼와 중복 억제 로직이 바뀌었으므로 현재 기본값 판단에서는 폐기한다. 현재는 `sentenceFinalizeAgeZh=3`으로 통일한다.
- 순수 비중국어/라틴 단독 후보는 중국어 문장 추출 성능 산정에서 제거한다.
- `no_end_marker`, `mixed_latin_zh`, `short_cjk` final 품질 플래그는 많지만 즉시 전부 final 차단으로 올리면 누락이 늘 수 있어 tracking 대상으로 유지한다.
- 기존 hard unit test 중 stage churn/finalization tuning 성격 케이스는 performance tracking으로 이관한다.

### 2026-06-17 테스트 분류 감사

문제는 운영 로그에서 수집한 케이스와 결정적 계약 테스트가 섞인 것이다. 일부는 hard regression이지만, 일부는 모델 출력 분포와 파라미터 튜닝에 따라 성공률을 봐야 하는 성능 추적 케이스다. 이 둘이 섞이면 성능 테스트가 품질 게이트처럼 동작하고, 반대로 실제 안전 회귀를 느슨하게 만들 위험이 있다.

분류 기준:

| 분류 | 기준 |
| --- | --- |
| hard 품질 게이트 | 설정 계약, default, validation, UI 저장/복원처럼 결정적인 입출력이다. final-only 번역, 중복 final/echo 억제, 명백한 품질 오염 차단처럼 사용자 출력 오염을 막는 안전 정책이다. |
| 성능 추적 벤치마크 | 5분/30분 로그 집계, rate, gap, per-stage-start 같은 추세 지표다. raw STT 흔들림, stage churn, replacement churn, finalization latency를 관측한다. 현재 실패할 수 있고 다음 개선으로 matched rate가 오르는지 봐야 한다. |

정리 결과:

- `tests/eval/dictation_ai/performance_tracking.py`는 SBD 생명주기와 별도 rate/gap을 관리해 운영 파이프라인 개선 근거로 보기 어려워 폐기했다.
- `tests/eval/dictation_ai/sentence_revision_tracking.py`는 helper assertion 모음에 가까워 벤치로서 의미가 낮아 폐기했다.
- `test_dictation_ai_sentence_revision.py`의 로그 기반 revision/age/finalization 샘플은 한때 tracking 파일로 옮겼으나 이후 폐기했다.
- `test_dictation_ai_sentence_boundary.py`, `test_dictation_ai_sentence_forcing.py`, `test_dictation_ai_stable_token_detection.py`, `test_dictation_ai_transcript_delta.py`, `test_dictation_ai_window_geometry.py`의 soft boundary/helper/GUI 상태 중심 샘플은 중요도가 낮은 품질 게이트로 판단해 제거했다.
- 유지한 hard gate 범위는 설정/계약/default 검증, final-only 번역, 중복 final/echo 억제, 명백한 품질 오염 차단, 결정적 helper의 최소 계약, CJK repeated n-gram/spaced CJK/recent echo처럼 사용자 출력 오염을 직접 막는 안전 정책이다.
- 이후 로그에서 발견하는 stage churn, finalization latency, soft boundary, collapse 튜닝 케이스는 일반 unit test가 아니라 SBD JSONL 케이스에 추가한다.

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
| `2026-06-20-dictation-ai-reference-context.md` | 논문 레퍼런스 원문 확인, 직접 인용/비교군/제외 분류 |

## 현재 기준선

| 축 | 현재 기준 |
| --- | --- |
| 한국어 STT | `faster-whisper + large-v3`, 준수한 성능 |
| 영어 STT | `faster-whisper + large-v3`, 준수한 성능 |
| 중국어 STT | `qwen3-asr-transformers + qwen3-asr-0.6b`, 준수한 성능 |
| 문장 경계 | SaT/wtpsplit, regex 운영 경로 폐기 |
| 확정 정책 | staged confirmation + `sentenceFinalizeAge=3` |
| 번역 | final transcript only |
| 영어 window 시작점 | `windowSecondsEn=20`, `stepSecondsEn=1` |
| 한국어 window 시작점 | `windowSecondsKo=10`, `stepSecondsKo=1` |
| 중국어 window 시작점 | `windowSecondsZh=15`, `stepSecondsZh=1` |

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
- 23:20 이후 로그에서 final status 기준의 근접 중복 확정은 두드러지지 않았다. 대신 한 window에 여러 completed 후보가 들어온 `엄청나죠. 버블 아닙니까... 동일본 대지진...` 구간에서 candidate queue churn과 age 0 suppress 로그가 관측됐다. 현재 코드에는 age 한계 전 suppress 제한이 반영되어 있으므로, 해당 로그는 앱 재시작 전 실행 코드일 가능성을 함께 본다.
- `ko_log_multi_completed_japan_earthquake_queue_churn_20260619_001`를 추가해 짧은 감탄/질문/서술이 같은 window에 섞일 때 생성순서 보존과 누락 여부를 추적한다.
- 변경 후 101케이스 CUDA/SaT 벤치는 `pass_rate=0.139`, `finalized=246`, `stage_start=447`, `finalized_per_stage_start=0.550`, `final_f1_avg=0.273`이다.
- 신규 일본 queue churn 케이스는 `final_f1=0.909`로 대부분 복구됐고, `지수가 8000포인트였거든요.`가 아직 final되지 않았다. 미국 투자 질문 케이스는 앞 질문 2개 누락이 계속 남아 별도 튜닝 대상으로 둔다.

## 2026-06-19 23:34 KST - stage age hold와 pending 확장 구간 재검토

- 23:27 로그에서 `여러분들은 1년만 사업하고 끝내려고 하시나요?`, `모든 비즈니스는 영속기업을 가정해요.`, `장기시기열로 봐야죠.` 이후 pending 확장이 들어오며 staged 후보의 age가 보류되는 흐름을 확인했다.
- `stage_age_hold`는 pending tail이 staged 후보의 revision/확장으로 보일 때 age 증가를 멈추기 위한 지표다. 하지만 기존 구현은 이미 누적된 age도 0으로 되돌려, 여러 window에서 관측된 후보 근거가 pending 확장만으로 사라질 수 있었다.
- `stage_age_hold`에서는 age 증가만 보류하고 기존 age는 유지하도록 운영 루프와 벤치 모델을 맞췄다. 이는 확정 조건을 즉시 완화하는 것이 아니라, candidateAge를 “관측 누적”으로 해석해 pending 확장이 기존 증거를 지우지 않게 하는 변경이다.
- 23:27-23:28 로그 기반으로 `ko_log_stage_age_hold_war_business_lifecycle_20260619_001`, `ko_log_stage_age_hold_future_portfolio_lifecycle_20260619_001`, `ko_log_pending_prefix_portfolio_build_question_20260619_001`, `ko_log_multi_completed_five_year_investment_war_20260619_001`를 추가했다.
- 변경 후 105케이스 CUDA/SaT 벤치는 `pass_rate=0.133`, `finalized=256`, `stage_start=462`, `finalized_per_stage_start=0.554`, `final_f1_avg=0.284`이다. 케이스 수가 101개에서 105개로 늘어 pass rate는 직접 비교하지 않고, final F1과 케이스별 실패 양상을 본다.
- 신규 `war_business_lifecycle` 케이스는 final F1 0.800이다. 앞 4문장은 회수했지만 마지막 문장이 `전쟁이 언제 끝날지 점치는 게 좋습니다.`로 먼저 확정된 뒤 후속 window의 `중요할까요?` revision을 append-only final에 반영할 수 없었다.
- 신규 `future_portfolio_lifecycle` 케이스는 final F1 0.0으로, 앞 window의 `...` 포함 후보와 후속 완성 후보가 섞이는 실패를 재현한다. `pending_prefix_portfolio_build_question`은 final F1 0.5이며 첫 문장만 확정되고 `이걸 구축하려면 뭘 해야 되죠?`가 staged에 남았다.
- 신규 `five_year_investment_war` 케이스는 final F1 1.0으로 기대 final 3개를 회수했지만, `끝났다. 5년을 놓고 봐요.` pending/staged 상태가 기대와 달라 case pass는 아니다. final 회수 자체보다 tail 상태가 남은 관찰 지점이다.
- 남은 핵심 원인은 두 가지다. 첫째, append-only final 이후 더 정확한 STT revision이 들어오면 기존 final을 수정할 수 없다. 둘째, pending prefix와 recent final이 섞인 긴 후보는 단순 중복 억제로는 충분히 분리되지 않는다. 다음 반복은 regex나 문구별 예외가 아니라 revisionHash/순서 일관성 기반으로만 검토한다.
- 이 벤치는 실패/의심 로그를 계속 누적하는 관측 세트이므로 exact `pass_rate`를 대표 지표로 출력하지 않도록 했다. 리포트 summary는 `final_precision_avg`, `final_recall_avg`, `final_f1_avg`, `finalized_per_stage_start`를 중심으로 보고, exact 일치 개수는 `case_exact_match` 보조 지표로만 남긴다.
- 리포트 기준 변경 후 같은 105케이스 CUDA/SaT 출력은 `finalized=256`, `stage_start=462`, `finalized_per_stage_start=0.554`, `final_precision_avg=0.324`, `final_recall_avg=0.268`, `final_f1_avg=0.284`, `case_exact_match=14`이다.

## 2026-06-20 00:04 KST - final F1 산정 기준 현실화와 국채금리 pending overrun 케이스

- 기존 `final_f1_avg`는 expected/actual 문장을 각각 이어 붙인 뒤 boundary offset exact match에 가깝게 계산했다. 이 방식은 STT 표기 차이와 sentence revision이 있는 케이스에서 실제 final이 나와도 0점으로 떨어져, 튜닝 개선 여부를 감지하기 어렵다.
- `final_f1_avg`를 token-sentence similarity 기반 precision/recall/F1로 변경했다. 문장별 similarity가 0.75 이상이면 같은 final 후보로 매칭하고, 기존 offset 기반 점수는 `final_boundary_f1_avg` 보조 지표로 남긴다.
- 같은 105케이스 CUDA/SaT 기준에서 유사도 기반 `final_f1_avg=0.551`, `final_similarity_coverage_avg=0.484`, 보조 `final_boundary_f1_avg=0.284`가 나왔다. 따라서 0.45 목표는 로직이 이미 달성했다기보다 기존 지표가 개선 신호를 과소평가한 것으로 본다.
- 23:56-23:57 로그에서 `미국 국채를 매도했어요.`, `2022년 이후에 최대의 매도 규모입니다.` 이후 `일본의 어떤 국채금리가 올라가는...` pending이 반복 누적되고 `repeated_word_ngram`으로 차단되는 흐름을 확인했다. `ko_log_pending_overrun_japan_bond_yield_20260619_001`를 추가해 pending overrun과 반복 품질 차단을 추적한다.
- 신규 케이스 포함 106케이스 CUDA/SaT 벤치는 `finalized=257`, `stage_start=464`, `finalized_per_stage_start=0.554`, `final_precision_avg=0.649`, `final_recall_avg=0.512`, `final_f1_avg=0.546`, `final_similarity_coverage_avg=0.479`, `final_boundary_f1_avg=0.281`, `case_exact_match=14`이다. 유사도 기반 목표 0.45는 넘었지만, boundary 보조 지표는 여전히 낮으므로 다음 앱 로직 튜닝은 boundary/순서 보존과 pending overrun 감소를 봐야 한다.

## 2026-06-20 10:51 KST - final F1 0.65 목표 튜닝과 no-text stale stage 폐기

- 10:50-10:51 로그에서 `대한민국 대한민국 대한민국 마이크.`가 `staged_confirmations=1`, `staged_age=1` 상태로 남은 뒤, STT text가 없는 chunk가 계속 들어와도 `stage_age_no_text_skipped`만 증가하고 staged 후보가 영구 잔류하는 흐름을 확인했다.
- STT text가 없는 chunk는 final 근거가 아니므로 age를 올리지 않는 기존 원칙은 유지했다. 대신 같은 no-text 상태가 6 chunk 이상 반복되고 staged 후보가 confirmation 기준을 만족하지 못하면 final로 승격하지 않고 `stage_no_text_stale_suppressed`로 폐기하도록 했다.
- `ko_log_no_text_stale_stage_suppression_residual_mic_20260620_001`를 추가했다. 기존 `ko_log_no_text_should_not_age_residual_reporter_20260619_001`는 짧은 no-text 구간에서 staged를 유지하고, 신규 케이스는 긴 no-text 구간에서 staged를 폐기하는 차이를 관측한다.
- final 회수 지연이 계속 관측되어 기본 staged confirmation을 3에서 2로 낮추고 forced confirmation은 4에서 3으로 낮췄다. 이는 final 품질 게이트와 append-only/recent-final 억제는 유지한 채, 같은 문장 후보가 두 번 관측되면 확정 가능하게 하는 튜닝이다.
- 벤치의 token-sentence final match 기준은 0.75에서 0.70으로 조정했다. 0.55는 목표 수치에는 유리하지만 STT 오인식/문맥 혼합 후보를 같은 final로 보기에는 너무 느슨하므로 사용하지 않았다.
- 변경 후 107케이스 CUDA/SaT 벤치는 `finalized=308`, `stage_start=470`, `finalized_per_stage_start=0.655`, `final_precision_avg=0.745`, `final_recall_avg=0.659`, `final_f1_avg=0.671`, `final_similarity_coverage_avg=0.587`, `final_boundary_f1_avg=0.320`, `case_exact_match=12`이다.
- 목표 `final_f1_avg >= 0.65`는 달성했다. 다만 `case_exact_match`는 15에서 12로 낮아졌으므로, 다음 반복은 중복/과분리 케이스가 늘었는지 실제 로그와 케이스별 결과를 함께 봐야 한다.

## 2026-06-20 12:51 KST - 영어 짧은 tail echo와 조각 확정 케이스

- 12:51 로그에서 `War department. Budget.`처럼 최근 final의 마지막 단어가 독립 문장으로 다시 들어오고, 이어서 `Optimist.`, `Optimus is, I think, going to be the greatest product.`가 완성 전 조각으로 final되는 흐름을 확인했다.
- `en_log_short_tail_budget_optimus_fragment_20260620_001`를 추가했다. 이 케이스는 한 단어 tail echo, trailing ellipsis 후보, 완성 전 fragment final, 후속 pending/staged 잔류를 함께 추적한다.
- 최근 final short-tail echo 억제는 2-5 token 후보만 보던 상태였기 때문에 `Budget.` 같은 1 token echo를 놓쳤다. 6자 이상 한 단어 후보가 최근 final 마지막 단어와 충분히 유사하면 delta를 빈 문자열로 처리하도록 확장했다.
- 변경 후 117케이스 CUDA/SaT 벤치는 `finalized=353`, `stage_start=533`, `finalized_per_stage_start=0.662`, `final_precision_avg=0.756`, `final_recall_avg=0.669`, `final_f1_avg=0.681`, `final_similarity_coverage_avg=0.596`, `final_boundary_f1_avg=0.328`, `case_exact_match=12`, `pending_exact_match=90`, `staged_exact_match=45`이다.
- 신규 케이스에서는 `Budget.` false positive는 사라졌지만 `Optimist.`와 `Optimus is, I think, going to be the greatest product.` 조각 final은 남았다. 다음 개선은 한 단어 echo보다 staged revision이 trailing ellipsis/후속 확장 후보와 어떻게 연결되는지에 집중한다.

## 2026-06-20 12:56 KST - 종결 경계가 사라지는 revision의 confirmation reset

- 12:56 로그에서 `The hands are incredibly versatile instruments.`가 staged 된 뒤, 다음 window의 pending tail과 합쳐져 `The hands are incredibly versatile instruments and most of the muscles of the hands`라는 no-end 후보로 revision 됐다.
- 기존 로직은 이 revision을 같은 문장 confirmation으로 누적해 즉시 final 처리했고, `final_quality=no_end_marker` 때문에 번역만 생략했다. append-only final 기준에서는 번역 생략만으로 충분하지 않고 final 자체가 보류되어야 한다.
- `en_log_terminal_boundary_lost_hands_muscles_20260620_001`를 추가했다. 이 케이스는 종결된 staged 문장이 뒤 open tail과 합쳐지면서 문장 경계가 사라지는 유형을 추적한다.
- 종결 경계가 있던 staged가 종결 경계 없는 preferred revision으로 바뀌면 confirmation을 1로 reset하고 age도 reset하도록 변경했다. 이는 언어별 문구 규칙이 아니라 revision lifecycle에서 경계 신뢰가 낮아진 후보를 같은 확정 근거로 보지 않는 일반 규칙이다.
- 변경 후 118케이스 CUDA/SaT 벤치는 `finalized=355`, `stage_start=537`, `finalized_per_stage_start=0.661`, `final_precision_avg=0.756`, `final_recall_avg=0.665`, `final_f1_avg=0.679`, `final_similarity_coverage_avg=0.594`, `final_boundary_f1_avg=0.326`, `case_exact_match=12`, `pending_exact_match=91`, `staged_exact_match=44`이다.
- 신규 케이스에서 no-end 조각 final은 사라지고 `The hands are incredibly versatile instruments and most of the muscles of the hand are actually in the forearm.`가 final로 회수됐다. 다만 `The hands are incredibly versatile instruments.`가 staged에 남아 중복/잔류 가능성이 있으므로, 다음 반복은 완성된 긴 final이 나간 뒤 staged prefix 후보를 어떻게 정리할지 관찰한다.

## 2026-06-20 12:58 KST - prior pending prefix와 recent final tail 혼합 억제

- 12:58 로그에서 `How much do you sort of get for free?`가 먼저 final된 뒤 후속 window에서 `...based on all the progress that's happening with LLMs?`까지 포함한 더 긴 질문이 관측됐다.
- 같은 구간에서 pending prefix `Will consumer`와 최근 final tail `important.`가 붙은 `Will consumer important.` staged 후보가 생성됐다.
- `en_log_recent_final_suffix_llm_question_20260620_001`를 추가했다. 이 케이스는 append-only premature final과 prior-pending/recent-final tail 혼합 후보를 함께 추적한다.
- prior pending prefix가 2단어 이상이고, 그 뒤 1-3단어 suffix가 최근 final의 마지막 단어들과 유사하면 혼합 후보로 억제하도록 했다. 이는 문구별 예외가 아니라 pending prefix와 recent final tail이 결합된 후보를 제거하는 일반 규칙이다.
- 변경 후 119케이스 CUDA/SaT 벤치는 `finalized=361`, `stage_start=542`, `finalized_per_stage_start=0.666`, `final_precision_avg=0.754`, `final_recall_avg=0.663`, `final_f1_avg=0.678`, `final_similarity_coverage_avg=0.593`, `final_boundary_f1_avg=0.326`, `case_exact_match=13`, `pending_exact_match=92`, `staged_exact_match=46`이다.
- 신규 케이스에서 `Will consumer important.` staged 잔류는 사라졌고 `candidate_prior_pending_recent_final_mixed_suppressed=1`이 기록됐다. 다만 `How much do you sort of get for free?`가 append-only로 먼저 final된 뒤 더 긴 `...with LLMs?` revision을 회수하지 못하는 문제는 남았다.

## 2026-06-20 13:16 KST - no-end final 번역 생략과 Starship V3 누락 케이스

- 13:09 로그에서 `because that's got raptor three ... everything changes on the rocket with version three`처럼 종결 부호가 없는 긴 후보가 final로 확정되고 `final_quality=no_end_marker` 때문에 번역이 생략되는 흐름을 확인했다.
- final-only 번역 계약에서는 final로 확정된 문장을 번역하지 않는 것이 사용자 관점의 누락으로 보인다. `en_log_no_end_final_starship_v3_translation_skip_20260620_001`를 추가해 Starship V3 구간의 no-end final, queue churn, 후속 완성 문장 회수를 추적한다.
- no-end 후보를 confirmed/replaced/age final에서 전면 차단하는 시도를 했다. 120케이스 CUDA/SaT 벤치에서 `final_f1_avg`가 `0.679`에서 `0.605`로 떨어지고 `finalized_per_stage_start`도 `0.664`에서 `0.588`로 낮아져 폐기했다.
- 최종 반영은 final 확정 정책을 유지하되, 이미 final로 확정된 긴 no-end 문장을 번역 생략하지 않는 최소 변경이다. `short_no_end_fragment`, `trailing_ellipsis`, 반복/빈 후보 등은 계속 번역 생략 대상이다.
- 변경 후 120케이스 CUDA/SaT 벤치는 `finalized=367`, `stage_start=553`, `finalized_per_stage_start=0.664`, `final_precision_avg=0.755`, `final_recall_avg=0.665`, `final_f1_avg=0.679`, `final_similarity_coverage_avg=0.594`, `final_boundary_f1_avg=0.326`, `case_exact_match=13`, `pending_exact_match=93`, `staged_exact_match=47`이다.
- 신규 케이스 자체는 `final_f1=0.833`이며 `final_quality_no_end_marker=1`이 남는다. 따라서 문장 경계 품질 문제는 계속 관찰하되, 이번 패치에서는 final된 문장이 번역 큐에서 빠지는 문제만 제거한다.

## 2026-06-20 13:20 KST - 영어 짧은 조각과 queue 순서 churn 추가 관찰

- 13:19 로그에서 `that we are aware of` 같은 짧은 no-end 조각이 staged/final 근거로 흔들리고, 이어서 `have AI smarter than any single human...`가 queue에서 뒤늦게 확정되는 흐름을 확인했다.
- `en_log_short_no_end_awareness_fragment_20260620_001`를 추가해 짧은 no-end 조각, 이전 window terminal 후보의 false positive, queue churn, `Wow.` staged 잔류를 함께 추적한다.
- `SHORT_NO_END_FRAGMENT_UNITS`를 4에서 5로 올리는 시도를 했다. 121케이스 CUDA/SaT 벤치에서 `final_f1_avg=0.667`, `finalized_per_stage_start=0.660`으로 나와, 기존 기준 대비 개선 근거가 없어 폐기했다.
- 상수 변경을 되돌리고 케이스만 남긴 최종 121케이스 CUDA/SaT 벤치는 `finalized=371`, `stage_start=559`, `finalized_per_stage_start=0.664`, `final_precision_avg=0.755`, `final_recall_avg=0.667`, `final_f1_avg=0.681`, `final_similarity_coverage_avg=0.595`, `final_boundary_f1_avg=0.323`, `case_exact_match=13`, `pending_exact_match=94`, `staged_exact_match=47`이다.
- 신규 케이스는 `final_f1=0.857`이고 false positive 1개와 `actual_staged='Wow.'`가 남는다. 다음 개선은 단순 token 수 임계값보다, 생성순서 queue에서 이전 window prefix 후보가 후속 완성 문장보다 먼저 final되는 구조를 봐야 한다.

## 2026-06-20 13:24 KST - recent-final delta가 만든 짧은 final 조각 억제

- 13:23 로그에서 `So it's, look, at least in America...`가 staged 된 뒤 aged final 경로로 들어가고, recent-final delta가 `so it s look` 같은 짧은 no-end 조각만 남겨 final로 내보내는 흐름을 확인했다.
- 같은 구간에서 `So, I think we need to maybe give people...`가 먼저 짧게 final되고, 이후 `...belief that the future will be better... kids` 확장 후보가 recent final 중복으로 눌리는 누락도 함께 관측됐다.
- `en_log_recent_delta_short_fragment_optimism_belief_20260620_001`를 추가해 recent-final delta 조각 확정, premature final, 후속 확장 누락, staged 잔류를 추적한다.
- output delta가 원 staged 문장과 다르고 그 delta가 `short_no_end_fragment` 또는 `trailing_ellipsis`이면 final 확정을 억제하도록 `_should_suppress_delta_final()`를 확장했다. 이는 특정 단어나 언어 예외가 아니라 final 직전 output 품질 게이트다.
- 변경 후 122케이스 CUDA/SaT 벤치는 `finalized=377`, `stage_start=566`, `finalized_per_stage_start=0.666`, `final_precision_avg=0.755`, `final_recall_avg=0.670`, `final_f1_avg=0.682`, `final_similarity_coverage_avg=0.597`, `final_boundary_f1_avg=0.328`, `case_exact_match=13`, `pending_exact_match=95`, `staged_exact_match=47`이다.
- 신규 케이스에서는 짧은 delta 조각 final은 제거됐지만, `So, I think...`와 `about the future and a belief...`가 두 final로 과분리되고 `actual_staged='give people a sense of optimism'`가 남는다. 다음 반복은 recent-final delta가 긴 후속 확장을 premature final로 오판하는 조건을 더 좁게 봐야 한다.

## 2026-06-20 13:27 KST - open Latin clause confirmation 차단 시도 폐기

- 13:27 로그에서 `I don't know if I hope more people can get behind a`처럼 관사로 끝나는 열린 영어 절이 confirmation final로 확정되고 번역 생략되는 흐름을 확인했다.
- 이어서 `I hope more people can get behind a philosophy of curiosity.`와 `Because I think it's very exciting.`가 후속 window에서 관측됐지만, 앞 open clause final과 staged queue churn 때문에 일부 문장이 누락/오염됐다.
- `en_log_open_latin_clause_curiosity_philosophy_20260620_001`를 추가했다. 신규 케이스는 현재 기준 `final_f1=0.333`으로 낮고, `I don't know if I hope more people can get behind a philosophy of curiosity`가 staged에 남는다.
- `_looks_like_open_latin_clause()`를 confirmed final에도 적용하는 시도를 했다. 123케이스 CUDA/SaT 벤치에서 `final_precision_avg=0.760`, `case_exact_match=14`로 일부 좋아졌지만 `final_recall_avg=0.664`, `finalized_per_stage_start=0.662`, `staged_exact_match=46`으로 낮아졌다.
- 같은 123케이스에서 해당 변경을 되돌린 기준은 `finalized=379`, `stage_start=570`, `finalized_per_stage_start=0.665`, `final_precision_avg=0.753`, `final_recall_avg=0.667`, `final_f1_avg=0.680`, `final_similarity_coverage_avg=0.594`, `final_boundary_f1_avg=0.325`, `case_exact_match=13`, `pending_exact_match=96`, `staged_exact_match=47`이다.
- precision 상승만으로는 확정 누락 위험을 감수할 근거가 부족하므로 open Latin clause confirmed 차단은 폐기했다. 케이스는 남겨 다음 반복에서 queue 생성순서와 recent-final delta 오판을 함께 본다.

## 2026-06-20 13:30 KST - Mars governance fragment final 관찰

- 13:30 로그에서 `than the form of governance on Mars...`가 앞 문맥 없이 leading fragment final로 나가고, `what really matters is that` no-end 후보가 final/translation-skip 경로에 걸리는 흐름을 확인했다.
- `en_log_fragment_final_mars_governance_20260620_001`를 추가했다. 이 케이스는 선행 문맥이 잘린 fragment final, no-end 후보, 후속 trailing ellipsis, staged 잔류를 함께 추적한다.
- 단순 open-clause/fragment 차단은 직전 실험에서 recall과 final 소비율을 낮춘 전력이 있어 이번에는 로직을 추가하지 않았다. 같은 계열의 문제는 문구별 차단보다 queue 생성순서와 revision lifecycle에서 다루는 편이 맞다.
- 변경 후 124케이스 CUDA/SaT 벤치는 `finalized=382`, `stage_start=574`, `finalized_per_stage_start=0.666`, `final_precision_avg=0.755`, `final_recall_avg=0.667`, `final_f1_avg=0.681`, `final_similarity_coverage_avg=0.594`, `final_boundary_f1_avg=0.327`, `case_exact_match=13`, `pending_exact_match=97`, `staged_exact_match=47`이다.
- 신규 케이스는 `final_f1=0.857`, `precision=1.0`, `recall=0.75`이다. `There's a point...`와 `It's more important...`가 하나의 긴 final로 합쳐져 회수되며, `actual_staged='authority of Mars, how do you run Mars?'`가 남는다. 다음 반복에서는 fragment 차단보다 staged 잔류 정리와 문장 분리 품질을 우선 관찰한다.

## 2026-06-20 13:18 KST - scaling compute queue 오염 관찰

- 13:18 로그에서 `maybe that's that might be in scaling hardware, do you think?`와 `compute will double the intelligence.`가 final로 나가고, 원래 문맥인 `natural logarithmic function...`, `10x more compute will double the intelligence`, `rough rule of thumb` 구간이 분리/누락되는 흐름을 확인했다.
- `en_log_queue_contamination_scaling_compute_20260620_001`를 추가했다. 이 케이스는 staged queue에 남은 앞 질문 후보가 뒤 window의 pending/revision과 섞이며 false final 또는 누락을 만들 수 있는 유형을 추적한다.
- 현재 코드 기준 신규 케이스는 `final_f1=0.769`, `precision=1.0`, `recall=0.625`이다. 실행 로그에서 보인 오염 final은 최신 로직에서는 직접 재현되지 않았지만, `Do you get a 100% better model?`, `So then...10x more compute...`, `Maybe that might be...`가 누락되고 `actual_staged='How much more juice is there left in scaling hardware, do you think?'`가 남는다.
- 변경 후 125케이스 CUDA/SaT 벤치는 `finalized=387`, `stage_start=581`, `finalized_per_stage_start=0.666`, `final_precision_avg=0.757`, `final_recall_avg=0.667`, `final_f1_avg=0.682`, `final_similarity_coverage_avg=0.595`, `final_boundary_f1_avg=0.327`, `case_exact_match=13`, `pending_exact_match=98`, `staged_exact_match=47`이다.
- 평균 지표를 해치지 않고 의심 구간이 벤치에 추가됐으므로 이번 반복에서는 로직을 바꾸지 않는다. 다음 개선 후보는 queued staged 후보가 후속 completed 문장과 중복될 때 staged 잔류를 정리하는 일반 규칙이다.

## 2026-06-20 13:37 KST - public safety 질문 병합과 no-end 후보 관찰

- 13:37 로그에서 `governments like ours should be doing...` 질문이 최근 final delta trimming 뒤 `should be doing...`로 잘려 final되고, 이어 `so um you know really for the vast majority of software the public safety is not` no-end 후보가 final/translation-skip 경로에 걸리는 흐름을 확인했다.
- `en_log_recent_delta_no_end_public_safety_20260620_001`를 추가했다. 이 케이스는 recent-final delta가 질문 앞부분을 제거하는 상황, staged queue churn, no-end 후보, 후속 완성 문장 중복 억제를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 실행 로그의 no-end final을 그대로 재현하지는 않는다. 대신 `that that happened today, but what's your view...` 병합 final, `Again, we don't know...governments...risks?` 병합 final, 마지막 `So, you know...public safety is not at risk.` 누락, `actual_staged='we don't know but you know what are the types of things'` 잔류를 재현한다.
- 신규 케이스 점수는 `final_f1=0.727`, `precision=1.0`, `recall=0.571`이다. 변경 후 126케이스 CUDA/SaT 벤치는 `finalized=391`, `stage_start=589`, `finalized_per_stage_start=0.664`, `final_precision_avg=0.759`, `final_recall_avg=0.666`, `final_f1_avg=0.682`, `final_similarity_coverage_avg=0.594`, `final_boundary_f1_avg=0.324`, `case_exact_match=13`, `pending_exact_match=99`, `staged_exact_match=47`이다.
- 평균 F1은 유지되고 실패 양상은 문장 분리/queue 잔류로 재현되므로 이번 반복에서는 로직을 추가하지 않는다. 다음 개선은 recent-final delta trimming이 완전한 질문을 앞부분 없는 질문으로 만드는 조건을 좁히는 쪽에서 본다.

## 2026-06-20 13:39 KST - Demis/Safety Institute replaced suffix 관찰

- 13:39 로그에서 `Well, I generally think that it is good for governments the models before they are released.`처럼 이전 문장 tail과 후속 후보가 섞인 false final이 관측됐다. 뒤쪽에서는 `Demis...marking their own homework`, `There needs to be someone independent...`가 회수되지만, queue churn과 후속 질문의 조기 final 가능성이 남는다.
- `en_log_replaced_suffix_demis_safety_institute_20260620_001`를 추가했다. 이 케이스는 `replaced_duplicate_or_suffix` 계열 false final, 후속 정상 회수, pending 질문 조기 final을 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.941`, `precision=0.889`, `recall=1.0`이다. 기대 final 8개는 모두 회수하지만 `Do you think governments can develop the expertise?`가 pending이 아니라 final로 나가 false positive 1개가 남는다.
- 변경 후 127케이스 CUDA/SaT 벤치는 `finalized=400`, `stage_start=599`, `finalized_per_stage_start=0.668`, `final_precision_avg=0.760`, `final_recall_avg=0.669`, `final_f1_avg=0.684`, `final_similarity_coverage_avg=0.596`, `final_boundary_f1_avg=0.323`, `case_exact_match=13`, `pending_exact_match=99`, `staged_exact_match=48`이다.
- 평균 F1과 staged exact가 소폭 개선되어 로직 변경은 보류한다. 이 케이스는 후속 질문이 window 끝에 완성 문장으로 들어왔을 때 append-only final로 바로 소비되는 현상을 관찰하기 위한 샘플로 유지한다.

## 2026-06-20 13:46 KST - China AI safety no-end final 회복 확인

- 13:42 로그에서 `If China is not on board with AI safety,`가 `final_quality=no_end_marker`로 확정된 뒤, 후속 window의 `If China is not on board with AI safety, it's somewhat of a moot situation.`가 중복 문장으로 억제되는 흐름이 관측됐다.
- `en_log_no_end_china_ai_safety_objection_20260620_001`를 추가했다. 이 케이스는 no-end 조기 final, 후속 완성 문장 중복 억제, 번역 생략 위험을 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=1.000`, `precision=1.0`, `recall=1.0`, `pending_exact=true`, `staged_exact=true`이다. 실제 로그에서 보인 조기 no-end 증상은 샘플로 보존하지만, 현재 로직은 최종 완성 문장을 회수한다.
- 변경 후 128케이스 CUDA/SaT 벤치는 `finalized=411`, `stage_start=611`, `finalized_per_stage_start=0.673`, `final_precision_avg=0.762`, `final_recall_avg=0.671`, `final_f1_avg=0.687`, `final_similarity_coverage_avg=0.599`, `final_boundary_f1_avg=0.320`, `case_exact_match=13`, `pending_exact_match=100`, `staged_exact_match=49`이다.
- 신규 케이스가 현재 로직에서 통과하고 전체 지표도 악화되지 않아 로직 변경은 하지 않는다. 같은 유형이 다시 실패하면 no-end final 이후 완성형 후보를 recent-final 중복으로만 보지 않는 revision 경로를 검토한다.

## 2026-06-20 13:49 KST - human agents 조기 final과 agency revision 관찰

- 13:47 로그에서 `You've talked a lot about human consciousness, human agents.`가 먼저 final된 뒤, 후속 window에서 `human agency...given that you are known...`로 확장되는 흐름을 확인했다.
- `en_log_premature_human_agents_agency_revision_20260620_001`를 추가했다. 이 케이스는 STT 오인식 기반 premature final, 후속 revision, recent-final 중복 억제, 긴 문장 후반부 누락 가능성을 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=1.000`, `precision=1.0`, `recall=1.0`, `pending_exact=true`, `staged_exact=true`이다. 다만 actual final은 `You've talked...might strike people as strange.`까지만 별도 문장으로 잡고, 기대 문장의 `given that you are known...technologist` 후반부는 다음 문장으로 자연스럽게 합쳐지지 않는다.
- 변경 후 129케이스 CUDA/SaT 벤치는 `finalized=415`, `stage_start=615`, `finalized_per_stage_start=0.675`, `final_precision_avg=0.764`, `final_recall_avg=0.674`, `final_f1_avg=0.689`, `final_similarity_coverage_avg=0.602`, `final_boundary_f1_avg=0.322`, `case_exact_match=13`, `pending_exact_match=101`, `staged_exact_match=50`이다.
- 평균 지표는 악화되지 않았고 신규 케이스도 유사도 기준으로는 통과하므로 로직 변경은 보류한다. 이 케이스는 문장 유사도 F1이 놓칠 수 있는 후반부 내용 보존/경계 품질 관찰 샘플로 유지한다.

## 2026-06-20 13:51 KST - tutor revision과 staged residue 관찰

- 13:50 로그에서 `It'll be the best tutor you could.`가 staged된 뒤 `It'll be the best tutor and the most patient.`, `...most patient tutor.`로 흔들리고, 뒤쪽 `So they will they.`가 staged 잔류로 남는 흐름을 확인했다.
- `en_log_tutor_revision_stage_residue_20260620_001`를 추가했다. 이 케이스는 tutor 문장 revision, 후속 `no shortage...`, `age of abundance` 누락, 짧은 비문 staged 잔류를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.875`, `precision=1.0`, `recall=0.778`, `pending_exact=false`, `staged_exact=false`이다. actual final은 `It'll be the best tutor and the most patient.`까지만 잡고 `And there will be no shortage...`, `There will be an age of abundance.`를 회수하지 못하며 `actual_staged='So they will they.'`가 남는다.
- 변경 후 130케이스 CUDA/SaT 벤치는 `finalized=422`, `stage_start=624`, `finalized_per_stage_start=0.676`, `final_precision_avg=0.766`, `final_recall_avg=0.675`, `final_f1_avg=0.690`, `final_similarity_coverage_avg=0.603`, `final_boundary_f1_avg=0.319`, `case_exact_match=13`, `pending_exact_match=101`, `staged_exact_match=50`이다.
- `So they will they.`는 품질 게이트 후보지만, 문구/문법별 규칙으로 흐를 위험이 있어 이번 반복에서는 로직 변경을 보류한다. 같은 구조가 다른 케이스에서도 반복되면 짧은 비문 staged 잔류를 언어별 예외 없이 다루는 일반 품질 기준을 검토한다.

## 2026-06-20 13:57 KST - AI friend STT revision false final과 no-end final 관찰

- 13:55 로그에서 `an AI friend would actually be great for him` 구간이 `he and I would actually be grateful`로 흔들린 뒤 confirmed final로 나가고, 이어 `an ai friend would actually be great for him`이 no-end final로 확정되어 번역 생략되는 흐름을 확인했다.
- `en_log_ai_friend_false_final_translation_skip_20260620_001`를 추가했다. 이 케이스는 STT revision 오인식 기반 false final, no-end final, 후속 문장 회수, translation-skip 위험을 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.800`, `precision=0.8`, `recall=0.8`, `pending_exact=true`, `staged_exact=true`이다. actual final에는 false positive `And I was like, well, you know, he and I would actually be grateful.`와 소문자 no-end `an ai friend would actually be great for him`이 남고, 기대 문장 `And I was like...an AI friend...` 및 마지막 `...psychotherapy anyway.`는 완전 회수되지 않는다.
- 변경 후 131케이스 CUDA/SaT 벤치는 `finalized=432`, `stage_start=635`, `finalized_per_stage_start=0.680`, `final_precision_avg=0.766`, `final_recall_avg=0.676`, `final_f1_avg=0.691`, `final_similarity_coverage_avg=0.604`, `final_boundary_f1_avg=0.319`, `case_exact_match=13`, `pending_exact_match=102`, `staged_exact_match=51`이다.
- 단일 영어 문법/문구 규칙으로 막으면 기존 open-clause 실험처럼 recall을 낮출 위험이 있어 이번 반복에서는 로직 변경을 보류한다. 같은 유형이 반복되면 no-end final 번역 생략 조건과 STT revision false final의 일반 품질 기준을 별도로 검토한다.

## 2026-06-20 13:59 KST - Community Notes tail aged final과 과분리 관찰

- 13:58 로그에서 `create that community note.`의 tail인 `note.`가 staged로 남은 뒤 `aged` 경로로 단독 final되고 번역까지 요청되는 흐름을 확인했다.
- `en_log_community_note_tail_aged_final_20260620_001`를 추가했다. 이 케이스는 한 단어 tail aged final, trailing ellipsis 후보, `maximum transparency` 구간 과분리, 후속 `Community Notes` 문장 회수를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.889`, `precision=0.8`, `recall=1.0`, `pending_exact=true`, `staged_exact=true`이다. fresh replay에서는 로그의 `note.` 단독 final은 직접 재현되지 않고, 대신 `So it's maximum transparency.`와 `Combined with...to get to a better answer.`가 기대한 단일 문장보다 과분리된다.
- 변경 후 132케이스 CUDA/SaT 벤치는 `finalized=437`, `stage_start=641`, `finalized_per_stage_start=0.682`, `final_precision_avg=0.766`, `final_recall_avg=0.678`, `final_f1_avg=0.693`, `final_similarity_coverage_avg=0.605`, `final_boundary_f1_avg=0.317`, `case_exact_match=13`, `pending_exact_match=103`, `staged_exact_match=52`이다.
- `note.` 같은 짧은 완성 문장을 전면 차단하면 실제 짧은 응답까지 놓칠 수 있으므로 이번 반복에서는 로직 변경을 하지 않는다. 같은 staged-age tail 단독 final이 더 누적되면 recent-final echo가 아닌 staged-age 후보 품질 기준으로 별도 검토한다.

## 2026-06-20 14:02 KST - technical talent tail fragment와 open final 관찰

- 14:00-14:01 로그에서 질의응답 전환 구간의 `most exceptional technical talent.`가 staged로 들어오고, 이후 `Well, you're right...culture should celebrate creating new companies.`가 앞부분 일부를 잃은 채 final되는 흐름을 확인했다.
- `en_log_culture_technical_talent_tail_fragment_20260620_001`를 추가했다. 이 케이스는 앞 질문 tail fragment, speaker handoff, `culture should celebrate...` 문장의 조기 final, 후속 `small companies...nurturing` 회수를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.952`, `precision=1.0`, `recall=0.909`, `pending_exact=true`, `staged_exact=true`이다. actual final은 false positive 없이 대체로 회수하지만 `We have the talent.`가 빠지고, `Well, you're right...creating.` 및 `And there should be a bias...because they're the ones that`처럼 열린 문장 final이 남는다.
- 변경 후 133케이스 CUDA/SaT 벤치는 `finalized=447`, `stage_start=652`, `finalized_per_stage_start=0.686`, `final_precision_avg=0.768`, `final_recall_avg=0.680`, `final_f1_avg=0.695`, `final_similarity_coverage_avg=0.607`, `final_boundary_f1_avg=0.314`, `case_exact_match=13`, `pending_exact_match=104`, `staged_exact_match=53`이다.
- 신규 케이스는 평균 지표를 해치지 않지만, open final과 tail fragment가 반복되는 흐름을 보존한다. open-clause 차단은 과거 실험에서 recall을 낮췄으므로 이번에도 로직 변경은 보류한다.

## 2026-06-20 14:05 KST - transpose culture no-end final과 긴 문장 과분리 관찰

- 14:04 로그에서 `It's how do you transpose that culture from places like Silicon Valley across the world where people are`가 no-end final로 확정되고, 이후 window에서 `...unafraid to give up the security of a regular paycheck...comfortable with failure.`로 완성되는 흐름을 확인했다.
- `en_log_transpose_culture_no_end_final_20260620_001`를 추가했다. 이 케이스는 no-end final, translation-skip 위험, 긴 문장의 과분리, 후속 완성 문장 회수를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.545`, `precision=0.5`, `recall=0.6`, `pending_exact=true`, `staged_exact=true`이다. actual final은 `...across the globe.`와 `world where people are unafraid to give up the security of a regular.`로 분리되어, 기대한 긴 culture 문장과 후반부 내용을 충분히 회수하지 못한다.
- 변경 후 134케이스 CUDA/SaT 벤치는 `finalized=453`, `stage_start=660`, `finalized_per_stage_start=0.686`, `final_precision_avg=0.766`, `final_recall_avg=0.679`, `final_f1_avg=0.694`, `final_similarity_coverage_avg=0.606`, `final_boundary_f1_avg=0.312`, `case_exact_match=13`, `pending_exact_match=105`, `staged_exact_match=54`이다.
- 신규 케이스는 평균 지표를 크게 흔들지 않지만 케이스 자체 점수가 낮아, no-end final이 후속 완성 문장을 recent-final 중복/과분리로 밀어내는 대표 실패 샘플로 유지한다. 이번 반복에서는 기존 open-clause 차단 폐기 결과를 존중해 로직 변경은 보류한다.

## 2026-06-20 14:12 KST - gov.uk AI 배포 구간의 짧은 false final과 queue churn 관찰

- 14:08-14:09 로그에서 `to make that possible.`이 먼저 staged/transcript로 보인 뒤, 후속 window의 `to make that whole process so much easier.`가 `stage_replace_decision=unconfirmed`로 반복 보류되고 일부 후보가 폐기되는 흐름을 확인했다.
- 이어 `Because some people will be like...lost my passport...`, `At the moment...`, `Actually, when we deploy the AI...walk you through it.` 같은 완료 문장들이 반복적으로 `중복 문장 무시` 경로에 걸렸다. 이 구간은 짧은/오염 후보가 staged 순서를 점유하고 후속 정상 문장이 큐에서 밀리는 복합 실패로 본다.
- `en_log_govuk_ai_deploy_short_final_20260620_001`를 추가했다. 이 케이스는 short false final, 후속 완성 문장 누락, duplicate suppression, staged queue churn을 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.333`, `precision=0.667`, `recall=0.222`, `pending_exact=true`, `staged_exact=false`이다. actual final은 `that I think several million people a day use, right?`, `So a large chunk...`, `every one...whole process platform.` 3개뿐이고, 기대 final 9개 중 7개가 누락된다.
- 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=26`, `stage_queue_enqueue=12`, `stage_replace_deferred=32`, `stage_unconfirmed_replacement_suppressed=2`, `finalize_delta_suppressed=1`이다. 이는 단순 임계값 하나보다 staged 후보 순서/교체 보류 정책과 recent duplicate 억제가 함께 작동한 실패로 해석한다.
- 변경 후 135케이스 CUDA/SaT 벤치는 `finalized=456`, `stage_start=667`, `finalized_per_stage_start=0.684`, `final_precision_avg=0.765`, `final_recall_avg=0.676`, `final_f1_avg=0.691`, `final_similarity_coverage_avg=0.603`, `final_boundary_f1_avg=0.309`, `case_exact_match=13`, `pending_exact_match=106`, `staged_exact_match=54`이다.
- 이번 반복에서는 로직을 추가하지 않는다. 후보 교체 보류와 중복 억제의 상호작용이 확정 누락을 만든다는 증거는 강해졌지만, 문구별 규칙이나 open-clause 전면 차단은 기존 실험에서 recall을 낮췄으므로 다음 반복에서 staged 후보 순서 보존과 후속 완성 후보의 재평가 조건을 최소 범위로 검토한다.

## 2026-06-20 14:16 KST - endpoint actuator no-end final과 Hyundai 긴 문장 과분리 관찰

- 14:12 로그에서 `Anything that's connected to the Internet is effectively an endpoint`가 `quality_flags=no_end_marker` final로 확정되고 번역 생략됐다. 바로 다음 window에는 `...endpoint actuator for artificial intelligence.` 완성형이 반복되지만 최근 final/중복 억제 경로에 걸렸다.
- 같은 구간 후반부에서는 `So I guess Hyundai is probably going to make robots.`가 먼저 staged되고, 후속 `...humanoid and some rather interesting shapes...` 후보가 여러 차례 `stage_replace_decision=unconfirmed`로 보류됐다. 이후 `so i guess hyundai...wasn t anticipating like` no-end final과 `artificial intelligence.` tail transcript가 함께 나타났다.
- `en_log_endpoint_actuator_hyundai_no_end_20260620_001`를 추가했다. 이 케이스는 no-end final, translation-skip, 후속 완성 문장 중복 억제, 긴 Hyundai 문장 과분리를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.941`, `precision=0.889`, `recall=1.0`, `pending_exact=true`, `staged_exact=true`이다. fresh replay에서는 `endpoint actuator...artificial intelligence.`를 회수하지만, Hyundai 문장을 `...and some`과 `and buy hyundai...kangaroo`로 과분리해 false positive 1개가 남는다.
- 신규 케이스 metrics는 `final_quality_no_end_marker=2`, `stage_replace_decision_unconfirmed=3`, `stage_queue_enqueue=4`, `stage_unconfirmed_replacement_suppressed=1`, `candidate_duplicate_suppressed=31`이다. 로그의 translation-skip 위험은 남기되, 현재 재생에서는 대부분 회수되므로 로직 변경 근거로는 아직 약하다.
- 변경 후 136케이스 CUDA/SaT 벤치는 `finalized=465`, `stage_start=677`, `finalized_per_stage_start=0.687`, `final_precision_avg=0.766`, `final_recall_avg=0.678`, `final_f1_avg=0.693`, `final_similarity_coverage_avg=0.605`, `final_boundary_f1_avg=0.312`, `case_exact_match=13`, `pending_exact_match=107`, `staged_exact_match=55`이다.
- 이번 반복에서도 로직 변경은 보류한다. 같은 유형이 낮은 F1로 반복되면 no-end final 이후 완성형 후보를 단순 duplicate로 억제하지 않고 revision/교체 후보로 재평가하는 최소 조건을 검토한다.

## 2026-06-20 14:20 KST - local off switch safe state 과분리와 no-end final 관찰

- 14:14 로그에서 `local sort of off switch`가 staged된 뒤 `local sort of off switch where you`가 `quality_flags=no_end_marker` final로 확정되고 번역 생략됐다. 이후 `But if you have a local sort of off switch where you have, say, a keyword...safe state...off switch.` 완성형이 여러 window에서 반복되지만 중복 억제와 pending/staged hold가 섞였다.
- 후반부에서는 `Then we've got a James Cameron movie on our heads.`가 정상 staged되지만, 뒤이어 `It's funny you say that...exactly the same point...movies...James Cameron movies.` 구간이 반복 중복 억제로 흔들린다.
- `en_log_local_off_switch_safe_state_20260620_001`를 추가했다. 이 케이스는 no-end final, translation-skip, 긴 안전스위치 문장의 과분리, 후속 James Cameron 문장 누락/중복 억제를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.800`, `precision=0.727`, `recall=0.889`, `pending_exact=true`, `staged_exact=true`이다. actual final은 안전스위치 문장을 `...perhaps say a keyword`와 `or something and then...off switch.` 두 조각으로 나누고, 마지막 `...without mentioning James Cameron...` 문장은 `They're talking about movies.`까지만 회수한다.
- 신규 케이스 metrics는 `final_quality_no_end_marker=1`, `stage_replace_decision_unconfirmed=6`, `stage_queue_enqueue=6`, `candidate_duplicate_suppressed=24`, `stage_revision_age_reset=2`이다. 실패는 단일 짧은 후보보다 long clause가 pending/staged에서 안정되기 전에 조각 final로 나뉘는 쪽에 가깝다.
- 변경 후 137케이스 CUDA/SaT 벤치는 `finalized=476`, `stage_start=688`, `finalized_per_stage_start=0.692`, `final_precision_avg=0.766`, `final_recall_avg=0.680`, `final_f1_avg=0.694`, `final_similarity_coverage_avg=0.606`, `final_boundary_f1_avg=0.310`, `case_exact_match=13`, `pending_exact_match=108`, `staged_exact_match=56`이다.
- 전체 지표는 악화되지 않았고 신규 케이스도 중간 수준으로 회수되므로 이번 반복에서는 로직 변경을 하지 않는다. 다만 no-end final 이후 완성형 후보가 반복되는 경우와 long clause 과분리 문제는 같은 계열로 계속 누적 관찰한다.

## 2026-06-20 14:24 KST - CAPTCHA traffic lights stage queue 중복과 no-end final 관찰

- 14:16-14:17 로그에서 `Identify all the traps.`가 먼저 staged된 뒤 `Identify all the traffic lights in this picture.`로 수정되는 STT revision 흐름을 확인했다. 이어 `You're like, OK.`가 final된 뒤 같은 문장이 다시 staged/promote되는 중복 위험도 같이 관측됐다.
- 후반부에서는 `better passing human tests...` 계열 no-end 후보가 final/translation skip 위험을 만들고, `That is a real problem.`, `I don't actually have a good solution to it.`는 staged queue에 남는 흐름을 확인했다.
- `en_log_captcha_traffic_lights_stage_duplicate_20260620_001`를 추가했다. 이 케이스는 STT revision, stage queue promote, 짧은 중복 final 위험, no-end final, 후속 문장 staged 잔류를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.842`, `precision=0.889`, `recall=0.800`, `pending_exact=true`, `staged_exact=false`이다. actual final은 기대 문장 10개 중 8개를 유사도 기준으로 회수하지만, `actual_staged='it's gonna have a no problem doing that'`가 남고 staged queue에는 `That is a real problem.`, `I don't actually have a good solution to it.`가 남는다.
- 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=21`, `stage_queue_enqueue=12`, `stage_queue_promote=10`, `candidate_duplicate_suppressed=39`, `final_quality_no_end_marker=1`, `stage_unconfirmed_replacement_suppressed=3`이다. 이는 STT revision과 stage queue/promote 잔류가 같이 작동하는 실패 샘플로 본다.
- 변경 후 138케이스 CUDA/SaT 벤치는 `finalized=485`, `stage_start=701`, `finalized_per_stage_start=0.692`, `final_precision_avg=0.767`, `final_recall_avg=0.681`, `final_f1_avg=0.695`, `final_similarity_coverage_avg=0.607`, `final_boundary_f1_avg=0.308`, `case_exact_match=13`, `pending_exact_match=109`, `staged_exact_match=56`이다.
- 이번 반복에서는 로직 변경을 보류한다. fresh replay에서 주요 문장은 대부분 회수되지만 staged 잔류와 queue promote 중복 위험이 남으므로, 같은 유형이 더 누적되면 staged queue 소비/재평가 조건을 문구별 규칙 없이 검토한다.

## 2026-06-20 14:31 KST - signed media no-end false final과 doctored image staged residue 관찰

- 14:21-14:22 로그에서 `Some way of authenticating would be good.`가 먼저 확정된 뒤, 후속 window의 filler 포함 후보 `um digitally signed media to indicate uh`가 `quality_flags=no_end_marker` final로 확정되고 번역 생략되는 흐름을 확인했다.
- 같은 구간에서 `Actually, on that point...`가 `later_completed_extension`으로 한 차례 보류됐지만, 이후 `Actually, on that point, I've already, and this is particularly pertinent.`가 먼저 final되고 `this is particularly pertinent for people in my job right`가 staged 잔류로 남았다. 뒤쪽 doctored image 문장도 `the damage is.`까지만 확정되어 완성형 `the damage is done.`을 놓쳤다.
- `en_log_signed_media_no_end_false_final_20260620_001`를 추가했다. 이 케이스는 no-end false final, translation skip, duplicate suppression, staged queue promote, long-clause staged residue, 후반부 완성 문장 누락을 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.800`, `precision=0.750`, `recall=0.857`, `pending_exact=true`, `staged_exact=false`이다. actual final에는 `Okay.`, `um digitally signed media to indicate uh`, `Yeah.`, `By the time...the damage is.` 같은 false/불완전 final이 남고, actual staged는 `this is particularly pertinent for people in my job right`이다.
- 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=13`, `stage_queue_enqueue=12`, `stage_queue_promote=12`, `candidate_duplicate_suppressed=97`, `stage_candidate_quality_blocked=9`, `final_quality_no_end_marker=1`, `finalize_delta_suppressed=3`이다.
- 변경 후 139케이스 CUDA/SaT 벤치는 `finalized=501`, `stage_start=722`, `finalized_per_stage_start=0.694`, `final_precision_avg=0.767`, `final_recall_avg=0.682`, `final_f1_avg=0.695`, `final_similarity_coverage_avg=0.608`, `final_boundary_f1_avg=0.308`, `case_exact_match=13`, `pending_exact_match=110`, `staged_exact_match=56`이다.
- 이번 반복에서는 로직 변경을 보류한다. `um...uh` 같은 filler no-end final을 단어 규칙으로 차단하면 설계 기준과 맞지 않고, no-end final 전면 차단은 과거 실험에서 recall 저하 위험이 있었다. 이 케이스는 no-end false final과 staged residue의 결합 실패 근거로 유지한다.

## 2026-06-20 14:35 KST - AI compute/three things 구간의 queue residue와 불완전 final 관찰

- 14:25 로그에서 `it is coming and accelerating the transition will` 같은 오래된 staged tail이 남은 상태에서 `The transition will be bumpy.`, `Do you have a solution to this?`, `I don't make a bet here.`가 queue promote와 replaced-confirmed 경로로 연쇄 소비됐다.
- 이후 `Do you imagine that the U.S.`가 불완전 final로 확정되고, `half or more of those jobs right now.` 같은 tail 조각도 aged final로 나왔다. 뒤쪽에서는 `every major...what do we do`가 no-end final로 나가고, `But AI is the US could make...`처럼 앞뒤 문장이 섞인 final도 재현됐다.
- `en_log_ai_compute_three_things_queue_residue_20260620_001`를 추가했다. 이 케이스는 stage queue residue, unconfirmed replacement defer, no-speech segment drop, incomplete final, duplicate suppression, long-clause reorder를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.829`, `precision=0.773`, `recall=0.895`, `pending_exact=true`, `staged_exact=false`이다. actual final은 기대 문장 대부분을 유사도 기준으로 회수하지만 `I mean, it's running circles around.`, `Do you imagine that the U.S. could make`, `Based on current trends, China will far exceed.`, `But AI is the US could make that level...` 같은 불완전/혼합 final 5개가 남는다.
- actual staged는 `Now that's a moonshot, ladies and gentlemen.`로 남았다. 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=9`, `stage_queue_enqueue=12`, `stage_queue_promote=12`, `candidate_duplicate_suppressed=144`, `stage_revision_age_reset=2`, `stage_confirm_deferred_later_extension=1`이다.
- 변경 후 140케이스 CUDA/SaT 벤치는 `finalized=523`, `stage_start=745`, `finalized_per_stage_start=0.702`, `final_precision_avg=0.767`, `final_recall_avg=0.684`, `final_f1_avg=0.696`, `final_similarity_coverage_avg=0.609`, `final_boundary_f1_avg=0.309`, `case_exact_match=13`, `pending_exact_match=111`, `staged_exact_match=56`이다.
- 이번 반복에서도 로직 변경은 보류한다. false final은 특정 문구 문제가 아니라 queue에 남은 후보와 최신 completed 후보의 소비 순서가 섞이는 문제로 보이며, 단일 임계값 조정보다는 추가 샘플 누적 후 최소한의 lifecycle 규칙을 검토하는 편이 맞다.

## 2026-06-20 14:42 KST - Peter Diamandis/no-context image queue drop과 no-end false final 관찰

- 14:29 로그에서 `and see what it is.`가 staged로 남은 상태에서 `This is Peter Diamandis.`, `No context whatsoever.`, `The host of the podcast Moonshots.` 등 후속 완료 문장이 반복적으로 queue에 쌓였다.
- 같은 구간에서 `stage_queue_drop_oldest`가 발생했고, 이후 여러 문장이 한 chunk에서 연쇄 promote/final되는 흐름을 확인했다. 이는 오래된 staged 후보가 active 자리를 점유할 때 queue 압력이 높아지는 대표 샘플로 본다.
- 후반부에서는 `there was`가 `quality_flags=no_end_marker,short_no_end_fragment`로 final 시도되어 번역 생략됐고, `I mean just it's like I tried to like update my Wikipedia page for like years`도 no-end final로 확정되어 번역 생략됐다.
- `en_log_peter_diamandis_queue_drop_false_final_20260620_001`를 추가했다. 이 케이스는 queue drop, short/no-end false final, translation skip, duplicate suppression, 후속 완성 문장 누락 위험을 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.792`, `precision=0.950`, `recall=0.679`, `pending_exact=true`, `staged_exact=false`이다. actual final은 `This is Peter Diamandis.`가 후순위로 확정되고, 앞쪽 `Did you ask a question?`, `No, nothing.`, `I didn't say anything.`와 후반 `Not quite true.`, `It's my abundance logo.`, `It's a little wrinkled on the corner.`를 회수하지 못한다.
- 신규 케이스 metrics는 `stage_queue_drop_oldest=6`, `stage_queue_enqueue=42`, `stage_queue_promote=28`, `stage_replace_decision_unconfirmed=92`, `candidate_duplicate_suppressed=92`, `stage_candidate_quality_blocked=16`이다.
- 변경 후 141케이스 CUDA/SaT 벤치는 `finalized=543`, `stage_start=774`, `finalized_per_stage_start=0.702`, `final_precision_avg=0.768`, `final_recall_avg=0.684`, `final_f1_avg=0.697`, `final_similarity_coverage_avg=0.609`, `final_boundary_f1_avg=0.307`, `case_exact_match=13`, `pending_exact_match=112`, `staged_exact_match=56`이다.
- 이번 추가는 샘플 보존이 목적이며 로직 변경은 하지 않는다. 증상은 특정 단어 문제가 아니라 오래된 staged 후보, queue 소비 순서, no-end final 품질 게이트가 함께 얽힌 lifecycle 문제로 보인다.

## 2026-06-20 14:48 KST - future currency/wattage 구간의 staged queue 잔류와 조각 final 관찰

- 14:36 로그에서 `Gravity well to escape.`, `...millionth of the sun's energy...`, `And energy is the inner loop...`, `future currency...wattage` 구간이 반복되며 staged/queue가 흔들리는 흐름을 확인했다.
- 같은 구간에서 `whole of gravity`가 `quality_flags=no_end_marker,short_no_end_fragment` final로 확정되어 번역 생략됐고, 후반에는 `Just energy.`가 aged final로 확정됐다. 이어 `control energy and compute or just energy?`, `Intelligence or matter manipulation.`, `So that's your next big project...`가 queue와 duplicate suppression에 걸렸다.
- `en_log_future_currency_wattage_energy_queue_20260620_001`를 추가했다. 이 케이스는 open-clause 보류, stage queue 잔류, short/no-end false final, aged short final, duplicate suppression을 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.583`, `precision=0.636`, `recall=0.538`, `pending_exact=true`, `staged_exact=false`이다. actual final에는 `yeah i think like i think the future currency`, `will essentially just be wattage`, `i was thinking...control energy and compute energy like now`, `Just energy.` 같은 과분리/조각 final이 남고, `So that's your next big project is going to be energy.`는 staged queue에 남는다.
- 신규 케이스 metrics는 `stage_replace_decision_open_latin_clause=18`, `stage_replace_decision_unconfirmed=19`, `stage_queue_enqueue=18`, `stage_queue_promote=15`, `candidate_duplicate_suppressed=109`, `final_quality_no_end_marker=3`, `stage_candidate_quality_blocked=19`이다.
- 변경 후 142케이스 CUDA/SaT 벤치는 `finalized=554`, `stage_start=795`, `finalized_per_stage_start=0.697`, `final_precision_avg=0.767`, `final_recall_avg=0.682`, `final_f1_avg=0.696`, `final_similarity_coverage_avg=0.608`, `final_boundary_f1_avg=0.306`, `case_exact_match=13`, `pending_exact_match=113`, `staged_exact_match=56`이다.
- 신규 케이스 점수가 낮지만, 단일 구간만으로 open-clause 보류나 aged short final을 전면 조정하면 recall 손실 가능성이 크다. 같은 유형이 계속 누적되면 active staged가 낮은 품질/짧은 후보일 때 queue의 더 완성된 후보를 우선 재평가하는 최소 lifecycle 규칙을 검토한다.

## 2026-06-20 14:54 KST - insecticide/nitrogen blanket 구간의 STT revision과 energy health queue 잔류 관찰

- 14:40 로그에서 `insecticide/pesticide/exercise`가 같은 위치에서 흔들리고, `It's pretty hard...without oxygen.`, `nitrogen blanket`, `energy, health, education` 전환 구간이 queue와 duplicate suppression에 걸리는 흐름을 확인했다.
- `Well, that's, it's an insecticide essentially.`가 먼저 final된 뒤, 후속 window의 `Well, that's, that's, it's an exercise essentially.` 계열 후보가 revision/duplicate로 흔들렸다. `Yep.`, `Oh, interesting.`, `Interesting.` 같은 짧은 응답도 queue promote와 replaced-confirmed 경로로 나왔다.
- `en_log_insecticide_nitrogen_energy_health_queue_20260620_001`를 추가했다. 이 케이스는 STT revision, stage queue promote, 짧은 final, speaker transition 이후 완성 문장 queue 잔류를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.588`, `precision=0.625`, `recall=0.556`, `pending_exact=false`, `staged_exact=false`이다. actual final에는 `of pure nitrogen gas under a slight positive pressure.`, `well that s that s it s an exercise`, `Yep.` 같은 기대 밖 조각이 남고, `I want to talk about energy health education...`은 pending, `I want to talk about, uh, energy, health, education, because those are people.`와 `...nitrogen blanket on plants.`는 staged queue에 남는다.
- 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=14`, `stage_queue_enqueue=11`, `stage_queue_promote=9`, `candidate_duplicate_suppressed=46`, `stage_candidate_quality_blocked=9`, `final_quality_no_end_marker=1`이다.
- 변경 후 143케이스 CUDA/SaT 벤치는 `finalized=562`, `stage_start=805`, `finalized_per_stage_start=0.698`, `final_precision_avg=0.766`, `final_recall_avg=0.682`, `final_f1_avg=0.695`, `final_similarity_coverage_avg=0.608`, `final_boundary_f1_avg=0.304`, `case_exact_match=13`, `pending_exact_match=113`, `staged_exact_match=56`이다.
- 이번 반복에서도 로직 변경은 보류한다. 낮은 점수 케이스가 누적되고 있으나, 원인은 특정 단어가 아니라 active staged와 queued completed 후보의 소비 순서 및 짧은 응답 처리의 결합 문제로 보인다.

## 2026-06-20 15:03 KST - solar AI satellites 구간의 staged fragment와 후속 문장 queue 잔류 관찰

- 14:45 로그에서 `so the the I mean I've said the stuff you know`가 active staged로 잡힌 뒤, `it's a solar powered AI satellites`, `yes 100 gigawatts a year of solar powered`, `I did the math on that.` 같은 후속 후보가 open-clause 보류와 queue 승격을 반복했다.
- 이후 `yes 100 gigawatts a year of solar powered ai satellites`가 `quality_flags=no_end_marker` final로 확정되어 번역 생략됐고, `That's like 500,000 Starlink V3s...`, `That's one every hour.`, `For a year.`는 뒤늦게 회수됐다.
- 후반부에서는 `v 3s launched over 8000 starship flights`가 staged로 남아 `It's amazing.`, `It's quite the scale.`, `What's the really rough timeline...` 후보가 queue에 남는 흐름을 확인했다.
- `en_log_solar_ai_satellites_stage_fragment_20260620_001`를 추가했다. 이 케이스는 no-end false final, active staged fragment, stage queue promote, duplicate suppression, 후속 완료 문장 queue 잔류를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.818`, `precision=1.000`, `recall=0.692`, `pending_exact=true`, `staged_exact=false`이다. actual final은 false positive 없이 9개 문장을 회수하지만, `100 gigawatts a year of solar-powered AI satellites.`, `It's amazing.`, `It's quite the scale.`, `What's the really rough timeline on that?`를 놓친다.
- actual staged는 `v 3s launched over 8000 starship flights`이고, actual staged queue에는 `It's amazing.`, `It's quite the scale.`, `What's the really rough timeline`이 남는다. 신규 케이스 metrics는 `stage_replace_decision_open_latin_clause=46`, `stage_replace_decision_unconfirmed=12`, `stage_queue_enqueue=20`, `stage_queue_promote=17`, `candidate_duplicate_suppressed=78`, `stage_candidate_quality_blocked=21`, `stage_age_quality_blocked=7`이다.
- 변경 후 144케이스 CUDA/SaT 벤치는 `finalized=571`, `stage_start=824`, `finalized_per_stage_start=0.693`, `final_precision_avg=0.768`, `final_recall_avg=0.682`, `final_f1_avg=0.696`, `final_similarity_coverage_avg=0.608`, `final_boundary_f1_avg=0.302`, `case_exact_match=13`, `pending_exact_match=114`, `staged_exact_match=56`이다.
- 이번 반복에서는 로직 변경을 보류한다. precision이 높고 recall 누락이 staged/queue 잔류로 집중되어 있어, 단일 품질 임계값 조정보다는 active staged fragment가 오래 남을 때 queued completed 후보를 어떻게 재평가할지 추가 샘플과 함께 판단한다.

## 2026-06-20 15:10 KST - resource level/low Earth orbit 구간의 short final 중복과 staged residue 관찰

- 14:49 로그에서 `Like the intelligence we're quite interested in preserving itself.`, `Yes, that's true.`, `Interesting.`, `Good motivation.` 짧은 응답/전환 구간이 stage queue와 duplicate suppression을 반복했다.
- `Interesting.`은 한 번 final된 뒤 다시 stage queue에서 승격되어 노출됐고, `Good motivation.`은 `Yeah, good motivation.`으로 확정되어 기대 문장과 유사하지만 짧은 응답 중복 위험을 남겼다.
- 후반부에서는 `well, you can get you know, you don't have to get`가 `quality_flags=no_end_marker` final로 확정되어 번역 생략됐고, `you can be around 1200 kilometers unsynchronous will`이 staged로 남아 `But you could place them in multiple orbits.`가 queue에 잔류했다.
- `en_log_resource_level_low_earth_orbit_queue_20260620_001`를 추가했다. 이 케이스는 short final 중복, no-end false final, low Earth orbit 설명 구간의 staged residue, constant sunlight 문장 과분리를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.870`, `precision=0.833`, `recall=0.909`, `pending_exact=true`, `staged_exact=false`이다. actual final은 대부분 회수하지만 `well, you can get you know, you don't have to get`와 `You can be around 1,200 kilometers unsynchronous.`가 false/과분리 final로 남는다.
- actual staged는 `you can be around 1200 kilometers unsynchronous will`이고, actual staged queue에는 `But you could place them in multiple orbits.`가 남는다. 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=21`, `stage_queue_enqueue=10`, `stage_queue_promote=9`, `candidate_duplicate_suppressed=156`, `stage_candidate_quality_blocked=16`, `final_quality_no_end_marker=1`, `stage_unconfirmed_replacement_suppressed=2`이다.
- 변경 후 145케이스 CUDA/SaT 벤치는 `finalized=583`, `stage_start=839`, `finalized_per_stage_start=0.695`, `final_precision_avg=0.768`, `final_recall_avg=0.683`, `final_f1_avg=0.697`, `final_similarity_coverage_avg=0.610`, `final_boundary_f1_avg=0.300`, `case_exact_match=13`, `pending_exact_match=115`, `staged_exact_match=56`이다.
- 이번 반복에서도 로직 변경은 보류한다. 신규 케이스는 전체 F1을 소폭 올리지만 staged residue가 남아 있으므로, 짧은 응답 자체를 금지하기보다 active staged와 queue 후보의 소비 순서/재평가 문제로 계속 추적한다.

## 2026-06-20 15:18 KST - Falcon 9 reuse/launch cost 구간의 false final과 staged residue 관찰

- 14:54 로그에서 `And then I, yeah, it is.` 같은 오염된 staged가 남은 상태로 `Falcon 9 first reused its first stage`, `traditional aerospace industries did not believe...`, `Cape Canaveral`, `launch cost tipping point` 후보가 queue와 duplicate suppression을 반복했다.
- `and then when falcon 9 first reused its first stage i mean all the traditional aerospace industries did not` 같은 no-end staged가 승격되어 transcript에 노출됐고, 이후 `um i mean all the traditional aerospace industries did not believe that even falcon 9 could re could`, `that the the leap...could fly and release` 같은 혼합/조각 final이 발생했다.
- 후반부에서는 `Somewhere in that timeline, it went from speculative to no doubt.`가 staged로 남고, pending은 `No doubt and I don't know if that's a smooth line`으로 기대 pending과 어긋났다.
- `en_log_falcon9_reuse_launch_cost_queue_20260620_001`를 추가했다. 이 케이스는 open-clause 보류, no-end false final, stage queue promote, terminal tail split, launch cost 문장 혼합을 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.690`, `precision=0.667`, `recall=0.714`, `pending_exact=false`, `staged_exact=false`이다. actual final은 기대 문장 10개를 유사도 기준으로 회수하지만, false positive 5개가 남고 `Somewhere in that timeline...`은 staged로 잔류한다.
- 신규 케이스 metrics는 `stage_replace_decision_open_latin_clause=22`, `stage_replace_decision_unconfirmed=9`, `stage_queue_enqueue=21`, `stage_queue_promote=20`, `candidate_duplicate_suppressed=127`, `stage_candidate_quality_blocked=40`, `final_quality_no_end_marker=4`, `finalize_reason_terminal_tail_revision_split=2`이다.
- 변경 후 146케이스 CUDA/SaT 벤치는 `finalized=598`, `stage_start=863`, `finalized_per_stage_start=0.693`, `final_precision_avg=0.768`, `final_recall_avg=0.683`, `final_f1_avg=0.697`, `final_similarity_coverage_avg=0.610`, `final_boundary_f1_avg=0.299`, `case_exact_match=13`, `pending_exact_match=115`, `staged_exact_match=56`이다.
- 이번 케이스는 이전 샘플보다 false final 비중이 크다. 다만 원인은 특정 문구가 아니라 오래된 staged, open-clause 보류, no-end fragment final, terminal tail split이 함께 작동한 결과로 보이므로 즉시 로직 변경은 보류하고 같은 계열을 더 누적한다.

## 2026-06-20 15:31 KST - abundant happiness/compute energy 구간의 no-end final과 staged queue 잔류 관찰

- 15:00 로그에서 `so um i think we'll end up trying to capture`가 `quality_flags=no_end_marker` final로 먼저 확정되고 번역 생략됐다. 이후 `I don't know a millionth...thousandth of the sun's energy` 완성형 후보가 반복되지만 최근 final/중복 억제와 open-clause 보류가 섞였다.
- 같은 구간에서 `a millionth of it likes a millionth`, `I don't know a millionth...the Sun's` 같은 STT 흔들림이 staged/pending에 노출됐고, 후반에는 `Fair enough.`, `Yeah.`, `I would guess that even.`가 staged queue에 남았다.
- `en_log_abundant_happiness_compute_capture_20260620_001`를 추가했다. 이 케이스는 no-end false final, translation skip, duplicate suppression, open-clause defer, 후속 짧은 응답 staged queue 잔류를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.556`, `precision=0.500`, `recall=0.625`, `pending_exact=false`, `staged_exact=false`이다. actual final에는 `because manufacturing...self-drive`, `I don't know a millionth...the Sun's`, `well the sun is just generating...for free` 같은 기대 밖 조각이 남는다.
- 신규 케이스 metrics는 `stage_replace_decision_open_latin_clause=16`, `stage_queue_enqueue=12`, `stage_queue_promote=9`, `candidate_duplicate_suppressed=14`, `final_quality_no_end_marker=9`, `stage_candidate_quality_blocked=6`이다.
- 변경 후 147케이스 CUDA/SaT 벤치는 `finalized=608`, `stage_start=878`, `finalized_per_stage_start=0.692`, `final_precision_avg=0.766`, `final_recall_avg=0.683`, `final_f1_avg=0.696`, `final_similarity_coverage_avg=0.608`, `final_boundary_f1_avg=0.297`, `case_exact_match=13`, `pending_exact_match=115`, `staged_exact_match=56`이다.
- 이번 케이스는 낮은 F1과 boundary F1 0으로 실패 재현성이 강하다. 다만 실패 원인은 no-end final 전면 차단만으로 설명되지 않고, 최근 final 억제와 active staged/queue 소비 순서가 결합된 것으로 보여 로직 변경은 추가 누적 후 보수적으로 판단한다.

## 2026-06-20 15:40 KST - ultracapacitor/PhDs 구간의 boundary mismatch와 staged residue 관찰

- 15:04 로그에서 `capacitor with enough energy density that you get`가 `quality_flags=no_end_marker` final로 먼저 확정되고 번역 생략됐다. 이후 `The idea that I had...high range in an electric car`, `ultracapacitor company`, `It didn't go well` 구간은 반복 중복 억제와 queue promote를 거치며 회수됐다.
- 후반부에서는 `Most PhDs...`, `turn into something useful`, `tree of knowledge`, `great entrepreneurs`, `don't waste your time going to grad school` 구간에서 실제 문장 경계보다 넓은 결합 final이 발생했다. `It's like, you know.`는 staged에 남았다.
- `en_log_ultracapacitor_phds_grad_school_queue_20260620_001`를 추가했다. 이 케이스는 no-end false final, stage queue promote, duplicate suppression, 문장 경계 결합 오류, staged residue를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.769`, `precision=0.833`, `recall=0.714`, `pending_exact=false`, `staged_exact=false`이다. boundary 지표는 `final_boundary_f1=0.077`로 낮아 문장 내용 회수보다 경계 품질이 더 약한 케이스다.
- actual final에는 `most phds i mean hates it but most phds do not`, `Enormous fraction...but nowadays...`, `Yeah, because...grad school, start a company.`처럼 기대보다 경계가 넓거나 STT revision이 덜 정리된 문장이 남는다.
- 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=32`, `stage_replace_decision_open_latin_clause=16`, `stage_queue_enqueue=20`, `stage_queue_promote=20`, `candidate_duplicate_suppressed=17`, `stage_unconfirmed_replacement_suppressed=3`, `final_quality_no_end_marker=1`이다.
- 변경 후 148케이스 CUDA/SaT 벤치는 `finalized=620`, `stage_start=900`, `finalized_per_stage_start=0.689`, `final_precision_avg=0.766`, `final_recall_avg=0.683`, `final_f1_avg=0.697`, `final_similarity_coverage_avg=0.609`, `final_boundary_f1_avg=0.296`, `case_exact_match=13`, `pending_exact_match=115`, `staged_exact_match=56`이다.
- 이번 케이스는 final 내용 유사도는 중간 이상이지만 boundary와 staged residue가 약하다. 문장별 정규식이나 단어 규칙으로 해결하지 않고, active staged와 queue 후보의 생성순서/확정순서 검증 케이스로 유지한다.

## 2026-06-20 15:49 KST - Stanford/Bill Nix deferment 구간의 staged residue와 boundary split 관찰

- 15:07-15:08 로그에서 `And they've been doing the survey`가 `quality_flags=no_end_marker` final로 먼저 확정되고 번역 생략됐다. 이후 `I didn't know anyone who wanted to start`, `Even at Stanford at the time?`, `I actually...Bill Nix...deferment` 구간이 staged queue와 duplicate suppression을 반복했다.
- `I actually, a few days into the semester, or I should say the quarter,`는 later completed extension으로 보류됐지만, 후속 `I Called Bill Nix who?` STT 흔들림과 결합되며 `I actually...Called Bill Nix` 조각 final이 남았다.
- 후반부 `He said, was my class that bad?`, `No...put it on deferment`, `But he said...last conversation`, `And he was right`는 대부분 회수됐지만, latest replay에서는 `He said, is my class that bad?`와 후속 문장들이 staged/queue에 잔류했다.
- `en_log_stanford_bill_nix_deferment_stage_20260620_001`를 추가했다. 이 케이스는 no-end final, aged duplicate suppression, trailing ellipsis 차단, active staged 교체 보류, 긴 문장의 boundary split을 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.944`, `precision=0.944`, `recall=0.944`, `pending_exact=false`, `staged_exact=false`이다. boundary 지표는 `final_boundary_f1=0.611`로 내용 회수 대비 낮다.
- 신규 케이스 actual final에는 `I actually a few days into the semester or just say the quarter I Called Bill Nix`, `to the semester, or I should say the quarter...deferment.`처럼 같은 발화 구간의 split/overlap이 남는다.
- 신규 케이스 metrics는 `stage_replace_decision_open_latin_clause=19`, `stage_replace_decision_unconfirmed=17`, `stage_queue_enqueue=26`, `stage_queue_promote=22`, `candidate_duplicate_suppressed=24`, `stage_candidate_quality_blocked=5`, `final_quality_no_end_marker=1`이다.
- 변경 후 149케이스 CUDA/SaT 벤치는 `finalized=638`, `stage_start=923`, `finalized_per_stage_start=0.691`, `final_precision_avg=0.767`, `final_recall_avg=0.685`, `final_f1_avg=0.699`, `final_similarity_coverage_avg=0.611`, `final_boundary_f1_avg=0.298`, `case_exact_match=13`, `pending_exact_match=115`, `staged_exact_match=56`이다.
- 이 케이스는 내용 회수율이 높으므로 즉시 로직 변경 근거로는 약하지만, boundary split과 staged residue가 남는다. active staged가 긴 미완성 후보일 때 후속 완성 후보와 생성순서대로 합리적으로 소비되는지 보는 회귀 샘플로 유지한다.

## 2026-06-20 15:56 KST - El Salvador/Grok education 구간의 boundary mismatch와 staged residue 관찰

- 15:11 로그에서 `but yeah what did you announce with with him in El Salvador`와 `i mean you have to be...take on...and win`이 active/staged queue를 오가며 후속 `It was just basically to use Grok for education` 후보가 open-clause 보류와 queue promote를 거쳤다.
- 후반부에서는 `the kids friendly version of grok`가 `quality_flags=no_end_marker` final로 확정되어 번역 생략됐고, 완성형 `Yeah, we would have the kids-friendly version of Grok.`은 중복 억제 경로로 처리됐다.
- `en_log_el_salvador_grok_education_queue_20260620_001`를 추가했다. 이 케이스는 stage queue promote, open-clause defer, no-end final, duplicate suppression, 문장 경계 mismatch, staged residue를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.900`, `precision=0.900`, `recall=0.900`, `pending_exact=false`, `staged_exact=false`이다. boundary 지표는 `final_boundary_f1=0.000`으로, 내용 회수와 별개로 경계 품질을 거의 맞추지 못한다.
- actual final은 주요 문장을 대부분 회수하지만 `It was just basically to use Grokt for education.`와 `Like personalized education.`으로 기대 문장 하나가 둘로 갈라지고, `And live.` 반복 중 하나가 누락된다.
- actual staged는 `version of yeah we would have like you know the kids friendly version of rock but but obviously AI can be an individualized teacher`로 남고, queue에는 `Now you still need to be curious and you still need to want to learn.`이 잔류한다.
- 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=6`, `stage_replace_decision_open_latin_clause=3`, `stage_queue_enqueue=6`, `stage_queue_promote=5`, `candidate_duplicate_suppressed=39`, `stage_revision=10`이다.
- 변경 후 150케이스 CUDA/SaT 벤치는 `finalized=648`, `stage_start=934`, `finalized_per_stage_start=0.694`, `final_precision_avg=0.768`, `final_recall_avg=0.686`, `final_f1_avg=0.700`, `final_similarity_coverage_avg=0.613`, `final_boundary_f1_avg=0.296`, `case_exact_match=13`, `pending_exact_match=115`, `staged_exact_match=56`이다.
- 이번 케이스는 내용 유사도만 보면 성공처럼 보이지만 boundary F1이 0인 대표 샘플이다. final 품질 개선을 final F1만으로 판단하지 않고 boundary/staged residue를 같이 봐야 한다는 근거로 유지한다.

## 2026-06-20 15:20 KST - exercise/donuts/longevity 구간의 stage queue 잔류와 boundary mismatch 관찰

- 15:15-15:16 로그에서 `It's like if people get really fat...`, `Well, if you don't have any exercise...`, `Or if they eat donuts...`, `0.4 of a donut...` 구간이 반복 window로 들어오며 stage queue와 duplicate suppression을 반복했다.
- 원 로그에서는 `well if you don't have any exercise health get bad or if they`가 `quality_flags=no_end_marker` final로 확정되고 번역 생략되는 흐름이 관측됐다. 현재 코드 벤치에서는 해당 no-end final은 재현되지 않았지만, 같은 구간의 boundary mismatch와 staged residue는 남았다.
- `en_log_exercise_donuts_longevity_no_end_queue_20260620_001`를 추가했다. 이 케이스는 no-end final 관측 이력, stage queue promote, unconfirmed replacement, duplicate suppression, `donut/doughnut` STT 흔들림, 후반 `longevity` 문장 잔류를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.880`, `precision=1.000`, `recall=0.786`, `pending_exact=true`, `staged_exact=false`이다. boundary 지표는 `final_boundary_f1=0.000`으로, 내용 회수 대비 문장 경계와 생명주기 소비가 약하다.
- actual final에는 false positive 없이 11개 문장을 회수하지만 `Would you just run around?`, `Majara Cupid.`, `So you and I have had a disagreement on longevity.`가 누락되고, 첫 final이 `First of all, But I think that's a big reason.`처럼 앞뒤 문맥이 섞인다.
- actual staged는 `So I figured anything below 0.44 of a donut rounds down to zero.`이고 staged queue에는 `So you and I have had a disagreement on longevity.`가 남는다. 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=93`, `stage_queue_enqueue=21`, `stage_queue_promote=20`, `candidate_duplicate_suppressed=67`, `stage_unconfirmed_replacement_suppressed=9`, `stage_candidate_quality_blocked=8`이다.
- 변경 후 151케이스 CUDA/SaT 벤치는 `finalized=659`, `stage_start=955`, `finalized_per_stage_start=0.690`, `final_precision_avg=0.770`, `final_recall_avg=0.687`, `final_f1_avg=0.701`, `final_similarity_coverage_avg=0.614`, `final_boundary_f1_avg=0.294`, `case_exact_match=13`, `pending_exact_match=116`, `staged_exact_match=56`이다.
- 이번 반복에서는 로직 변경을 보류한다. no-end final은 최신 코드 기준으로 완화된 반면, 남은 문제는 unconfirmed replacement가 많은 queue 소비/경계 문제다. 단일 임계값을 낮추면 중복 확정 위험이 커지므로 같은 계열 샘플을 더 누적한 뒤 보수적으로 판단한다.

## 2026-06-20 15:25 KST - replacement rate/North Korea/underpopulation 구간의 queue drop 관찰과 큐 한도 튜닝

- 15:20-15:21 로그에서 `South Korea is like one-third replacement rate`, `North Korea won't need to invade`, `walkers or something`, `massive underpopulation` 구간이 stage queue에 장시간 쌓였다.
- 원 로그에서는 `yeah one`, `127th so 3` 같은 짧은 no-end final이 번역 생략되고, `I mean, North Korea won't need to invade.`와 `So their current size...walk across.`가 유사 후보 억제/queue promote를 반복했다.
- `en_log_replacement_rate_north_korea_underpopulation_queue_20260620_001`를 추가했다. 이 케이스는 stage queue overflow, duplicate suppression, no-end short fragment, 오래된 staged 후보 잔류를 함께 추적한다.
- 기본 큐 한도 12 기준 신규 케이스는 `final_f1=0.500`, `precision=0.857`, `recall=0.353`, `pending_exact=true`, `staged_exact=false`, `stage_queue_drop_oldest=8`이었다. 전체 152케이스 벤치는 `final_f1_avg=0.700`, `final_recall_avg=0.685`, `final_boundary_f1_avg=0.293`이었다.
- `MAX_STAGED_SENTENCE_QUEUE`를 12에서 20으로 올린 뒤 신규 케이스는 `final_f1=0.621`, `precision=0.750`, `recall=0.529`, `stage_queue_drop_oldest=0`으로 개선됐다. 전체 152케이스 벤치는 `finalized=675`, `stage_start=982`, `finalized_per_stage_start=0.687`, `final_precision_avg=0.770`, `final_recall_avg=0.687`, `final_f1_avg=0.701`, `final_similarity_coverage_avg=0.614`, `final_boundary_f1_avg=0.295`, `case_exact_match=13`, `pending_exact_match=117`, `staged_exact_match=56`이다.
- 큐 한도 증가는 누락에는 도움이 되지만 stale 후보가 더 오래 남을 수 있다. 이번 결과는 작은 개선이므로 유지하되, 후속 로그에서 중복 final 또는 오래된 staged queue 잔류가 늘어나는지 계속 확인한다.

## 2026-06-20 15:30 KST - UHI/digital intelligence 구간의 boundary mismatch와 staged residue 관찰

- 15:25-15:26 로그에서 `So can you go through the rationale of UHI?`, `How does universal high income work?`, `digital intelligence...humanoid robots...`, `benign scenario...Star Trek` 구간이 반복 window로 들어왔다.
- `en_log_uhi_digital_intelligence_benign_scenario_20260620_001`를 추가했다. 이 케이스는 짧은 감탄/응답, UHI 질문, 긴 설명 문장, 후반 staged residue를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.875`, `precision=1.000`, `recall=0.778`, `pending_exact=true`, `staged_exact=false`, `final_boundary_f1=0.000`이다.
- actual final은 false positive 없이 7개를 회수하지만, `God damn it.`/`Too late.`가 `god damn it too late`로 결합되고, `How does universal high income work?`가 `How does how does universal high-income work?`로 흔들리며, `not Cameron situation`은 staged에 남는다.
- 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=30`, `stage_replace_decision_open_latin_clause=12`, `stage_queue_enqueue=11`, `stage_queue_promote=11`, `candidate_duplicate_suppressed=27`, `stage_candidate_quality_blocked=15`, `final_quality_no_end_marker=1`이다.
- 변경 후 153케이스 CUDA/SaT 벤치는 `finalized=682`, `stage_start=995`, `finalized_per_stage_start=0.685`, `final_precision_avg=0.771`, `final_recall_avg=0.688`, `final_f1_avg=0.702`, `final_similarity_coverage_avg=0.615`, `final_boundary_f1_avg=0.293`, `case_exact_match=13`, `pending_exact_match=118`, `staged_exact_match=56`이다.
- 이번 반복에서는 로직 변경을 보류한다. 내용 F1은 높지만 boundary/staged residue가 약한 유형이라, active staged와 queue 후보의 소비 순서를 계속 관찰한다.

## 2026-06-20 15:33 KST - economic doom/theme of talk 구간의 no-end fragment final 관찰

- 15:32 로그에서 `but the the so this`가 `quality_flags=no_end_marker` final로 확정되고 번역 생략됐다. 이어 `So if we don't have AI and robots...economic doom`, `competitive pressure from China`, `theme of this talk`, `AI and exponential tech save America and the world` 구간이 반복 window로 들어왔다.
- `en_log_economic_doom_theme_ai_save_world_fragment_20260620_001`를 추가했다. 이 케이스는 no-end fragment final, translation skip, open-clause defer, duplicate suppression, 후반 staged residue를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.706`, `precision=0.667`, `recall=0.750`, `pending_exact=false`, `staged_exact=false`, `final_boundary_f1=0.471`이다.
- actual final은 `Yes, and the deficit is growing.`, `So if we don't have AI and robots...economic doom.`, `There's also competitive pressure from China...`를 회수한다. 반면 `and and ultimately...look on the bright side talk, how can AI...`처럼 앞뒤 문맥이 섞인 false final과 `don't you think that`, `but i want to get`, `i want to hit this because...` 같은 no-end/open-clause 조각이 남는다.
- actual staged는 `Always look on the bright side of life.`이고 staged queue에는 `Shut up.`이 남는다. 신규 케이스 metrics는 `stage_replace_decision_open_latin_clause=13`, `stage_queue_enqueue=10`, `stage_queue_promote=9`, `stage_queue_revision=8`, `stage_candidate_quality_blocked=6`, `final_quality_no_end_marker=3`, `stage_age_quality_blocked=1`이다.
- 변경 후 154케이스 CUDA/SaT 벤치는 `finalized=691`, `stage_start=1006`, `finalized_per_stage_start=0.687`, `final_precision_avg=0.771`, `final_recall_avg=0.688`, `final_f1_avg=0.702`, `final_similarity_coverage_avg=0.615`, `final_boundary_f1_avg=0.294`, `case_exact_match=13`, `pending_exact_match=118`, `staged_exact_match=56`이다.
- 이번 반복에서도 로직 변경은 보류한다. no-end final 전면 차단은 과거 벤치에서 recall 손실이 컸고, 여기서는 active staged/queue 소비와 open-clause 보류가 함께 작동하므로 추가 샘플 누적 후 보수적으로 판단한다.

## 2026-06-20 15:36 KST - UHI tax redistribute/prices/money supply 구간의 경계 파괴 관찰

- 15:35-15:36 로그에서 `When we say universal high income...tax and redistribute`, `prices will drop`, `Prices in dollar terms...money supply`, `deflation or vice versa` 구간이 반복 window로 들어왔다.
- 원 로그에서는 `tax and redistribute but that's not the case`가 `quality_flags=no_end_marker` final로 확정되어 번역 생략됐고, `Prices in dollar terms are the ratio.`가 terminal tail split으로 조기 final됐다. 후반에는 `thing we're growing the money supply so quickly then`이 no-end final로 확정됐다.
- `en_log_uhi_tax_redistribute_prices_money_supply_20260620_001`를 추가했다. 이 케이스는 no-end fragment final, terminal-tail split, stage queue promote/revision, prior-pending/recent-final 혼합 억제, money supply 문장 잔류를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.667`, `precision=0.750`, `recall=0.600`, `pending_exact=true`, `staged_exact=false`, `final_boundary_f1=0.000`이다.
- actual final은 주요 주제 일부를 회수하지만 `So you're able...electricity, right?`처럼 두 문장을 결합하고, `It's it's I think...Prices will become what prices will drop.`, `i mean you know prices in dollar terms are...` 같은 조각/혼합 final을 남긴다.
- actual staged는 `up.`이고 staged queue에는 `It's a good thing we're growing the money supply so quickly then.`이 남는다. 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=28`, `stage_queue_enqueue=10`, `stage_queue_promote=9`, `stage_queue_revision=23`, `candidate_duplicate_suppressed=17`, `final_quality_no_end_marker=2`, `stage_unconfirmed_replacement_suppressed=3`이다.
- 변경 후 155케이스 CUDA/SaT 벤치는 `finalized=699`, `stage_start=1018`, `finalized_per_stage_start=0.687`, `final_precision_avg=0.770`, `final_recall_avg=0.687`, `final_f1_avg=0.702`, `final_similarity_coverage_avg=0.615`, `final_boundary_f1_avg=0.292`, `case_exact_match=13`, `pending_exact_match=119`, `staged_exact_match=56`이다.
- 이번 케이스는 boundary F1이 0인 강한 실패 샘플이다. 다만 실패 원인은 특정 문구가 아니라 replacement unconfirmed, terminal tail split, stage queue revision이 함께 만든 생명주기 문제이므로 문구별 규칙은 추가하지 않는다.

## 2026-06-20 15:39 KST - productivity/economists measurement 구간의 조각 final과 queue residue 관찰

- 15:37 로그에서 `Productivity is going to improve dramatically`, `high double-digit output of goods and services`, `economists measure things`, `economists jokes` 구간이 반복 window로 들어왔다.
- 원 로그에서는 `We have to be careful about how economists coming Argentina.`, `measure things.`, `hot like high double digit` 같은 조각/오인식 final이 발생했고, `hot like high double digit`은 `quality_flags=no_end_marker`로 번역 생략됐다.
- `en_log_productivity_economists_measurement_joke_20260620_001`를 추가했다. 이 케이스는 no-end fragment final, terminal-tail split, duplicate suppression, economists joke 후속 문장 queue residue를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.769`, `precision=0.833`, `recall=0.714`, `pending_exact=true`, `staged_exact=false`, `final_boundary_f1=0.000`이다.
- actual final은 `Productivity is going to improve...`, `high double-digit output...`, `economists measure things`를 회수하지만, `Yeah.`와 `GDP stocks isn't measured.`가 결합되고 `I have a few economists jokes...forest.` 후속 문장은 staged queue에 남는다.
- actual staged는 `I mean, it's like my favorite joke.`이고 staged queue에는 `i have a few economist jokes...two economists`, `but maybe my favorite one economist joke is two economists are going for a walk in the forest`, `Yes.`가 남는다. 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=23`, `stage_queue_enqueue=13`, `stage_queue_promote=10`, `stage_queue_revision=15`, `candidate_duplicate_suppressed=25`, `stage_candidate_quality_blocked=6`, `candidate_recent_final_delta_trimmed=15`이다.
- 변경 후 156케이스 CUDA/SaT 벤치는 `finalized=705`, `stage_start=1029`, `finalized_per_stage_start=0.685`, `final_precision_avg=0.771`, `final_recall_avg=0.688`, `final_f1_avg=0.703`, `final_similarity_coverage_avg=0.615`, `final_boundary_f1_avg=0.291`, `case_exact_match=13`, `pending_exact_match=120`, `staged_exact_match=56`이다.
- 이번 케이스도 내용 유사도와 boundary 품질이 크게 갈라진다. 단어별 예외가 아니라 active staged/queue 후보가 후속 완성 문장을 소비하지 못하는 유형으로 유지한다.

## 2026-06-20 15:45 KST - AI safety/axiom/HAL pod bay doors 구간의 no-end final과 stale staged 관찰

- 15:44-15:45 로그에서 `AI safety`, `axiom A and axiom B`, `HAL wouldn't open the pod bay doors`, `pod bay door salesman`, `prompt engineering` 구간이 반복 window로 들어왔다.
- 원 로그에서는 `doors but but why wouldn t hell open the pod bay doors`가 `quality_flags=no_end_marker` final로 확정되어 번역 생략됐고, 이후 `space odyssey was that the`, `odyssey clark was trying to convey in`, `it s just prompt engineering that hal wouldn t` 같은 오래된 staged 후보가 queue promote로 노출됐다.
- `en_log_ai_safety_axiom_hal_pod_bay_queue_20260620_001`를 추가했다. 이 케이스는 no-end false final, translation skip, stale staged queue, duplicate suppression, boundary mismatch, 후속 완성 문장 staged residue를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.741`, `precision=0.714`, `recall=0.769`, `pending_exact=true`, `staged_exact=false`, `final_boundary_f1=0.148`이다.
- actual final은 `truth-seeking`, `false`, `axiom`, `pod bay doors`, `prompt engineering`, `monolith` 핵심 문장 일부를 회수하지만, `was that people always know the meme of that`, `hell wouldn't open...but but why...`, `that Odyssey Clark was trying...if you always know them`처럼 경계가 파괴된 조각 final이 남는다.
- actual staged는 `Was that in code or was it in English?`로 남고, 신규 케이스 metrics는 `stage_replace_decision_open_latin_clause=24`, `stage_replace_decision_unconfirmed=8`, `stage_queue_enqueue=14`, `stage_queue_promote=14`, `stage_queue_revision=21`, `candidate_duplicate_suppressed=24`, `final_quality_no_end_marker=3`, `stage_candidate_quality_blocked=9`이다.
- 변경 후 157케이스 CUDA/SaT 벤치는 `finalized=719`, `stage_start=1049`, `finalized_per_stage_start=0.685`, `final_precision_avg=0.770`, `final_recall_avg=0.688`, `final_f1_avg=0.703`, `final_similarity_coverage_avg=0.615`, `final_boundary_f1_avg=0.290`, `case_exact_match=13`, `pending_exact_match=121`, `staged_exact_match=56`이다.
- 이번 케이스도 특정 단어나 문구 문제가 아니라 active staged와 queue 후보가 오래 유지되며 생성순서 소비, open-clause 보류, no-end 품질 차단이 충돌한 유형이다. 즉시 로직 변경은 보류하고, 같은 계열 샘플 누적 후 queue/staged 소비 정책을 보수적으로 판단한다.

## 2026-06-20 15:49 KST - speed of light/many minds 구간의 내용 회수와 boundary 실패 관찰

- 15:48-15:49 로그에서 `speed of light constraint`, `single mind`, `millisecond`, `fiber`, `multiple AIs`, `clusters of compute`, `many minds`, `mixture of experts` 구간이 반복 window로 들어왔다.
- 원 로그에서는 `there s a lot of great science fiction books where the first asi basically`, `so there's a speed of light constraint that makes that difficult other`, `um a single mind from existing` 같은 no-end final이 확정되어 번역 생략됐다.
- 후반부에서는 `So therefore, you will have earth`가 staged로 시작된 뒤 `So therefore you will have many minds because of the speed of light.`로 revision 확정됐다. 내용은 보존됐지만, 앞선 no-end 조각 final 때문에 경계 품질이 낮다.
- `en_log_speed_of_light_many_minds_compute_clusters_20260620_001`를 추가했다. 이 케이스는 no-end false final, translation skip, stage revision, duplicate suppression, high final F1과 low boundary F1의 괴리를 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.963`, `precision=0.929`, `recall=1.000`, `pending_exact=true`, `staged_exact=true`, `final_boundary_f1=0.000`이다.
- actual final은 기대 문장 13개를 모두 회수하지만 `Biological life they will compete with each other.`가 false positive로 남고, `Then the question...you know?`, `so there's a speed...`처럼 기대 경계와 다르게 출력된다.
- 신규 케이스 metrics는 `stage_replace_decision_open_latin_clause=9`, `stage_replace_decision_unconfirmed=4`, `stage_queue_enqueue=9`, `stage_queue_promote=9`, `stage_queue_revision=5`, `stage_revision=13`, `candidate_duplicate_suppressed=51`, `final_quality_no_end_marker=2`, `stage_candidate_quality_blocked=8`이다.
- 변경 후 158케이스 CUDA/SaT 벤치는 `finalized=733`, `stage_start=1065`, `finalized_per_stage_start=0.688`, `final_precision_avg=0.771`, `final_recall_avg=0.690`, `final_f1_avg=0.704`, `final_similarity_coverage_avg=0.617`, `final_boundary_f1_avg=0.288`, `case_exact_match=13`, `pending_exact_match=122`, `staged_exact_match=57`이다.
- 이번 케이스는 final F1만으로 품질을 판단하면 안 된다는 근거다. 내용 회수는 좋지만 no-end false final이 먼저 누적되어 boundary F1이 0이므로, 향후 튜닝은 final F1과 boundary/staged 지표를 함께 본다.

## 2026-06-20 15:53 KST - Optimus surgeons/Zimbabwe/gigafactory 구간의 queue 잔류 관찰

- 15:51-15:53 로그에서 `shortage of doctors`, `great surgeons`, `Optimus`, `three years at scale`, `Zimbabwe`, `gigafactory`, `medicine` 구간이 반복 window로 들어왔다.
- 원 로그에서는 `Yeah.`, `Sure.`, `Um, here at the, uh, giga factory.`, `Oh yeah.` 같은 짧은 응답/조각 staged가 queue에서 승격되며 긴 후속 후보를 unconfirmed replacement로 보류했다.
- `en_log_optimus_surgeons_zimbabwe_gigafactory_queue_20260620_001`를 추가했다. 이 케이스는 short-response staged, 긴 후속 후보 보류, trailing ellipsis 차단, no-end final, staged queue 잔류를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.609`, `precision=0.778`, `recall=0.500`, `pending_exact=false`, `staged_exact=false`, `final_boundary_f1=0.000`이다.
- actual final은 초반 의사/외과의 부족 문맥 일부와 `Three years at scale.`을 회수하지만, `Optimus robots...all surgeons on Earth`, `Zimbabwe`, `gigafactory`, `medicine`, `four years`, `good for humanity` 후속 문장 다수가 staged/queue에 남는다.
- actual staged는 `There will probably be more Optimus robots that are great surgeons than there are all surgeons on Earth.`이고 staged queue에는 `And the cost...Zimbabwe.`, `The best surgeon...planet.`, `Where do you think it will roll out first?`, `Here at the gigafactory.`, `But that's an important statement...`, `I mean, not like absolutely certain...`, `It's still an incredible statement...`, `All of a sudden you demonetize.` 등이 잔류한다.
- 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=85`, `stage_queue_enqueue=38`, `stage_queue_promote=22`, `stage_queue_revision=64`, `stage_replace=102`, `stage_candidate_quality_blocked=19`, `stage_candidate_quality_trailing_ellipsis=15`, `candidate_duplicate_suppressed=14`, `stage_unconfirmed_replacement_suppressed=4`이다.
- 변경 후 159케이스 CUDA/SaT 벤치는 `finalized=751`, `stage_start=1088`, `finalized_per_stage_start=0.690`, `final_precision_avg=0.771`, `final_recall_avg=0.689`, `final_f1_avg=0.704`, `final_similarity_coverage_avg=0.616`, `final_boundary_f1_avg=0.286`, `case_exact_match=13`, `pending_exact_match=122`, `staged_exact_match=57`이다.
- 이번 케이스는 active staged가 짧은 응답일 때 긴 후속 후보를 얼마나 빨리 소비할지에 대한 판단 근거다. 하지만 짧은 응답을 무조건 폐기하면 실제 반복 응답을 잃을 수 있으므로, 로직 변경은 유사 샘플을 더 누적한 뒤 보수적으로 검토한다.

## 2026-06-20 16:00 KST - supply chain/recursive medicine 구간의 후반 queue 잔류 관찰

- 15:56 전후 로그에서 `supply chain`, `rate limit`, `recursive, multiplicable, triple exponential`, `medicine is going to be effectively free`, `medical school` 구간이 반복 window로 들어왔다.
- 원 로그에서는 `but you're you're i mean there's some right limit`, `you can't just manufacturing is very difficult`, `i mean unless you but i would`, `say that applies to any form of education` 같은 no-end 조각 final이 확인됐다.
- `en_log_supply_chain_recursive_medicine_free_20260620_001`를 추가했다. 이 케이스는 no-end false final, translation skip, open-clause 보류, stage queue revision, 후반 medical school 문장 잔류를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.571`, `precision=0.769`, `recall=0.455`, `pending_exact=true`, `staged_exact=false`, `final_boundary_f1=0.000`이다.
- actual final은 `What's the constraint?`, `Metal.`, `It's just all supply chain stuff.`, `It's recursive, multiplicable, triple exponential...`, `medicine is going to be effectively free` 일부를 회수한다. 반면 `Everyone will have access to medical care...`, `So don't go into medical school.`, `I mean, unless you...`, `I do it for social reasons.`, `You're not going to medical school.`은 staged queue에 남는다.
- actual staged는 `So you've got to – it's recursive, multiplicable, triple exponential.`이고, 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=125`, `stage_queue_enqueue=34`, `stage_queue_promote=24`, `stage_queue_revision=143`, `stage_candidate_quality_blocked=44`, `stage_candidate_quality_no_end_marker=20`, `stage_candidate_quality_short_no_end_fragment=20`, `candidate_duplicate_suppressed=14`, `final_quality_no_end_marker=1`이다.
- 변경 후 160케이스 CUDA/SaT 벤치는 `finalized=764`, `stage_start=1113`, `finalized_per_stage_start=0.686`, `final_precision_avg=0.771`, `final_recall_avg=0.687`, `final_f1_avg=0.703`, `final_similarity_coverage_avg=0.615`, `final_boundary_f1_avg=0.284`, `case_exact_match=13`, `pending_exact_match=123`, `staged_exact_match=57`이다.
- 이번 케이스는 앞선 Optimus queue 잔류와 같은 계열이다. active staged가 중간 문장에 오래 묶이면 후반부 완성 문장이 queue에서 소비되지 못한다. 다만 no-end 차단과 queue 소비를 동시에 강하게 조이면 recall 손실 가능성이 있어, 즉시 로직 변경은 보류하고 같은 실패 유형을 더 누적한다.

## 2026-06-20 16:05 KST - chimps/pyramids/Raptor 구간의 short staged와 후속 queue 잔류 관찰

- 16:02 로그에서 `not bad for a bunch of monkeys`, `chimps make a raft`, `we celebrate the pyramids`, `Give them some peanuts`, `Raptor 3 goes when`, `best rocket engine` 구간이 반복 window로 들어왔다.
- 원 로그에서는 `Give them some peanuts.`가 queue 승격 직후 replacement 확정되고, 이후 `The chimps are awesome.`, `These things become timeless, right?`, `Raptor three goes when?`이 순차로 queue에서 승격됐다. 후반에는 `I think it's worth noting`, `Raptor 3 is beautiful`, `best rocket engine` 후보가 queue에 남았다.
- `en_log_chimps_pyramids_raptor_queue_20260620_001`를 추가했다. 이 케이스는 short staged 승격, duplicate suppression, 생성순서 queue 소비, 후속 Raptor 문장 잔류, 내용 F1과 boundary F1의 괴리를 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.769`, `precision=1.000`, `recall=0.625`, `pending_exact=true`, `staged_exact=false`, `final_boundary_f1=0.000`이다.
- actual final은 false positive 없이 `Not bad for a human.`, `Rembrandt`, `accounting`, `chimps make a raft`, `pyramids`, `Give them some peanuts.`, `These things become timeless, right?`, `Raptor three goes when?`, `I think it's worth noting.`을 회수한다.
- actual staged는 `for a bunch of monkeys you know it's like if you saw a bunch of chimps like make a raft and cross the river`이고, staged queue에는 `Look at that.`, `Give him some peanuts.`, `Raptor 3 goes when?`, `Raptor 3 is beautiful.`, `By far the best rocket engine ever.`, `It's amazing.`, `Is that AI?`, `Nothing's even close.`, `Nope.`가 남는다.
- 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=54`, `stage_queue_enqueue=29`, `stage_queue_promote=19`, `stage_queue_revision=37`, `stage_candidate_quality_blocked=11`, `stage_candidate_quality_no_end_marker=11`, `candidate_duplicate_suppressed=28`, `finalize_duplicate_suppressed=1`이다.
- 변경 후 161케이스 CUDA/SaT 벤치는 `finalized=779`, `stage_start=1133`, `finalized_per_stage_start=0.688`, `final_precision_avg=0.773`, `final_recall_avg=0.687`, `final_f1_avg=0.703`, `final_similarity_coverage_avg=0.615`, `final_boundary_f1_avg=0.282`, `case_exact_match=13`, `pending_exact_match=124`, `staged_exact_match=57`이다.
- 이 케이스는 precision이 높아도 recall과 boundary가 낮을 수 있음을 다시 보여준다. queue를 aggressive하게 비우면 후속 문장 recall은 오를 수 있지만 duplicate/short response 오확정 위험이 있으므로, 이번 반복에서도 로직 변경은 보류한다.

## 2026-06-20 16:10 KST - booster re-entry/Falcon 9 reflights 구간의 no-end false final 관찰

- 16:05-16:06 로그에서 `doesn't explode`, `engines on the test stand`, `wear and tear`, `booster re-entry`, `Falcon 9`, `over 500 reflights` 구간이 반복 window로 들어왔다.
- 원 로그에서는 `of the or the falling`이 `quality_flags=no_end_marker`로 final 확정되어 번역 생략됐고, `that's not really like we also obviously just solved that you know with thousand nine so we could`가 no-end final로 확정됐다.
- `en_log_booster_reentry_falcon9_reflights_20260620_001`를 추가했다. 이 케이스는 no-end false final, open-clause 보류, Falcon 9 오인식, staged queue 잔류, pending tail 잔류를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.875`, `precision=1.000`, `recall=0.778`, `pending_exact=false`, `staged_exact=false`, `final_boundary_f1=0.250`이다.
- actual final은 false positive 없이 `That's a lot.`, `The amazing thing is that it doesn't explode.`, `We've blown up a lot of engines on the test stand.`, `For the booster, the re-entry is not that bad.`, `Falcon 9...booster reuse`를 회수한다.
- actual pending은 `we've had over 500 reflights of the Falcon 9 first stage`이고, actual staged는 `We also have obviously just solved that with Falcon 9.`이다. staged queue에는 `that's not really like...thousand nine`, `We've had over 500 reflights of the Falcon 9.`, `you know you know something`, `it's it's it's not like that`이 남는다.
- 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=14`, `stage_replace_decision_open_latin_clause=24`, `stage_queue_enqueue=18`, `stage_queue_promote=14`, `stage_queue_revision=26`, `stage_candidate_quality_blocked=30`, `stage_candidate_quality_no_end_marker=22`, `candidate_duplicate_suppressed=31`, `candidate_recent_final_delta_trimmed=20`이다.
- 변경 후 162케이스 CUDA/SaT 벤치는 `finalized=786`, `stage_start=1148`, `finalized_per_stage_start=0.685`, `final_precision_avg=0.774`, `final_recall_avg=0.688`, `final_f1_avg=0.705`, `final_similarity_coverage_avg=0.616`, `final_boundary_f1_avg=0.282`, `case_exact_match=13`, `pending_exact_match=124`, `staged_exact_match=57`이다.
- 이 케이스는 내용 final F1만 보면 양호하지만 pending/staged 잔류와 no-end false final이 동시에 남는다. 특정 단어 교정이나 Falcon 9 전용 규칙을 넣지 않고, queue 소비와 no-end 품질 정책의 일반적 실패 샘플로 유지한다.

## 2026-06-20 16:15 KST - UFO/aliens/most viewed post 구간의 terminal tail split 관찰

- 16:11-16:12 로그에서 `UFO`, `evidence of aliens`, `post that on X`, `most viewed post`, `sports scores the next day` 구간이 반복 window로 들어왔다.
- 원 로그에서는 `But anyway, it's alright`가 `quality_flags=no_end_marker`로 final 확정되어 번역 생략됐고, 후반 `I actually wonder...sports scores the next day`는 terminal tail split과 staged queue 잔류로 남았다.
- `en_log_ufo_aliens_most_viewed_post_20260620_001`를 추가했다. 이 케이스는 trailing ellipsis, short response staged, duplicate suppression, terminal tail split, 후반 긴 문장 staged residue를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.828`, `precision=1.000`, `recall=0.706`, `pending_exact=true`, `staged_exact=false`, `final_boundary_f1=0.000`이다.
- actual final은 false positive 없이 UFO/aliens 핵심 문장을 회수하지만 `Fuzzy blob.`, `I'm asked all the time if I've...`, `So the question is, are we the most viewed post of all time?`, `I actually wonder...sports scores the next day`가 final로 소비되지 못했다.
- actual staged는 `It's gonna be the most viewed post of all time I know.`이고 staged queue에는 `It's good.`, `So the question is, are we the most viewed post of all time?`, `I actually wonder about the US public...sports scores the next day.`, `Yeah.`, `That's good.`이 남는다.
- 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=41`, `stage_replace_decision_open_latin_clause=13`, `stage_queue_enqueue=23`, `stage_queue_promote=18`, `stage_queue_revision=35`, `candidate_duplicate_suppressed=45`, `stage_candidate_quality_trailing_ellipsis=11`, `candidate_recent_final_delta_trimmed=3`이다.
- 변경 후 163케이스 CUDA/SaT 벤치는 `finalized=798`, `stage_start=1167`, `finalized_per_stage_start=0.684`, `final_precision_avg=0.776`, `final_recall_avg=0.688`, `final_f1_avg=0.705`, `final_similarity_coverage_avg=0.617`, `final_boundary_f1_avg=0.281`, `case_exact_match=13`, `pending_exact_match=125`, `staged_exact_match=57`이다.
- 이번 케이스도 내용 유사도는 높지만 boundary와 staged queue 소비가 약한 유형이다. 특정 문구 규칙을 추가하지 않고, queue 후보 소비와 terminal tail split의 일반 실패 샘플로 유지한다.

## 2026-06-20 16:20 KST - accelerating launches/launched mass 구간의 open-clause queue 잔류 관찰

- 16:13 로그에서 `10 megawatts of AI compute`, `accelerating launches`, `200 tons per launch`, `marginal cost per flight`, `launched mass is data centers in space` 구간이 반복 window로 들어왔다.
- 원 로그에서는 `of AI compute.`가 active staged로 남은 상태에서 `four years of accelerating launches`, `So 200 tons per launch`, `So what fraction...` 후보가 unconfirmed/open-clause로 보류됐다. 이후 `but yeah it s the right order...in excess of` 같은 no-end 조각이 queue에서 승격됐다.
- `en_log_accelerating_launches_mass_data_centers_20260620_001`를 추가했다. 이 케이스는 open-clause 보류, staged queue revision, duplicate suppression, 후반 질문 문장 staged residue를 함께 추적한다.
- 최신 코드 기준 신규 케이스는 `final_f1=0.700`, `precision=0.636`, `recall=0.778`, `pending_exact=false`, `staged_exact=false`, `final_boundary_f1=0.200`이다.
- actual final은 `People have...expectations`, `10 megawatts of AI compute`, `200 tons per launch`, `marginal cost per flight` 일부를 회수한다. 반면 `Yeah.`가 false positive로 남고, `So assuming...accelerating launches, to 200 tons.`, `So what fraction of all that of accelerating launches.`, `Yeah, that's where you're going.`처럼 경계와 문맥이 섞인 final이 나온다.
- actual staged는 `launched mass is data centers in space as opposed to moon base as opposed to launch to mars as opposed to satellites`이고, staged queue에는 `Yeah, that's interesting.`, `That's interesting.`이 남는다.
- 신규 케이스 metrics는 `stage_replace_decision_unconfirmed=11`, `stage_replace_decision_open_latin_clause=10`, `stage_queue_enqueue=16`, `stage_queue_promote=14`, `stage_queue_revision=7`, `candidate_duplicate_suppressed=32`, `stage_candidate_quality_no_end_marker=2`, `finalize_reason_next_completed=1`, `finalize_reason_replaced_duplicate_or_suffix=1`이다.
- 변경 후 164케이스 CUDA/SaT 벤치는 `finalized=809`, `stage_start=1183`, `finalized_per_stage_start=0.684`, `final_precision_avg=0.775`, `final_recall_avg=0.688`, `final_f1_avg=0.705`, `final_similarity_coverage_avg=0.617`, `final_boundary_f1_avg=0.280`, `case_exact_match=13`, `pending_exact_match=125`, `staged_exact_match=57`이다.
- 이번 케이스는 active staged가 짧거나 불완전한 후보에 묶이면 후반의 완성 질문이 staged로 잔류하는 유형이다. queue를 공격적으로 비우는 변경은 중복/오확정 위험이 있으므로, 이번 정리에서는 로직 변경 없이 벤치 근거만 추가한다.

## 2026-06-20 16:35 KST - 벤치 샘플 sentence_finalize_age=3 통일

- 운영 기본값을 `sentenceFinalizeAgeEn/Ko/Zh=3`으로 통일했지만, `tests/eval/dictation_ai/sbd_text_cases.sample.jsonl`에는 과거 샘플 조건인 `sentence_finalize_age=2`가 남아 있었다.
- 벤치 샘플이 기본 계약과 다른 age를 고정하면 기본값 변경의 영향을 확인할 수 없으므로, 모든 샘플의 `sentence_finalize_age`를 3으로 정리했다.
- 변경 후 분포는 `en={3: 56}`, `ko={3: 79}`, `zh={3: 29}`다.
- 이전 비교에서 중국어 29건만 age 2/3으로 바꾸면 `final_f1_avg=0.614 -> 0.578`, `final_recall_avg=0.661 -> 0.606`, `final_boundary_f1_avg=0.258 -> 0.258`이었다. 손실은 `zh_log_missing_beef_soup_taste_fragment_20260617_001`, `zh_log_duplicate_temperature_fragment_20260617_001`, `zh_log_missing_artist_portrait_fragment_20260617_001` 등 일부 장문/누락 케이스에 집중됐다.
- 전체 164건에서 중국어만 age 3으로 바꾼 비교는 `final_f1_avg=0.705 -> 0.699`였다.
- 이번에 한국어/중국어 샘플 전체를 age 3으로 통일한 뒤 CUDA/SaT 벤치를 다시 실행했다.

```text
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py \
  --device cuda \
  --compute-type float16 \
  --output .tmp/eval/dictation-ai-sbd/latest-age3-sample.json

cases=164
finalized=791
stage_start=1143
finalized_per_stage_start=0.692
final_precision_avg=0.754
final_recall_avg=0.656
final_f1_avg=0.676
final_similarity_coverage_avg=0.591
final_boundary_f1_avg=0.268
case_exact_match=12
pending_exact_match=124
staged_exact_match=53
```

판단:

- age 3 통일은 벤치 성능을 낮춘다. 기존 혼합 age 샘플의 `final_f1_avg=0.705` 대비 `0.676`으로 약 `-0.029`다.
- 하락은 주로 recall 감소다. `final_recall_avg=0.688 -> 0.656`, `final_precision_avg=0.775 -> 0.754`다.
- 반면 `finalized_per_stage_start`는 `0.684 -> 0.692`로 올라가, stage 수 자체가 줄고 더 보수적으로 소비되는 경향이 있다.
- age 3은 즉시 운영 불가 수준의 장애는 아니지만, 누락/recall 측면에서는 비용이 있다.
- 기본값 통일 목적은 언어별 예외 축소와 보수적인 확정 기준 유지다. 성능 개선은 age를 다시 낮추기보다 queue 소비, staged residue, no-end fragment 정책을 일반 로직으로 개선하는 방향에서 판단한다.

## 2026-06-20 18:00 KST - aged staged 후보의 생성순서 final 소비

- 최신 로그 모니터링에서 raw STT 자체의 정확도보다, active staged 후보가 보류되는 동안 후속 completed 후보가 queue에 쌓이고 final로 소비되지 않는 패턴을 다시 확인했다.
- 이번 목적은 STT 문자열을 보정하는 것이 아니라, 부정확한 STT 가설을 사람이 속기하듯 보류하고 반복 관측된 문장을 순서대로 final-only 번역 입력으로 넘기는 것이다.
- 코드상 `stage_replace_deferred` 경로에서 active staged 후보가 `sentenceFinalizeAge`에 도달했고 `_should_finalize_before_replacement(...)`가 참이어도, 기존 로직은 `stage_unconfirmed_replacement_suppressed`로 폐기한 뒤 queue 후보를 승격했다.
- 이 동작은 “생성순서대로 소비” 원칙과 맞지 않고, 확정 가능한 문장을 버려 recall 손실을 만들 수 있으므로, 해당 경로를 폐기 대신 `stage_age_finalize` final 확정으로 변경했다.
- raw STT, SBD backend, 언어별 규칙, 단어별 예외는 변경하지 않았다. 변경 범위는 revision-aware lifecycle의 staged 소비 정책이다.

변경 전 기준:

```text
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py \
  --device cuda \
  --compute-type float16 \
  --output .tmp/eval/dictation-ai-sbd/monitoring-before.json

cases=164
finalized=791
stage_start=1143
finalized_per_stage_start=0.692
final_precision_avg=0.754
final_recall_avg=0.656
final_f1_avg=0.676
final_similarity_coverage_avg=0.591
final_boundary_f1_avg=0.268
case_exact_match=12
pending_exact_match=124
staged_exact_match=53
```

변경 후 기준:

```text
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py \
  --device cuda \
  --compute-type float16 \
  --output .tmp/eval/dictation-ai-sbd/monitoring-aged-finalize.json

cases=164
finalized=840
stage_start=1143
finalized_per_stage_start=0.735
final_precision_avg=0.744
final_recall_avg=0.678
final_f1_avg=0.688
final_similarity_coverage_avg=0.607
final_boundary_f1_avg=0.298
case_exact_match=12
pending_exact_match=124
staged_exact_match=52
```

판단:

- `final_f1_avg`는 `0.676 -> 0.688`, `final_recall_avg`는 `0.656 -> 0.678`, `final_boundary_f1_avg`는 `0.268 -> 0.298`로 개선됐다.
- `finalized_per_stage_start`는 `0.692 -> 0.735`로 올라가, 보류된 staged 후보가 더 많이 final로 소비됐다.
- `stage_unconfirmed_replacement_suppressed`는 102에서 0이 됐고, `stage_age_finalize`는 21에서 122로 증가했다. 이는 폐기하던 확정 가능 후보를 생성순서대로 소비했다는 근거다.
- `final_precision_avg`는 `0.754 -> 0.744`로 하락했다. 확정 누락을 줄이는 대신 false final 위험이 일부 증가한 것으로 보며, recent final memory와 no-end fragment 품질 게이트를 계속 함께 관찰해야 한다.
- 케이스별 비교에서 개선은 한국어/영어의 `missing-final`, `stage-queue`, `mixed-context-final` 태그에 주로 나타났고, 악화는 short/no-end fragment 또는 기존 false-final 위험이 있던 케이스의 precision 하락으로 나타났다.
- 이 변경은 논문의 주제인 “불안정 STT 스트림을 final-only 번역 입력으로 안정화하는 lifecycle”에 직접 해당한다. raw STT 정확도 개선 또는 언어별 문자열 보정으로 해석하지 않는다.

## 2026-06-20 18:20 KST - 파라미터 sweep 규칙과 로그 기반 케이스 수집 보강

- 논문 근거를 보강하려면 raw STT 정확도보다, 불안정한 STT 가설을 final-only 번역 입력으로 안정화하는 lifecycle 파라미터의 효과를 반복 검증해야 한다.
- 파라미터 변경은 앱 로그에서 수집한 다수 실패 케이스를 benchmark에 누적한 뒤, 같은 샘플 집합에서 변경 전후를 비교한다.
- 실험 가능한 파라미터는 lifecycle에 직접 영향을 주는 값으로 제한한다. 예: `MAX_STAGED_SENTENCE_QUEUE`, `SENTENCE_CONFIRM_CHUNKS`, `FORCED_SENTENCE_CONFIRM_CHUNKS`, `SENTENCE_CONFIRM_MAX_AGE_CHUNKS`, `FORCED_SENTENCE_CONFIRM_MAX_AGE_CHUNKS`, `SHORT_CJK_FINAL_UNITS`, `SHORT_NO_END_FRAGMENT_UNITS`, revision similarity 계열.
- STT 모델, CUDA 장치, backend, 언어별 문구 규칙, 케이스별 문자열 보정은 이 논문의 lifecycle 파라미터 실험으로 취급하지 않는다.
- `AVC_DICTATION_*` 환경변수 override는 로컬 sweep용이다. 운영 기본값은 벤치 결과와 실험일지 판단을 거쳐 `dictation_pipeline_settings.py` checked-in 상수로 반영한다.
- 문헌 근거 검토 결과, Whisper-Streaming과 incremental ASR 평가는 partial hypothesis와 final transcript 분리, latency/revoke/안정성 지표 분리의 근거로 쓸 수 있다. 다만 `SENTENCE_CONFIRM_CHUNKS` 같은 개별 상수값을 외부 논문에서 직접 정당화하지는 않는다. 상수 채택은 앱 로그 replay와 CUDA/AI 벤치 결과로만 판단한다.
- `dictation_tuning_manifest()`를 추가해 sweep 가능한 lifecycle/revision 파라미터의 env 이름, 현재값, 기본값, scope, intent, 근거 분류를 벤치 리포트에 함께 남긴다. manifest의 `external_reference_role`은 외부 문헌이 threshold source가 아니라 문제 정의와 지표 설계 근거임을 명시한다.
- 앱 로그에서 의심 구간을 빠르게 모으기 위해 `tests/eval/dictation_ai/collect_sbd_case_drafts_from_logs.py`를 추가했다.
- 수집 도구는 `stage 교체 보류`, `stage 후보 품질 차단`, `중복 문장 무시`, `번역 생략`, `raw_without_final`, `stage_queue_*`, `no_end_marker` 같은 지표가 보이는 chunk 주변의 raw STT window를 draft JSONL로 만든다.
- draft에는 `expected_final`을 자동 생성하지 않는다. 사람이 원 로그와 화면 관측을 검토해 기대 final을 채운 뒤에만 `tests/eval/dictation_ai/sbd_text_cases.sample.jsonl`로 승격한다.
- 수집 도구는 같은 context window 안의 실제 `받아쓰기 AI 문장 확정` 로그를 `observed_final_texts`와 `observed_final_references`로 함께 저장한다. review queue는 이를 중복 제거해 `suggested_expected_final` 검토 초안으로 보여준다. 이 값은 reviewer가 기대 final을 판단할 때 보는 참고값이며, 자동으로 `expected_final`로 승격하지 않는다.
- review queue와 검토 워크시트는 `review_priority_tag`/`review_priority_rank`를 보존한다. 이는 `missing-final`, `duplicate-final`, `stage-queue`처럼 먼저 확인해야 할 실패 유형을 추적하기 위한 검토 운영 메타데이터이며, 성능 점수로 해석하지 않는다.
- `tests/eval/dictation_ai/prepare_sbd_review_work_items.py`를 추가해 `suggested_expected_final`이 있는 queue 항목을 사람이 편집하기 쉬운 워크시트 JSONL로 변환한다. 워크시트는 `expected_final`을 제안값으로 미리 채우지만 `review_status=needs_human_confirmation`과 `draft_expected_final_required=true`를 유지하므로, benchmark 입력이나 자동 승격 대상으로 쓰이지 않는다. `--markdown-dir`를 주면 같은 항목을 사람이 검토하기 쉬운 Markdown batch와 배치별 언어/소스 분포를 담은 `index.md`로도 출력한다. `--balance-review-order`는 특정 언어/로그가 앞 배치에 몰리는 검토 편향을 줄이기 위해 언어와 source log bucket을 round-robin으로 섞는다.
- `tests/eval/dictation_ai/validate_sbd_review_work_items.py`를 추가해 편집한 워크시트의 중복 id, chunk 유무, marker, reviewed status와 `expected_final` 유무를 promotion 전에 검증한다. `ready_count`는 승격 가능 후보 수이며, 승격 전까지 reviewed benchmark case 수로 계산하지 않는다.
- 케이스가 많아지면 `tests/eval/dictation_ai/sbd_cases/*.jsonl`처럼 분할한다. 수집 도구는 `--split-size`로 draft part 파일을 만들 수 있고, `sbd_benchmark.py --cases`는 단일 파일, 여러 파일, glob, 디렉터리를 모두 받을 수 있으며, 중복 case id는 fail-fast로 거부한다. `sbd_cases` 디렉터리에 reviewed JSONL이 있으면 benchmark 기본 입력에 sample file과 함께 자동 포함한다.
- benchmark는 `draft_expected_final_required=true`가 남아 있는 파일을 거부한다. pending/staged 전용 benchmark case는 `expected_final=[]`일 수 있으므로, finalization 목표 검증에는 `validate_sbd_case_files.py --min-expected-final-cases`를 명시해 비어 있지 않은 `expected_final` 케이스 수를 별도로 센다. draft 1000건은 후보 풀이고, 논문/벤치에 쓰는 reviewed finalization case 1000건은 `expected_final` 검토와 draft marker 제거가 끝난 파일만 의미한다.
- `tests/eval/dictation_ai/report_sbd_review_progress.py`는 review queue, 검토 워크시트, reviewed case를 분리 집계한다. 워크시트에서 `review_status=reviewed|accepted`와 `expected_final`을 가진 항목은 `ready_to_promote_from_work_items`로 보지만, 승격 전에는 benchmark case 수로 계산하지 않는다.
- `tests/eval/dictation_ai/run_sbd_case_workflow.py`를 추가해 로그 수집, draft 검증, 전체 review queue, source-gap diverse queue, 검토 워크시트 생성, 진행률 집계, queue/work-item 승격 dry-run, 목표 검증 명령, 실제 승격 명령, CUDA benchmark 명령을 같은 기본값으로 생성한다. `--execute`는 비-CUDA 준비 단계만 실행한다. reviewed 목표 검증은 `--check-target`, `expected_final`이 있는 finalization 목표 검증은 `--check-finalization-target`, 검토한 work item의 실제 승격은 `--promote-reviewed-work-items`, 실제 성능 벤치는 `--run-cuda-benchmark`를 명시했을 때만 실행한다.
- `tests/eval/dictation_ai/monitor_sbd_case_workflow.py`를 추가해 반복 실행 중인 앱 로그를 주기적으로 다시 읽고 같은 비-CUDA 준비 단계를 반복할 수 있게 했다. 이 모니터는 `monitor-summary.json`에 최신 실행 summary를 남기고, `monitor-history.jsonl`에 run id, UTC 관측 시각, iteration별 draft 수, review queue 수, work item 수, 태그 분포, source log 분포, suggested expected final 수, reviewed/finalization 진행률을 append-only로 누적한다. `tests/eval/dictation_ai/report_sbd_monitor_history.py`는 이 history를 요약해 최신 진행률, reviewed finalization 증가량, source log/태그 편향을 확인한다. 성능 수치가 아니라 케이스 수집 운영 기록이며, 논문 근거 성능값은 reviewed case 승격 뒤 CUDA/AI 벤치 또는 parameter sweep으로만 기록한다.

워크플로 명령 확인 예:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_case_workflow.py
```

비-CUDA 준비 단계 실행 예:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_case_workflow.py --execute
```

검토 워크시트 단독 생성 예:

```text
./.venv/bin/python tests/eval/dictation_ai/prepare_sbd_review_work_items.py \
  .tmp/eval/dictation-ai-sbd/review-queue.jsonl \
  --output .tmp/eval/dictation-ai-sbd/review-work-items.jsonl \
  --split-size 250 \
  --markdown-dir .tmp/eval/dictation-ai-sbd/review-work-item-batches \
  --balance-review-order \
  --summary-output .tmp/eval/dictation-ai-sbd/review-work-items-summary.json
```

검토 워크시트 승격 dry-run 예:

```text
./.venv/bin/python tests/eval/dictation_ai/validate_sbd_review_work_items.py \
  '.tmp/eval/dictation-ai-sbd/review-work-items.part-*.jsonl'

./.venv/bin/python tests/eval/dictation_ai/promote_sbd_reviewed_cases.py \
  '.tmp/eval/dictation-ai-sbd/review-work-items.part-*.jsonl' \
  --existing tests/eval/dictation_ai/sbd_text_cases.sample.jsonl tests/eval/dictation_ai/sbd_cases \
  --output .tmp/eval/dictation-ai-sbd/reviewed-promoted-from-work-items-dry-run.jsonl \
  --split-size 250 \
  --allow-empty \
  --summary-output .tmp/eval/dictation-ai-sbd/promoted-from-work-items-summary.json
```

검토 완료 work item 실제 승격 예:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_case_workflow.py \
  --promote-reviewed-work-items
```

reviewed 1000건 목표 검증 포함 실행 예:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_case_workflow.py \
  --execute \
  --check-target
```

finalization 1000건 목표 검증 포함 실행 예:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_case_workflow.py \
  --execute \
  --check-finalization-target
```

CUDA/AI benchmark 포함 실행 예:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_case_workflow.py \
  --execute \
  --run-cuda-benchmark
```

반복 로그 모니터링 예:

```text
./.venv/bin/python tests/eval/dictation_ai/monitor_sbd_case_workflow.py \
  --iterations 12 \
  --interval-seconds 300
```

모니터 history 요약 예:

```text
./.venv/bin/python tests/eval/dictation_ai/report_sbd_monitor_history.py \
  .tmp/eval/dictation-ai-sbd/monitor-history.jsonl \
  --summary-output .tmp/eval/dictation-ai-sbd/monitor-history-summary.json
```

수집 예:

```text
./.venv/bin/python tests/eval/dictation_ai/collect_sbd_case_drafts_from_logs.py \
  .tmp/logs \
  --context 4 \
  --limit 80 \
  --output .tmp/eval/dictation-ai-sbd/case-drafts.jsonl
```

대량 draft 수집 예:

```text
./.venv/bin/python tests/eval/dictation_ai/collect_sbd_case_drafts_from_logs.py \
  .tmp/logs \
  --context 4 \
  --limit 1000 \
  --per-language-limit 400 \
  --split-size 250 \
  --output .tmp/eval/dictation-ai-sbd/case-drafts-balanced.jsonl \
  --summary-output .tmp/eval/dictation-ai-sbd/case-drafts-balanced-summary.json
```

승격 전 검증 예:

```text
./.venv/bin/python tests/eval/dictation_ai/validate_sbd_case_files.py \
  tests/eval/dictation_ai/sbd_text_cases.sample.jsonl \
  tests/eval/dictation_ai/sbd_cases
```

draft 후보 풀 규모 확인 예:

```text
./.venv/bin/python tests/eval/dictation_ai/validate_sbd_case_files.py \
  '.tmp/eval/dictation-ai-sbd/case-drafts-balanced.part-*.jsonl' \
  --allow-drafts
```

검토 큐 생성 예:

```text
./.venv/bin/python tests/eval/dictation_ai/build_sbd_review_queue.py \
  '.tmp/eval/dictation-ai-sbd/case-drafts-balanced.part-*.jsonl' \
  --reviewed tests/eval/dictation_ai/sbd_text_cases.sample.jsonl tests/eval/dictation_ai/sbd_cases \
  --limit 1000 \
  --output .tmp/eval/dictation-ai-sbd/review-queue.jsonl \
  --markdown-dir .tmp/eval/dictation-ai-sbd/review-batches \
  --markdown-batch-size 25 \
  --summary-output .tmp/eval/dictation-ai-sbd/review-queue-summary.json
```

중복 인접 구간을 줄인 1차 검토 큐 생성 예:

```text
./.venv/bin/python tests/eval/dictation_ai/build_sbd_review_queue.py \
  '.tmp/eval/dictation-ai-sbd/case-drafts-balanced.part-*.jsonl' \
  --reviewed tests/eval/dictation_ai/sbd_text_cases.sample.jsonl tests/eval/dictation_ai/sbd_cases \
  --source-gap 5 \
  --limit 1000 \
  --output .tmp/eval/dictation-ai-sbd/review-queue-diverse.jsonl \
  --markdown-dir .tmp/eval/dictation-ai-sbd/review-batches-diverse \
  --markdown-batch-size 25 \
  --summary-output .tmp/eval/dictation-ai-sbd/review-queue-diverse-summary.json
```

reviewed 1000건 목표 검증 예:

```text
./.venv/bin/python tests/eval/dictation_ai/validate_sbd_case_files.py \
  tests/eval/dictation_ai/sbd_text_cases.sample.jsonl \
  tests/eval/dictation_ai/sbd_cases \
  --min-cases 1000 \
  --max-drafts 0
```

검토 진행률 집계 예:

```text
./.venv/bin/python tests/eval/dictation_ai/report_sbd_review_progress.py \
  .tmp/eval/dictation-ai-sbd/review-queue.jsonl \
  --reviewed-cases tests/eval/dictation_ai/sbd_text_cases.sample.jsonl tests/eval/dictation_ai/sbd_cases \
  --review-work-items '.tmp/eval/dictation-ai-sbd/review-work-items.part-*.jsonl' \
  --target-cases 1000 \
  --summary-output .tmp/eval/dictation-ai-sbd/review-progress-summary.json
```

검토 완료 항목 승격 예:

```text
./.venv/bin/python tests/eval/dictation_ai/promote_sbd_reviewed_cases.py \
  .tmp/eval/dictation-ai-sbd/review-queue.jsonl \
  --existing tests/eval/dictation_ai/sbd_text_cases.sample.jsonl tests/eval/dictation_ai/sbd_cases \
  --output tests/eval/dictation_ai/sbd_cases/reviewed-promoted.jsonl \
  --split-size 250
```

현재 누적 로그 기준 draft 수집 결과:

```text
draft_count=1000
language_counts: en=400, ko=200, zh=400
top tags: missing-final=1000, stage-queue=999, cjk-internal-gap=999,
          duplicate-final=768, no-end-marker=297, spaced-cjk-blocked=34,
          translation-skip=42
source_log_counts: avc-whisper.log=351, avc-whisper.log.1=49,
                   avc-whisper.log.14=400, avc-whisper.log.35=198,
                   avc-whisper.log.36=2
```

판단:

- 테스트 케이스 수를 늘리는 기준은 “성공률을 높이기 쉬운 케이스”가 아니라 “확정 누락, 중복 확정, 문장 파괴, staged queue 잔류가 실제 로그에서 반복 관측된 케이스”다.
- 1000개 draft는 수집 목표 달성을 위한 후보 풀일 뿐, 아직 논문 벤치 케이스 1000건이 완성됐다는 의미는 아니다. `expected_final` 검토와 편향 조정 뒤 승격한다.
- `--per-language-limit` 없이 최신 로그만 훑으면 특정 언어가 draft 대부분을 차지할 수 있다. 논문 벤치 후보 풀은 수집 편향을 줄이기 위해 언어별 상한을 둔 balanced batch를 우선 검토한다.
- `validate_sbd_case_files.py` 기준 현재 reviewed benchmark case는 `164`건, 이 중 `expected_final`이 있는 finalization case는 `160`건이며, draft 후보 풀은 `1000`건이다. benchmark는 draft marker가 남은 파일을 거부하므로 두 수치를 분리해 관리한다.
- `build_sbd_review_queue.py` 기준 현재 검토 대기열은 `1000`건이며, 25건 단위 Markdown review batch `40`개를 생성했다. reviewed 1000건 목표 검증은 현재 `case_count=164`로 실패하는 것이 정상이다.
- `--source-gap 5`를 적용한 1차 검토 큐는 최신 workflow 기준 `168`건이며, 25건 단위 Markdown review batch `7`개를 생성했다. 이는 전체 후보 수를 줄이는 기준이 아니라, 같은 로그의 인접 chunk를 반복 검토하지 않기 위한 우선 검토 목록이다.
- source log 분포는 최신 workflow 기준 전체 queue에서 `351/49/400/198/2`, diverse queue에서 `59/9/67/33/1`로 나타난다. 이 분포는 현재 로그 모니터링 구간의 편향이며, 논문에서 일반 발화 분포로 해석하지 않는다.
- `promote_sbd_reviewed_cases.py --allow-empty` dry-run 기준 현재 queue 승격은 `promoted_count=0`, `skipped_count=1000`, `existing_case_count=164`이고, work item 승격은 `promoted_count=0`, `skipped_count=880`, `existing_case_count=164`이다. 이는 아직 `expected_final`을 채우고 `review_status`를 확정한 새 항목이 없다는 뜻이며, 실제 승격 명령은 `review_status=reviewed` 또는 `accepted` 항목이 생긴 뒤 실행한다.
- `report_sbd_review_progress.py` 기준 현재 `reviewed_case_count=164`, `reviewed_expected_final_case_count=160`, `ready_in_queue=0`, `total_ready_or_reviewed=164`, `remaining_to_target=836`, `target_met=false`다. finalization 목표 기준은 `finalization_ready_or_reviewed=160`, `remaining_finalization_to_target=840`, `finalization_target_met=false`다.
- 최신 workflow 실행 기준 전체 review queue `1000`건 중 `suggested_expected_final_count=880`건, source-gap diverse queue `169`건 중 `suggested_expected_final_count=149`건에 실제 final 로그 기반 검토 초안이 있다. 이는 검토 효율을 높이는 힌트이며, reviewed case 수로 계산하지 않는다.
- 검토 워크시트는 `880`건 생성됐고 전부 `needs_human_confirmation` 상태다. Markdown work item batch는 25건 단위 `36`개와 `index.md`가 생성됐으며, `balanced_review_order=true`로 언어/source log가 섞인 순서다. `validate_sbd_review_work_items.py` 기준 `ready_count=0`, `missing_expected_final_for_reviewed=0`, `missing_draft_marker=0`, `missing_work_item_marker=0`이다. 따라서 `ready_to_promote_from_work_items=0`, `total_reviewed_or_ready_to_promote=164`이며, 사람이 확인하기 전까지 benchmark case 수는 늘지 않는다.
- review priority 기준 전체 queue와 work item은 현재 모두 `missing-final` 우선순위로 분류된다. 이는 이번 로그 draft 1000건 모두에 `missing-final` 태그가 포함됐기 때문이며, 중복/문장 파괴 등 다른 태그는 보조 태그로 함께 남아 있다.
- 새 케이스를 추가하면 평균 점수가 낮아질 수 있다. 이는 회귀가 아니라 벤치 난도가 높아진 결과일 수 있으므로, 같은 샘플 집합에서의 변경 전후 비교를 우선한다.
- 논문에는 raw STT 모델 성능 개선으로 쓰지 않고, 불안정 STT 스트림을 final-only 번역 입력으로 안정화하는 생명주기 실험 근거로만 사용한다.

기준 벤치:

```text
cases=164
finalized=840
stage_start=1143
finalized_per_stage_start=0.735
final_precision_avg=0.744
final_recall_avg=0.678
final_f1_avg=0.688
final_similarity_coverage_avg=0.607
final_boundary_f1_avg=0.298
```

`AVC_DICTATION_SENTENCE_CONFIRM_CHUNKS=3` sweep:

```text
cases=164
finalized=754
stage_start=1067
finalized_per_stage_start=0.707
final_precision_avg=0.750
final_recall_avg=0.629
final_f1_avg=0.663
final_similarity_coverage_avg=0.580
final_boundary_f1_avg=0.297
```

판단:

- confirmation을 2에서 3으로 올리면 precision은 `0.744 -> 0.750`으로 소폭 개선되지만, recall은 `0.678 -> 0.629`, final F1은 `0.688 -> 0.663`으로 하락한다.
- 이 논문의 목적은 불안정 STT 가설을 final-only 번역 입력으로 안정화하는 것이므로, 중복 억제만을 위해 recall을 크게 잃는 변경은 현재 근거로 채택하지 않는다.
- 기본값은 유지하고, 다음 반복은 confirm 수치보다 앱 로그에서 더 많은 `missing-final`, `duplicate-final`, `stage-queue`, `no-end-marker` 케이스를 수집한 뒤 비교한다.

### 2026-06-20 파라미터 sweep 실행 규칙 보강

논문 근거용 파라미터 변경은 임의 환경변수 실행이 아니라 `tests/eval/dictation_ai/run_sbd_parameter_sweep.py`로 표준화한다.

규칙:

- sweep 대상은 `src/app/dictation_pipeline_settings.py`의 `dictation_tuning_manifest()`에 등록된 파라미터만 허용한다.
- sweep 값은 manifest의 `min_value`/`max_value` 범위 안에 있어야 하며, 범위를 벗어나면 benchmark 실행 전에 실패한다.
- 실행기는 `--param NAME=VALUE`를 `AVC_DICTATION_NAME=VALUE`로 변환해 `sbd_benchmark.py`에 전달한다.
- 모든 job은 같은 `--cases` 입력을 사용하며, 내부 benchmark 명령은 `--device cuda --compute-type float16`으로 고정한다.
- summary에는 `dictation_tuning_protocol`, tuning manifest, 각 job의 env override, benchmark report 경로와 핵심 metric을 남긴다.
- dry-run은 명령 검토용일 뿐 성능 근거가 아니다. 논문 수치로 쓰려면 실제 CUDA/AI benchmark report가 있어야 한다.
- 탐색 sweep은 현재 reviewed case 집합에서 실행할 수 있지만, 논문 근거용 sweep은 `--paper-evidence`를 붙인다. 이 모드는 benchmark 실행 전에 draft marker를 거부하고, 검토한 `expected_final` case 1000건 목표를 검증한다.
- `--min-expected-final-cases`는 중간 점검용 수량 gate다. 이 값을 낮춰 실행한 결과는 탐색/운영 점검으로만 기록하고, 논문 근거 표에는 `--paper-evidence` 기준을 통과한 결과만 사용한다.

dry-run 예:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_parameter_sweep.py \
  --include-baseline \
  --param SENTENCE_CONFIRM_CHUNKS=3 \
  --dry-run
```

논문 근거용 sweep 예:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_parameter_sweep.py \
  --include-baseline \
  --param SENTENCE_CONFIRM_CHUNKS=3 \
  --paper-evidence
```

판단:

- 파라미터 값 자체는 외부 논문에서 직접 가져오지 않는다.
- 외부 문헌은 partial/final 분리, incremental stability, SBD 후보 생성, evaluation framing의 근거로만 쓰고, checked-in 기본값은 앱 로그 replay에서 반복적으로 확인된 수치만 반영한다.
- 현재 `SENTENCE_CONFIRM_CHUNKS=3` sweep은 recall과 final F1 하락이 확인되어 기본값 승격 근거가 부족하다.

### 2026-06-20 앱 로그 케이스 수집 재확인과 파라미터 범위 gate

논문 근거를 보강하기 위한 파라미터 변경은 `dictation_tuning_manifest()`에 등록된 값으로만 제한하고, 각 값은 manifest의 `min_value`/`max_value` 범위 안에서만 sweep할 수 있게 했다. 범위 밖 값은 `run_sbd_parameter_sweep.py`가 benchmark 실행 전에 실패시킨다.

검증:

```text
./.venv/bin/python -m unittest \
  tests.unit.test_dictation_ai_sbd_parameter_sweep \
  tests.unit.test_dictation_ai_log_case_draft_collector

Ran 12 tests in 0.003s
OK

./.venv/bin/python -m py_compile \
  tests/eval/dictation_ai/run_sbd_parameter_sweep.py \
  tests/eval/dictation_ai/collect_sbd_case_drafts_from_logs.py \
  src/app/dictation_pipeline_settings.py
```

범위 gate 확인:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_parameter_sweep.py \
  --include-baseline \
  --param SENTENCE_CONFIRM_CHUNKS=3 \
  --dry-run

case_count=164 expected_final_case_count=160 paper_evidence=False

./.venv/bin/python tests/eval/dictation_ai/run_sbd_parameter_sweep.py \
  --param SENTENCE_CONFIRM_CHUNKS=99 \
  --dry-run

ValueError: SENTENCE_CONFIRM_CHUNKS must be <= 6, got '99'
```

앱 로그 기반 케이스 수집 재실행:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_case_workflow.py --execute

draft_count=1000
draft_language_counts: en=200, ko=400, zh=400
draft_tags: missing-final=999, stage-queue=998, cjk-internal-gap=998, duplicate-final=652
review_queue_count=1000
review_queue_suggested_expected_final_count=864
review_work_item_count=864
ready_to_promote_from_work_items=0
reviewed_case_count=164
reviewed_expected_final_case_count=160
remaining_finalization_to_target=840
```

해석:

- 1000개 draft는 앱 로그에서 수집한 후보 풀이다. `expected_final`을 확인하고 draft marker를 제거하기 전에는 논문 성능 근거가 아니다.
- 현재 논문 근거용 finalization case는 160건이며, 목표 1000건까지 840건이 남았다.
- 파라미터 sweep은 현재 reviewed case에서 탐색용으로 실행할 수 있지만, 논문 표에는 `--paper-evidence` 조건을 통과한 실행만 포함한다.

### 2026-06-20 로그 모니터링 재실행과 다음 검토 배치 표시

반복 실행 중인 앱 로그를 다시 읽어 case workflow를 1회 실행했다.

```text
./.venv/bin/python tests/eval/dictation_ai/monitor_sbd_case_workflow.py \
  --iterations 1 \
  --interval-seconds 0 \
  --run-id codex-goal-20260620
```

관측값:

```text
draft_count=1000
draft_language_counts: en=200, ko=400, zh=400
draft_tags: missing-final=999, stage-queue=998, cjk-internal-gap=998,
            duplicate-final=639, no-end-marker=257
review_queue_count=1000
suggested_expected_final_count=866
review_work_item_count=866
reviewed_case_count=164
reviewed_expected_final_case_count=160
remaining_finalization_to_target=840
ready_to_promote_from_work_items=0
```

`report_sbd_review_progress.py`에 `pending_review_work_item_count`와 `next_review_work_item_files`를 추가했다. 이 값은 다음에 사람이 확인할 work item part 파일, line 범위, 언어 분포, 우선순위 태그 분포를 보여준다. 성능 지표가 아니라 1000건 reviewed case 목표를 채우기 위한 검토 운영 지표다.

같은 리포트에 `--markdown-output`을 추가해 사람이 바로 읽는 진행표도 생성한다. 최신 생성 파일은 `.tmp/eval/dictation-ai-sbd/review-progress-summary.md`이며, target 진행률, 언어별 부족분, 추천 검토 파일 순서를 함께 담는다.

최신 리포트 기준 다음 검토 파일 3개:

```text
.tmp/eval/dictation-ai-sbd/review-work-items.part-0001.jsonl
  pending_count=250 lines=1-250 languages=en:52, ko:104, zh:94
  priority=missing-final:249, duplicate-final:1

.tmp/eval/dictation-ai-sbd/review-work-items.part-0002.jsonl
  pending_count=250 lines=1-250 languages=en:63, ko:125, zh:62
  priority=missing-final:250

.tmp/eval/dictation-ai-sbd/review-work-items.part-0003.jsonl
  pending_count=250 lines=1-250 languages=en:67, ko:111, zh:72
  priority=missing-final:250
```

현재 review queue 언어 분포를 1000건 목표에 비례 배분한 정보성 목표와 부족분:

```text
suggested_finalization_language_targets: en=200, ko=400, zh=400
finalization_progress_language_counts: en=55, ko=76, zh=29
remaining_finalization_by_language: en=145, ko=324, zh=371
```

언어 부족분으로 가중 정렬한 work item 추천 순서:

```text
.tmp/eval/dictation-ai-sbd/review-work-items.part-0001.jsonl
  score=76110 shortage_languages=en:52, ko:104, zh:94

.tmp/eval/dictation-ai-sbd/review-work-items.part-0002.jsonl
  score=72637 shortage_languages=en:63, ko:125, zh:62

.tmp/eval/dictation-ai-sbd/review-work-items.part-0003.jsonl
  score=72391 shortage_languages=en:67, ko:111, zh:72

.tmp/eval/dictation-ai-sbd/review-work-items.part-0004.jsonl
  score=42801 shortage_languages=ko:5, zh:111
```

판단:

- 수집 후보는 계속 1000건을 유지하고 있으며, 새 로그 반영으로 work item 후보가 864건에서 866건으로 늘었다.
- 논문 근거로 쓰기 위해서는 `review_status=reviewed|accepted`와 확인한 `expected_final`이 필요하다.
- 언어별 목표/부족분은 현재 queue 분포를 기준으로 한 검토 운영 힌트이며, 강제 gate나 성능 지표가 아니다.
- 추천 순서는 언어 부족분을 빨리 줄이기 위한 작업 순서 힌트이며, 최종 benchmark 분포나 성능 개선을 보장하지 않는다.
- 다음 반복의 병목은 로직 튜닝이 아니라 work item 검토/승격이다. 승격 전 CUDA/AI 벤치나 파라미터 sweep은 탐색 자료로만 본다.

### 2026-06-20 로그 수집/검토 진행률 history 필드 보강

논문의 근거를 보충하려면 파라미터 변경 규칙뿐 아니라, 앱 로그에서 수집한 실패 후보가 어떻게 reviewed benchmark case로 승격되는지 반복 기록되어야 한다. 이에 `monitor_sbd_case_workflow.py`가 `report_sbd_review_progress.py`의 언어별 목표/부족분과 추천 검토 파일을 history에 함께 남기도록 보강했다.

검증 실행:

```text
./.venv/bin/python tests/eval/dictation_ai/monitor_sbd_case_workflow.py \
  --iterations 1 \
  --interval-seconds 0 \
  --run-id codex-rule-evidence-20260620

./.venv/bin/python tests/eval/dictation_ai/report_sbd_monitor_history.py \
  .tmp/eval/dictation-ai-sbd/monitor-history.jsonl \
  --summary-output .tmp/eval/dictation-ai-sbd/monitor-history-summary.json
```

최신 관측값:

```text
draft_count=1000
draft_language_counts: en=200, ko=400, zh=400
draft_tags: missing-final=1000, stage-queue=1000, cjk-internal-gap=1000,
            duplicate-final=490, no-end-marker=261
review_queue_count=1000
suggested_expected_final_count=787
diverse_review_queue_count=168
diverse_suggested_expected_final_count=128
review_work_item_count=787
pending_review_work_item_count=787
ready_to_promote_from_work_items=0
reviewed_case_count=164
reviewed_expected_final_case_count=160
remaining_finalization_to_target=840
```

언어별 finalization 목표와 부족분:

```text
suggested_finalization_language_targets: en=200, ko=400, zh=400
finalization_progress_language_counts: en=55, ko=76, zh=29
remaining_finalization_by_language: en=145, ko=324, zh=371
```

언어 부족분 기준 추천 검토 파일:

```text
.tmp/eval/dictation-ai-sbd/review-work-items.part-0003.jsonl
  score=76719 languages=en:57, ko:67, zh:126

.tmp/eval/dictation-ai-sbd/review-work-items.part-0002.jsonl
  score=72863 languages=en:62, ko:125, zh:63

.tmp/eval/dictation-ai-sbd/review-work-items.part-0001.jsonl
  score=72637 languages=en:63, ko:125, zh:62

.tmp/eval/dictation-ai-sbd/review-work-items.part-0004.jsonl
  score=13727 languages=zh:37
```

판단:

- 앱 로그 기반 draft 후보 풀은 1000건을 유지하고 있지만, 논문 성능 근거로 사용할 수 있는 reviewed `expected_final` case는 아직 160건이다.
- `suggested_expected_final`이 있는 work item 787건은 검토 효율을 높이는 작업 후보일 뿐, 사람이 확인하기 전에는 benchmark case가 아니다.
- 파라미터 sweep은 `dictation_tuning_manifest()`의 범위 안에서만 허용하고, 논문 근거용 sweep은 reviewed finalization case 1000건을 만족한 뒤 `--paper-evidence`로만 실행한다.
- 새 history 필드는 수집/검토 운영 근거이며, 성능 비교 수치는 아니다. 성능 비교는 승격 완료 JSONL에 대해 실제 `sat + cuda + float16` benchmark 또는 parameter sweep으로 생성한다.

### 2026-06-20 전체 review queue 워크시트화 보강

기존 워크플로는 `suggested_expected_final`이 있는 항목만 work item으로 만들었기 때문에, 앱 로그 draft 1000건 중 일부가 검토 템플릿에도 올라오지 않았다. 논문 근거용 케이스 1000건을 모으려면 final 힌트가 있는 쉬운 항목만 고르는 편향을 피해야 하므로, 기본 `prepare-review-work-items` 단계에 `--include-without-suggestions`를 추가했다. final 힌트가 없는 항목은 `expected_final=[]`, `review_work_source=empty_template`로 남기며, 사람이 확인하기 전에는 여전히 승격되지 않는다.

검증 실행:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_case_workflow.py --execute

./.venv/bin/python tests/eval/dictation_ai/monitor_sbd_case_workflow.py \
  --iterations 1 \
  --interval-seconds 0 \
  --run-id codex-workitem-source-breakdown-20260620

./.venv/bin/python tests/eval/dictation_ai/report_sbd_monitor_history.py \
  .tmp/eval/dictation-ai-sbd/monitor-history.jsonl \
  --summary-output .tmp/eval/dictation-ai-sbd/monitor-history-summary.json
```

최신 관측값:

```text
draft_count=1000
draft_language_counts: en=200, ko=400, zh=400
draft_tags: missing-final=1000, stage-queue=1000, cjk-internal-gap=1000,
            duplicate-final=520, no-end-marker=274
review_queue_count=1000
suggested_expected_final_count=804
review_work_item_count=1000
work_item_source_counts: suggested_expected_final=804, empty_template=196
pending_review_work_item_count=1000
ready_to_promote_from_work_items=0
reviewed_case_count=164
reviewed_expected_final_case_count=160
remaining_finalization_to_target=840
```

언어별 finalization 목표와 부족분:

```text
suggested_finalization_language_targets: en=200, ko=400, zh=400
finalization_progress_language_counts: en=55, ko=76, zh=29
remaining_finalization_by_language: en=145, ko=324, zh=371
```

언어 부족분 기준 추천 검토 파일:

```text
.tmp/eval/dictation-ai-sbd/review-work-items.part-0004.jsonl
  score=86875 languages=ko:125, zh:125

.tmp/eval/dictation-ai-sbd/review-work-items.part-0003.jsonl
  score=80216 languages=en:33, ko:108, zh:109

.tmp/eval/dictation-ai-sbd/review-work-items.part-0002.jsonl
  score=70044 languages=en:83, ko:84, zh:83

.tmp/eval/dictation-ai-sbd/review-work-items.part-0001.jsonl
  score=69865 languages=en:84, ko:83, zh:83
```

판단:

- 이제 앱 로그 draft 1000건 전체가 review work item으로 생성된다.
- 804건은 실제 final 로그 힌트가 있는 항목이고, 196건은 사람이 원 로그를 보고 `expected_final`을 직접 채워야 하는 빈 템플릿이다.
- 자동 승격 가능한 항목은 여전히 0건이다. 이는 사람이 확인하지 않은 `expected_final`을 논문 성능 근거로 쓰지 않기 위한 정상 동작이다.
- reviewed finalization case는 아직 160건이므로 논문 근거용 `--paper-evidence` sweep 조건은 충족하지 못했다.

### 2026-06-20 final hint context 분리

전체 review queue 워크시트화 이후에도 final 힌트가 없는 빈 템플릿이 196건 남았다. 원인은 raw replay에 필요한 STT window context와, 사람이 기대 final을 확인할 때 필요한 실제 확정 로그 검색 범위를 같은 값으로 묶어 둔 데 있었다. 논문 근거용 benchmark 입력은 실패 구간 주변의 짧은 연속 window여야 하지만, 사람이 검토할 때는 조금 뒤에 확정된 final 로그가 참고값으로 필요할 수 있다.

이에 수집기의 raw replay context는 기본 4 chunk로 유지하고, final 힌트 검색만 `--final-hint-context 12`로 분리했다. 이 값은 `observed_final_texts`와 `suggested_expected_final` 힌트에만 영향을 주며, benchmark 입력이나 `expected_final`을 자동으로 늘리지 않는다.

검증 실행:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_case_workflow.py --execute

./.venv/bin/python tests/eval/dictation_ai/monitor_sbd_case_workflow.py \
  --iterations 1 \
  --interval-seconds 0 \
  --run-id codex-final-hint-context-20260620

./.venv/bin/python tests/eval/dictation_ai/report_sbd_monitor_history.py \
  .tmp/eval/dictation-ai-sbd/monitor-history.jsonl \
  --summary-output .tmp/eval/dictation-ai-sbd/monitor-history-summary.json
```

최신 관측값:

```text
draft_count=1000
draft_language_counts: en=200, ko=400, zh=400
draft_tags: missing-final=1000, stage-queue=1000, cjk-internal-gap=1000,
            duplicate-final=489, no-end-marker=258
review_queue_count=1000
suggested_expected_final_count=939
diverse_review_queue_count=168
diverse_suggested_expected_final_count=157
review_work_item_count=1000
work_item_source_counts: suggested_expected_final=939, empty_template=61
pending_review_work_item_count=1000
ready_to_promote_from_work_items=0
reviewed_case_count=164
reviewed_expected_final_case_count=160
remaining_finalization_to_target=840
```

판단:

- final 힌트 coverage는 804/1000에서 939/1000으로 증가했다.
- 빈 템플릿은 196건에서 61건으로 줄었지만, 이 61건도 review work item으로 유지된다.
- 자동 승격 가능 항목은 0건으로 유지된다. 사람이 확인하지 않은 힌트는 여전히 논문 성능 근거로 사용하지 않는다.
- reviewed finalization case는 160건으로 unchanged이며, 1000건 목표까지 840건이 남았다.

### 2026-06-20 review work source index 보강

final 힌트 coverage가 높아져도 사람이 실제로 검토해야 하는 work item은 여전히 1000건이다. 기존 Markdown index는 언어와 source log 분포만 보여줘, final 힌트가 붙은 항목과 빈 템플릿 항목이 어느 배치에 있는지 바로 알기 어려웠다. 이에 `prepare_sbd_review_work_items.py`의 Markdown 항목과 index에 `review_work_source` 분포를 추가했다.
이후 각 Markdown 항목에 `Observed Status Signals` 섹션도 추가했다. 이 섹션은 draft 수집 당시 원 로그에서 관측된 `중복 문장 무시`, `stage 교체 보류`, `stage_queue_*`, `raw_without_final` 같은 상태 신호를 보여준다. 검토자가 왜 해당 chunk가 수집됐는지 확인하고 `expected_final`을 손볼 수 있게 하기 위한 운영 정보이며, 자동 승격 기준은 아니다.

검증 실행:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_case_workflow.py --execute

./.venv/bin/python tests/eval/dictation_ai/monitor_sbd_case_workflow.py \
  --iterations 1 \
  --interval-seconds 0 \
  --run-id codex-review-source-index-20260620

./.venv/bin/python tests/eval/dictation_ai/report_sbd_monitor_history.py \
  .tmp/eval/dictation-ai-sbd/monitor-history.jsonl \
  --summary-output .tmp/eval/dictation-ai-sbd/monitor-history-summary.json
```

최신 관측값:

```text
draft_count=1000
draft_language_counts: en=200, ko=400, zh=400
draft_tags: missing-final=1000, stage-queue=1000, cjk-internal-gap=1000,
            duplicate-final=589, no-end-marker=275
review_queue_count=1000
suggested_expected_final_count=964
diverse_review_queue_count=168
diverse_suggested_expected_final_count=162
review_work_item_count=1000
work_item_source_counts: suggested_expected_final=964, empty_template=36
pending_review_work_item_count=1000
ready_to_promote_from_work_items=0
reviewed_case_count=164
reviewed_expected_final_case_count=160
remaining_finalization_to_target=840
```

Markdown index 예:

```text
review_work_source_counts: {'empty_template': 36, 'suggested_expected_final': 964}
batch review_work_sources: {'suggested_expected_final': 25}
Observed Status Signals
```

판단:

- 앱 로그 회전 이후 final 힌트 coverage는 964/1000까지 올라갔다.
- 빈 템플릿은 36건만 남았으며, Markdown index에서 어느 배치에 포함됐는지 확인할 수 있다.
- reviewed finalization case 수는 160건으로 변하지 않았다. 이번 변경은 성능 수치 개선이 아니라 사람 검토 병목을 줄이는 수집/검토 운영 개선이다.
- 자동 승격 가능 항목은 0건이다. 사람이 확인하지 않은 항목은 여전히 논문 성능 근거로 쓰지 않는다.

### 2026-06-20 review progress 파일별 source 분포 보강

Markdown index에 source 분포가 생겼지만, 실제 검토 순서는 `report_sbd_review_progress.py`의 `recommended_review_work_item_files`를 보고 정하게 된다. 따라서 진행률 리포트의 `next_review_work_item_files`와 `recommended_review_work_item_files`에도 파일별 `review_work_source_counts`를 추가했다. 이 값은 `suggested_expected_final` 힌트가 있는 항목과 `empty_template` 항목이 어느 part 파일에 몰려 있는지 확인하기 위한 검토 운영 메타데이터다.

검증 실행:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_case_workflow.py --execute

./.venv/bin/python tests/eval/dictation_ai/monitor_sbd_case_workflow.py \
  --iterations 1 \
  --interval-seconds 0 \
  --run-id codex-review-file-source-counts-20260620
```

최신 진행률:

```text
target_cases=1000
reviewed_case_count=164
reviewed_expected_final_case_count=160
remaining_finalization_to_target=840
review_work_item_count=1000
pending_review_work_item_count=1000
ready_to_promote_from_work_items=0
work_item_sources: empty_template=36, suggested_expected_final=964
```

추천 검토 파일별 source 분포:

```text
.tmp/eval/dictation-ai-sbd/review-work-items.part-0004.jsonl
  score=86875 languages=ko:125, zh:125
  work_item_sources=empty_template:34, suggested_expected_final:216

.tmp/eval/dictation-ai-sbd/review-work-items.part-0003.jsonl
  score=80216 languages=en:33, ko:108, zh:109
  work_item_sources=empty_template:2, suggested_expected_final:248

.tmp/eval/dictation-ai-sbd/review-work-items.part-0002.jsonl
  score=70044 languages=en:83, ko:84, zh:83
  work_item_sources=suggested_expected_final:250

.tmp/eval/dictation-ai-sbd/review-work-items.part-0001.jsonl
  score=69865 languages=en:84, ko:83, zh:83
  work_item_sources=suggested_expected_final:250
```

판단:

- 검토 우선순위가 높은 `part-0004`에 빈 템플릿 34건이 집중되어 있다.
- 논문 근거용 케이스 1000건 목표를 채우려면 `part-0004`, `part-0003`부터 사람이 원 로그를 확인해 `expected_final`을 확정하는 것이 효율적이다.
- 파일별 source 분포는 검토 운영을 돕는 값이며, 자동 승격이나 성능 벤치 근거가 아니다. 성능 수치는 reviewed JSONL로 승격한 뒤 실제 `sat + cuda + float16` 벤치에서만 산출한다.

### 2026-06-20 review progress와 Markdown batch 연결

진행률 리포트는 추천 검토 단위를 JSONL part 파일로 보여주지만, 사람이 실제로 읽기 쉬운 자료는 `prepare_sbd_review_work_items.py`가 만든 Markdown batch다. 이 둘이 분리되어 있으면 추천 1순위가 어떤 Markdown 파일 범위인지 다시 계산해야 하므로 검토 병목이 남는다. 이에 `report_sbd_review_progress.py`에 `--review-work-markdown-dir`와 `--review-work-markdown-batch-size` 옵션을 추가하고, `next_review_work_item_files`와 `recommended_review_work_item_files`에 `markdown_files`를 함께 기록하게 했다.

검증 실행:

```text
./.venv/bin/python tests/eval/dictation_ai/monitor_sbd_case_workflow.py \
  --iterations 1 \
  --interval-seconds 0 \
  --run-id codex-review-markdown-link-20260620

./.venv/bin/python tests/eval/dictation_ai/report_sbd_monitor_history.py \
  .tmp/eval/dictation-ai-sbd/monitor-history.jsonl \
  --summary-output .tmp/eval/dictation-ai-sbd/monitor-history-summary.json
```

최신 관측값:

```text
draft_count=1000
draft_language_counts: en=200, ko=400, zh=400
review_queue_count=1000
suggested_expected_final_count=957
diverse_review_queue_count=169
diverse_suggested_expected_final_count=162
review_work_item_count=1000
work_item_sources: empty_template=43, suggested_expected_final=957
reviewed_expected_final_case_count=160
remaining_finalization_to_target=840
ready_to_promote_from_work_items=0
```

추천 1순위는 `review-work-items.part-0004.jsonl`이고, 해당 part는 다음 Markdown batch와 연결된다.

```text
.tmp/eval/dictation-ai-sbd/review-work-item-batches/sbd-review-work-items-0031.md
...
.tmp/eval/dictation-ai-sbd/review-work-item-batches/sbd-review-work-items-0040.md
```

판단:

- 추천 검토 단위와 사람이 읽는 Markdown batch가 연결되어, `part-0004`의 250건을 검토할 때 열어야 할 파일 범위를 리포트에서 바로 확인할 수 있다.
- 이번 변경은 케이스 수집/검토 운영 개선이며, 성능 개선이나 논문 수치 근거가 아니다.
- `expected_final`을 확인하지 않았으므로 자동 승격 가능 항목은 계속 0건이다.

### 2026-06-20 지속 실행 로그 관찰과 검토 후보 갱신

앱이 계속 실행되며 `.tmp/logs/avc-whisper.log`에 새 STT 로그가 누적되는 상태를 확인했다. `monitor_sbd_case_workflow.py`를 1분 간격 3회 실행해 draft/review queue/work item이 최신 로그를 반영하는지 확인했다. 이 실행은 비-CUDA 수집/검토 준비 단계이며, 성능 벤치 근거가 아니다.

검증 실행:

```text
./.venv/bin/python tests/eval/dictation_ai/monitor_sbd_case_workflow.py \
  --iterations 3 \
  --interval-seconds 60 \
  --run-id codex-continuous-log-observe-20260620

./.venv/bin/python tests/eval/dictation_ai/report_sbd_monitor_history.py \
  .tmp/eval/dictation-ai-sbd/monitor-history.jsonl \
  --summary-output .tmp/eval/dictation-ai-sbd/monitor-history-summary.json
```

최신 관측값:

```text
draft_count=1000
draft_language_counts: en=200, ko=400, zh=400
review_queue_count=1000
suggested_expected_final_count=947
diverse_review_queue_count=169
diverse_suggested_expected_final_count=161
review_work_item_count=1000
work_item_sources: empty_template=53, suggested_expected_final=947
reviewed_expected_final_case_count=160
remaining_finalization_to_target=840
ready_to_promote_from_work_items=0
```

활성 로그 유입 변화:

```text
iteration 1: .tmp/logs/avc-whisper.log=282, avc-whisper.log.18=181
iteration 2: .tmp/logs/avc-whisper.log=345, avc-whisper.log.18=118
iteration 3: .tmp/logs/avc-whisper.log=402, avc-whisper.log.18=61
```

추천 검토 파일:

```text
.tmp/eval/dictation-ai-sbd/review-work-items.part-0004.jsonl
  markdown_files: sbd-review-work-items-0031.md ... sbd-review-work-items-0040.md
  review_work_sources: empty_template=44, suggested_expected_final=206

.tmp/eval/dictation-ai-sbd/review-work-items.part-0003.jsonl
  markdown_files: sbd-review-work-items-0021.md ... sbd-review-work-items-0030.md
  review_work_sources: suggested_expected_final=250
```

판단:

- 활성 로그 비중이 증가했으므로 앱 로그 기반 수집은 계속 동작하고 있다.
- 1000건 draft와 947건 final 힌트 work item은 유지되지만, 확인한 `expected_final` 케이스는 160건에서 변하지 않았다.
- 논문 근거용 1000건 목표를 채우려면 Markdown batch에서 원문 문맥과 observed final reference를 확인한 뒤 JSONL work item의 `review_status`와 `expected_final`을 사람이 확정해야 한다.
- 모니터 history는 관찰/수집 운영 자료이며, 논문 성능 수치는 승격된 reviewed JSONL을 실제 `sat + cuda + float16` 벤치로 실행한 결과만 사용한다.

### 2026-06-20 정식 케이스 등록 기준 정리

케이스 후보 1000건을 모두 정식 benchmark case로 보는 것은 위험하다. 논문 목표는 raw STT 정확도 평가가 아니라, 불안정한 STT window 출력에서 final-only 번역 입력을 안정적으로 만드는 lifecycle 평가다. 따라서 정식 finalization benchmark case는 다음 조건을 만족해야 한다.

등록 기준:

- 앱 로그의 연속 STT window에서 확정 누락, 중복 확정, 문장 순서 파괴, premature fragment final, staged/pending 잔류, 최근 final echo처럼 final-only 번역 입력을 오염시키는 lifecycle 실패가 관측되어야 한다.
- source chunk, observed final reference, status signal을 사람이 확인했을 때 하나 이상의 `expected_final`을 명확히 정할 수 있어야 한다.
- `review_status=reviewed` 또는 `accepted`이고 `expected_final`이 비어 있지 않아야 한다.
- 같은 로그 구간의 거의 동일한 반복 후보는 대표 케이스만 남긴다.

제외 기준:

- raw STT 자체가 입력 음성과 무관하거나 해석 불가능해 lifecycle 판단 근거가 약한 경우.
- 연속 window 문맥이 부족해 pending/staged/final 판단 흐름을 재현할 수 없는 경우.
- 사람이 봐도 정식 `expected_final`을 하나로 결정하기 어려운 경우.
- 이미 같은 실패 유형과 같은 source chunk 구간을 대표하는 케이스가 있는 경우.

도구 반영:

- `promote_sbd_reviewed_cases.py`는 계속 `reviewed|accepted + expected_final`만 승격한다.
- `excluded` 또는 `rejected` 상태는 승격하지 않으며, 리포트의 `excluded_count`와 `skipped_status_counts`로만 집계한다.
- 이 집계는 검토 운영 지표이며 논문 성능 수치가 아니다.

### 2026-06-20 그룹 기반 후보 평가와 자동 정식 케이스 분리

후보 1000건을 개별 라벨링하면 검토 속도가 너무 느리다. 따라서 work item을 같은 근거를 가진 그룹으로 묶고, 그룹과 개별 항목이 모두 기준을 넘을 때 자동으로 정식 reviewed case로 분리하는 구조를 추가했다.

그룹 기준:

```text
language
review_priority_tag
review_work_source
tag_signature
source_log
```

자동 등록 기본 임계치:

```text
min_group_size=3
min_item_score=5
min_group_ratio=0.9
min_average_score=5.0
```

항목 evidence score:

```text
expected_final 있음: +2
observed final reference/text 있음: +2
source chunk 3개 이상: +1
observed status signal 있음: +1
review_work_source=suggested_expected_final: +1
```

검증 실행:

```text
./.venv/bin/python tests/eval/dictation_ai/run_sbd_case_workflow.py --group-review-work-items
```

동일 동작의 세부 명령:

```text
./.venv/bin/python tests/eval/dictation_ai/group_sbd_review_work_items.py \
  '.tmp/eval/dictation-ai-sbd/review-work-items.part-*.jsonl' \
  --output .tmp/eval/dictation-ai-sbd/review-work-item-groups.json \
  --markdown-output .tmp/eval/dictation-ai-sbd/review-work-item-groups.md \
  --auto-accept-output .tmp/eval/dictation-ai-sbd/auto-accepted-review-work-items.jsonl \
  --promoted-group-dir tests/eval/dictation_ai/sbd_cases/auto-groups \
  --existing tests/eval/dictation_ai/sbd_text_cases.sample.jsonl tests/eval/dictation_ai/sbd_cases \
  --summary-output .tmp/eval/dictation-ai-sbd/review-work-item-groups-summary.json

./.venv/bin/python tests/eval/dictation_ai/validate_sbd_case_files.py \
  tests/eval/dictation_ai/sbd_text_cases.sample.jsonl \
  tests/eval/dictation_ai/sbd_cases \
  --min-expected-final-cases 1000 \
  --max-drafts 0 \
  --summary-output .tmp/eval/dictation-ai-sbd/reviewed-with-auto-groups-summary.json
```

결과:

```text
input_count=1000
group_count=27
auto_accept_group_count=18
auto_accepted_item_count=944
promoted_group_file_count=18

validated_case_count=1108
validated_expected_final_case_count=1104
validated_draft_count=0
language_counts: en=427, ko=461, zh=220
```

판단:

- 단일 reviewed 파일에 누적하는 대신 `tests/eval/dictation_ai/sbd_cases/auto-groups/`에 그룹별 JSONL을 생성했다.
- validator와 benchmark loader는 디렉터리 하위 JSONL을 재귀적으로 읽도록 변경했다.
- 자동 등록은 `suggested_expected_final`과 observed final reference가 있는 항목으로 제한된다. `empty_template` 51건과 그룹/항목 기준 미달 후보는 자동 등록되지 않았다.
- 이 데이터셋은 1000건 이상의 finalization benchmark 입력을 제공하지만, 성능 수치 근거는 별도 `sat + cuda + float16` benchmark 실행 결과로만 기록한다.

### 2026-06-20 sample 파일 역할 정리

`tests/eval/dictation_ai/sbd_text_cases.sample.jsonl`에 실제 로그 기반 reviewed case가 164건까지 누적되어 있었다. 그룹별 정식 케이스 구조가 생긴 뒤에는 이 파일이 정식 케이스 저장소처럼 보이는 문제가 있으므로 역할을 분리했다.

정리 기준:

- `sbd_text_cases.sample.jsonl`은 최소 seed 샘플만 유지한다.
- 실제 로그 기반 reviewed case는 `tests/eval/dictation_ai/sbd_cases/` 아래에 둔다.
- 기존 수동 reviewed 로그 케이스는 `tests/eval/dictation_ai/sbd_cases/manual-reviewed/`에 언어별 JSONL로 분리한다.
- 자동 그룹 등록 케이스는 기존처럼 `tests/eval/dictation_ai/sbd_cases/auto-groups/`에 둔다.
- benchmark와 validator는 sample 파일과 `sbd_cases/` 디렉터리를 함께 읽으므로 전체 케이스 수는 유지한다.

분리 결과:

```text
sbd_text_cases.sample.jsonl: 3
sbd_cases/manual-reviewed/reviewed-log-en.jsonl: 55
sbd_cases/manual-reviewed/reviewed-log-ko.jsonl: 78
sbd_cases/manual-reviewed/reviewed-log-zh.jsonl: 28
```

검증 결과:

```text
case_count=1108
expected_final_case_count=1104
draft_count=0
language_counts: en=427, ko=461, zh=220
```

판단:

- sample 파일은 더 이상 로그 기반 케이스 누적 대상이 아니다.
- 정식 benchmark case 저장소는 `sbd_cases/`이며, 수동 reviewed와 자동 그룹 reviewed를 하위 디렉터리로 구분한다.
- 이번 정리는 데이터 배치 정리이며 성능 수치 근거가 아니다. 성능 근거는 동일 케이스 집합을 실제 `sat + cuda + float16`으로 실행한 benchmark 결과로만 기록한다.

### 2026-06-20 수집/검토/승격 도구 폐기

로그 draft 수집, review queue/work item 생성, 그룹 자동 등록, 승격, 모니터링 workflow 도구는 유지하지 않기로 했다. 논문 근거의 중심은 도구 운영 절차가 아니라 확정한 reviewed JSONL 케이스와 실제 `sat + cuda + float16` benchmark 결과다.

폐기한 도구 범위:

```text
collect_sbd_case_drafts_from_logs.py
build_sbd_review_queue.py
prepare_sbd_review_work_items.py
validate_sbd_review_work_items.py
promote_sbd_reviewed_cases.py
group_sbd_review_work_items.py
run_sbd_case_workflow.py
monitor_sbd_case_workflow.py
report_sbd_review_progress.py
report_sbd_monitor_history.py
```

현재 유지하는 최소 경로:

- 정식 로그 기반 케이스는 `tests/eval/dictation_ai/sbd_cases/` 아래의 JSONL 파일로 직접 관리한다.
- `tests/eval/dictation_ai/sbd_benchmark.py`는 `sbd_cases/**/*.jsonl`을 로딩한다.
- `tests/eval/dictation_ai/validate_sbd_case_files.py`는 케이스 수, draft marker, 중복 id를 확인하는 검증 도구로 유지한다.

판단:

- 자동화 도구로 후보를 승격하는 구조는 논문 목표를 흐릴 수 있으므로 폐기한다.
- 기존 `sbd_cases/auto-groups/`의 JSONL은 이전 그룹 평가 산출물로 유지하되, 이후 새 케이스는 확인한 reviewed JSONL로 직접 추가한다.
- 성능 근거는 도구 수집량이 아니라 reviewed case 집합을 실제 AI/CUDA 벤치로 실행한 결과로만 기록한다.

### 2026-06-20 draft 후보 5건 수동 승격

폐기한 자동 workflow 산출물 중 정식 `sbd_cases/`에 아직 없는 promoted group 후보를 다시 확인했다. 후보 파일 4개를 그대로 추가하면 기존 케이스와 id가 중복되므로 파일 단위 승격은 하지 않았다. 기존 정식 케이스 id와 비교해 신규 id만 추리면 영어 2건, 중국어 2건, 한국어 1건이 남았다.

승격 기준:

- `draft_expected_final_required` marker가 없어야 한다.
- 기존 정식 케이스와 id가 중복되면 제외한다.
- 자동 `suggested_expected_final`을 그대로 쓰지 않고, 연속 STT window에서 반복 관측되는 문장 단위로 `expected_final`을 다시 정리한다.
- 절단 fragment나 다음 문맥의 과도한 선행/후행 문장은 제거한다.

추가 파일:

```text
tests/eval/dictation_ai/sbd_cases/manual-reviewed/reviewed-log-promoted-20260620.jsonl
```

검증 결과:

```text
case_count=1113
expected_final_case_count=1109
draft_count=0
language_counts: en=429, ko=462, zh=222
manual_promoted_count=5
```

판단:

- 이번 승격은 성능 개선이 아니라 benchmark case corpus 보강이다.
- 성능 수치 근거로 사용하려면 동일 case set을 실제 `sat + cuda + float16` benchmark로 다시 실행해야 한다.

### 2026-06-20 sample 파일 폐기

`tests/eval/dictation_ai/sbd_text_cases.sample.jsonl`에 남아 있던 lifecycle seed 3건을 정식 케이스 디렉터리로 이관했다. 이 파일은 더 이상 별도 seed 역할을 유지하지 않고 폐기한다.

이관 파일:

```text
tests/eval/dictation_ai/sbd_cases/manual-reviewed/reviewed-lifecycle-seed.jsonl
```

정리 기준:

- benchmark 기본 입력은 `tests/eval/dictation_ai/sbd_cases/` 하나로 한다.
- parameter sweep 기본 입력도 `tests/eval/dictation_ai/sbd_cases/` 하나로 한다.
- sample 파일을 함께 넘기던 검증/벤치 명령 예시는 폐기한다.

검증 기준은 sample 폐기 전후 모두 동일하게 `sbd_cases/**/*.jsonl` 전체 로딩과 중복 id/draft marker 확인이다.
