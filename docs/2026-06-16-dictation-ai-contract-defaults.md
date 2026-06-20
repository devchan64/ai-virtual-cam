# 받아쓰기 AI 계약과 기본값

## 문서 상태

이 문서는 받아쓰기 AI 설정 계약, 허용값, 기본값, 검증 규칙을 정리한다. 실시간 파이프라인 기준은 [받아쓰기 AI 실시간 처리 파이프라인 기준](2026-06-16-dictation-ai-realtime-pipeline.md)을 따르고, 실험 기록은 [받아쓰기 AI 실험일지](2026-06-16-dictation-ai-experiment-log.md)에 둔다. 외부 레퍼런스는 [받아쓰기 AI 참조 레퍼런스 모음](2026-06-16-dictation-ai-reference-index.md)에 둔다.

받아쓰기 AI 설정의 코드 기준 진실 공급원은 `src/domain/contracts/dictation_ai.py`의 `DICTATION_AI_CONTRACT`다. 카메라 기능 enabled 계약은 `src/domain/contracts/camera.py`, 윈도우 지오메트리 저장 키와 파일 계약은 `src/domain/contracts/window_geometry.py`에 분리한다. 이 문서는 그 계약을 운영자가 읽을 수 있는 형태로 풀어쓴다.

## 저장 위치와 호환성

받아쓰기 AI 설정은 `setting.json`의 `dictationAi` 블록에 저장한다. 초기에는 사용 모델이 Whisper였기 때문에 `whisper` 블록으로 시작했지만, 기능이 확장되면서 도메인명과 모델명을 동일하게 두는 것이 오류가 되어 `dictationAi`로 변경했다. 과거 `whisper` 명칭은 사용자 기능명이 아니라 내부 호환 맥락에 남은 기술명으로 취급한다.

기본 원칙:

- 사용자 기능명은 `받아쓰기 AI`다.
- `language`는 `ko`, `en`, `zh` 중 하나여야 하며 `auto`는 허용하지 않는다.
- STT, STT 결과 문장 경계 처리, 실행 파라미터는 STT 인식 언어 기준으로 묶는다.
- 번역 backend/model/device/compute/beam/token은 번역 대상 언어 기준으로 묶는다.
- active 키는 현재 선택 언어/대상 언어의 projection으로 유지한다.
- 설정값이 유효하지 않으면 자동 폴백하지 않고 즉시 실패한다.

## 현재 운영 기본 판단

| 언어 | 현재 STT | 모델 | 운영 판단 |
| --- | --- | --- | --- |
| `ko` | `faster-whisper` | `large-v3` | 현재 사용 중이며 준수한 성능으로 판단한다. |
| `en` | `faster-whisper` | `large-v3` | 현재 사용 중이며 준수한 성능으로 판단한다. |
| `zh` | `qwen3-asr-transformers` | `qwen3-asr-0.6b` | 현재 사용 중이며 준수한 성능으로 판단한다. |

중국어에서 `faster-whisper`는 운영 품질 후보가 아니라 baseline으로 둔다. `qwen3-asr-vllm-streaming`은 계약상 후보로 남아 있지만 공유 `.venv`에서는 vLLM 의존성 충돌 때문에 지원하지 않는다.

## 공통 설정 기본값

| 키 | 기본값 | 허용값/범위 | 의미 |
| --- | --- | --- | --- |
| `enabled` | `false` | boolean | 받아쓰기 AI 실행 여부 |
| `showSttStatusWindow` | `false` | boolean | STT 원문창 표시 여부 |
| `inputDevice` | 환경 탐지값 | non-empty string | STT 입력 장치 |
| `language` | `en` | `ko`, `en`, `zh` | 단일 STT 인식 언어 |
| `task` | `transcribe` | `transcribe`, `translate` | STT task. 외부 번역 backend 사용 시 `transcribe`여야 한다. |
| `device` | `cuda` | non-empty string | STT 실행 장치 |
| `computeType` | `float16` | non-empty string | STT 연산 타입 |
| `postProcessingProfile` | `manual` | `manual` | 후처리 프로필 |

`inputDevice` 기본값은 고정 문자열이 아니다. Linux에서는 사용 가능한 입력 장치 또는 PulseAudio/PipeWire source를 탐지하고, 그 결과가 설정 생성 시 저장된다.

## STT 계약

### 언어별 허용 백엔드

| 언어 | 허용 STT backend |
| --- | --- |
| `en` | `faster-whisper`, `mock` |
| `ko` | `faster-whisper`, `mock` |
| `zh` | `faster-whisper`, `qwen3-asr-transformers`, `qwen3-asr-vllm-streaming`, `mock` |

### 기본 STT 모델

| 키 | 기본값 | 의미 |
| --- | --- | --- |
| `backend` | `faster-whisper` | legacy/global STT backend projection |
| `model` | `large-v3` | legacy/global STT model projection |
| `sttBackendEn` | `faster-whisper` | 영어 STT backend |
| `sttModelEn` | `large-v3` | 영어 STT 모델 |
| `sttBackendKo` | `faster-whisper` | 한국어 STT backend |
| `sttModelKo` | `large-v3` | 한국어 STT 모델 |
| `sttBackendZh` | `qwen3-asr-transformers` | 중국어 STT backend |
| `sttModelZh` | `qwen3-asr-0.6b` | 중국어 STT 모델 |

Qwen 모델 alias:

| 설정값 | 실제 모델 |
| --- | --- |
| `qwen3-asr-0.6b` | `Qwen/Qwen3-ASR-0.6B` |
| `qwen3-asr-1.7b` | `Qwen/Qwen3-ASR-1.7B` |

## 런타임 파라미터 기본값

언어별 키가 기준이다. active 키(`stepSeconds`, `windowSeconds`, `sentenceFinalizeAge`, `beamSize`, `maxNewTokens`, `temperature`)는 현재 선택한 `language`의 언어별 값을 projection한다.

| 언어 | `stepSeconds` | `windowSeconds` | `sentenceFinalizeAge` | `beamSize` | `maxNewTokens` | `temperature` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `en` | `1.0` | `20.0` | `3` | `3` | `192` | `0.0` |
| `ko` | `1.0` | `10.0` | `3` | `3` | `192` | `0.0` |
| `zh` | `1.0` | `15.0` | `2` | `3` | `192` | `0.0` |

legacy/global 기본값:

| 키 | 기본값 | 범위 |
| --- | ---: | --- |
| `chunkSeconds` | `20.0` | `1.0` - `30.0` |
| `stepSeconds` | `2.0` | `0.5` - `5.0` |
| `windowSeconds` | `20.0` | `1.0` - `30.0` |
| `sentenceFinalizeAge` | `3` | `1` - `8` |
| `beamSize` | `3` | `1` - `8` |
| `maxNewTokens` | `192` | `16` - `512` |
| `temperature` | `0.0` | `0.0` - `1.0` |

검증 규칙:

- `stepSeconds`는 `windowSeconds`보다 크면 안 된다.
- 언어별 `stepSeconds{Lang}`도 `windowSeconds{Lang}`보다 크면 안 된다.
- 영어는 `windowSecondsEn=20.0`을 기본값으로 사용한다.
- 한국어는 `windowSecondsKo=10.0`을 기본값으로 사용한다.
- 중국어는 `windowSecondsZh=15.0`을 기본값으로 사용한다.

## 실행 플랫폼/디바이스 계약

받아쓰기 AI는 Linux + NVIDIA CUDA 전용 기능이다. `dictationAi.enabled=false`인 과거 설정 파일은 호환 로딩을 위해 일부 `cpu` 값을 읽을 수 있지만, `dictationAi.enabled=true`인 실제 실행 설정은 다음 조건을 만족해야 한다.

- OS는 Linux여야 한다.
- `dictationAi.device`는 `cuda`여야 한다.
- `dictationAi.sentenceBoundaryDevice`는 `cuda`여야 한다.
- 번역을 켠 경우 active `translationDevice`와 대상 언어별 `translationDeviceEn/Ko/Zh`는 모두 `cuda`여야 한다.
- 전사 창 실행 시 `torch.cuda.is_available()`이 `false`면 자동 CPU fallback 없이 실패한다.

macOS/Windows, CPU 실행, `auto`에서 CPU로 암묵 전환되는 경로는 운영 계약에 포함하지 않는다.

설정 GUI 계약:

- macOS/Windows에서 `./bin/avc config`를 실행하면 받아쓰기 AI 전사, STT 원문창, 번역 창 토글은 모두 OFF로 강제한다.
- 지원하지 않는 호스트에서는 ON으로 전환되는 토글만 비활성화하고, 입력/모델/다운로드 같은 나머지 GUI 조작은 데모용으로 허용한다.
- 저장되는 `dictationAi.enabled`, `translationEnabled`, `showSttStatusWindow`는 `false`로 유지한다.

## STT 결과 문장 경계 처리 계약

| 키 | 기본값 | 허용값/범위 | 의미 |
| --- | --- | --- | --- |
| `sentenceBoundaryBackend` | `sat` | `sat`, `mock` | active/global 문장 경계 backend |
| `sentenceBoundaryModel` | `sat-3l-sm` | non-empty string | active/global 문장 경계 모델 |
| `sentenceBoundaryBackendEn` | `sat` | `sat`, `mock` | 영어 경계 backend |
| `sentenceBoundaryModelEn` | `sat-3l-sm` | non-empty string | 영어 경계 모델 |
| `sentenceBoundaryBackendKo` | `sat` | `sat`, `mock` | 한국어 경계 backend |
| `sentenceBoundaryModelKo` | `sat-3l-sm` | non-empty string | 한국어 경계 모델 |
| `sentenceBoundaryBackendZh` | `sat` | `sat`, `mock` | 중국어 경계 backend |
| `sentenceBoundaryModelZh` | `sat-3l-sm` | non-empty string | 중국어 경계 모델 |
| `sentenceBoundaryDevice` | `cuda` | `cuda`, `cpu` | 경계 모델 실행 장치. enabled 실행 시 `cuda` 필수 |
| `sentenceBoundaryComputeType` | `float16` | `float16`, `float32` | 경계 모델 연산 타입 |

운영 계약:

- regex 기반 문장 분할은 운영/설정 시나리오에서 사용하지 않는다.
- SBD 결과는 final 결정자가 아니라 staged 후보 생성기다.
- final 확정은 `sentenceFinalizeAge`와 revision lifecycle이 담당한다.

## 번역 계약

### 공통 active 기본값

| 키 | 기본값 | 허용값/범위 | 의미 |
| --- | --- | --- | --- |
| `translationEnabled` | `false` | boolean | 번역 창/번역 경로 활성화 |
| `translationTargetLanguage` | `ko` | `en`, `ko`, `zh` | 번역 대상 언어 |
| `translationBackend` | `nllb-transformers` | `whisper`, `nllb-transformers`, `m2m100-transformers`, `mock` | active 번역 backend |
| `translationModel` | `facebook/nllb-200-distilled-600M` | backend별 모델 목록 | active 번역 모델 |
| `translationDevice` | `cuda` | `cuda`, `cpu` | active 번역 장치. enabled 실행 시 `cuda` 필수 |
| `translationComputeType` | `float16` | `float16`, `float32` | active 번역 연산 타입 |
| `translationBeamSize` | `1` | `1` - `8` | 번역 beam |
| `translationMaxNewTokens` | `128` | `16` - `512` | 번역 최대 토큰 |

### 대상 언어별 기본값

| 대상 언어 | backend | model | device | compute | beam | max tokens |
| --- | --- | --- | --- | --- | ---: | ---: |
| `en` | `whisper` | 빈 문자열 | `cuda` | `float16` | `1` | `128` |
| `ko` | `nllb-transformers` | `facebook/nllb-200-distilled-600M` | `cuda` | `float16` | `1` | `128` |
| `zh` | `m2m100-transformers` | `facebook/m2m100_1.2B` | `cuda` | `float16` | `1` | `128` |

### 번역 backend 모델 목록

| backend | 지원 대상 | 모델 |
| --- | --- | --- |
| `whisper` | `en` | 모델 문자열 없음. Whisper 내장 translate 경로 |
| `nllb-transformers` | `en`, `ko`, `zh` | `facebook/nllb-200-distilled-600M`, `facebook/nllb-200-distilled-1.3B`, `facebook/nllb-200-1.3B`, `facebook/nllb-200-3.3B` |
| `m2m100-transformers` | `en`, `ko`, `zh` | `facebook/m2m100_1.2B` |
| `mock` | `en`, `ko`, `zh` | 모델 문자열 없음 |

검증 규칙:

- 번역이 켜져 있으면 backend는 현재 STT 언어를 source로 지원해야 한다.
- 번역 대상 언어는 선택 backend가 지원해야 한다.
- `whisper` 번역 backend는 대상 언어가 `en`일 때만 허용한다.
- `nllb-transformers`, `m2m100-transformers` 사용 시 `task`는 `transcribe`여야 한다.
- `nllb-transformers`, `m2m100-transformers` 사용 시 `translationModel`은 비어 있으면 안 된다.
- `nllb-transformers`, `m2m100-transformers` 사용 시 번역 장치는 `cuda`여야 한다.
- 번역은 final transcript만 입력으로 받는다. staged/partial 후보는 번역하지 않는다.
- final transcript가 `latin_only_for_zh`, `mixed_latin_zh`, `short_cjk`, `no_end_marker`, `spaced_cjk`, `cjk_repeated_ngram` 품질 플래그를 가지면 번역 큐에 넣지 않는다. 전사 출력은 보존하되 번역 오염을 막기 위한 계약이다.

## 모델 준비와 실행 순서

Serve 시작 전 모델 캐시 검사 대상:

1. 현재 설정에 적용된 STT 모델
2. 언어별 STT 모델 묶음
3. 현재 설정에 적용된 STT 결과 문장 경계 처리 모델
4. 언어별 STT 결과 문장 경계 처리 모델 묶음
5. 현재 설정에 적용된 번역 모델
6. 대상 언어별 번역 모델 묶음

실행 순서:

1. 설정을 읽고 `dictationAi` 계약을 검증한다.
2. STT/문장 경계/번역 모델 캐시를 확인한다.
3. 누락 또는 부분 다운로드 상태가 있으면 Serve를 시작하지 않는다.
4. 모델 로딩이 끝난 뒤 입력 장치를 연다.
5. raw STT window를 생성한다.
6. 문장 경계 후보와 revision lifecycle을 거쳐 final transcript를 확정한다.
7. 번역이 켜져 있으면 final transcript만 번역 큐에 넣는다.

## Fail-Fast 조건

다음 조건은 자동 대체 없이 실패해야 한다.

- `dictationAi.inputDevice`가 비어 있다.
- `dictationAi.enabled=true`인데 OS가 Linux가 아니다.
- `dictationAi.enabled=true`인데 STT/STT 결과 문장 경계 처리/번역 실행 장치가 `cuda`가 아니다.
- `language`가 `ko`, `en`, `zh` 중 하나가 아니다.
- 언어별 STT backend가 해당 언어의 허용 목록에 없다.
- 언어별 STT model이 비어 있다.
- `stepSeconds > windowSeconds`다.
- `sentenceBoundaryModel` 또는 언어별 sentence boundary model이 비어 있다.
- 번역 backend/model/target 조합이 계약에 맞지 않는다.
- 외부 번역 backend 사용 시 번역 장치가 `cuda`가 아니다.
- `qwen3-asr-vllm-streaming`을 공유 `.venv`에서 실행하려 한다.
- CUDA/float16이 요구되는 경로에서 CUDA 또는 모델 캐시가 준비되지 않았다.

## GUI와 stdout 계약

- config GUI는 현재 선택한 STT 언어의 STT/문장 경계/런타임 묶음만 편집 대상으로 보여준다.
- 번역 설정은 현재 선택한 번역 대상 언어의 묶음을 보여준다.
- 언어를 바꾸면 이전 언어 값은 메모리에 보존되고, `JSON 저장` 시 언어별 키로 함께 저장한다.
- `JSON 저장`, `Serve 시작`, `Serve 중지`, 가상 장치 생성/삭제 같은 주요 버튼 동작은 stdout에 출력한다.
- config 오류는 모달만으로 표시하지 않고 stdout에도 출력한다.

## 관련 코드

- 계약 정의: `src/domain/contracts/dictation_ai.py`
- 카메라 기능 계약: `src/domain/contracts/camera.py`
- 윈도우 지오메트리 계약: `src/domain/contracts/window_geometry.py`
- 설정 파싱/검증: `src/domain/config.py`
- 기본값 export: `src/domain/dictation_ai_defaults.py`
- GUI 탭: `scripts/config/dictation_ai_tab.py`
- 설정 저장: `src/tools/config_builder.py`
- 모델 캐시 검사/다운로드: `scripts/setup/download-dictation-ai-models.py`
- 계약 테스트: `tests/unit/test_dictation_ai_contract.py`
