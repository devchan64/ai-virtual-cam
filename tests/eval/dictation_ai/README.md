# 받아쓰기 AI 평가 도메인

이 디렉터리는 받아쓰기 AI의 실험, 벤치마크, 논문 근거 관리 도구를 둔다. 앱 런타임 품질관리 유닛테스트가 아니라, 로그 기반 case replay와 논문 evidence package를 관리하기 위한 평가 영역이다.

## 도메인 경계

| 도메인 | 현재 파일 | 역할 |
| --- | --- | --- |
| Benchmark core | `sbd_benchmark.py`, `benchmark/` | 단일 실행 엔트리, 실제 `sat + cuda + float16` SBD replay 실행과 report/runtime contract 생성 |
| Case corpus | `cases/`, `sbd_cases/`, `sbd_representative_cases/` | challenge/representative/structural case 로딩, 검증, 해석 계약 |
| Parameter sweep/evidence | `sweeps/` | 파라미터 sweep 실행, complete evidence report 검증, 논문 표준 summary 생성 |
| Paper audit | `paper/` | 논문 claim scope, 수치, reference, readiness gate 검증 |
| Representative workflow | `representative/` | 운영 로그에서 representative 후보를 뽑고 사람이 검토한 case로 승격 |
| Structural workflow | `structural/` | challenge replay 병목 case를 exploratory structural preflight subset으로 선정 |
| Tool contract tests | `tool_tests/` | 위 평가 도구의 입출력 계약 테스트. 성능 근거가 아니다. |

## 배치 규칙

- `tests/eval/dictation_ai/` 루트에는 `sbd_benchmark.py` 단일 entrypoint만 둔다.
- 구현 코드는 `benchmark/`, `cases/`, `sweeps/`, `paper/`, `representative/`, `structural/` 중 하나에 둔다.
- 새 보조 모듈이나 실행 스크립트는 루트에 추가하지 않는다. 필요하면 하위 도메인 모듈을 만들고 `sbd_benchmark.py` subcommand에 연결한다.
- `tool_tests/`는 평가 도구의 계약 테스트만 둔다. 앱 코드 품질관리 유닛테스트는 `tests/unit/`에 둔다.
- benchmark 성능 근거는 `tool_tests` 통과가 아니라 `sbd_benchmark.py`를 실제 `sat + cuda + float16`로 실행한 report만 사용한다.
- challenge replay, representative replay, structural preflight 결과를 같은 표로 합치지 않는다. corpus role과 evidence protocol이 다르면 별도 해석한다.

## 단일 엔트리

기본 benchmark는 기존처럼 실행한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py --cases tests/eval/dictation_ai/sbd_cases
```

보조 작업은 같은 엔트리의 subcommand로 실행한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py commands
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py validate-cases --help
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py run-sweep --help
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py paper-readiness --help
```

새 코드에서 import할 때는 루트가 아니라 하위 도메인 경로를 사용한다. 예를 들어 paper readiness 구현은 `tests.eval.dictation_ai.paper.audit_paper_readiness`에서 가져온다.
