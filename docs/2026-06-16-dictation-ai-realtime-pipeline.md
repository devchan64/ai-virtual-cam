# 받아쓰기 AI 실시간 파이프라인 디자인

## 컨텍스트

이 문서는 받아쓰기 AI 실시간 파이프라인을 파이프라인, 노드, 계약 중심으로 정의하는 압축 설계 컨텍스트다.

기존 흐름은 STT, 문장 경계 처리, revision lifecycle, 번역 입력 제어 코드가 한 실행 루프 안에 섞이기 쉬웠다. 이 문서는 구현 순서가 아니라 도메인 경계와 메시지 계약을 먼저 고정해 코드 분리와 회귀 판단의 기준으로 사용한다.

상세 설정 계약과 기본값은 [받아쓰기 AI 계약과 기본값](2026-06-16-dictation-ai-contract-defaults.md)에 두고, 실험 기록은 [받아쓰기 AI 실험일지](2026-06-16-dictation-ai-experiment-log.md)에 둔다.

핵심 문제:

실시간 ASR은 매 step마다 최근 오디오 window 전체를 다시 전사한다. 같은 음성 구간이 여러 window에 반복 포함되므로 raw STT 결과를 그대로 출력하거나 번역하면 중복 출력, 누락, premature translation, 뒤 window revision 문제가 생긴다.

목표는 raw STT window 결과를 append-only final 전사 이벤트로 안정화하고, final 이벤트만 전사 창과 번역 sink로 전달하는 것이다.

구성 원칙:

- 파이프라인은 실행 순서가 아니라 도메인 메시지 흐름으로 정의한다.
- 노드는 입력 계약, 출력 계약, 소유 상태, 불변식으로 구분한다.
- queue, list, loop는 구현 수단이며 도메인 경계가 아니다.
- 노드 내부 상태는 해당 노드만 소유한다. 다른 노드는 출력 계약만 소비한다.
- 전사 창과 번역은 sink다. sink는 final 계약만 소비하고 확정 정책에 개입하지 않는다.
- regex/ad-hoc 문장 보정, VAD/silence final trigger, CPU/backend fallback은 운영 파이프라인 기준에서 제외한다.
- 소절 단위 분할은 전역 기본 정책으로 두지 않는다. 긴 문장 과결합은 `next_completed` 직전의 제한된 revision/finalize 경로에서만 구조적으로 완화한다.

## 파이프라인

```text
오디오 입력 source
  -> AudioEvidence
  -> 음성증거-STT가설 생성 노드
  -> RecognitionHypothesis
  -> STT가설-문장후보 해석 노드 + UncommittedContext
  -> SentenceCandidateSet
  -> 문장후보-확정전사 커밋 노드 + CommitState
  -> CommittedTranscriptEvent
  -> 전사 창 / 번역 sink
```

이 파이프라인의 final 기준은 silence가 아니라 텍스트 안정성, 문장 후보 경계, revision 계열, candidate age, 소비 순서다.

## 노드

| 노드 | 책임 | 입력 | 출력 | 소유 상태 | 불변식 |
| --- | --- | --- | --- | --- | --- |
| `음성증거-STT가설 생성 노드` | 설정된 시간 범위의 음성 증거를 단일 언어 STT 가설로 변환한다. | `AudioEvidence` | `RecognitionHypothesis` | 최근 window 텍스트, stable token/char 관측값 | raw text는 가설이며 final/translation으로 직접 나가지 않는다. 설정 backend/model/device 실패 시 자동 대체하지 않는다. |
| `STT가설-문장후보 해석 노드` | STT 가설과 미확정 context를 문장 단위 후보로 해석한다. | `RecognitionHypothesis`, `UncommittedContext` | `SentenceCandidateSet` | pending tail, boundary detector, boundary metrics | 후보 순서를 보존한다. regex/ad-hoc 분할, 후보 의미 재작성, pending 강제 completed 승격을 하지 않는다. |
| `문장후보-확정전사 커밋 노드` | 문장 후보의 revision lifecycle과 소비 순서를 관리해 final 이벤트만 발행한다. | `SentenceCandidateSet`, `CommitState` | `CommittedTranscriptEvent`, `SuppressedCandidate` | `candidateBuffer`, `revisionHashIndex`, `committedText`, recent finals, lifecycle metrics | final은 append-only다. 생성순서와 소비순서를 분리한다. 나중 revision이 먼저 소비되면 같은 revision 계열의 이전 미소비 후보는 폐기한다. |

## 계약

### 메시지

| 계약 | 필수 의미 |
| --- | --- |
| `AudioEvidence` | `chunkIndex`, `inputDevice`, `sampleRate`, `windowSeconds`, `stepSeconds`, `audioWindow`, `queueDrops`를 포함한 특정 시간 범위의 음성 증거 |
| `RecognitionHypothesis` | `chunkIndex`, `language`, `rawText`, `acceptedSegments`, `rejectedReasons`, `stableText`, `stability`, `segmentBoundaryConfidence`, `stableBoundaryConfidence`, `boundaryConfidence`를 포함한 미확정 STT 가설 |
| `UncommittedContext` | 이미 final로 커밋된 `committedText`와 아직 커밋되지 않은 `pendingText` |
| `SentenceCandidateSet` | 순서가 보존된 `completedCandidates[]`, `pendingTail`, `boundarySignals`, `candidateQualityFlags` |
| `CommitState` | 후보 버퍼, revision 계열 인덱스, 소비순서, 최근 final 참조를 포함한 커밋 상태 |
| `CommittedTranscriptEvent` | `consumeSequence`, `createdSequence`, `revisionHash`, `chunkIndex`, `language`, `text`, `qualityFlags`, `final=true`를 포함한 되돌릴 수 없는 전사 이벤트 |

### 문장 후보 버퍼

문장 후보 관리는 단순 queue가 아니라 생성순서와 소비순서를 함께 가진 revision-aware buffer다.

| 필드 | 의미 |
| --- | --- |
| `createdSequence` | 후보가 처음 관측되어 버퍼에 들어온 순서. 같은 chunk 안 후보도 모델 경계 순서대로 증가한다. |
| `revisionHash` | 같은 발화 구간의 revision 후보를 묶는 안정 식별자. 완전 동일 텍스트가 아니라 token-sentence(토큰센텐스) 유사도와 위치 맥락으로 판단한다. |
| `candidateAge` | 후보가 소비되지 않고 버퍼에서 재관측/검증된 chunk 수. final 소비 판단의 핵심 입력이다. |
| `consumeSequence` | final 이벤트가 외부 sink로 발행된 순서. append-only transcript와 번역 sink는 이 순서만 따른다. |
| `candidateBuffer` | 미소비 후보를 `createdSequence` 기준으로 보존하는 제한 크기 버퍼. 누락 소비와 중복 소비를 줄이기 위한 보류 장치다. |

커밋 규칙:

- 후보는 `createdSequence` 순서로 버퍼에 들어간다.
- final 발행은 `consumeSequence` 순서로만 수행한다.
- `candidateAge`가 기준에 도달하기 전에는 뒤 후보가 관측되어도 즉시 소비하지 않는다.
- pending tail이 staged 후보의 revision/확장으로 보이면 `candidateAge` 증가는 보류하지만, 이미 누적된 age를 reset하지 않는다.
- token-sentence(토큰센텐스) 유사도가 낮아 confirmation을 보존할 수 없는 reset 대상 revision은 active staged 후보를 즉시 덮지 않고 candidate buffer에 보류한다. 해당 대안 후보가 같은 revision 계열로 반복 관측될 때만 이후 순서에 따라 소비한다.
- 종결부호/문장부호가 window마다 흔들려도 token-sentence가 같은 revision이면 confirmation과 age를 reset하지 않는다. 문장부호 손실은 token-sentence 유사도와 internal stability로 같은 revision이 아니라고 판단된 뒤에만 reset 근거로 사용한다.
- candidate buffer에 active staged 후보의 더 긴 token-sentence revision이 남아 있으면, active staged 후보가 age 기준에 도달해도 fragment final로 먼저 소비하지 않는다. 단, stale 한계를 넘은 revision 후보는 흡수하지 않고 suppressed 후보로 폐기한다.
- candidate buffer head가 active staged 후보보다 오래 관측된 다른 revision 계열이면, active staged 후보가 확정 조건을 만족해도 먼저 final로 소비하지 않고 buffer head를 먼저 재평가한다. 단, stale 한계를 넘은 buffer head는 final 순서 보류 근거가 아니라 suppressed 후보로 폐기한다.
- 같은 STT chunk에서 생성된 completed 후보도 staged 후보의 첫 관측 근거로 본다. candidateAge는 후속 chunk만 세는 지연 타이머가 아니라, SBD가 completed 후보로 내보낸 관측 횟수/순서의 보조 근거다.
- candidate buffer에서 승격된 이전 후보가 짧은 과거 prefix를 끌고 온 상태이고, 같은 chunk의 새 후보가 해당 prefix 뒤 본문과 높은 token-sentence coverage로 정렬되면 새 후보를 같은 revision의 preferred candidate로 본다.
- active staged 후보가 과거 prefix 뒤에 새 문장의 앞부분만 붙은 형태이고, candidate buffer 후보가 그 앞부분에서 시작해 충분한 suffix를 이어가면 같은 token-sentence revision으로 보고 queue 후보를 preferred candidate로 본다.
- STT text가 없는 chunk는 candidateAge 증가 근거로 사용하지 않는다.
- STT text가 없는 chunk가 반복되면 confirmation 기준을 만족하지 못한 staged 후보는 final로 승격하지 않고 stale 후보로 폐기할 수 있다.
- 이전 pending tail이 다음 completed 후보 앞에 붙어 기존 staged 문장의 revision처럼 보이는 경우, pending tail prefix는 final 후보에서 제거하고 staged 본문 기준으로 비교한다.
- CJK 문자 사이에 삽입된 STT 공백 artefact는 후보 품질 판단 전에 제거한다. 이는 문장 재작성이나 overlap 접합이 아니라 no-space 문자의 표준화이며, Latin/숫자 token 경계는 유지한다.
- 언어 설정과 후보 script가 일치하지 않는 상황은 진단 플래그로만 기록한다. STT window에서 반복 관측되고 token-sentence 확정 조건을 만족한 후보를 언어별 예외만으로 final 차단하지 않는다.
- revision 후보 비교에서 한 후보가 명확한 종결 경계를 가진 prefix 문장이고 다른 후보가 그 뒤에 짧은 tail을 붙여 하나의 문장처럼 만든 경우, 더 긴 문자열보다 종결 경계를 보존한 후보를 우선한다.
- CJK 긴 문장 과결합은 접속어 사전이나 언어별 ad-hoc 소절 규칙으로 자르지 않는다. 대신 active staged 후보가 이미 충분한 종결 경계와 안정성을 갖고 있고, 뒤 revision이 무종결 tail을 덧붙인 상태에서 `next_completed`로 조기 확정되려는 경우에만 staged 본문 보존 또는 제한적 분할을 검토한다.
- 미확정 replacement는 기존 후보를 삭제하지 않고 새 후보를 candidate buffer에 보류한다. 앞 후보는 확정, revision 대체, 품질/중복 suppress 중 하나로 정리된 뒤에 다음 후보로 넘어간다. 단, 미확정 replacement와 충돌 중인 앞 후보는 age만으로 final 승격하지 않고, age 한계 전에는 즉시 suppress하지 않는다.
- 짧은 CJK staged 후보가 replacement와 충돌할 때는 추가 hold를 기본 적용하지 않는다. 현재 운영 기준 challenge replay에서도 짧은 active head hold가 queue 소비를 막는 사례가 반복되어 `SHORT_CJK_REPLACEMENT_HOLD_CHUNKS=0`을 유지한다. 이 값은 짧은 문장을 즉시 final로 보내는 규칙이 아니라, 확정 불가능한 짧은 head가 오래 남아 생성순서 queue를 막지 않게 하는 suppress/promote 정책이다.
- 현재 chunk에서 candidate buffer로부터 승격된 staged 후보는 같은 chunk 안의 후속 replacement로 즉시 final 확정하지 않는다. 최소 다음 STT window에서 재평가해 stale queue burst가 false final로 소비되는 경로를 막는다.
- 이전 chunk부터 staged로 유지된 후보가 종결 경계와 품질 게이트를 만족하고, candidate buffer에 뒤따르는 다른 후보가 있으면 오른쪽 문맥이 확인된 것으로 보고 생성순서대로 final 소비할 수 있다. 단, 같은 chunk에서 막 생성/승격된 staged 후보는 이 규칙으로 즉시 final하지 않는다.
- 같은 `revisionHash` 계열에서 나중 후보가 final로 소비되면, 이전 미소비 후보는 stale revision으로 폐기한다.
- 다른 revision 계열이라도 뒤 후보가 앞 후보의 의미 구간을 포함하거나 대체한 것이 확인되면, 앞 후보는 중복 소비 방지를 위해 폐기한다.
- 최근 final과 새 후보가 prefix 관계이고 새 suffix가 충분히 길면, 이미 final된 prefix는 다시 확정하지 않고 suffix만 새 후보로 회수할 수 있다. 최근 final과 동일한 token-sentence는 짧은 CJK 문장이라도 echo로 보고 다시 확정하지 않는다. 최근 final의 tail 일부가 표기만 조금 바뀐 후보로 다시 나오면 fuzzy tail echo로 보고 다시 확정하지 않는다. 짧은 suffix 보정은 echo로 보고 기존 중복 억제를 유지한다. 최근 final보다 상당히 짧고 문장 종료 표지가 있는 후보의 대부분이 recent-final token-sentence run으로 설명되면 fragment echo로 suppressed 처리한다. 다만 이미 독립 staged 문장으로 확인된 후보를 committed-text delta가 종결부 없는 조각으로 만들면, append-only final 단위를 보존하기 위해 staged 원문을 final 후보로 유지한다.
- 버퍼 초과는 강제 final 승격 사유가 아니다. age, revisionHash, recent final delta, 품질 기준을 만족하지 못한 오래된 후보는 suppressed로 폐기한다.
- 생성순서 buffering은 누락 소비를 줄이기 위한 장치이며 append-only 소비 순서를 깨는 근거가 될 수 없다.

### 출력 상태

| 상태 | 의미 | sink 전달 |
| --- | --- | --- |
| `raw` | 최신 STT window의 원시 가설 | 아니오 |
| `pending` | 아직 경계 또는 안정성이 부족한 후보 | 아니오 |
| `staged` | completed 후보이나 재확인 전 상태 | 아니오 |
| `final` | 복사/번역 가능한 확정 이벤트 | 예 |
| `suppressed` | 중복, 품질 문제, stale revision으로 폐기된 후보 | 아니오 |
| `revised` | 다음 window에서 갱신된 후보 | 아니오 |

### 관측 기준

관측 기준은 노드 경계와 계약 위반을 찾기 위한 최소 지표만 둔다. 모델 품질 실험이나 언어별 튜닝 근거는 실험일지에 둔다.

| 관측 대상 | 지표 | 판단 기준 |
| --- | --- | --- |
| `AudioEvidence` 처리량 | `input_queue_drops`, `input_queue_size_peak`, `stt_step_load`, `total_step_load`, `audio_rms_db`, `audio_peak_db` | drop이 발생하거나 step load가 1.0을 넘으면 실시간 처리량 초과로 본다. 오디오 레벨은 STT raw 반복 원인 분석용 관측값이며 final 판단 기준으로 쓰지 않는다. |
| `RecognitionHypothesis` 안정성 | `stable_token_ratio`, `stable_internal_chars`, `raw_without_final` | raw 가설이 계속 나오는데 final이 없으면 인식/후보/커밋 경계 중 병목을 추적한다. |
| `SentenceCandidateSet` 경계 품질 | `boundary_end_marks`, `boundary_right_context_starts`, `segment_state_pending`, `pending_quality_*` | completed/pending 분포와 경계 신호가 후보 생성 계약을 만족하는지 본다. |
| `candidateBuffer` 동작 | `stage_queue_enqueue`, `stage_queue_promote`, `stage_queue_revision`, `stage_queue_revision_token_sentence_deferred`, `stage_finalize_deferred_for_queue_revision`, `stage_finalize_right_context`, `stage_queue_quality_suppressed`, `stage_queue_drop_oldest`, `stage_queue_recent_final_suppressed`, `stage_queue_recent_final_delta_trimmed`, `stage_replace_deferred`, `stage_replaced_unconfirmed`, `stage_age_finalize`, `stage_age_hold`, `stage_age_no_text_skipped`, `stage_no_text_stale_suppressed`, `stage_candidate_quality_no_end_marker_with_active_stage`, `stage_candidate_quality_no_end_marker_with_queue`, `stage_candidate_quality_no_end_marker_without_blocker`, `candidate_prior_pending_prefix_trimmed` | 생성순서는 queue 보존과 idle 승격으로 유지하고, active staged 후보의 final을 단순 queue age만으로 선점 보류하지 않는다. `stage_replaced_unconfirmed`가 많이 발생하면 확정 전 후보 삭제로 인한 누락 가능성을 우선 검토한다. `stage_queue_revision_token_sentence_deferred`는 queue 안 후보가 reset 대상 token-sentence revision을 만나 기존 age/confirmation을 즉시 덮지 않고 별도 후보로 보류한 관측값이다. `stage_finalize_deferred_for_queue_revision`은 active staged 후보를 final하기 전에 queue의 더 선호되는 token-sentence revision을 흡수해 fragment final을 보류한 관측값이다. `stage_finalize_right_context`는 이전 chunk부터 staged였던 후보가 뒤따르는 buffer 후보를 오른쪽 문맥으로 삼아 final 소비된 관측값이다. `stage_queue_quality_suppressed`는 queue 후보가 승격 직전 stage 품질 게이트를 다시 통과하지 못해 active staged로 내보내지 않은 관측값이다. `stage_queue_recent_final_suppressed`는 이미 final된 이전 revision이 뒤늦게 queue에서 승격되지 않고 폐기된 관측값이다. `stage_queue_recent_final_delta_trimmed`는 queue 후보 중 recent final prefix 뒤의 의미 있는 suffix만 회수된 관측값이다. `stage_age_finalize`는 충분히 오래 관측된 staged 후보가 final로 소비된 관측값이다. `stage_age_hold`는 pending 확장으로 age 증가가 보류된 관측값이다. `stage_no_text_stale_suppressed`는 STT text가 없는 반복 구간에서 미확정 staged 후보가 final로 가지 않고 폐기된 관측값이다. `stage_candidate_quality_no_end_marker_with_*`와 `stage_candidate_quality_short_no_end_fragment_with_*`는 no-end 후보가 품질 차단될 때 active staged/queue가 함께 존재했는지 구분해, no-end 완화가 필요한지 active-stage 교착 해소가 필요한지 판단하는 관측값이다. `candidate_prior_pending_prefix_trimmed`는 pending prefix 오염 제거 관측값이다. |
| 커밋 품질 | `finalized_per_stage_start`, `segment_state_final`, `segment_state_suppressed`, `final_quality_*`, `candidate_recent_final_delta_trimmed`, `finalize_delta_suppressed_stage_retained`, `finalize_delta_suppressed_stage_dropped`, `finalize_delta_fragment_preserved` | final 전환 비율과 suppressed 사유로 중복/오염 후보 차단 여부를 본다. 최근 final prefix 뒤의 긴 suffix가 회수되는지와 짧은 echo 보정이 억제되는지도 함께 본다. delta가 broken fragment로 계산되면 active staged 후보를 잠시 유지하되, 반복 보류가 누락을 만들면 폐기하고 다음 후보로 진행한다. 단, 독립 staged 문장이 committed-text delta 때문에 종결부 없는 조각으로 바뀌는 경우는 `finalize_delta_fragment_preserved`로 관측하고 staged 원문을 보존한다. |
| final-only sink | `translation_skip_final_quality`, 번역 입력의 `final=true` 여부 | 번역 sink가 `CommittedTranscriptEvent` 외 입력을 소비하지 않는지 본다. |

지표 일반화 원칙:

- 새 지표는 특정 문구나 언어별 접속어 이름이 아니라 `경계 감지`, `revision 보류`, `queue 순서`, `품질 차단`, `recent-final 억제`, `delta 보존`처럼 구조적 병목 축으로 묶는다.
- 세부 원인 지표는 유지하되, 비교/튜닝 우선순위는 per-case 원시 카운트보다 축별 aggregate와 strict subset case presence를 먼저 본다.
- 소절 관련 개선 전에는 `underfinal_boundary_or_revision` 같은 증상 이름보다, 해당 증상을 만든 상위 메커니즘(`stage_replace_deferred`, `stage_revision_token_sentence_deferred`, `stage_candidate_quality_blocked`, `stage_finalize_before_replace`)을 먼저 최적화 대상으로 삼는다.

소절 개선 전 우선 최적화 대상:

- `revision 보류/대기`: `stage_replace_deferred`, `stage_revision_token_sentence_deferred`, `stage_queue_revision`
- `조기 확정`: `stage_finalize_before_replace`, `stage_confirm_deferred_later_extension`, `stage_finalize_right_context`
- `품질 차단으로 인한 교착`: `stage_candidate_quality_blocked`, `stage_age_quality_blocked`, `stage_age_hold`
- `경계 민감도`: `underfinal_boundary_or_revision`, `boundary_granularity`, `strict_boundary_sensitive_case_count`

이 순서는 소절 분할을 전역 완화하기 전에, 현재 파이프라인이 어디서 긴 revision을 과하게 유지하거나 반대로 너무 이르게 확정하는지 일반화된 구조 신호로 먼저 좁히기 위한 것이다.

### 불변 계약

- final transcript는 append-only이며 되돌리지 않는다.
- STT 원문창은 raw만 표시하고, 복사용 전사 창은 final만 표시한다.
- 번역 sink는 `CommittedTranscriptEvent`만 소비한다. staged/partial/pending은 번역하지 않는다.
- 최근 final과 같은 후보, recent-final echo, 순서가 섞인 후보는 다시 final로 확정하지 않는다. 단, 최근 final이 새 후보의 안정된 prefix이고 의미 있는 길이의 suffix가 추가된 경우에는 append-only 원칙에 따라 suffix만 새 후보로 회수할 수 있다. 문장 종료 표지가 없는 후보는 fragment echo suppression보다 stage/age 판단에 맡긴다.
- 외부 번역 backend 사용 시 Whisper는 `task=transcribe`만 수행하고 번역은 외부 번역 경로가 담당한다.
- 모델/장치/설정 오류는 자동 폴백하지 않고 실패한다. CUDA/float16 요구 경로에서 CPU fallback은 허용하지 않는다.
- 운영 파라미터와 모델/장치 허용값은 계약 기본값 문서를 따른다.

### 소절 경계 계획

- 목표는 CJK 발화의 모든 소절을 더 잘게 자르는 것이 아니라, `stage 리비전 -> pending tail 연장 -> next_completed 확정` 경로에서 생기는 과결합 final을 줄이는 것이다.
- 분할 검토 위치는 active staged 후보의 revision 채택 직후와 `next_completed` 직전으로 제한한다. candidate 해석 단계에서 언어별 접속어 규칙으로 completed 후보를 쪼개지 않는다.
- 분할 조건은 접속어 문자열 자체가 아니라 종결 경계 존재, `no_end_marker`, internal stability, pending tail 길이, deferred revision 여부, later completed extension 부재 같은 구조 신호만 사용한다.
- 성능 평가는 전체 평균 `final_f1_avg`보다 strict logic candidate subset, `underfinal_boundary_or_revision`, `boundary_granularity`, `stage_replace_deferred`, `stage_revision_token_sentence_deferred` 변화로 먼저 판단한다.
- 소절 분할 완화는 `overfinal_or_extra_final`을 늘릴 위험이 있으므로, 전역 완화가 아니라 strict subset에서 근거가 확인된 경로에만 단계적으로 적용한다.
- 현재 운영 채택 경로는 전역 소절 분할이 아니라 `raw STT -> SBD candidate -> revision-aware lifecycle -> final-only sink`다. fragment revision replay와 same-chunk tail merge는 벤치 실험으로만 남겼고, 운영 파이프라인에는 채택하지 않는다.
- 2026-06-29 기준 same-chunk tail merge는 한국어 shard에서는 `final_f1_avg 0.588 -> 0.608`, `final_boundary_f1_avg 0.158 -> 0.165` 신호가 있었지만, full challenge replay에서는 strict exactness를 낮춰 미채택으로 정리했다. 따라서 현재 파이프라인의 소절 대응은 새 문구 규칙이나 병합 규칙 추가가 아니라 lifecycle 상위 축 최적화로 제한한다.

### 소절 관리 패턴 작성 방법

- 소절 관리 문서는 특정 문구를 어떻게 자를지 적는 문서가 아니라, 어떤 구조 병목을 어떤 파라미터 축으로 다룰지 적는 문서로 작성한다.
- 시작점은 예시 문장 모음이 아니라 로그 증상 분류다. 먼저 `긴 문장 과결합`, `미확정 소절 잔류`, `조기 final`, `recent-final echo`, `queue residue` 중 어디에 속하는지 정한다.
- 증상을 정한 뒤에는 곧바로 문구 규칙을 추가하지 않고, 현재 계측값을 상위 축에 매핑한다. 예를 들어 `stage_replace_deferred`, `stage_revision_token_sentence_deferred`, `stage_finalize_right_context`, `stage_candidate_quality_blocked`, `stage_age_hold` 중 무엇이 주원인인지 먼저 적는다.
- 그 다음에만 파라미터 후보를 고른다. 소절 관리에서 우선 검토할 축은 `SENTENCE_CONFIRM_CHUNKS`, `SHORT_NO_END_FRAGMENT_UNITS`, `STAGED_QUEUE_MAX_PROMOTION_AGE_CHUNKS`, `DELTA_SUPPRESSED_STAGE_MAX_CHUNKS`, recent-final compact/echo 계열, revision similarity/confirmation preserve 계열이다.
- 문서에는 "이 문장을 자르기 위해 값을 바꾼다"가 아니라 "이 축을 바꾸면 어떤 구조 병목이 줄어야 한다"를 적는다. 예: `SHORT_NO_END_FRAGMENT_UNITS` 완화는 no-end 품질 차단 완화, `STAGED_QUEUE_MAX_PROMOTION_AGE_CHUNKS` 조정은 stale queue head 감소, `SENTENCE_CONFIRM_CHUNKS` 조정은 premature final 대 recall trade-off 검토다.
- 후보 파라미터는 한 번에 한 축만 바꾼다. 두 개 이상을 동시에 조정한 결과는 원인 해석 문서가 아니라 탐색 메모로만 남긴다.
- 채택 기준은 예시 문장 성공 여부가 아니라, strict subset과 상위 lifecycle metric의 동시 개선이다. `final_f1_avg`만 오르고 `boundary_f1`, `stage_age_quality_blocked`, `stage_replace_deferred`, 언어별 precision이 악화되면 채택하지 않는다.
- 기각 기준도 함께 적는다. 이미 sweep이나 실험일지에서 악화가 확인된 축은 같은 목적의 새 예외 패치 대신 "왜 재시도하지 않는지"를 명시한다.
- 따라서 소절 관리 패턴의 기본 형식은 `증상 -> 상위 메커니즘 -> 파라미터 축 -> 예상 trade-off -> sweep 결과 -> 채택/기각`이다.
