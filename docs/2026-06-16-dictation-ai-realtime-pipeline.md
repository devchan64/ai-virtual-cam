# 받아쓰기 AI 실시간 처리 파이프라인 기준

## 문서 상태

이 문서는 받아쓰기 AI 실시간 처리 파이프라인의 기준 설계다. 기준은 2026-06-16 재설계 버전이며, 과거 실험에서 추가된 보정 시나리오와 튜닝 후보는 이 문서의 필수 구현 기준으로 취급하지 않는다.

커밋 기록 기반 실험 흐름은 [받아쓰기 AI 실험일지](2026-06-16-dictation-ai-experiment-log.md)에 두고, 설정 계약과 기본값은 [받아쓰기 AI 계약과 기본값](2026-06-16-dictation-ai-contract-defaults.md)에 둔다. 중국어 STT 후보 세부검증 판단은 [받아쓰기 AI 중국어 STT 후보 세부검증 리포트](2026-06-16-dictation-ai-chinese-stt-candidate-validation.md)에 둔다. 외부 논문, 모델 카드, 구현 링크는 [받아쓰기 AI 참조 레퍼런스 모음](2026-06-16-dictation-ai-reference-index.md)에 둔다.

## 핵심 문제 정의

실시간 ASR은 매 step마다 최근 오디오 window 전체를 다시 전사한다. 같은 음성 구간이 여러 window에 반복 포함되므로 raw STT window 결과를 그대로 사용자 출력이나 번역 입력으로 쓰면 다음 문제가 생긴다.

- 같은 문장이 여러 번 출력된다.
- 다음 window에서 이전 hypothesis가 수정된다.
- 문장 경계가 늦게 나오거나 흔들린다.
- 확정되지 않은 문장이 번역되어 중복 번역과 premature translation이 발생한다.

목표는 raw STT window 결과를 append-only final 문장으로 안정화하고, final 문장만 번역 큐에 넣는 것이다.

## 실시간 처리 파이프라인

```text
오디오 입력
  ↓
슬라이딩 윈도우 STT
  - 언어별 운영 backend 실행
  - raw STT window 결과 생성
  ↓
안정성/경계 판단
  - 여러 window에서 유지되는 token/char 구간 확인
  - SaT/SBD와 punctuation/right-context로 문장 경계 후보 생성
  ↓
세그먼트 생명주기
  - pending / staged / final / suppressed / revised
  - final은 append-only
  - 최근 final 저장소로 유사 final 재확정 억제
  ↓
final-only 번역
```

이 흐름에서는 "음성이 멈췄는가"보다 "토큰이 안정되었는가"와 "문장 경계 후보가 확인되었는가"가 우선이다.

## 적용 상태

| 단계 | 상태 | 기준 |
| --- | --- | --- |
| 오디오 입력 | 구현됨 | 설정된 입력 장치에서 오디오를 읽는다. 설정값이 유효하지 않으면 자동 폴백하지 않고 실패한다. |
| 슬라이딩 윈도우 STT | 구현됨 | `windowSeconds`, `stepSeconds` 기준으로 raw STT window 결과를 생성한다. |
| raw STT 표시 | 구현됨 | 원문창은 raw STT window 결과만 표시한다. staged/final 처리 결과와 섞지 않는다. |
| 안정성 판단 | 구현됨 | 여러 window에서 유지되는 token/char 구간을 관측한다. 이 신호는 staged 생명주기 판단 입력이다. |
| 경계 판단 | 구현됨 | SaT/SBD, punctuation/end-mark, right-context 지표로 completed/pending 후보를 생성한다. |
| 세그먼트 생명주기 | 구현됨 | `pending`, `staged`, `final`, `suppressed`, `revised` 상태를 분리한다. |
| append-only final | 구현됨 | final transcript는 되돌리지 않고 append-only로 출력한다. |
| 최근 final 중복 억제 | 구현됨 | 일정 기간 보관한 최근 final 문장과 확정 후보를 비교해 유사 후보의 중복 확정을 막고, 최근 final의 확장 후보는 새 suffix만 final로 넘긴다. |
| 짧은 CJK 확정 보류 | 구현됨 | 종결부호가 있는 짧은 CJK 후보는 다음 후보에 바로 밀려나지 않도록 제한적으로 더 보류해 반복 관측 confirmation을 채운다. |
| final-only 번역 | 구현됨 | 번역 큐에는 final 문장만 넣는다. staged/partial은 번역하지 않는다. |
| 과거 보정 경로 제거 | 구현됨 | 반복 phrase collapse, pending 강제 completed 승격, CJK 조기 replacement 확정 경로를 운영/벤치 기준에서 제거했다. |

## 폐기 범위

다음 항목은 재설계 기준의 필수 구현이 아니며 운영 기준에서 제외한다.

- pending/new overlap 접합 보정
- CJK no-space 내부 재시작 접합 보정
- completed 후보 재구성 또는 합성
- 반복 phrase collapse 기반 raw/completed/pending 재작성
- pending overrun을 completed 후보로 강제 승격하는 final trigger
- regex 기반 운영 문장 분할
- VAD/silence 기반 final trigger
- 케이스별 정규식 또는 언어별 ad-hoc 문장 보정
- staged/partial 번역
- CPU fallback 또는 실행 중 backend/model 자동 전환

detector 입력을 만들기 위한 단순 문자열 결합은 허용하지만, 의미 단위 재작성이나 경계 보정으로 확장하지 않는다.

## 출력 상태

| 상태 | 의미 | 화면 출력 | 번역 큐 |
| --- | --- | --- | --- |
| `raw` | 최신 STT window의 원시 전사 | 원문창 | 아니오 |
| `pending` | 아직 문장 경계 또는 안정성이 부족한 후보 | 진단 로그 | 아니오 |
| `staged` | completed 후보이나 재확인 전 상태 | 진단 로그 | 아니오 |
| `final` | 복사/번역 가능한 확정 문장 | 전사 창 | 예 |
| `suppressed` | 중복 또는 최근 final echo로 억제된 후보 | 아니오 | 아니오 |
| `revised` | 다음 window에서 수정된 staged 후보 | 진단 로그 | 아니오 |

정합성 규칙:

- raw STT window 결과는 사용자 final 출력으로 직접 append하지 않는다.
- final transcript는 append-only다.
- final로 확정한 문장은 UI와 번역 큐에서 되돌리지 않는다.
- 최근 final과 같은 후보는 다시 final로 확정하지 않는다.
- 최근 final의 확장 후보는 이미 확정된 prefix를 반복 출력하지 않고 새 suffix만 final로 확정한다.
- staged/partial 후보는 다음 window에서 수정될 수 있으므로 번역하지 않는다.
- STT 원문창은 raw 결과만 표시한다.
- 복사용 문장은 전사 창의 final 결과만 사용한다.

## 런타임 상태

| 상태/필드 | 의미 |
| --- | --- |
| `audio_buffer` | `windowSeconds` 기준 오디오 원본 |
| `last_window_text` | 직전 raw STT window 텍스트 |
| `pending_text` | 아직 확정되지 않은 후보 구간 |
| `committed_text` | 이미 final로 확정한 append-only 텍스트 |
| `recent_committed_fragments` | 최근 final echo 억제와 확장 후보 delta 산출을 위한 제한된 참조 저장소 |
| `sentence_boundary_detector` | STT 텍스트를 completed/pending 후보로 나누는 detector |
| `staged_sentence` | final 전 재확인 중인 completed 후보 |
| `staged_sentence_queue` | active staged 뒤에 순서대로 대기 중인 completed 후보 |
| `staged_confirmations` | 같은 후보가 재관측된 횟수 |
| `staged_age` | staged 상태로 남은 chunk 수 |
| `lifecycle_metrics` | 세그먼트 상태와 확정 흐름 관측 지표 |

## 문장 경계 처리

- 운영/설정 시나리오에서 regex 기반 문장 분할은 사용하지 않는다.
- 문장 경계 후보는 SaT/wtpsplit 같은 다국어 SBD 모델을 우선한다.
- SBD 결과가 completed 후보를 제안해도 즉시 final로 출력하지 않는다.
- final 승격은 staged confirmation, `sentenceFinalizeAge`, revision lifecycle이 담당한다.
- age와 confirmation은 문자열 완전 일치가 아니라 token-sentence 유사도와 revision 판단을 기준으로 누적한다.
- 종결부호가 있는 짧은 CJK 후보는 age만으로 바로 버리지 않고, 제한된 추가 보류 기간 동안 같은 후보 재관측을 기다릴 수 있다.
- 한 window에서 여러 completed 후보가 나오면 모델 경계 순서를 보존한다. active staged와 다른 CJK 후보는 버리지 않고 제한된 staged queue에 넣고, active가 final/suppressed 된 뒤 순서대로 승격한다.
- 같은 chunk에서 이미 revision/replacement로 age가 증가한 staged 후보는 추가 aging하지 않는다.
- punctuation/end-mark, right-context 시작 징후, soft boundary, end probability는 관측 지표로 기록한다.
- 여러 completed 후보가 한 window에서 나와도 모델 경계 단위를 보존한다.
- boundary backend/model은 명시 설정값만 사용한다. 실행 중 언어에 따라 암묵 전환하지 않는다.

## VAD와 무음 구간

VAD와 silence 길이는 받아쓰기 AI 실시간 처리 파이프라인의 구현 목표에서 제외한다.

이유:

- pause가 sentence boundary와 반드시 일치하지 않는다.
- 긴 발화에서는 명확한 silence가 드물다.
- 짧은 pause로 연결된 문장은 VAD가 안정적으로 구분하기 어렵다.
- 이 프로젝트의 final 기준은 텍스트 안정성, SBD, punctuation/right-context, staged confirmation이다.

따라서 VAD/무음 길이/발화 종료 예측은 final trigger, boundary confidence 보정, 번역 큐 투입 조건에 넣지 않는다.

## 번역 정책

- 번역 입력은 final 문장만 사용한다.
- staged/partial 번역은 운영 경로에서 사용하지 않는다.
- NLLB 선택 시 Whisper backend는 `task=transcribe`만 수행하고 번역은 NLLB 경로만 사용한다.
- 번역 backend/model/device/compute/beam/token 설정은 번역 대상 언어를 기준으로 결정한다.
- 번역 경로도 CUDA/float16 요구 시 CPU fallback을 허용하지 않는다.

## 운영 전제

- 실행 진입점은 `./bin/avc`다.
- `config`는 설정/GUI, `serve`는 저장된 설정 실행만 담당한다.
- config GUI의 `Serve 시작`으로 실행할 때만 받아쓰기 AI 전사/번역 창을 연다.
- 받아쓰기 AI 실행은 STT 모델, 문장 경계 모델, 번역 모델 준비가 끝난 뒤 오디오 입력 장치를 연다.
- Serve 런타임은 로컬 모델 캐시만 사용한다.
- 모델/장치/설정 오류는 자동 폴백하지 않고 실패한다.
- CUDA/float16이 요구되는 경로는 CPU fallback으로 계속 실행하지 않는다.
- config 오류는 모달뿐 아니라 stdout에도 출력한다.

## 운영 파라미터 기준

| 항목 | 영어/한국어 시작값 | 중국어 시작값 | 판단 기준 |
| --- | ---: | ---: | --- |
| `windowSeconds` | 7.0 | 12.0 | raw STT 안정성과 final 지연의 균형 |
| `stepSeconds` | 1.0 | 1.0 | 화면 갱신과 반복 처리량의 균형 |
| `sentenceFinalizeAge` | 3 | 2 | staged 후보 재관측 횟수 |
| `beamSize` | 3 | 3 | 정확도/지연 비교 시작점 |
| `temperature` | 0.0 | 0.0 | 재현성과 안정성 |
| `maxNewTokens` | 192 | 192 | 긴 문장 절단 방지 |
| `translationBeamSize` | 1 | 1 | 실시간 번역 시작점 |
| `translationMaxNewTokens` | 128 | 128 | 번역 지연 제어 |

성능 로그의 `stt_step_load` 또는 `total_step_load`가 1.0을 넘거나 `input_queue_drops`가 1 이상이면 실시간 처리량을 초과한 상태로 본다.

## 품질 지표와 테스트 분류

받아쓰기 AI 실시간 전사/번역 품질은 unittest 성공/실패만으로 판단하지 않는다.

하드 품질 게이트로 둘 수 있는 경우:

- 설정/계약/default 값처럼 입력과 출력이 명확한 public contract
- CPU fallback 금지, 번역 큐 final-only 같은 안전 정책
- 실패 시 사용자 출력이 즉시 오염되는 결정적 helper

성능 추적 하네스에 둬야 하는 경우:

- 누락/중복/확정 지연처럼 로그 분포에 따라 판단해야 하는 케이스
- STT 모델 출력 흔들림에 의존하는 케이스
- 파라미터 튜닝 근거용 케이스

핵심 관측 지표:

| 지표 | 의미 |
| --- | --- |
| `segment_state_pending/staged/final/suppressed/revised` | 세그먼트 상태 비율 |
| `finalized_per_stage_start` | staged 후보 대비 final 확정 비율 |
| `stage_queue_enqueue/promote/revision/drop_oldest` | 순서 보존 staged queue의 보존/승격/갱신/폐기 흐름 |
| `MAX_STAGED_SENTENCE_QUEUE=12` | sliding window에서 관측된 completed 후보를 순서대로 보존하는 최대 queue 크기 |
| `revision_similarity_policy` | token-sentence revision/confirmation 유사도 임계값 묶음. 운영 설정이 아니라 내부 튜닝 policy로 관리하며 SBD 벤치 리포트에 기록한다. |
| `stage_candidate_quality_low_value_cjk_fragment` | 문장 종료 부호 없는 CJK 초단편 후보 차단 횟수 |
| `stage_revision_age_reset`, `stage_queue_revision_age_reset` | 내용이 바뀐 CJK revision의 age 재시작 횟수 |
| `stage_replaced_unconfirmed` | 확정 전 교체된 staged 후보 |
| `raw_without_final` | raw STT 관측 대비 final 미발생 횟수 |
| `boundary_end_marks` | punctuation/end-mark 경계 신호 |
| `boundary_right_context_starts` | right-context 시작 경계 신호 |
| `stable_token_ratio` | 여러 window에서 유지되는 token/char 안정성 |
| `translation_skip_final_quality` | final-only 번역 안전장치 작동 여부 |
| `input_queue_drops` | 실시간 처리량 초과 여부 |

## 배포 기준

| 단계 | 기준 |
| --- | --- |
| RC 1 | raw/STT, staged/final, translation 입력이 분리되어 동작한다. |
| RC 2 | SaT/SBD 운영 경로가 CUDA/float16 Fail-Fast 정책을 지킨다. |
| GA 후보 | KO/EN/ZH에서 중복, 누락, 확정 지연 지표가 반복 측정에서 허용 범위 안에 있다. |

실패 대응:

- 백엔드 초기화/로딩/분절 실패는 CPU fallback 또는 regex fallback 없이 즉시 실패한다.
- 모델 다운로드가 필요한 경로는 Serve 시작 전에 사용자에게 알려야 한다.
- 다운로드/로딩 단계가 끝나기 전에는 오디오 입력 장치를 열지 않는다.
- 임계 지표가 악화되면 자동 rollback보다 원인 로그 수집과 운영자 판단을 우선한다.
