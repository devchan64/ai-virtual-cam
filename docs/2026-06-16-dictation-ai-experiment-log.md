# 받아쓰기 AI 실험일지

## 문서 상태

이 문서는 폐기된 원본 문서 `docs/2026-06-13-dictation-ai-feature-design.md`의 Git 커밋 기록을 기준으로 재구성한 실험일지다. 이 파일은 이전에 다른 이름의 설계 문서로 존재했으므로 rename 이전 문서의 변경 이력까지 추적 대상에 포함한다. 또한 받아쓰기 AI의 실험 판단이 README, 논문 초안, 발표용 세그먼트 레퍼런스 문서에 분산되어 기록된 경우 해당 문서 업데이트 히스토리도 보조 근거로 포함한다. 설계/운영 기준은 [받아쓰기 AI 설계 및 실험 노트](2026-06-16-dictation-ai-design-experiment-notes.md), 설정 계약과 기본값은 [받아쓰기 AI 계약과 기본값](2026-06-16-dictation-ai-contract-defaults.md)을 따른다. Qwen3-ASR vLLM streaming, Dolphin-CN-Dialect, WeNet의 세부검증 판단은 [받아쓰기 AI 중국어 STT 후보 세부검증 리포트](2026-06-16-dictation-ai-chinese-stt-candidate-validation.md)에 둔다.

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
| CJK 접합 | 공백 없는 중국어는 문자 n-gram, prefix/suffix, 내부 prefix overlap을 우선한다. | 내부 재시작을 새 continuation으로 오인하지 않아야 한다. |
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
- 모델 다운로드는 setup이 아니라 config GUI 모델 다운로드 모달과 Serve 시작 전 캐시 검사 흐름으로 분리한다.
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
| pending tail 뒤에 새 STT가 같은 CJK 구간 중간부터 다시 시작함 | CJK no-space 텍스트에서는 내부 prefix overlap을 찾아 `pending prefix + new_text`로 병합한다. | `pending_new_text_combined()`가 내부 재시작과 독립 continuation을 구분하도록 정리됐다. |
| 서로 다른 중국어 continuation 사이에 공백이 삽입됨 | CJK continuation은 인위적 공백 없이 이어붙인다. | 중국어 pending 접합에서 의미 없는 whitespace 삽입을 줄였다. |
| 원문창이 staged 후보를 보여주던 시기의 로그가 raw STT 품질 판단을 흐림 | 원문창은 `stt_raw` 이벤트만 표시하고, staged/partial은 진단 로그로만 둔다. | raw STT 품질, revision lifecycle, final 출력의 관측 위치를 분리했다. |
| `raw_without_final`이 증가했지만 입력 큐 드롭은 없었음 | 후보 차단/보류 규칙을 늘리기보다 final 생성률 회복을 우선한다. | 명백한 오류만 차단하고 나머지는 staged 교체와 재확인으로 처리하는 방향을 채택했다. |
| CJK revision 내용이 바뀌어도 기존 confirmations가 남을 수 있음 | 실제 내용이 바뀐 revision은 confirmations를 1부터 다시 센다. | 흔들리는 후보가 누적 확인만으로 final이 되는 문제를 줄였다. |

### 반영 판단

- CJK no-space 텍스트에서 긴 내부 prefix overlap이 확인되면 `pending prefix + new_text`로 병합한다.
- 서로 다른 중국어 continuation은 인위적 공백 없이 이어붙인다.
- 원문창은 `stt_raw` 이벤트만 표시한다.
- staged/partial 후보는 final 확정 전 내부 상태이므로 원문창에 표시하지 않는다.
- 영어/한국어 기본 시작점은 `windowSeconds=7`, `stepSeconds=1`, `sentenceFinalizeAge=3`이다.
- 중국어/Qwen3-ASR 기본 시작점은 `windowSeconds=12`, `stepSeconds=1`, `sentenceFinalizeAge=3`이다.
- 30초 window는 장문 안정성에는 유리할 수 있지만 final script 갱신 지연과 긴 문장 확정 비용이 커질 수 있다.

### 주요 기본값 변경

| 축 | 기본값/정책 변화 | 사유 |
| --- | --- | --- |
| 언어별 runtime | active/global 값보다 `stepSeconds{Lang}`, `windowSeconds{Lang}`, `sentenceFinalizeAge{Lang}`를 기준으로 정리 | 영어/한국어와 중국어의 적정 window가 달라 단일 기본값으로 품질을 맞추기 어려웠기 때문이다. |
| 영어/한국어 window | `windowSecondsEn=7`, `windowSecondsKo=7` | `faster-whisper + large-v3`에서 실시간성과 문장 안정성의 균형점으로 판단했다. |
| 중국어 window | `windowSecondsZh=12`를 시작점으로 설정 | 30초 window의 안정성은 인정하되 final 갱신 지연이 커서 운영 시작점은 낮췄다. |
| step | `stepSecondsEn/Ko/Zh=1` | 화면 갱신성과 STT 처리량이 모두 감당 가능한 범위로 관측됐다. |
| 확정 age | `sentenceFinalizeAgeEn/Ko/Zh=3` | 2회 확정보다 premature final을 줄이고, 4회 이상보다 지연을 낮추는 균형점이다. |
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

## 남은 실험 과제

- 동일 입력 replay 기반으로 `faster-whisper`, `qwen3-asr-0.6b`, 과거 FunASR 기준선을 비교한다.
- 중국어 `windowSeconds=12/16/20/24/30`의 raw STT 안정성과 final 지연을 같은 입력에서 비교한다.
- 중한 번역은 STT/확정 품질과 분리된 평가셋으로 NLLB, M2M100, 더 큰 NLLB 모델을 비교한다.
- `translation_quality` 회귀 샘플을 늘려 고유명사, 서비스명, 구어체 오역을 추적한다.
- 정답 전사 코퍼스가 준비되면 한국어/중국어는 CER, 영어는 WER를 추가한다.
- Qwen3-ASR vLLM streaming은 공유 `.venv`가 아니라 격리 런타임 설계가 준비된 뒤 다시 검토한다.
