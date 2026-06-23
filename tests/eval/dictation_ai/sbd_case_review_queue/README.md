# SBD Case Review Queue

이 디렉터리는 active challenge replay에서 제외한 케이스를 보관한다.

여기에 있는 JSONL은 `sbd_benchmark.py`의 기본 입력이 아니며, 앱 로직 성능 근거로 사용하지 않는다.
각 record의 `_review_queue`에는 active case에서 뺀 이유, 원래 파일/라인, 입력 근거 요약을 둔다.

다시 `sbd_cases/{en,ko,zh}/`로 돌려보내려면 다음 중 하나를 먼저 수행한다.

- `expected_final`을 replay chunks에서 `sentence_finalize_age`회 이상 반복 관측된 token-sentence 기준으로 다시 쓴다.
- replay 시작점, tail, 또는 `initial_final`을 조정해 expected 문장이 입력 구간 안에서 설명되게 만든다.
- source trace가 없거나 불충분하면 원 로그에서 같은 현상을 다시 잘라 case를 재생성한다.

이 큐는 삭제 대기열이 아니라 라벨/윈도우 정의 재검토 대기열이다.
