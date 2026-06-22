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
- structural preflight는 앱 lifecycle 병목을 보기 위한 도구이므로 `expected_final` 정의 품질 review 후보와 replay 입력 근거가 일부만 있거나 약한 후보를 기본적으로 제외한다. case 정의 문제를 일부러 보려면 `--expected-quality include` 또는 `only`, 입력 근거 문제를 보려면 `--input-evidence include` 또는 `weak-only`를 명시한다.

## 단일 엔트리

기본 benchmark는 기존처럼 실행한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py --cases tests/eval/dictation_ai/sbd_cases
```

보조 작업은 같은 엔트리의 subcommand로 실행한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py commands
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py validate-cases --help
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py audit-initial-final-context --help
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py run-sweep --help
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py paper-readiness --help
```

중간 스트림에서 시작한 challenge case가 이전 final/committed 상태 없이 재생되는지 확인할 때는
`audit-initial-final-context`에 CUDA benchmark report를 함께 넘긴다.
이 감사는 `initial_final` 보정 후보와 함께 같은 `expected_final`이 여러 sliding-window case에 반복 등록된 그룹,
case 내부의 중복/포함 expected 문장, replay 입력 chunks에서 근거가 약한 expected도 케이스 정의 검토 신호로
출력한다. 출력은 자동 삭제 규칙이 아니라 사람이 로그 근거와 lifecycle 차이를 보고 정리할 후보 목록이다.
기본 CUDA report의 `case_definition_action_summary`도 같은 목적의 감사 신호다. 이 요약은
`initial_final` 보정, raw STT에서 관측되지 않은 expected 재작성, fragment expected 재작성,
shifted-window 반복 그룹 정리, 수동 문장 경계 검토를 분리해서 보여준다. 앱 로직 튜닝 근거는 먼저 `strict_logic_candidate_summary`와
`clean_low_bottleneck_intersection_summary`를 본다. 두 요약은 모든 `expected_final`이 replay 입력에서
확인되고 raw STT text로 관측되는 케이스를 기준으로 해석한다.
`validate-cases`의 `input_unsupported_case_count`는 `expected_final`이 replay 입력에서 충분히
지지되지 않는 케이스 수다. `input_unobserved_case_count`는 충분한 unit coverage가 있어도
`expected_final`이 raw STT text 그대로 관측되지 않는 케이스까지 포함한다.
`case_definition_action_summary.evidence_disposition_counts`는 action을 두 부류로 다시 묶는다.
`exclude_from_logic_tuning_until_fixed`는 window/label/initial state가 고쳐지기 전까지 앱 로직
성능 근거에서 제외할 케이스다. `manual_review_before_deduplicate`는 입력 근거는 충분하지만
shifted-window 반복이므로 distinct lifecycle failure가 있는지 사람이 확인할 케이스다.
`case_definition_action_summary`의 우선순위는 다음과 같다.

1. `remove_or_recut_expected_outside_replay_input`: `expected_final`이 replay chunks에 충분히 없으므로 제거하거나 window/label을 다시 잡는다.
2. `rewrite_expected_final_to_observed_stt_text`: `expected_final`이 유사 unit으로는 커버되지만 raw STT text로 관측되지 않으므로 STT 출력 기준으로 label을 다시 쓴다.
3. `add_initial_final_or_recut_mid_stream_case`: 중간 스트림 시작 후보이므로 이미 확정됐어야 할 prefix를 `initial_final`로 옮기거나 시작점을 조정한다. 입력 chunk 또는 actual final에서 expected 앞의 완결 prefix가 보이면 이 검토 대상으로 분류한다.
4. `restore_source_log_or_recut_from_observed_log`: source trace가 없는 이관 케이스는 원 로그 근거를 복원하거나 관측 로그에서 다시 자른다.
5. `rewrite_expected_final_to_final_sentence_boundary`: final-only 번역 큐 기준의 완성 문장으로 expected를 다시 쓴다.
6. `extend_replay_tail_or_reclassify_staged_expectation`: expected의 terminal suffix가 replay 종료 시점에 staged/pending으로 남아 있으면 tail을 늘리거나 final expectation에서 분리한다.
7. `deduplicate_or_justify_shifted_window_repeat`: 같은 expected 묶음이 반복된 case는 distinct lifecycle failure가 있는 경우만 남긴다.
8. `manual_boundary_review`: nested boundary, label boundary, 또는 높은 recall이지만 actual final이 더 잘게 나뉜 boundary granularity 케이스는 사람이 경계를 다시 판단한다.

이 action에 걸린 case는 앱 로직 성능 저하로 해석하지 않는다. 로직 튜닝 후보는 action summary의
`logic_tuning_candidate_count`와 clean/strict 요약을 기준으로 좁힌다.
벤치 stdout의 `case_definition_review`, `logic_tuning_candidates`, `strict_logic_candidates`,
`strict_final_f1_avg`는 전체 challenge 점수와 앱 로직 튜닝 후보 점수를 즉시 구분하기 위한 확인값이다.
파라미터 변경이나 앱 로직 변경의 유효성은 전체 `final_f1_avg`보다 strict 후보 요약을 먼저 비교한다.
`final_boundary_f1_avg`는 문장 boundary offset을 엄격하게 비교하는 보조 지표다. final 문장 유사도와
순서가 충분히 맞아도 STT 표기 차이, punctuation 차이, label boundary 차이 때문에 0점이 될 수 있다.
이 경우 report의 `boundary_zero_high_final_summary`를 같이 확인한다. 여기에 잡힌 케이스는 먼저
metric sensitivity 또는 label boundary 검토 대상으로 보고, 곧바로 앱 로직 실패로 보지 않는다.
`boundary_granularity_summary`는 expected content recall은 높지만 actual final이 expected보다 더 잘게
나뉘어 boundary 점수가 낮은 케이스를 보여준다. 이 케이스는 missing-final 병목이 아니라 label boundary
또는 허용 가능한 과분할 여부를 먼저 검토한다.
`staged_queue_residue_summary.top_active_or_pending_residue_cases`는 queue가 비어 있어도 active staged
또는 pending tail이 남은 케이스를 보여준다. 여기서 `final_f1`이 이미 높은 케이스는 다음 chunk에서
소비될 tail 또는 label/metric 해석 문제일 수 있으므로, 낮은 `final_f1`과 높은 quality/revision metric이
같이 보이는 케이스부터 앱 lifecycle 병목 후보로 검토한다. expected의 마지막 구간이 active staged/pending
tail로 남아 있으면 `extend_replay_tail_or_reclassify_staged_expectation`으로 분류되며, 이 상태에서는 앱
로직 튜닝 후보에서 제외한다.

앱 lifecycle 병목만 따로 재생할 때는 `select-structural-cases`를 사용한다. 기본값은
case-definition review action이 없는 케이스, `source_log/source_chunk`가 있는 케이스,
expected-quality flag가 없는 케이스, replay input evidence가 충분하고 raw STT text로 관측되는
케이스만 고른다.
이 subset은 paper evidence가 아니라 다음 로직 튜닝 후보를 좁히는 exploratory preflight다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py select-structural-cases \
  .tmp/eval/dictation-ai-sbd/current-20260623-case-health-trace-report.json \
  --case-output .tmp/eval/dictation-ai-sbd/clean-structural-preflight-cases.jsonl \
  --markdown-output .tmp/eval/dictation-ai-sbd/clean-structural-preflight-cases.md

./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py validate-cases \
  .tmp/eval/dictation-ai-sbd/clean-structural-preflight-cases.jsonl \
  --require-expected-final \
  --require-source-trace \
  --require-input-evidence \
  --require-observed-input-evidence
```

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py audit-initial-final-context \
  tests/eval/dictation_ai/sbd_cases \
  --benchmark-report .tmp/eval/dictation-ai-sbd/current-20260622-short-cjk-hold-0-default.json \
  --summary-output .tmp/eval/dictation-ai-sbd/case-definition-action-audit.json \
  --action-output .tmp/eval/dictation-ai-sbd/case-definition-action-items.jsonl
```

`--summary-output`은 action별 개수와 제한된 예시를 저장한다. `--action-output`은 정리 대상
전체를 JSONL로 저장한다. 이 JSONL은 대량 삭제 명령이 아니라 recut, `initial_final` 보정,
raw STT 기준 expected 재작성, 반복 case 정당화 여부를 사람이 검토하기 위한 작업 목록이다.

로그 기반 감사는 패치 전후가 섞이지 않도록 시간 구간을 명시할 수 있다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py representative-sources \
  .tmp/logs \
  --since "2026-06-21 12:02:00" \
  --until "2026-06-21 12:04:00" \
  --compact
```

새 코드에서 import할 때는 루트가 아니라 하위 도메인 경로를 사용한다. 예를 들어 paper readiness 구현은 `tests.eval.dictation_ai.paper.audit_paper_readiness`에서 가져온다.
