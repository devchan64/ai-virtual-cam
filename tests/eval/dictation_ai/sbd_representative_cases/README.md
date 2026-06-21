# SBD representative benchmark cases

이 디렉터리는 받아쓰기 AI SBD benchmark의 representative corpus를 둘 위치다.
현재는 아직 정식 case를 두지 않는다.

## 현재 상태

2026-06-21 기준 source audit과 review packet은 준비됐지만, 사람이 확정한 representative JSONL case는 아직 없다.

- source audit: `.tmp/eval/dictation-ai-sbd/representative-source-audit.json`
- source review manifest: `.tmp/eval/dictation-ai-sbd/representative-source-review-manifest.json`
- source review packets: `.tmp/eval/dictation-ai-sbd/representative-source-review-packets.json`
- review packet validation: `.tmp/eval/dictation-ai-sbd/representative-source-review-packets.validation.json`

최신 packet validator 결과:

```text
packet_count=5
ready_packet_count=5
language_counts={en:2, ko:2, zh:1}
event_totals={raw_chunks:3789, final_events:911, transcripts:2942, performance_events:3851}
missing_source_log_count=0
not_ready_packet_count=0
```

이 값은 representative case가 준비됐다는 뜻이 아니다. 사람이 각 source packet을 보고 `expected_final`을 확정한 JSONL record를 작성해야 논문 수치로 사용할 수 있다.
review packet Markdown은 case 작성을 돕기 위한 체크리스트, source runtime 후보, raw/final/transcript 샘플, performance 샘플을 포함한다.
`extract_sbd_representative_case_drafts.py`로 `.tmp` 아래 manual draft JSONL을 만들 수 있지만, 이 draft는 `expected_final=[]`, `expected_final_generated=false`, `draft_expected_final_required=true` 상태이므로 benchmark 입력이나 논문 수치로 사용하지 않는다.

## 승격 게이트

representative 자료는 아래 순서로만 승격한다.

| 단계 | 위치 | 상태 | 논문 수치 사용 |
| --- | --- | --- | --- |
| source audit | `.tmp/eval/dictation-ai-sbd/representative-source-audit.json` | 후보 seed 가능 여부 확인 | 불가 |
| source manifest | `.tmp/eval/dictation-ai-sbd/representative-source-review-manifest.json` | 사람이 볼 source 선택 목록 | 불가 |
| review packet | `.tmp/eval/dictation-ai-sbd/representative-source-review-packets.json` | raw/final/transcript/performance 검토 묶음 | 불가 |
| draft case | `.tmp/eval/dictation-ai-sbd/representative-case-drafts.jsonl` | `expected_final`을 사람이 채우기 전 템플릿 | 불가 |
| reviewed case | `tests/eval/dictation_ai/sbd_representative_cases/{en,ko,zh}/` | 사람이 `expected_final`과 reviewer를 확정한 JSONL | 가능 |

정식 representative case가 되려면 다음 조건을 모두 만족해야 한다.

- `expected_final`이 비어 있지 않다.
- `expected_final_reviewed_by`가 비어 있지 않다.
- `draft_expected_final_required`가 없다.
- `expected_final_generated=false`를 유지한다.
- `paper_evidence=false` draft marker를 제거하거나 정식 실험 report에서 `paper_evidence=true` eligibility를 새로 검증한다.
- `validate_sbd_case_files.py --review-packets`에서 `review_packet_id`, `source_log`, `language`가 기존 review packet과 일치한다.

이 게이트를 통과하기 전에는 representative 결과를 운영 평균, latency, translation 안정성 근거로 쓰지 않는다.

## 목적

- 운영 로그의 일반 평균 품질을 추정하기 위한 표본을 둔다.
- failure-enriched challenge set인 `../sbd_cases/`와 섞지 않는다.
- 논문에서 일반 운영 품질을 주장할 때만 이 corpus의 결과를 사용한다.

## 수집 규칙

- 표본 단위는 사람이 관측한 실패 구간이 아니라 운영 로그의 연속 시간 구간 또는 세션 구간이다.
- 언어별로 독립 shard를 두되, 파일명 해시는 저장 단위일 뿐 실험 의미를 갖지 않는다.
- 시간 구간, 세션, 언어 기준으로 층화 추출한다.
- 확정 누락, 중복 확정, boundary mismatch가 많이 보이는 구간만 의도적으로 고르지 않는다.
- 같은 세션에서 연속 구간을 뽑을 때는 fixed interval 또는 deterministic hash sampling처럼 재현 가능한 규칙을 기록한다.
- 가능하면 동일 오디오 replay, 사람이 작성한 참조 전사, final event timestamp를 함께 연결한다.
- `expected_final`을 사람이 확정하지 않은 draft case는 논문 수치에 포함하지 않는다.
- challenge replay에서 이미 사용한 실패 구간을 그대로 복사하지 않는다. 같은 로그가 포함되더라도 representative sampling rule로 선택된 구간이어야 한다.

## 필수 metadata

각 JSONL record는 기존 SBD case schema를 따르되, representative 해석을 위해 아래 필드를 추가한다.

- `corpus_role`: `representative`
- `sampling_unit`: `time-window` 또는 `session-window`
- `sampling_rule`: 예: `fixed-interval-10min`, `session-hash-mod-20`
- `source_log`: 원 로그 경로
- `source_started_at`: 가능하면 로그 기준 시작 시각 또는 chunk index
- `source_ended_at`: 가능하면 로그 기준 종료 시각 또는 chunk index
- `language`: `en`, `ko`, `zh`
- `stt_backend`: 표본 구간의 STT backend
- `stt_model`: 표본 구간의 STT model
- `window_seconds`: 표본 구간의 STT context window
- `step_seconds`: 표본 구간의 step interval
- `sentence_finalize_age`: 표본 구간의 finalization age
- `review_packet_id`: 사람이 검토한 source review packet id
- `expected_final_reviewed_by`: `expected_final`을 사람이 확정했음을 표시하는 reviewer id 또는 검토 단위
- `chunks`: 실제 STT context window 결과
- `expected_final`: 사람이 확정한 final 문장 목록
- `tags`: 진단 태그가 아니라 표본 설명 태그를 우선한다. 실패 증상 태그는 관측된 경우만 추가한다.

예시:

```json
{"id":"ko_representative_20260621_session_a_0001","corpus_role":"representative","sampling_unit":"time-window","sampling_rule":"fixed-interval-10min","source_log":".tmp/logs/avc-whisper.log.94","source_started_at":"chunk:120","source_ended_at":"chunk:135","language":"ko","stt_backend":"faster-whisper","stt_model":"large-v3","window_seconds":10.0,"step_seconds":1.0,"sentence_finalize_age":3,"review_packet_id":"ko_representative_review_abc123","expected_final_reviewed_by":"human-reviewed","chunks":["..."],"expected_final":["..."],"expected_pending":"","expected_staged":"","tags":["ko","representative","fixed-interval"]}
```

## 해석 규칙

- 이 corpus의 평균은 운영 평균 추정치로만 해석한다.
- challenge replay보다 점수가 높거나 낮아도 lifecycle 개선/악화를 직접 뜻하지 않는다. 두 corpus는 질문이 다르다.
- 파라미터 후보는 먼저 challenge replay에서 실패군 악화가 없는지 본 뒤, representative corpus에서 운영 평균 악화가 없는지 확인한다.
- representative corpus만으로 특정 실패군의 개선을 주장하지 않는다. 실패군 개선은 challenge replay/tag summary로 판단한다.

## 실행 규칙

- benchmark 기본 입력에는 포함되지 않는다.
- 실행할 때는 반드시 명시적으로 `--cases tests/eval/dictation_ai/sbd_representative_cases`를 지정한다.
- challenge replay 결과와 representative 결과의 평균은 한 표에서 섞지 않는다.
- `run_sbd_parameter_sweep.py --paper-evidence`로 실행할 때는 `--min-expected-final-cases`를 명시한다. 대표 표본의 표본 수 목표는 challenge replay의 1000건 기준을 암묵적으로 공유하지 않는다.
- representative `--paper-evidence` sweep은 `--review-packets`도 함께 지정해 source packet 추적성을 먼저 검증한다.
- follow-up readiness와 paper readiness를 실행할 때는 가능하면 `--representative-draft-validation`도 함께 지정해 `.tmp` draft가 review packet과 traceable한지 한 화면에서 확인한다.
- `validate_sbd_case_files.py`는 이 루트나 루트 아래 JSONL shard가 입력되면 representative 필수 metadata와 비어 있지 않은 `expected_final`을 검증한다.
- validator summary에는 `representative_metadata.sampling_unit_counts`, `sampling_rule_counts`, `source_log_count`, `source_log_counts`, `review_packet_count`, `review_packet_counts`, `expected_final_reviewer_counts`가 포함된다. 이 값으로 표본이 한 규칙, 한 로그, 한 검토 packet에 과도하게 몰렸는지 확인한다.
- `sbd_benchmark.py` 단독 report의 `case_summary`에도 같은 `representative_metadata`가 포함된다.
- representative parameter sweep Markdown summary header에도 `representative_sampling_units`, `representative_sampling_rules`, `representative_source_log_count`, `representative_review_packet_count`, `representative_reviewers`, `representative_review_packet_validation_*`가 출력된다.
- `sampling_unit`은 `time-window` 또는 `session-window`만 허용한다. 실패 유형 묶음, 수동 후보 그룹, tag cluster는 representative 표본 단위로 쓰지 않는다.
- 첫 case를 만들기 전에는 운영 로그 source audit을 실행해 로그 보존량, timestamp, raw STT window, final event, transcript, runtime metadata가 남아 있는지 확인한다.
- source audit은 candidate seed 가능 여부만 판단한다. `expected_final` 자동 생성이나 정식 representative case 등록을 수행하지 않는다.
- source audit의 runtime metadata는 STT, SBD, 번역 backend/model을 분리해 본다. 정식 case metadata는 선택된 source window 안에서 다시 확인한다.
- source audit 이후 `select_sbd_representative_sources.py`로 사람 검수용 source manifest를 만들 수 있다. 이 manifest도 정식 case가 아니며 논문 수치에 포함하지 않는다.
- source manifest 이후 `extract_sbd_representative_review_packets.py`로 source 로그의 raw STT, final event, transcript, 성능 event를 검토용 packet으로 축약할 수 있다. 이 packet도 `expected_final`을 만들지 않으며 정식 case가 아니다.
- review packet은 manifest의 `source_started_at`과 `source_ended_at` 범위 안 이벤트만 수집한다. `source_window_filter.applied=true`를 확인해 사람이 검토할 representative 구간이 로그 전체로 넓어지지 않았는지 확인한다.
- review packet 이후 `extract_sbd_representative_case_drafts.py`로 사람이 채울 draft JSONL을 만들 수 있다. 이 draft도 정식 case가 아니며, 사람이 bounded window를 정하고 `expected_final`과 `expected_final_reviewed_by`를 채운 뒤 `draft_expected_final_required`를 제거해야 한다.
- review packet의 `ready_packet_count`는 raw STT, final event, transcript, performance event가 모두 있는 packet 수다. 부족한 source는 `packet_readiness_blockers`를 먼저 해소한 뒤 사람이 검토한다.
- review packet을 만든 뒤에는 `validate_sbd_representative_review_packets.py`로 packet version, manifest 선택 수와 언어별 선택 수, packet count, readiness, source 누락, readiness blocker 일치, non-case 해석 계약을 확인한다.
- representative JSONL case를 작성한 뒤에는 `validate_sbd_case_files.py --review-packets`로 각 case의 `review_packet_id`, `source_log`, `language`가 검증된 review packet과 일치하는지 확인한다. case와 packet의 source range가 timestamp 형식이면 case range가 packet의 `source_window_filter` 범위 안에 있는지도 확인한다.

## 예

아래 명령은 representative JSONL case가 추가된 뒤 실행한다.

```text
./.venv/bin/python tests/eval/dictation_ai/audit_sbd_representative_sources.py \
  .tmp/logs \
  --compact \
  --summary-output .tmp/eval/dictation-ai-sbd/representative-source-audit.json
```

```text
./.venv/bin/python tests/eval/dictation_ai/select_sbd_representative_sources.py \
  .tmp/eval/dictation-ai-sbd/representative-source-audit.json \
  --per-language 2 \
  --output .tmp/eval/dictation-ai-sbd/representative-source-review-manifest.json \
  --markdown-output .tmp/eval/dictation-ai-sbd/representative-source-review-manifest.md
```

```text
./.venv/bin/python tests/eval/dictation_ai/extract_sbd_representative_review_packets.py \
  .tmp/eval/dictation-ai-sbd/representative-source-review-manifest.json \
  --output .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json \
  --markdown-output .tmp/eval/dictation-ai-sbd/representative-source-review-packets.md
```

```text
./.venv/bin/python tests/eval/dictation_ai/validate_sbd_representative_review_packets.py \
  .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json \
  --summary-output .tmp/eval/dictation-ai-sbd/representative-source-review-packets.validation.json
```

```text
./.venv/bin/python tests/eval/dictation_ai/extract_sbd_representative_case_drafts.py \
  .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json \
  --jsonl-output .tmp/eval/dictation-ai-sbd/representative-case-drafts.jsonl \
  --summary-output .tmp/eval/dictation-ai-sbd/representative-case-drafts.summary.json \
  --markdown-output .tmp/eval/dictation-ai-sbd/representative-case-drafts.md
```

```text
./.venv/bin/python tests/eval/dictation_ai/validate_sbd_case_files.py \
  .tmp/eval/dictation-ai-sbd/representative-case-drafts.jsonl \
  --corpus-role representative \
  --allow-drafts \
  --review-packets .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json \
  --summary-output .tmp/eval/dictation-ai-sbd/representative-case-drafts.validation.json
```

이 검증은 `.tmp` draft가 정식 case가 되었다는 뜻이 아니다. draft의 `review_packet_id`, `source_log`, `language`, timestamp source range가 기존 review packet과 맞는지 확인해 사람이 `expected_final`을 채우기 전 템플릿 품질을 확인하는 단계다.

```text
./.venv/bin/python tests/eval/dictation_ai/promote_sbd_representative_cases.py \
  .tmp/eval/dictation-ai-sbd/representative-case-drafts.jsonl \
  --review-packets .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json \
  --dry-run
```

위 승격 명령은 사람이 `expected_final`, `expected_final_reviewed_by`를 채우고 `draft_expected_final_required`를 제거한 JSONL에만 사용한다. 현재 draft 그대로 실행하면 실패해야 정상이다. 검증을 통과하면 언어별 `reviewed-representative-{language}-{hash}.jsonl` shard로 저장한다.

```text
./.venv/bin/python tests/eval/dictation_ai/validate_sbd_case_files.py \
  tests/eval/dictation_ai/sbd_representative_cases \
  --max-drafts 0 \
  --review-packets .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json
```

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py \
  --cases tests/eval/dictation_ai/sbd_representative_cases \
  --review-packets .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json \
  --device cuda \
  --compute-type float16
```

```text
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
./.venv/bin/python tests/eval/dictation_ai/run_sbd_parameter_sweep.py \
  --cases tests/eval/dictation_ai/sbd_representative_cases \
  --include-baseline \
  --paper-evidence \
  --min-expected-final-cases 1 \
  --review-packets .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json
```
