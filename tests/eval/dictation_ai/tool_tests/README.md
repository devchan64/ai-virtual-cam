# 받아쓰기 AI 벤치 주요 기능 테스트

이 디렉터리는 `tests/eval/dictation_ai/sbd_benchmark.py`로 실행되는 SBD 벤치의 주요 기능 테스트만 둔다.

여기 있는 테스트는 앱 런타임 품질을 보장하는 유닛테스트가 아니다. 검증 범위는 다음에 한정한다.

- SBD benchmark entrypoint와 subcommand dispatch
- challenge replay case 로딩과 검증
- `chunks` 기반 `expected_final` 재생성
- benchmark report의 핵심 summary 산출
- parameter sweep 실행 계획과 summary 산출

앱 코드의 품질관리 유닛테스트는 `tests/unit/`에 둔다. 실제 SBD 성능 근거는 이 디렉터리의 테스트가 아니라 `tests/eval/dictation_ai/sbd_benchmark.py`를 `sat + cuda + float16`로 실행한 결과만 사용한다.
