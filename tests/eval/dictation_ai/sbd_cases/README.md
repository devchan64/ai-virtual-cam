# SBD reviewed benchmark cases

이 디렉터리는 받아쓰기 AI SBD benchmark에 사용할 정식 reviewed case를 둔다.
모든 benchmark case는 이 디렉터리 아래의 JSONL 파일로 관리한다.

## 운영 규칙

- JSONL 파일만 benchmark 입력으로 사용한다.
- 케이스 파일은 `manual-reviewed/`, `auto-groups/`처럼 하위 디렉터리로 나눌 수 있다.
- `tests/eval/dictation_ai/sbd_benchmark.py`는 이 디렉터리 아래 `*.jsonl`을 재귀적으로 읽는다.
- `draft_expected_final_required=true`가 남은 draft 파일은 이 디렉터리에 넣지 않는다.
- 정식 finalization benchmark case는 앱 로그에서 관측된 lifecycle 실패 현상과 확정한 `expected_final`이 모두 있어야 한다.
- 실패 현상은 확정 누락, 중복 확정, 문장 순서 파괴, premature fragment final, staged/pending 잔류, 최근 final echo처럼 final-only 번역 입력을 오염시키는 동작을 기준으로 본다.
- raw STT 자체가 해석 불가능하거나 입력 음성과 무관한 경우, 연속 window 문맥이 부족한 경우, 사람이 봐도 하나의 `expected_final`을 정하기 어려운 경우, 같은 로그 구간의 거의 동일한 반복 후보는 정식 케이스로 승격하지 않는다.
- pending/staged 전용 benchmark case는 `expected_final=[]`일 수 있다. finalization 목표 검증에는 비어 있지 않은 `expected_final` 케이스 수를 별도로 확인한다.

## 현재 배치

- `manual-reviewed/`: 기존 수동 reviewed 로그 케이스를 언어별로 분리한 파일.
- `auto-groups/`: 이전 그룹 평가 결과로 생성된 reviewed case 파일. 수집/검토/승격 도구는 폐기되었으므로 새 케이스는 검토한 JSONL로 직접 추가한다.

## 검증 예

```text
./.venv/bin/python tests/eval/dictation_ai/validate_sbd_case_files.py \
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
