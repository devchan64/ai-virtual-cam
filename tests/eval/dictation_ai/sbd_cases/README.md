# SBD reviewed benchmark cases

이 디렉터리는 받아쓰기 AI SBD benchmark에 사용할 정식 reviewed challenge replay case를 둔다.
현재 파일들은 일반 운영 평균을 대표하는 표본이 아니라, 앱 로그에서 관측된 확정 누락과 중복 확정 같은 실패 구간을 누적한 failure-enriched challenge set이다.

## 운영 규칙

- JSONL 파일만 benchmark 입력으로 사용한다.
- 케이스 파일은 `en/`, `ko/`, `zh/` 언어별 하위 디렉터리에 둔다.
- 각 언어 디렉터리의 파일은 case id 해시 prefix shard인 `reviewed-context-{language}-{hash}.jsonl` 형식을 따른다.
- `tests/eval/dictation_ai/sbd_benchmark.py`의 기본 입력은 이 디렉터리의 `en/`, `ko/`, `zh/` shard만 읽는다.
- 대표 운영 품질을 보기 위한 representative corpus는 이 루트 아래에 넣지 않는다. `../sbd_representative_cases/`와 명시적 `--cases` 입력으로 관리해야 challenge 기준선에 섞이지 않는다.
- `draft_expected_final_required=true`가 남은 draft 파일은 이 디렉터리에 넣지 않는다.
- 정식 finalization benchmark case의 `chunks`는 실제 STT 컨텍스트 윈도우 처리 결과로 본다.
- benchmark의 목표는 이 입력에서 문장 경계와 final lifecycle을 산출하고, 그 결과가 확정한 `expected_final`과 충분히 유사한지 평가하는 것이다.
- 로그 구간이 이미 이전 window에서 확정된 문장을 포함한 중간 스트림에서 시작한다면 `initial_final`에 그 문장을 넣는다. `initial_final`은 recent-final/committed memory로만 사용하며 `actual_final` 평가 대상에는 포함하지 않는다.
- 정식 finalization benchmark case는 앱 로그에서 관측된 lifecycle 실패 현상과 확정한 `expected_final`이 모두 있어야 한다.
- 실패 현상은 확정 누락, 중복 확정, 문장 순서 파괴, premature fragment final, staged/pending 잔류, 최근 final echo처럼 final-only 번역 입력을 오염시키는 동작을 기준으로 본다.
- `expected_final`은 같은 case의 `chunks`에서 입력 근거를 가져야 한다. 입력 근거가 없거나 일부 expected만 chunks에서 확인되는 케이스, `expected_final`이 window 밖 문장으로 보이는 케이스는 로직 튜닝 근거로 쓰지 않고 제거하거나 재검토한다.
- raw STT 자체가 해석 불가능하거나 입력 음성과 무관한 경우, 연속 window 문맥이 부족한 경우, 사람이 봐도 하나의 `expected_final`을 정하기 어려운 경우, 같은 로그 구간의 거의 동일한 반복 후보는 정식 케이스로 승격하지 않는다.
- 중간 스트림에서 시작한 케이스는 이전에 이미 확정됐어야 할 문장을 `expected_final`에 섞지 않는다. 필요하면 `initial_final`에 넣거나 케이스 시작점을 조정한다.
- `expected_final`은 final-only 번역 큐에 들어갈 완성 문장 기준이다. 영어 소문자 접속구로 시작하는 조각, 모든 expected가 종결부호 없이 끝나는 조각, 같은 expected 묶음의 과도한 shifted-window 반복은 benchmark report의 case-definition review 신호로 보며 앱 로직 튜닝 근거에서 먼저 제외한다.
- 앱 로직 튜닝 근거는 모든 `expected_final`이 replay 입력에서 확인되는 `full_input_evidence` 또는 `strict_logic_candidate_summary`를 우선한다. 일부 expected만 확인되는 `partial_input_evidence_review`는 케이스 정의/수집 검토 대상으로 본다.
- pending/staged 전용 benchmark case는 `expected_final=[]`일 수 있다. finalization 목표 검증에는 비어 있지 않은 `expected_final` 케이스 수를 별도로 확인한다.

## 현재 배치

- `en/`: 영어 STT 컨텍스트 윈도우 reviewed case shard.
- `ko/`: 한국어 STT 컨텍스트 윈도우 reviewed case shard.
- `zh/`: 중국어 STT 컨텍스트 윈도우 reviewed case shard.

파일명 해시는 케이스를 작은 JSONL shard로 나누기 위한 저장 단위일 뿐 실험 의미를 갖지 않는다. 수집/검토/승격 도구는 폐기되었으므로 새 challenge case는 언어별 shard JSONL에 직접 추가한다.

## 검증 예

```text
./.venv/bin/python tests/eval/dictation_ai/cases/validate_sbd_case_files.py \
  tests/eval/dictation_ai/sbd_cases \
  --min-expected-final-cases 1000 \
  --max-drafts 0
```

## CUDA 벤치 예

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py \
  --cases tests/eval/dictation_ai/sbd_cases \
  --device cuda \
  --compute-type float16
```

성능 근거는 반드시 실제 `sat + cuda + float16` benchmark 결과로만 기록한다.
