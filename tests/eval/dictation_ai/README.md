# 받아쓰기 AI 평가 도메인

이 디렉터리는 받아쓰기 AI의 실험, 벤치마크, 논문 근거 관리 도구를 둔다. 앱 런타임 품질관리 유닛테스트가 아니라, 로그 기반 case replay와 논문 evidence package를 관리하기 위한 평가 영역이다.

## 도메인 경계

| 도메인 | 현재 파일 | 역할 |
| --- | --- | --- |
| Benchmark core | `sbd_benchmark.py`, `sbd_benchmark_report.py`, `sbd_runtime_contract.py` | 실제 `sat + cuda + float16` SBD replay 실행과 report 생성 |
| Case corpus | `sbd_case_loader.py`, `sbd_case_paths.py`, `sbd_diagnostic_tags.py`, `validate_sbd_case_files.py`, `sbd_cases/`, `sbd_representative_cases/` | challenge/representative/structural case 로딩, 검증, 해석 계약 |
| Parameter sweep/evidence | `run_sbd_parameter_sweep.py`, `refresh_sbd_parameter_sweep_summary.py`, `sbd_parameter_sweep_report.py`, `summarize_sbd_evidence_reports.py`, `validate_sbd_evidence_report.py` | 파라미터 sweep 실행, complete evidence report 검증, 논문 표준 summary 생성 |
| Paper audit | `audit_paper_*.py`, `audit_sbd_followup_readiness.py` | 논문 claim scope, 수치, reference, readiness gate 검증 |
| Representative workflow | `audit_sbd_representative_sources.py`, `select_sbd_representative_sources.py`, `extract_sbd_representative_review_packets.py`, `extract_sbd_representative_case_drafts.py`, `promote_sbd_representative_cases.py`, `validate_sbd_representative_review_packets.py` | 운영 로그에서 representative 후보를 뽑고 사람이 검토한 case로 승격 |
| Structural workflow | `select_sbd_structural_cases.py` | challenge replay 병목 case를 exploratory structural preflight subset으로 선정 |
| Tool contract tests | `tool_tests/` | 위 평가 도구의 입출력 계약 테스트. 성능 근거가 아니다. |

## 배치 규칙

- `tests/eval/dictation_ai/` 루트에는 사람이 직접 실행하는 entrypoint script만 둔다.
- 새 보조 모듈을 추가할 때는 기존 도메인에 맞는 하위 디렉터리를 먼저 검토한다. 루트에 새 파일을 추가하려면 명령 진입점이어야 한다.
- `tool_tests/`는 평가 도구의 계약 테스트만 둔다. 앱 코드 품질관리 유닛테스트는 `tests/unit/`에 둔다.
- benchmark 성능 근거는 `tool_tests` 통과가 아니라 `sbd_benchmark.py`를 실제 `sat + cuda + float16`로 실행한 report만 사용한다.
- challenge replay, representative replay, structural preflight 결과를 같은 표로 합치지 않는다. corpus role과 evidence protocol이 다르면 별도 해석한다.

## 후속 정리 방향

현재 루트 script는 과거 실험일지와 논문 프로토콜에서 직접 참조한다. 따라서 즉시 파일 이동보다 다음 순서로 정리한다.

1. 루트 파일을 위 도메인 표 기준으로 유지/분류한다.
2. 새 기능은 가능한 한 도메인 하위 디렉터리로 추가하고, 루트에는 thin entrypoint만 둔다.
3. 문서와 명령 참조를 한 번에 갱신할 수 있을 때 `paper/`, `representative/`, `sweeps/`, `cases/` 같은 하위 패키지로 이동한다.
4. 이동 후에는 legacy wrapper를 짧게 유지하거나 실험일지 명령을 함께 갱신해 재현성을 깨지 않게 한다.
