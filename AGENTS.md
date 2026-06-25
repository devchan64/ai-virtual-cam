# AGENTS.md

## 커밋 메시지 규칙

- 모든 커밋 메시지는 **컨벤셔널 커밋(Conventional Commits)** 형식을 따른다.
- 모든 커밋 메시지는 **한글**로 작성한다.

### 형식

`<type>: <한글 요약>`

예시:

- `feat: 맥용 CMIO 설정 자동 생성 추가`
- `fix: setup에서 Xcode 경로 검증 오류 수정`
- `chore: 문서의 단일 진입점 안내 정리`

### 권장 type

- `feat`
- `fix`
- `refactor`
- `docs`
- `test`
- `chore`

## 공통 개발 정책

- 환경 탐지/디바이스 탐색은 기본 동작으로 수행할 수 있으나, 실제 실행 단계에서는 설정값을 우선한다.
- 설정값이 유효하지 않거나 동작 불가할 경우 자동 폴백(대체 장치/포맷/출력 경로 전환) 대신 즉시 예외를 발생시키고 종료한다.
- 성능이나 정확도에 직접 영향을 주는 실행 경로는 Fail-Fast를 우선한다. 예를 들어 GPU/CUDA가 요구되는 기능은 CPU fallback으로 계속 실행하지 않고, 설정값/실패 원인/권장 조치를 출력한 뒤 중지한다.
- `auto` 설정은 탐색 단계에서 후보를 고르는 용도로만 제한한다. 실제 실행에서 `auto`가 더 느리거나 다른 의미의 런타임으로 암묵 전환되어서는 안 된다.
- 에러는 사용자에게 재시도 가능한 정보(설정 값, 실패 원인, 권장 조치)를 함께 출력한다.
- config에서 발생하는 오류는 모달만으로 표시하지 않고 stdout에도 함께 출력한다.
- config의 stdout에는 사용자의 주요 버튼 동작(예: 저장, Serve 시작/중지, 가상 장치 생성/삭제)을 출력한다.
- 소스코드는 파일당 1000라인을 넘지 않도록 한다. 가능하면 500라인 내외로 유지하는 것이 좋다.
- 파일이 커지면 역할별 모듈로 분리하고, 특히 GUI 파일은 탭/위젯/동작 단위로 분할한다.
- 받아쓰기 AI의 문장 경계/중복 확정 문제는 케이스별 정규식 또는 언어별 ad-hoc 규칙 추가로 해결하지 않는다. 다국어 모델 기반 sentence boundary detector와 revision lifecycle 개선을 우선한다.
- `regex` 기반 문장 분할은 운영/설정 시나리오에서 폐기한다. 남아 있는 legacy helper는 과거 회귀 테스트 보존용이며 새 기능, 기본값, 비교 기준선으로 사용하지 않는다.

## 현재 프로젝트 문맥 요약

- 실행 진입점은 `./bin/avc`이다. `config`는 설정/GUI, `serve`는 저장된 설정 실행만 담당한다.
- 설정 GUI는 탭/위젯/동작 단위로 계속 분리한다. 큰 변경은 기존 `scripts/config/*_tab.py` 패턴을 따른다.
- 사용자 기능 도메인은 큰 축 기준으로 `카메라`와 `오디오`로 구분한다. STT, 문장 추적, 번역, 모델 준비는 오디오의 하위 도메인인 `받아쓰기 AI`로 부른다. Whisper는 받아쓰기 AI의 백엔드/기술명일 뿐 사용자 기능명으로 확대하지 않는다.
- 받아쓰기 AI 전사/번역 창은 config GUI의 `Serve 시작`에서만 열며, 창에는 복사용 STT/번역 결과만 표시한다. 추적 로그는 stdout/stderr에 남긴다.
- 받아쓰기 AI 실시간 경로는 Linux + NVIDIA CUDA 전용이며 CUDA/float16 중심의 Fail-Fast 정책을 따른다. macOS/Windows/CPU 실행은 운영 대안으로 두지 않는다. NLLB 선택 시 Whisper 백엔드는 `task=transcribe`만 수행하고 번역은 NLLB 경로만 사용한다.
- 받아쓰기 AI/설정 GUI 창 위치와 UI 언어는 `setting.json`의 `meta`에 저장한다. README 받아쓰기 AI 문서는 `docs/images/whisper-config-runtime-sample.png` 기준으로 유지한다.

## 문서 배치 정책

- `README.md`는 사용자가 프로젝트를 이해하고 시작하는 엔트리 문서로 유지한다.
- `AGENTS.md`는 AI 에이전트가 따라야 할 작업 규칙, 정책, 프로젝트 문맥을 기록한다.
- 설계안, 디자인 자료, 검토 기록, 운영 실험 기록은 `docs/` 아래에 날짜나 주제가 드러나는 Markdown 문서로 작성한다.
- README에는 상세 설계를 직접 길게 넣지 않고, 필요한 경우 `docs/` 문서를 링크한다.

## 테스트 정책

- 가상 비디오/오디오 장치 동작 계약(생성/상태/삭제)을 변경하는 패치에는 반드시 스펙 테스트를 포함한다.
- `scripts/bin/avc-device`, `scripts/bin/avc-docker`, `scripts/config/create-config-gui.py` 변경 시 `./bin/avc test` 실행 결과를 확인한다.
- 테스트 없이 가상장치 생성/검증 로직의 분기, 기본값, 권한/릴레이 경로를 변경하지 않는다.
- `tests/unit/`은 앱 코드의 품질관리 유닛테스트만 둔다. 받아쓰기 AI 논문/벤치/케이스 관리 도구의 계약 테스트는 `tests/eval/dictation_ai/tool_tests/`에 둔다.
- `tests/eval/dictation_ai/` 루트에는 `sbd_benchmark.py` 단일 평가 entrypoint만 둔다. 새 구현/보조 모듈은 `tests/eval/dictation_ai/README.md`의 도메인 경계를 먼저 확인하고 하위 도메인에 배치한 뒤, 필요하면 `sbd_benchmark.py` subcommand로 연결한다.
- 받아쓰기 AI 로그 기반 challenge replay 케이스의 기존 `tests/eval/dictation_ai/sbd_cases/` corpus는 폐기되었다. 새 challenge replay 입력은 `tests/eval/dictation_ai/sbd_predicted_cases/{en,ko,zh}/`에 두며, 레코드는 `language`, `chunks`, `expected_final`만 가진다. `expected_final`은 SBD 벤치 출력이 아니라 백업 chunks의 반복 token-sentence 근거로 예측한다.
- 일반 운영 평균을 보기 위한 representative corpus는 `.tmp/eval/dictation-ai-sbd/representative-cases/`에 별도로 두고, challenge replay 평균과 섞어 해석하지 않는다.
- 받아쓰기 AI 논문/실험 해석은 `docs/2026-06-21-dictation-ai-experiment-protocol.md`의 corpus 역할, 지표, 파라미터 채택 기준을 따른다.
- 받아쓰기 AI 파라미터 sweep 결과를 논문/실험일지 근거로 정리할 때는 `summary.json`의 `corpus_role`과 `evidence_summary`를 우선 확인하고, full `tag_summary`는 세부 진단용으로 사용한다.
- 받아쓰기 AI SBD 벤치마크는 반드시 실제 `sat + cuda + float16`로만 실행한다. mock/smoke/CPU 벤치는 성능 근거로 사용하지 않는다.
- 받아쓰기 AI SBD 벤치마크와 파라미터 sweep은 캐시된 모델만 사용하도록 `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`을 기본 실행 계약으로 둔다.
- Codex sandbox에서 CUDA 장치가 보이지 않을 수 있으므로, 벤치 실행은 필요 시 승인된 sandbox 밖 실행으로 수행하고 결과 수치를 기록한다.
