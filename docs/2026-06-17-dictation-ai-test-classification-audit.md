# 2026-06-17 받아쓰기 AI 테스트 분류 감사

## 문제

받아쓰기 AI 테스트에는 운영 로그에서 수집한 케이스가 많이 들어 있다. 일부는 실제 불변 계약을 검증하는 hard regression이지만, 일부는 모델 출력 분포와 파라미터 튜닝에 따라 성공률을 봐야 하는 성능 추적 케이스다. 이 둘이 섞이면 성능 테스트가 품질 게이트처럼 동작하고, 반대로 실제 안전 회귀를 느슨하게 만들 위험이 있다.

## 분류 기준

### 하드 품질 게이트

다음 조건을 만족할 때만 일반 unit test의 `assert*`로 둔다.

- 설정 계약, default, validation, UI 저장/복원처럼 입력과 출력이 결정적이다.
- 중복 final 억제, final-only 번역, 명백한 품질 오염 차단처럼 사용자 출력 오염을 막는 안전 정책이다.
- 로그에서 출발했더라도 최소 입력으로 축소되어 모델 출력 분포와 무관하다.
- 실패하면 로직 계약이 깨진 것으로 볼 수 있다.

### 성능 추적 벤치마크

다음 조건이면 `tests/eval/dictation_ai/sbd_text_cases.sample.jsonl`에 케이스를 누적하고 `tests/eval/dictation_ai/sbd_benchmark.py`로 실행한다.

- 5분/30분 로그 집계, rate, gap, per-stage-start 같은 추세 지표다.
- raw STT 흔들림, stage churn, replacement churn, finalization latency를 관측한다.
- 현재는 실패할 수 있고, 다음 개선으로 matched rate가 오르는지 봐야 한다.
- 파라미터 튜닝 근거로 쓰는 케이스다.

## 현재 감사 결과

| 영역 | 현재 상태 | 판단 |
| --- | --- | --- |
| `tests/eval/dictation_ai/performance_tracking.py` | 폐기 | SBD 생명주기와 별도로 rate/gap을 관리해 실제 운영 파이프라인 개선 근거로 보기 어렵다. |
| `tests/eval/dictation_ai/sentence_revision_tracking.py` | 폐기 | helper assertion 모음에 가까워 벤치로서 의미가 낮다. 로그 기반 케이스는 SBD JSONL로 흡수한다. |
| `test_dictation_ai_transcript_delta.py` | 폐기 | SBD 생명주기 벤치와 분리된 helper assertion으로 남아 있어 현재 품질 판단 기준에서 제외한다. |
| `test_dictation_ai_sentence_boundary.py` | 폐기 | soft boundary 결과를 hard assert로 고정해 운영 SBD 벤치 기준과 맞지 않는다. |
| `test_dictation_ai_repeat_collapse.py` | collapse 결과를 hard assert로 고정한다. | 사용자 출력 오염 방지 계약은 유지하되, 언어별/로그별 tuning 샘플은 tracking 후보로 본다. |

## 정리 원칙

- 새 로그 수집 케이스는 기본적으로 SBD JSONL 케이스에 추가한다.
- 일반 unit test에 로그 케이스를 추가하려면 주석에 `hard regression` 성격을 명시한다.
- hard regression에서 성능 지표로 성격이 바뀐 케이스는 삭제하지 말고 performance tracking 벤치로 먼저 복제한 뒤, 다음 패치에서 unit assert를 제거한다.
- tracking rate가 낮아도 품질 게이트 실패로 만들지 않는다. 낮은 rate는 개선 backlog와 파라미터 튜닝 근거다.

## 우선 이관 후보

1. `test_dictation_ai_repeat_collapse.py`의 언어별 반복 collapse 샘플 중 출력 오염 안전 계약이 아닌 케이스

이관은 한 번에 대량 수행하지 않는다. 각 이관 패치에서 기존 hard assert가 어떤 tracking domain으로 이동했는지 문서화하고, tracking rate 변화를 확인한다.

## 2026-06-17 정리 결과

다음 hard unit test는 중요도가 낮은 품질 게이트로 판단해 제거했다.

- `test_dictation_ai_sentence_revision.py`의 로그 기반 revision/age/finalization 샘플을 일시적으로 `tests/eval/dictation_ai/sentence_revision_tracking.py`로 이동했으나, 이후 벤치로서 의미가 낮다고 판단해 폐기
- `test_dictation_ai_sentence_boundary.py`의 legacy soft boundary 로그 샘플
- `test_dictation_ai_repeat_collapse.py`의 특정 로그 문장 기반 collapse 샘플 일부
- `test_dictation_ai_sentence_forcing.py`, `test_dictation_ai_stable_token_detection.py`, `test_dictation_ai_transcript_delta.py`, `test_dictation_ai_window_geometry.py`의 helper/GUI 상태 중심 샘플

유지한 hard gate 범위:

- 설정/계약/default 검증
- final-only 번역, 중복 final/echo 억제, 명백한 품질 오염 차단
- 결정적 helper의 최소 계약
- CJK repeated n-gram, spaced CJK, recent echo처럼 사용자 출력 오염을 직접 막는 안전 정책

이후 로그에서 새로 발견한 stage churn, finalization latency, soft boundary, collapse 튜닝 케이스는 일반 unit test나 별도 helper tracking 파일이 아니라 SBD JSONL 케이스에 추가한다.
