# 받아쓰기 AI 실험 도구 테스트

이 디렉터리는 `tests/eval/dictation_ai/` 아래의 논문, 벤치마크, 케이스 관리 도구에 대한 계약 테스트를 둔다.

여기 있는 테스트는 앱 런타임 품질을 보장하는 유닛테스트가 아니다. 검증 범위는 다음에 한정한다.

- SBD benchmark report와 parameter sweep summary의 스키마/해석 계약
- challenge replay, representative, structural case 파일 검증 규칙
- 논문 claim scope, evidence number, reference scope, readiness audit 계약
- representative source, review packet, case draft/promote 도구의 입출력 계약

앱 코드의 품질관리 유닛테스트는 `tests/unit/`에 둔다. 실제 SBD 성능 근거는 이 디렉터리의 테스트가 아니라 `tests/eval/dictation_ai/sbd_benchmark.py`를 `sat + cuda + float16`로 실행한 결과만 사용한다.
