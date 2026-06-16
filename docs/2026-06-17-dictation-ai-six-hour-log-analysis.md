# 2026-06-17 받아쓰기 AI 6시간 로그 분석

## 범위

- 로그 파일: `.tmp/logs/avc-whisper.log*`
- 분석 시간: `2026-06-17 00:25:27`부터 `2026-06-17 06:25:27`까지 6시간
- 대상: `Dictation AI` 로그
- 총 로그 라인: 152,868
- 문장 진단 라인: 20,943
- 성능 라인: 20,943

## 요약

계산 처리량은 주 병목이 아니다. 6시간 동안 `input_queue_drops_total=0`이 유지됐고, 평균 `total_step_load`는 약 `0.458`이었다. 다만 순간 queue peak는 최대 `75`까지 관측되어 짧은 STT 지연 spike는 존재한다.

품질 병목은 확정 생명주기와 품질 차단에 있다. completed 후보 18,763개 중 final은 1,177개로 약 `6.3%`다. `completed=1 final=0` 진단은 17,589회로, 대부분은 stage 후보 품질 차단, 미확정 교체, revision reset, 중복 억제 상태가 섞여 있다.

## 핵심 지표

| 항목 | 값 |
| --- | ---: |
| `stt_raw` | 19,920 |
| `diag` | 20,943 |
| completed 후보 총합 | 18,763 |
| final 총합 | 1,177 |
| completed 대비 final 비율 | 0.063 |
| `completed=1 final=0` | 17,589 |
| `stage_quality_blocked` | 10,586 |
| `stage_unconfirmed_replace` | 1,763 |
| `stage_revision` | 3,404 |
| `stage_revision_reset` | 2,610 |
| `stage_start` | 2,990 |
| `candidate_duplicate` | 1,783 |
| `final_quality_skip` | 754 |
| `age_quality_blocked` | 41 |

## 성능 지표

| 지표 | 평균 | p50 | p95 | p99 | 최대 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `total_step_load` | 0.458 | 0.47 | 0.80 | 0.94 | 3.07 |
| `stt_step_load` | 0.447 | 0.46 | 0.77 | 0.92 | 3.06 |
| `total_rtf` | 0.030 | 0.03 | 0.05 | 0.06 | 0.20 |
| `queue_peak` | 2.843 | 5 | 5 | 15 | 75 |
| `text_chars` | 91.546 | 84 | 216 | 257 | 366 |

`input_queue_drops_total`은 시작, 종료, 최대 모두 0이었다.

## 시간대별 요약

| 시간 | diag | completed | final | `completed=1 final=0` | 미확정 교체 | stage 품질 차단 | 번역 생략 | 평균 load | queue max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 00시 일부 | 1,415 | 1,398 | 215 | 1,183 | 163 | 236 | 129 | 0.608 | 75 |
| 01시 | 3,600 | 3,125 | 416 | 2,709 | 331 | 887 | 282 | 0.512 | 15 |
| 02시 | 3,600 | 2,854 | 33 | 2,822 | 261 | 2,351 | 30 | 0.364 | 30 |
| 03시 | 3,600 | 2,962 | 26 | 2,938 | 218 | 2,313 | 22 | 0.336 | 30 |
| 04시 | 3,600 | 3,495 | 102 | 3,393 | 480 | 2,026 | 25 | 0.380 | 55 |
| 05시 | 3,600 | 3,435 | 372 | 3,063 | 237 | 1,429 | 253 | 0.599 | 40 |
| 06시 일부 | 1,528 | 1,494 | 13 | 1,481 | 73 | 1,344 | 13 | 0.555 | 30 |

02~04시는 final 비율이 크게 낮고 stage 품질 차단이 지배적이다. 이 구간의 중국어 문장 추출 성능 판단은 spaced CJK, 내부 공백, 문장 종결 미검출처럼 중국어 후보 자체가 확정되지 않은 사례만 대상으로 본다. 순수 비중국어/라틴 단독 입력은 중국어 문장 추출 성능 산정에서 제외한다.

## Final 사유와 품질 플래그

Final 사유:

| 사유 | 수 |
| --- | ---: |
| `aged` | 708 |
| `stable_cjk` | 317 |
| `confirmed` | 104 |
| `next_completed` | 48 |

Final 품질 플래그:

| 플래그 | 수 |
| --- | ---: |
| `no_end_marker` | 586 |
| `mixed_latin_zh` | 180 |
| `short_cjk` | 105 |
| `cjk_internal_gap` | 24 |
| `spaced_cjk` | 19 |

번역 생략 플래그도 거의 같은 분포다. final은 보존하되 번역 큐를 막는 정책은 동작한다. 다만 final 품질 오염 자체를 줄이는지는 별도 개선 대상이다.

## Stage 품질 차단 플래그

| 플래그 | 수 |
| --- | ---: |
| `no_end_marker` | 1,119 |
| `spaced_cjk` | 1,035 |
| `cjk_internal_gap` | 1,035 |
| `mixed_latin_zh` | 132 |
| `short_cjk` | 39 |
| `cjk_repeated_ngram` | 19 |
| `empty` | 1 |

`latin_only_for_zh`는 9,533회 관측됐지만 중국어 문장 추출 성능 판단에서는 제외한다. 순수 비중국어 입력은 중국어 확정 로직이 해결해야 할 문장 추출 실패가 아니라 입력/언어 분류 문제이기 때문이다. 따라서 성능 추적 케이스는 중국어 후보가 글자 단위 공백, 내부 공백, 미확정 교체 등으로 final에 도달하지 못한 사례를 우선 수집한다.

## 대표 케이스

### Spaced CJK stage 차단

- 시간: `2026-06-17 00:25:27`
- 후보 tail: `... 在 搭 的 七 点 我 们 刚 刚 就 是 在 这 边 搞 超 爆 酒 ...`
- flags: `spaced_cjk,cjk_internal_gap,no_end_marker`
- 판단: 글자 단위 공백 CJK는 stage 진입 차단이 맞다.

### Age quality 차단

- 시간: `2026-06-17 00:49:06`
- staged tail: `。有啊。`
- flags: `short_cjk`
- 판단: age가 차도 짧은 CJK 조각은 final로 보내지 않는 품질 게이트가 동작했다.

### No-end final

- 시간: `2026-06-17 00:25:46`
- reason: `aged`
- text: `分什么快线然后蓝色的橘色的然后j`
- flags: `no_end_marker`
- 판단: final로는 들어갔지만 번역은 생략됐다. final 품질 자체를 더 보수적으로 할지, 전사 보존을 우선할지는 정책 판단이 필요하다.

### Short final

- 시간: `2026-06-17 00:26:39`
- reason: `confirmed`
- text: `超爽`
- flags: `short_cjk,no_end_marker`
- 판단: 짧지만 반복 확인된 표현이다. 무조건 차단하면 실제 짧은 발화를 잃을 수 있어 tracking 대상으로 유지한다.

### Queue spike

- 시간: `2026-06-17 00:48:13`
- `total_step_load=2.79`, `queue_peak=30`, drop 0
- 판단: 순간 STT spike는 있지만 누적 drop은 없다. 처리량 파라미터 변경의 직접 근거는 아니다.

## 판단

- `windowSecondsZh=15.0`, `stepSecondsZh=1.0`, `beamSizeZh=3`, `maxNewTokensZh=192`, `sentenceFinalizeAgeZh=3`은 유지한다.
- 처리량보다 STT raw 품질 흔들림과 stage 생명주기 churn이 병목이다.
- 순수 비중국어/라틴 단독 후보는 중국어 문장 추출 성능 산정에서 제거한다.
- final 품질 플래그 중 `no_end_marker`, `mixed_latin_zh`, `short_cjk`는 많지만, 전사 보존 목적상 즉시 final 차단으로 올리면 누락이 늘 수 있다.
- 성능 테스트를 품질 게이트로 오해하지 않도록, 이 구간의 케이스는 hard unit test가 아니라 tracking case 후보로만 다룬다.

## 후속 액션

1. 중국어 후보가 final에 도달하지 못한 spaced CJK, 내부 공백, 미확정 교체 케이스를 performance tracking으로 누적한다.
2. `final_quality_no_end_marker`와 `translation_skip_final_quality`의 증가가 사용자 체감상 허용 가능한지 확인한다.
3. stage churn 개선은 `stage_replaced_unconfirmed_per_stage_start`와 `finalized_per_stage_start`를 함께 보고 판단한다.
4. 기존 hard unit test 중 stage churn/finalization tuning 성격 케이스는 performance tracking으로 이관한다.
