# 2026-06-17 받아쓰기 AI 확정 미처리 케이스 수집

## 수집 범위

- 로그 파일: `.tmp/logs/avc-whisper.log.2`, `.tmp/logs/avc-whisper.log.1`, `.tmp/logs/avc-whisper.log`
- 시간 범위: `2026-06-16 23:57:00`부터 `2026-06-17 00:27:00`까지 약 30분
- 실행 조건: 중국어 실시간 경로, `window=15.0`, `step=1.0`, `beam=3`, `maxNewTokens=192`

## 집계 요약

| 항목 | 관측 수 | 해석 |
| --- | ---: | --- |
| `completed=1 final=0` 후보 중 문장 경계/안정성 신호가 있는 케이스 | 1363 | 단순 raw 관측 수이며, 모두 결함은 아니다. stage 생명주기상 보류/교체/품질 차단이 섞여 있다. |
| `staged_age>=2`인 revision | 194 | age가 쌓인 뒤에도 표현 변화로 confirmation이 1/3에 머무르는 대표 미처리 후보군이다. |
| `stage 미확정 교체` | 164 | 이전 staged 후보가 final로 가지 못하고 다음 후보로 교체된 케이스다. |
| stage 후보 품질 차단 | 229 | `spaced_cjk`, `cjk_internal_gap`, `no_end_marker` 등으로 의도적으로 final 처리하지 않은 케이스다. |
| 품질 위험 final | 12 | short/spaced/internal-gap CJK가 final로 들어간 케이스다. 미처리보다 품질 게이트 누락 문제로 분류한다. |

## 대표 케이스

> 이 문서의 대표 케이스는 로그 당시 관측된 실패/차단 사례다. 성능 추적 테스트로 옮길 때는 raw 문장 하나가 현재 함수에서 성공하는지만 보지 않고, 실패 원인인 confirmation reset, staged age, replacement, 품질 gate 조건을 함께 기록한다. 이 케이스들은 로직 튜닝 근거로 쓰는 성능 지표이며, 개별 케이스가 무조건 성공해야 한다는 품질 게이트가 아니다.

### C1. age 누적 뒤에도 revision reset으로 미처리

| 항목 | 값 |
| --- | --- |
| 시간/chunk | `2026-06-17 00:22:53`, chunk `521`~`524` |
| 증상 | `staged_age`가 `1 -> 4`까지 누적됐지만 `confirmations=1/3`으로 계속 reset되고 `final=0`이 유지됐다. |
| 후보 | `远方忽远忽近` -> `远方忽远忽近它` -> `远方忽远忽近他在放` -> `远方忽远忽近它在发亮` |
| 근거 | 각 chunk에 `boundary_end_marks>=1`, `completed=1`, `stage_revision_confirmation_reset=1`, `raw_without_final=1`이 반복된다. |
| 판단 | 문장형으로 닫힌 후보가 보이지만 STT 재표현이 계속 바뀌어 confirmation이 누적되지 않는다. age 기준 확정이 필요하지만 품질 게이트도 함께 필요하다. |

### C2. age 누적 뒤 품질 위험 final로 잘못 처리

| 항목 | 값 |
| --- | --- |
| 시간/chunk | `2026-06-17 00:22:57`, chunk `525` |
| 증상 | chunk `521`~`524`의 미처리 후보가 다음 교체 시 `replaced_aged`로 final 처리됐지만, 출력이 글자 단위 공백 조각이었다. |
| final text | `远 方 忽 远 忽` |
| 품질 flag | `short_cjk,cjk_internal_gap,no_end_marker` |
| 판단 | 확정 미처리 보완만 하면 품질 위험 후보가 final로 들어갈 수 있다. age/replacement final에도 품질 게이트가 필요하다. |

### C3. 안정 신호가 강하지만 `final=0`

| 항목 | 값 |
| --- | --- |
| 시간/chunk | `2026-06-17 00:19:53`, chunk `341` |
| 증상 | `stable_token_ratio=0.852`, `boundary_end_marks=7`, `boundary_right_context=6`, `staged_age=2`인데 `final=0`이다. |
| staged tail | `对啊这个很棒好推荐大家一定要来` |
| 판단 | common-prefix 안정성이 강하고 문장 경계가 충분하지만 `confirmations=1/3`이라 final이 보류됐다. 테스트에서는 단일 문장 함수 호출만으로 성공 여부를 보지 않고, 낮은 confirmation과 누적 age가 함께 있을 때만 final 가능해야 한다. |

### C4. 문장형 후보가 단일 관측 교체로 미처리

| 항목 | 값 |
| --- | --- |
| 시간/chunk | `2026-06-17 00:21:53`, chunk `462` |
| 증상 | 이전 staged 후보가 `staged_confirmations=1`, `staged_age=1`에서 `unconfirmed_cjk`로 교체되어 final 처리되지 않았다. |
| staged tail | `前进，没有方向，逃不出去。你为是我的决心，还是我自己，此生此刻依然好奇。我幸福中。` |
| candidate tail | `自己怎生怎可以燃好奇？幸福中就会抵达，越过彷徨来到身旁，转身看见。` |
| 판단 | 단일 관측 교체는 계속 보류하는 것이 맞다. 다만 이 패턴이 반복될 때는 age가 누적될 수 있어야 한다. |

### C5. 의도적 미처리: stage 후보 품질 차단

| 항목 | 값 |
| --- | --- |
| 시간/chunk | `2026-06-17 00:24:53`, chunk `641` |
| 증상 | completed 후보가 있었지만 `spaced_cjk,cjk_internal_gap,no_end_marker`로 stage 진입 전 차단됐다. |
| candidate tail | `...票 都 超 贵 的 大 家 就 是 都 要 心 里 准 备 但 是 呢 没 关 系 我 们 想 要 去 拍 好 看 的 东 西 给 大 家 然 后 呢 我 们 这 次 呢 会 拍` |
| 판단 | 확정 미처리가 아니라 의도적 품질 차단이다. 이 경로는 유지해야 한다. |

## 반영된 보완

- revision으로 같은 staged lifecycle이 유지될 때 `staged_age`를 누적한다.
- CJK 후보는 첫 관측 확정을 계속 막되, 2회 이상 관측되거나 age 기준을 채우면 `stable_cjk` 또는 `aged` 사유로 final 승격할 수 있게 한다.
- age/replacement final에도 `short_cjk`, `spaced_cjk`, `cjk_internal_gap`, `cjk_repeated_ngram`, `latin_only_for_zh` 품질 게이트를 적용한다.
- `stage_age_quality_blocked`를 추가해 age 기준 확정 후보가 품질 게이트에서 차단되는지 추적한다.

## 테스트 반영 원칙

- `tests/eval/dictation_ai/performance_tracking.py`의 수집 케이스는 성공/실패 자체를 품질 게이트로 보지 않는다.
- 벤치 실행 성공은 수집 케이스가 실행되고 tracking rate/gap이 출력됐다는 뜻이다.
- 확정 미처리 케이스는 confirmation reset, staged age 누적, replacement 판단을 함께 넣어 실패 현상을 재현한다.
- 품질 차단 케이스는 final 성공이 아니라 `spaced_cjk`, `cjk_internal_gap`, `short_cjk` 등 차단 사유가 유지되는지를 지표로 기록한다.
- 로그 이후 이미 구현된 보완으로 matched가 올라가는 것은 성능 개선으로 해석한다. 반대로 matched가 낮은 케이스는 다음 파라미터 튜닝과 로직 보완의 근거로 남긴다.

## 다음 검증 기준

- 새 실행 로그에서 `stage_age_quality_blocked`가 관측되는지 확인한다.
- `final_quality_short_cjk`, `final_quality_spaced_cjk`, `final_quality_cjk_internal_gap` 증가가 멈추는지 확인한다.
- `finalized_per_stage_start`가 기존 장기 스냅샷 약 `0.255`보다 높은 수준을 유지하는지 확인한다.
- `stage_replaced_unconfirmed_per_stage_start`가 기존 장기 스냅샷 약 `0.738`보다 낮은 수준을 유지하는지 확인한다.
