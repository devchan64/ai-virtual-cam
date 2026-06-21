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
- candidate buffer에 active staged 후보의 더 긴 token-sentence revision이 남아 있으면, active staged 후보가 age 기준에 도달해도 fragment final로 먼저 소비하지 않는다.
- STT text가 없는 chunk는 candidateAge 증가 근거로 사용하지 않는다.
- STT text가 없는 chunk가 반복되면 confirmation 기준을 만족하지 못한 staged 후보는 final로 승격하지 않고 stale 후보로 폐기할 수 있다.
- 이전 pending tail이 다음 completed 후보 앞에 붙어 기존 staged 문장의 revision처럼 보이는 경우, pending tail prefix는 final 후보에서 제거하고 staged 본문 기준으로 비교한다.
- CJK 문자 사이에 삽입된 STT 공백 artefact는 후보 품질 판단 전에 제거한다. 이는 문장 재작성이나 overlap 접합이 아니라 no-space 문자의 표준화이며, Latin/숫자 token 경계는 유지한다.
- revision 후보 비교에서 한 후보가 명확한 종결 경계를 가진 prefix 문장이고 다른 후보가 그 뒤에 짧은 tail을 붙여 하나의 문장처럼 만든 경우, 더 긴 문자열보다 종결 경계를 보존한 후보를 우선한다.
- 미확정 replacement는 기존 후보를 삭제하지 않고 새 후보를 candidate buffer에 보류한다. 앞 후보는 확정, revision 대체, 품질/중복 suppress 중 하나로 정리된 뒤에 다음 후보로 넘어간다. 단, 미확정 replacement와 충돌 중인 앞 후보는 age만으로 final 승격하지 않고, age 한계 전에는 즉시 suppress하지 않는다.
- 현재 chunk에서 candidate buffer로부터 승격된 staged 후보는 같은 chunk 안의 후속 replacement로 즉시 final 확정하지 않는다. 최소 다음 STT window에서 재평가해 stale queue burst가 false final로 소비되는 경로를 막는다.
- 같은 `revisionHash` 계열에서 나중 후보가 final로 소비되면, 이전 미소비 후보는 stale revision으로 폐기한다.
- 다른 revision 계열이라도 뒤 후보가 앞 후보의 의미 구간을 포함하거나 대체한 것이 확인되면, 앞 후보는 중복 소비 방지를 위해 폐기한다.
- 최근 final과 새 후보가 prefix 관계이고 새 suffix가 충분히 길면, 이미 final된 prefix는 다시 확정하지 않고 suffix만 새 후보로 회수할 수 있다. 짧은 suffix 보정은 echo로 보고 기존 중복 억제를 유지한다. 다만 이미 독립 staged 문장으로 확인된 후보를 committed-text delta가 종결부 없는 조각으로 만들면, append-only final 단위를 보존하기 위해 staged 원문을 final 후보로 유지한다.
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
| `candidateBuffer` 동작 | `stage_queue_enqueue`, `stage_queue_promote`, `stage_queue_revision`, `stage_queue_drop_oldest`, `stage_queue_recent_final_suppressed`, `stage_queue_recent_final_delta_trimmed`, `stage_replace_deferred`, `stage_replaced_unconfirmed`, `stage_age_finalize`, `stage_age_hold`, `stage_age_no_text_skipped`, `stage_no_text_stale_suppressed`, `candidate_prior_pending_prefix_trimmed` | 생성순서 보존, revision 갱신, 미확정 replacement 보류, 버퍼 소비 흐름이 의도대로 발생하는지 본다. `stage_replaced_unconfirmed`가 많이 발생하면 확정 전 후보 삭제로 인한 누락 가능성을 우선 검토한다. `stage_queue_recent_final_suppressed`는 이미 final된 이전 revision이 뒤늦게 queue에서 승격되지 않고 폐기된 관측값이다. `stage_queue_recent_final_delta_trimmed`는 queue 후보 중 recent final prefix 뒤의 의미 있는 suffix만 회수된 관측값이다. `stage_age_finalize`는 충분히 오래 관측된 staged 후보가 후속 후보보다 먼저 final로 소비된 관측값이다. `stage_age_hold`는 pending 확장으로 age 증가가 보류된 관측값이다. `stage_no_text_stale_suppressed`는 STT text가 없는 반복 구간에서 미확정 staged 후보가 final로 가지 않고 폐기된 관측값이다. `candidate_prior_pending_prefix_trimmed`는 pending prefix 오염 제거 관측값이다. |
| 커밋 품질 | `finalized_per_stage_start`, `segment_state_final`, `segment_state_suppressed`, `final_quality_*`, `candidate_recent_final_delta_trimmed`, `finalize_delta_suppressed_stage_retained`, `finalize_delta_suppressed_stage_dropped`, `finalize_delta_fragment_preserved` | final 전환 비율과 suppressed 사유로 중복/오염 후보 차단 여부를 본다. 최근 final prefix 뒤의 긴 suffix가 회수되는지와 짧은 echo 보정이 억제되는지도 함께 본다. delta가 broken fragment로 계산되면 active staged 후보를 잠시 유지하되, 반복 보류가 누락을 만들면 폐기하고 다음 후보로 진행한다. 단, 독립 staged 문장이 committed-text delta 때문에 종결부 없는 조각으로 바뀌는 경우는 `finalize_delta_fragment_preserved`로 관측하고 staged 원문을 보존한다. |
| final-only sink | `translation_skip_final_quality`, 번역 입력의 `final=true` 여부 | 번역 sink가 `CommittedTranscriptEvent` 외 입력을 소비하지 않는지 본다. |

### 불변 계약

- final transcript는 append-only이며 되돌리지 않는다.
- STT 원문창은 raw만 표시하고, 복사용 전사 창은 final만 표시한다.
- 번역 sink는 `CommittedTranscriptEvent`만 소비한다. staged/partial/pending은 번역하지 않는다.
- 최근 final과 같은 후보, recent-final echo, 순서가 섞인 후보는 다시 final로 확정하지 않는다. 단, 최근 final이 새 후보의 안정된 prefix이고 의미 있는 길이의 suffix가 추가된 경우에는 append-only 원칙에 따라 suffix만 새 후보로 회수할 수 있다.
- 외부 번역 backend 사용 시 Whisper는 `task=transcribe`만 수행하고 번역은 외부 번역 경로가 담당한다.
- 모델/장치/설정 오류는 자동 폴백하지 않고 실패한다. CUDA/float16 요구 경로에서 CPU fallback은 허용하지 않는다.
- 운영 파라미터와 모델/장치 허용값은 계약 기본값 문서를 따른다.
