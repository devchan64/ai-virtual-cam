# 받아쓰기 AI 실험 프로토콜

## 목적

이 문서는 받아쓰기 AI 논문과 실험일지에서 사용할 실험 해석 기준을 고정한다. 목표는 raw STT 정확도 개선이 아니라, 흔들리는 실시간 STT window 결과를 문장 단위 final 이벤트로 안정화하고 final-only 번역 입력을 오염시키지 않는지 검증하는 것이다.

상세 설계는 [받아쓰기 AI 실시간 파이프라인](2026-06-16-dictation-ai-realtime-pipeline.md), 누적 실행 기록은 [받아쓰기 AI 실험일지](2026-06-16-dictation-ai-experiment-log.md), 외부 문헌 분류는 [받아쓰기 AI 논문 레퍼런스 원문 확인 컨텍스트](2026-06-20-dictation-ai-reference-context.md)를 따른다.

## 현재 결론

현재 1223건 `tests/eval/dictation_ai/sbd_cases/{en,ko,zh}/` 집합은 일반 운영 평균을 대표하지 않는다. 이 집합은 운영 로그에서 확정 누락, 중복 확정, boundary mismatch, staged residue가 반복 관측된 구간을 모은 failure-enriched challenge replay corpus다.

따라서 이 corpus는 다음 목적에는 유효하다.

- 같은 입력 집합에서 revision lifecycle 변경 전후 trade-off 비교
- 실패 증상별 회귀 감지
- 파라미터 후보의 채택/기각 근거 정리
- `raw STT`, `SBD 후보`, `revision lifecycle`, `final-only sink`의 실패 축 분리

다음 주장은 현재 corpus만으로는 하지 않는다.

- 일반 사용자 전체 입력의 평균 품질
- raw STT backend 자체의 WER/CER 개선
- 번역 BLEU, 번역 만족도, 사용자 체감 지연 개선
- 특정 threshold의 보편적 최적성

## 코드와 테스트 도메인

받아쓰기 AI 앱 로직의 품질관리 테스트와 논문/벤치 도구 테스트는 분리한다. `tests/unit/`은 앱 코드의 계약, 설정, 모델 준비, 파이프라인 단위 동작을 검증하는 유닛테스트만 둔다. 논문, evidence report, challenge replay case, representative case, structural preflight, parameter sweep을 관리하는 도구의 테스트는 `tests/eval/dictation_ai/tool_tests/`에 둔다.

이 분리는 결과 해석을 위한 안전장치다. `tool_tests`가 통과했다는 것은 논문/벤치 도구의 입출력 계약이 깨지지 않았다는 뜻이지, SBD 로직의 성능이 좋아졌다는 뜻이 아니다. 성능 근거는 계속 실제 `tests/eval/dictation_ai/sbd_benchmark.py`를 `sat + cuda + float16`로 실행한 report만 사용한다.

`tests/eval/dictation_ai/` 루트는 `sbd_benchmark.py` 단일 entrypoint만 유지한다. 기본 replay는 기존 benchmark options로 실행하고, sweep/case/paper/representative/structural 보조 작업은 같은 파일의 subcommand로 실행한다. 실제 구현은 `benchmark/`, `cases/`, `sweeps/`, `paper/`, `representative/`, `structural/` 하위 도메인으로 나눈다. 도메인 해석은 [tests/eval/dictation_ai/README.md](../tests/eval/dictation_ai/README.md)의 분류를 따른다. 새 보조 모듈은 루트에 추가하지 않고 하위 도메인으로 배치한다.

## 재구성한 최소 실험 설계

현재 자료를 기준으로 실험 설계는 다음 네 단계로 축소한다. 이 구조는 기존 실험을 폐기하지 않고, 각 자료가 감당할 수 있는 주장만 남기기 위한 재배치다.

| 단계 | 유지할 이유 | 산출물 | 논문 해석 |
| --- | --- | --- | --- |
| 로그 관측 | 실제 앱에서 반복된 확정 누락, 중복 확정, 문장 파괴를 식별한다. | 실패 후보, representative source 후보 | 문제 정의와 사례 근거 |
| challenge replay | 같은 실패 입력 집합에서 lifecycle 변경 전후를 재현 가능하게 비교한다. | 1223건 reviewed case, CUDA/SaT benchmark report | failure lifecycle trade-off |
| structural lifecycle check | threshold로 설명되지 않는 queue/revision/no-end/boundary 병목을 검증한다. | 구조 변경 전후 counter와 metric delta | 새 개선 후보의 제한적 근거 |
| representative/translation replay | 운영 평균과 downstream 번역 안정성을 별도로 검증한다. | 사람이 확정한 representative case, final/translation 연결 report | 준비 전까지 보류 |

이 설계에서 중심 질문은 `final_f1_avg`를 목표값까지 끌어올리는 것이 아니다. 중심 질문은 불안정한 STT window hypothesis가 `raw STT -> SBD 후보 -> revision lifecycle -> final-only sink`를 거치며 어디에서 중복, 누락, 경계 파괴를 만드는지 분리해 설명할 수 있는가다.

따라서 결과 해석은 다음 기준으로 고정한다.

- `challenge replay`의 낮은 평균 점수는 제품 전체 품질 실패가 아니라 실패 중심 입력의 난도를 뜻한다.
- `final_f1_avg`는 내용 회수율이고, 번역 단위 안정성은 `final_boundary_f1`, queue residue, staged residue를 함께 봐야 한다.
- threshold sweep은 부정 결과도 가치가 있다. 0 delta 또는 trade-off는 해당 축을 닫고 구조 병목으로 초점을 옮기는 근거다.
- representative corpus가 없으면 운영 평균, 실제 latency, 사용자 체감 품질을 주장하지 않는다.
- translation replay가 없으면 final-only sink는 시스템 계약이지 번역 품질 개선 결과가 아니다.

## 가설 상태

현재 논문 가설은 "raw STT 정확도를 높였다"가 아니라 "흔들리는 STT window hypothesis를 final-only 번역 입력으로 소비하려면 revision-aware lifecycle과 corpus 역할 분리가 필요하다"로 고정한다.

| 가설 | 현재 상태 | 근거 | 다음 증거 |
| --- | --- | --- | --- |
| partial hypothesis를 바로 final로 소비하면 중복/누락/문장 파괴가 발생한다. | 유지 | 운영 로그와 1223건 challenge replay의 `missing-final`, `duplicate-final`, `stage-queue`, `boundary-mismatch` 케이스 | 새 로그 case가 늘어도 같은 실패 축이 재현되는지 확인 |
| `raw STT`, `SBD 후보`, `revision lifecycle`, `final-only sink`를 분리 계측해야 원인을 설명할 수 있다. | 유지 | lifecycle counter, evidence strata, queue residue strata가 평균값 뒤의 병목을 분리한다. | representative corpus와 translation replay에서도 같은 계층 분리가 유효한지 확인 |
| 단일 threshold 튜닝으로 `final_f1_avg`를 크게 끌어올릴 수 있다. | 축소 | 12개 manifest 축 대부분이 0 delta 또는 precision/recall/boundary trade-off를 만든다. | 새 구조 변경이 나오기 전까지 추가 미세 sweep 우선순위 낮음 |
| 현재 challenge replay 평균으로 운영 평균 품질을 주장할 수 있다. | 폐기 | 1223건은 failure-enriched challenge replay이며 무작위/시간 표본이 아니다. | representative `time-window`/`session-window` corpus 필요 |
| final-only sink가 번역 안정성을 높인다. | 보류 | speech translation segmentation 문헌과 시스템 계약상 타당하지만 현재 수치는 SBD/finalization replay에 한정된다. | final event timestamp와 translation output replay 필요 |

## 실험 설계 재구성 판단

현재까지의 실험은 "단일 점수를 계속 올리는 최적화 실험"으로는 의미가 약하다. 1113건 challenge replay에서 여러 threshold 축을 실제 `sat + cuda + float16`로 재검증한 결과, 대부분의 값은 metric을 움직이지 않거나 precision/recall/boundary trade-off를 만든다. 따라서 이 자료를 `final_f1_avg` 목표 달성 실험으로 해석하면 논문 주장이 불안정해진다.

반대로 다음 구조로 재구성하면 실험의 의미가 분명하다.

1. `challenge-replay`: 운영 로그에서 관측된 실패를 재현하고, revision lifecycle 변경이 확정 누락/중복 확정/staged residue/boundary mismatch를 어떻게 움직이는지 비교한다.
2. `parameter-axis evidence`: 한 번에 한 파라미터 축만 baseline과 비교해 채택/기각 근거를 남긴다. 이 결과는 보편 최적값이 아니라 현재 failure corpus에서의 trade-off 증거다.
3. `representative`: 시간 또는 세션 단위 표본으로 운영 평균을 추정한다. challenge replay 평균과 섞지 않는다.
4. `translation replay`: final event timestamp와 번역 출력을 연결해 final-only sink가 downstream 번역 churn을 줄이는지 별도 검증한다.

즉 현재 자료의 핵심 가치는 "raw STT 정확도 개선"이나 "운영 평균 성능"이 아니라, 흔들리는 STT partial을 final-only 번역 입력으로 만들 때 필요한 실패 축 분리와 lifecycle 계측에 있다.

따라서 현재 실험 설계의 결론은 "폐기"가 아니라 "역할 축소와 재배치"다. 기존 challenge replay는 논문의 중심 실험으로 유지하되, 성능 일반화 자료가 아니라 실패 재현 및 구조 병목 분석 자료로만 사용한다. `final_f1_avg` 목표치를 계속 올리는 방식은 중단하고, threshold sweep은 채택/기각 근거가 필요한 축에서만 제한적으로 수행한다. 논문 기여는 특정 threshold 최적값이 아니라, 불안정한 STT hypothesis를 final-only sink로 보내기 전 어떤 상태와 지표를 분리해야 하는지 보여주는 실험 프로토콜이다.

재구성 판단을 요약하면 다음과 같다.

| 항목 | 유지 여부 | 이유 |
| --- | --- | --- |
| 1113건 challenge replay | 유지 | 실제 로그에서 반복된 확정 누락, 중복 확정, boundary mismatch를 재현한다. |
| 단일 `final_f1_avg` 목표 달성 실험 | 폐기 | 케이스가 failure-enriched라 평균값이 운영 품질을 대표하지 않고, threshold별 trade-off가 크다. |
| parameter sweep | 축소 | 기본값 채택/기각 기록에는 유효하지만, 논문 핵심 기여로 두지 않는다. |
| structural lifecycle check | 강화 | `stage_replace_deferred`, `stage_queue_revision`, queue residue, boundary collapse가 남은 병목을 설명한다. |
| representative replay | 신규 필요 | 운영 평균 품질과 latency 주장을 하려면 시간/세션 표본이 별도로 필요하다. |
| translation replay | 신규 필요 | final-only sink가 번역 churn을 줄였다는 주장은 번역 출력 로그 연결 전까지 보류한다. |

## 반복 실험의 현재 판정

현재까지의 반복 실험은 받아쓰기 AI 로직 변경 지점을 직접 찾은 것이 아니라, 단일 파라미터 튜닝으로 설명 가능한 개선축이 대부분 닫혔음을 확인한 것으로 해석한다. 표준 complete paper-evidence package 기준으로 report 23개, 고유 parameter axis 12개가 있고, `hypothesis_status_counts={유지:2, 축소:2, 폐기:8}`이다. baseline은 1113건 challenge replay에서 `final_precision_avg=0.601920572081`, `final_recall_avg=0.439944451819`, `final_f1_avg=0.483242163472`, `final_boundary_f1_avg=0.107749021040`, `finalized_per_stage_start=0.711599858106`로 일관된다.

축별 결과는 다음처럼 읽는다.

| 관측 | 해석 |
| --- | --- |
| 대부분의 confirm/max-age/forced/no-text/CJK hold 축은 metric delta가 0 또는 매우 작다. | 해당 상수만 바꾸는 실험은 현재 failure corpus에서 의미 있는 로직 변경 근거가 아니다. |
| `SENTENCE_CONFIRM_CHUNKS=1`은 `final_f1`과 recall을 올리지만 precision을 크게 낮춘다. | 확정을 빠르게 하는 단일 정책은 중복/오확정 위험을 키우므로 채택 근거가 아니다. |
| `REVISION_FALLBACK_COVERAGE_MIN`, `SHORT_NO_END_FRAGMENT_UNITS`, 일부 CJK/queue 축은 regression flag가 붙는다. | 누락을 줄이려는 완화가 boundary 또는 precision 손실로 전이된다. |
| complete report의 `state_machine_parity=partial`이고 audio timestamp, translation linkage가 replay에 없다. stable internal overlap은 현재 text replay에서 재계산하지만, 과거 complete report는 재생성 전까지 이전 계약을 따른다. | 현재 replay만 반복해서는 운영 loop의 구체 로직 변경 지점을 단정할 수 없다. |

따라서 현 상태에서 새 앱 로직 변경을 바로 넣는 것은 근거가 약하다. 다음 개선 후보는 더 많은 threshold sweep이 아니라 다음 두 방향 중 하나여야 한다.

1. structural lifecycle preflight: `stage-queue`, `staged-residue`, `boundary-mismatch`, `no-end-final`이 큰 exploratory subset에서 후보 소비 순서, revision 보류/확정, final 직전 boundary 보존 같은 상태 전이 변경을 작게 검증한다. 이 결과는 전체 1113건 challenge replay 재검증 전까지 논문 수치로 쓰지 않는다.
2. runtime signal 보강: text replay가 빠뜨리는 audio timestamp latency, translation request/output linkage를 연결해 운영 loop에서만 보이는 병목을 찾는다.

즉 현재 결론은 "로직 변경 지점이 없다"가 아니라 "현재 반복한 파라미터 실험만으로는 로직 변경 지점을 찾지 못했으며, 새 변경은 구조 병목 preflight 또는 runtime signal 보강으로 원인을 좁힌 뒤에만 수행한다"이다.

참조 논문과의 비교도 이 범위에 맞춰 제한한다.

| 참조 축 | 논문에서 가져올 수 있는 의미 | 현재 실험이 보태는 의미 |
| --- | --- | --- |
| Whisper-Streaming | 확정 prefix와 미확정 hypothesis를 분리해야 한다. | prefix agreement만으로 설명하기 어려운 문장 단위 final, duplicate suppression, staged residue를 앱 로그 replay로 계측한다. |
| Incremental ASR 평가 | WER 외 latency/update/revoke/stability가 필요하다. | final F1, boundary F1, lifecycle counter, duplicate/staged residue를 함께 남기는 실험 포맷을 제시한다. |
| SaT / punctuation | rule/regex 대신 모델 기반 문장 경계 후보와 right context가 필요하다. | SaT 후보가 final 결정 자체는 아니며, revision lifecycle과 결합해야 함을 실패 replay로 보인다. |
| Speech translation segmentation | 번역 단위가 downstream 품질에 영향을 준다. | final-only 번역 sink를 별도 검증 대상으로 분리한다. 현재 challenge replay만으로 번역 품질 개선은 주장하지 않는다. |
| Qwen3-ASR / NLLB | STT/번역 backend 후보의 배경을 제공한다. | backend 성능과 final lifecycle 품질을 분리해, raw STT 오류가 있어도 final 입력 안정화 실험을 진행한다. |

따라서 후속 실험은 단순 threshold sweep을 계속 늘리기보다 representative 표본 구축, final timestamp/translation replay 연결, 그리고 challenge replay에서 반복적으로 보이는 active staged/candidate queue 병목을 작은 구조 변경으로 검증하는 순서가 타당하다.

현재 실험 설계의 유효성은 다음처럼 판단한다.

| 판단 항목 | 결론 | 이유 |
| --- | --- | --- |
| 문제 정의 | 유효 | 운영 로그와 challenge replay 모두 partial hypothesis를 바로 final로 소비할 때 중복, 누락, 문장 파괴가 반복됨을 보여준다. |
| 핵심 실험 단위 | 조건부 유효 | `chunks -> SBD 후보 -> lifecycle -> final` replay는 finalization 계층 검증에 적합하지만, raw ASR 정확도나 운영 평균을 대표하지 않는다. |
| 주요 지표 | 유효 | `final_f1`과 `final_boundary_f1`의 격차, queue residue, lifecycle counter가 서로 다른 병목을 분리한다. |
| threshold 최적화 | 중심 실험으로 부적합 | 12개 축 대부분이 0 delta 또는 precision/recall/boundary trade-off를 만들었으므로 새 중심 기여가 되기 어렵다. |
| 참조 논문 연결 | 유효하되 제한 필요 | Whisper-Streaming, incremental ASR, SaT/punctuation 문헌은 계층 분리와 stability 평가의 필요성을 뒷받침하지만, 앱의 개별 threshold 값을 정당화하지 않는다. |
| 논문 기여 | 재구성 필요 | "성능을 크게 올렸다"가 아니라 "실패 중심 로그 replay로 finalization 병목을 분리하고, 어떤 주장을 보류해야 하는지 드러냈다"로 써야 한다. |

따라서 실험방법은 과감하게 재구성한다. 첫째, challenge replay는 논문의 중심 자료로 유지하되 실패 재현과 병목 분석에만 사용한다. 둘째, parameter sweep은 부정 결과를 포함한 채택/기각 근거로 축소한다. 셋째, 새 개선 주장은 structural lifecycle check에서만 만든다. 넷째, 운영 평균과 번역 안정성은 representative replay와 translation replay가 준비되기 전까지 논문 결론으로 승격하지 않는다.

## 논문 주장 재배치

현재 자료를 논문에 사용할 때는 "성능 개선 논문"보다 "실시간 STT partial을 final-only 번역 입력으로 안정화하기 위한 실험 프로토콜과 실패 축 분석"으로 배치한다. 이 배치는 참조 논문과도 충돌이 적다. Whisper-Streaming과 incremental ASR 평가는 partial/committed output 분리와 stability 평가의 필요성을 뒷받침하고, SaT/streaming punctuation은 문장 후보 생성 배경을 제공하며, speech translation segmentation 문헌은 번역 단위가 downstream 품질에 영향을 줄 수 있다는 문제 설정만 제공한다. 반대로 이 문헌들은 현재 앱의 `sentenceFinalizeAge`, queue 크기, no-end threshold를 직접 정당화하지 않는다.

논문 본문에서 사용할 수 있는 주장은 다음처럼 제한한다.

| 주장 | 현재 판정 | 논문 사용 방식 |
| --- | --- | --- |
| 불안정한 STT window hypothesis를 바로 final로 소비하면 중복/누락/문장 파괴가 발생한다. | 사용 가능 | 운영 로그 예시와 challenge replay case로 문제 정의를 뒷받침한다. |
| SBD 후보 생성과 final lifecycle은 분리해 계측해야 한다. | 사용 가능 | `final_f1`, `final_boundary_f1`, lifecycle counter, queue residue 격차를 핵심 결과로 제시한다. |
| 단일 threshold sweep으로 목표 성능을 달성할 수 있다. | 사용 금지 | 12개 축 결과가 대부분 0 delta 또는 trade-off였다는 부정 결과로만 쓴다. |
| challenge replay 평균이 운영 평균 품질을 대표한다. | 사용 금지 | failure-enriched corpus의 한계로 명시하고 representative replay를 후속 실험으로 분리한다. |
| final-only sink가 번역 품질을 개선했다. | 보류 | 시스템 계약과 후속 translation replay 필요성으로만 다룬다. |
| raw STT backend 정확도를 개선했다. | 사용 금지 | 본 연구 범위 밖으로 둔다. raw STT 오류가 있어도 finalization 계층을 평가한다는 문제 설정에만 사용한다. |

따라서 결과 해석은 "최신 기준선의 `final_f1_avg=0.483`이 낮다"가 아니라, "실패 중심 로그 replay에서 내용 회수율과 문장 경계 품질이 분리되고, lifecycle counter가 queue/revision/no-end 병목을 설명한다"로 정리한다. 이 해석이면 낮은 점수도 논문을 약화시키는 값이 아니라, 현재 실험 corpus가 어려운 실패 구간이라는 사실과 남은 구조 병목을 보여주는 값이 된다.

주장별 현재 근거 상태는 다음과 같이 고정한다. 이 표는 논문 초안의 각 주장이 어떤 artifact에 기대고 있는지 확인하기 위한 claim-evidence matrix다.

| 주장 | 현재 근거 | 현재 판정 | 추가 필요 증거 |
| --- | --- | --- | --- |
| partial hypothesis와 final transcript를 분리해야 한다. | 운영 로그 사례, 1113건 challenge replay, Whisper-Streaming/incremental ASR 문헌 | 사용 가능 | representative에서도 같은 실패축이 관측되는지 확인 |
| SBD 후보와 final lifecycle은 별도 계층으로 평가해야 한다. | `final_f1_avg=0.483`, `final_boundary_f1_avg=0.108`, lifecycle counter, queue residue strata | 사용 가능 | representative replay의 boundary/queue strata |
| threshold 단일 튜닝은 중심 개선축이 아니다. | complete evidence report 23개, 고유 parameter axis 12개, `hypothesis_status_counts={유지:2, 축소:2, 폐기:8}` | 사용 가능 | 새 구조 변경 후에도 닫힌 축이 다시 열리는지 확인 |
| current baseline은 실패 중심 입력에서 재현 가능한 기준선이다. | 기존 `sat + cuda + float16` complete report 23개. 현재 evidence 계약에서는 `lifecycle_replay_contract.replayed_runtime_signals`가 추가되어 이 report들은 재실행 후보로 분류된다. | 보류 | 최신 계약으로 complete report 재생성 |
| 운영 평균 품질을 개선했다. | 없음. representative root에는 아직 정식 JSONL case 없음 | 사용 금지 | 사람이 확정한 representative case와 validator summary |
| final-only sink가 번역 안정성을 높였다. | 시스템 계약과 speech translation segmentation 배경만 있음 | 보류 | final event, translation request id, translation output replay |
| raw STT 모델 정확도를 개선했다. | 없음. 현재 입력은 STT window hypothesis replay | 사용 금지 | 별도 참조 전사와 ASR CER/WER 평가 |

기존 evidence inventory 기준으로 전체 report 재고에는 exploratory/incomplete 결과가 섞여 있었다. 당시 `sbd_benchmark.py validate-evidence --complete-only --summary-only` 기준 전체 report는 135개이고, complete paper-evidence report는 23개였다. 이 23개 subset은 `experiment_stage=challenge-replay`, `claim_scope_key=failure-lifecycle-tradeoff`로만 구성되며 `complete_mixed_experiment_stage=false`, `complete_mixed_claim_scope_key=false`였다. 다만 현재 evidence 계약은 `lifecycle_replay_contract.replayed_runtime_signals`를 필수 필드로 추가했으므로, 같은 report들은 새 validator 기준에서 재실행 후보로 분류된다. 논문 본문에 새 수치를 직접 옮길 때는 최신 계약으로 complete report를 재생성해야 하며, 나머지 exploratory/incomplete report는 실험 설계나 후속 후보를 설명할 때만 사용한다.

논문 표 작성에 사용할 표준 evidence package 산출물은 다음 두 파일로 고정한다.

- `.tmp/eval/dictation-ai-sbd/parameter-sweeps/complete-paper-evidence-summary.json`
- `.tmp/eval/dictation-ai-sbd/parameter-sweeps/complete-paper-evidence-summary.md`

이 파일은 다음 명령으로 재생성한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py summarize-evidence \
  .tmp/eval/dictation-ai-sbd/parameter-sweeps \
  --complete-only \
  --summary-output .tmp/eval/dictation-ai-sbd/parameter-sweeps/complete-paper-evidence-summary.json \
  --markdown-output .tmp/eval/dictation-ai-sbd/parameter-sweeps/complete-paper-evidence-summary.md
```

같은 성격의 임시 summary가 `.tmp/eval/dictation-ai-sbd/` 바로 아래에 있더라도, 논문 본문과 실험일지는 위 표준 경로의 값을 기준으로 인용한다. 표준 summary를 갱신한 뒤에는 `sbd_benchmark.py validate-evidence --complete-only --summary-only` 결과의 `complete_report_count`, `complete_experiment_stage_counts`, `complete_claim_scope_key_counts`, `complete_mixed_*` 값을 함께 확인한다.

표준 summary JSON과 Markdown은 `case_set_summary`, `baseline_metric_summary`, `paper_claim_matrix`, `lifecycle_replay_summary`도 포함한다. `case_set_summary`는 complete report들이 같은 case 집합과 언어 분포를 사용했는지 확인하고, `baseline_metric_summary`는 complete report들의 baseline metric이 같은 값인지 확인해 논문에 옮길 반올림 수치의 기준값을 제공한다. `paper_claim_matrix`는 complete evidence package가 각 논문 주장에 대해 `사용 가능`, `보류`, `사용 금지` 중 어떤 상태인지 자동으로 남긴다. `lifecycle_replay_summary`는 complete report 전체의 replay parity, 운영 loop 상태 소유자, benchmark replay 상태 소유자, replay에 없는 runtime signal을 집계한다. 논문 초안에 새 주장을 추가하거나 abstract 표현을 바꿀 때는 먼저 이 행렬의 상태와 `required_next_evidence`를 확인하고, 모든 complete report가 `state_machine_parity=partial`이면 운영 loop와 동일 검증을 했다고 쓰지 않는다. 이 금지는 `paper_claim_matrix.runtime_loop_equivalence` 행에도 별도 claim으로 남긴다.

논문 초안을 수정한 뒤에는 다음 audit으로 금지/보류 claim의 방어 문장이 남아 있는지 확인한다. 이 도구는 문장 의미를 완전히 판정하지 않고, `paper_claim_matrix`에서 `사용 금지` 또는 `보류`인 주요 claim에 대응하는 안전 문구가 초안에 존재하는지만 확인한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py paper-claim-scope \
  --summary .tmp/eval/dictation-ai-sbd/parameter-sweeps/complete-paper-evidence-summary.json \
  --paper docs/paper/ko-revision-aware-realtime-stt.md
```

비교군 문헌을 논문에 직접 넣을 때는 다음 audit으로 범위 방어 문장이 남아 있는지도 확인한다. 이 도구는 현재 `Optimizing Sentence Segmentation for Speech Translation`처럼 비교군으로만 허용한 문헌이 직접 구현 근거처럼 읽히지 않도록 guard phrase를 요구하고, 원문 확보 실패 또는 범위 밖으로 분류한 URL이 초안에 들어오면 실패한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py paper-reference-scope \
  --paper docs/paper/ko-revision-aware-realtime-stt.md
```

논문 초안의 기준선 metric 숫자, report 수, case 수, 언어별 case 수를 수정하거나 표준 summary를 재생성한 뒤에는 다음 audit으로 본문에 남은 수치가 `baseline_metric_summary`와 `case_set_summary`에 일치하는지도 확인한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py paper-evidence-numbers \
  --summary .tmp/eval/dictation-ai-sbd/parameter-sweeps/complete-paper-evidence-summary.json \
  --paper docs/paper/ko-revision-aware-realtime-stt.md
```

논문 초안과 표준 evidence package를 함께 점검할 때는 다음 통합 audit을 사용한다. 이 audit은 complete report 재고, claim guard, evidence number, reference scope, follow-up readiness를 한 번에 확인한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py paper-readiness \
  .tmp/eval/dictation-ai-sbd/parameter-sweeps \
  --summary .tmp/eval/dictation-ai-sbd/parameter-sweeps/complete-paper-evidence-summary.json \
  --paper docs/paper/ko-revision-aware-realtime-stt.md \
  --source-audit .tmp/eval/dictation-ai-sbd/representative-source-audit.json \
  --review-packet-validation .tmp/eval/dictation-ai-sbd/representative-source-review-packets.validation.json \
  --representative-cases tests/eval/dictation_ai/sbd_representative_cases \
  --review-packets .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json \
  --representative-draft-validation .tmp/eval/dictation-ai-sbd/representative-case-drafts.validation.json \
  --structural-preflight-validation .tmp/eval/dictation-ai-sbd/structural-lifecycle-cases.validation.json \
  --summary-output .tmp/eval/dictation-ai-sbd/paper-readiness.json
```

`current_claim_scope=challenge-replay-only`이면 현재 초안은 failure lifecycle trade-off 범위의 논문 근거로만 해석한다. 이 상태에서 `followup_readiness.paper_evidence_ready=false`가 함께 나오면 representative/translation 관련 성능 주장은 계속 보류한다. `representative_draft_traceable=true`는 사람이 채울 draft 템플릿이 준비됐다는 뜻이지, representative paper evidence가 준비됐다는 뜻이 아니다.

통합 audit의 `methodology_decision`은 현재 실험 방법을 어떻게 읽어야 하는지 구조화해 남긴다. `primary_interpretation=failure-enriched challenge replay lifecycle analysis`이고 `challenge_replay_valid=true`이면 현재 complete report는 실패 농축 challenge replay의 lifecycle trade-off 근거로는 유효하다. 이 판정은 `checks.methodology`에도 포함되므로, complete report의 `experiment_stage`나 `claim_scope_key`가 challenge-only 논문 범위와 섞이면 readiness는 실패해야 한다. 동시에 `recommended_next_experiment=human-review representative expected_final labels`이면 다음 주요 실험은 새 threshold sweep이 아니라 사람이 확정한 representative case 승격이다. `translation_next_experiment=build translation replay linkage before translation claims`가 남아 있는 동안 final-only sink의 번역 안정성은 시스템 계약과 후속 실험 필요성으로만 다룬다. `translation_next_experiment=run translation replay`이면 final/translation 연결은 준비된 상태지만, 아직 번역 안정성 성능 주장으로 승격된 것은 아니다.

`structural_preflight.ready=true`이면 queue/revision/boundary 병목을 빠르게 재현할 exploratory subset이 준비됐다는 뜻이다. 이 값은 `paper_evidence=false`로 유지되며 readiness의 `ok`를 올리거나 논문 claim scope를 넓히지 않는다. 구조 변경 후보가 이 subset에서 좋아 보이면 전체 1113건 challenge replay를 실제 `sat + cuda + float16`로 다시 실행해 paper evidence로 승격할지 판단한다.

`structural_preflight.ready=true`는 실행 완료가 아니다. 이 값은 단지 실행 가능한 단일 JSONL 입력과 검증된 case metadata가 준비됐다는 뜻이다. 실제 결과가 없으면 로직 변경 여부를 판단하지 않는다. CUDA 실행이 불가능한 환경에서는 CPU, mock, smoke 결과로 대체하지 않고 `not-run`으로 기록한다.

readiness 출력은 structural preflight 상태를 다음 필드로 분리한다.

| 필드 | 의미 |
| --- | --- |
| `ready` | 단일 JSONL source, exploratory role, reviewed expected final이 있어 실행 입력이 준비됐다는 뜻이다. |
| `execution_status` | `input-not-ready`, `input-ready-not-run`, `result-present` 중 하나다. |
| `expected_result_path` | CUDA preflight가 써야 하는 결과 JSON 경로다. |
| `result_exists` | `expected_result_path`에 결과 파일이 실제로 있는지 여부다. |

따라서 `ready=true`이고 `execution_status=input-ready-not-run`이면 아직 결과가 없으므로 로직 변경 판단을 보류한다. `execution_status=result-present`여도 subset 결과는 exploratory이며, 전체 challenge replay 재검증 전에는 논문 수치가 아니다.

structural preflight 결과는 다음 게이트를 모두 통과해야만 전체 challenge replay 재검증 후보가 된다.

| 게이트 | 판단 기준 |
| --- | --- |
| 실행 계약 | `sat + cuda + float16`, offline cache, 실제 `sbd_benchmark.py` 실행이어야 한다. |
| 입력 계약 | validation summary의 단일 `sources`와 실행 `--cases`가 같아야 한다. |
| 결과 해석 | `final_f1`만 보지 않고 `final_boundary_f1`, `stage-queue`, `staged-residue`, `missing-final`, `false-final`, `translation-skip` counter를 함께 본다. |
| 승격 조건 | subset에서 좋아 보여도 전체 1113건 challenge replay를 `--paper-evidence`로 다시 실행하기 전에는 논문 수치가 아니다. |
| 실패 처리 | CUDA 접근 불가, 모델 cache 불일치, runtime contract 위반은 결과 없음으로 기록하고 대체 벤치를 만들지 않는다. |

`methodology_decision.available_next_experiments`는 후속 작업을 역할별로 분리한다. `paper-evidence expansion`은 사람이 representative `expected_final`을 확정해야 진행되고, `translation claim expansion`은 final event와 translation output linkage가 있어야 진행된다. linkage가 준비되면 `blocked_by`가 비고 다음 실험 이름은 `run translation replay`가 된다. `logic-change preflight`는 structural exploratory subset이 준비됐을 때 사람 라벨링 없이도 시작할 수 있지만, 이 결과는 전체 challenge replay 재실행 전까지 논문 성능 근거가 아니다. 이 항목에는 `case_path`, `preflight_command`, `full_challenge_replay_command`, `promotion_requirement`를 함께 남겨 어떤 입력으로 preflight를 실행하고, 어떤 전체 재검증을 통과해야 paper evidence로 승격할 수 있는지 명확히 한다.

## Representative 승격 조건

representative source audit과 review packet은 논문 근거가 아니라 사람이 참조 전사를 만들기 위한 준비물이다. 대표 표본은 다음 승격 게이트를 통과한 뒤에만 benchmark와 논문 표에 포함한다.

| 단계 | 산출물 | 허용 해석 |
| --- | --- | --- |
| source audit | 로그 보존량, 이벤트 종류, runtime 후보 | representative 후보를 seed할 수 있는지 |
| source manifest | 언어별 선택 source 목록 | 사람이 검토할 구간 선정 |
| review packet | raw STT, final event, transcript, performance 샘플 | 참조 전사 작성 보조 |
| draft case | 빈 `expected_final`을 가진 `.tmp` JSONL | 수작업 템플릿 |
| reviewed case | 사람이 `expected_final`을 채운 representative shard | 운영 평균 추정 실험 입력 |

reviewed case로 승격하려면 `expected_final`과 `expected_final_reviewed_by`가 비어 있지 않아야 하고, `draft_expected_final_required`가 남아 있으면 안 된다. 또한 `expected_final_generated=false`를 유지해 자동 생성 정답이 아니었음을 남긴다. 정식 case를 만든 뒤에는 `validate_sbd_case_files.py --review-packets`로 `review_packet_id`, `source_log`, `language` 추적성을 확인한다.

review packet은 manifest의 `source_started_at`과 `source_ended_at` 범위 안 이벤트만 담아야 한다. packet의 `source_window_filter.applied=true`와 시작/종료 timestamp를 확인해 사람이 참조 전사를 작성할 범위가 로그 전체로 확장되지 않았는지 점검한다. 이 필터가 없거나 범위가 비어 있는 packet은 사람이 추가로 bounded window를 정한 뒤 representative case로 승격한다.

이 조건이 만족되기 전에는 `ready_packet_count=5` 같은 수치도 "case 준비 완료"가 아니라 "사람 검토 가능 packet 준비"로만 해석한다. 즉 현재 상태에서 논문 claim scope는 계속 `challenge-replay-only`다.

## 재구성한 실험 방법

현재 실험은 다음 세 단계로 재구성한다. 각 단계는 서로 다른 주장을 담당하므로 결과표를 합치지 않는다.

| 단계 | 목적 | 입력 | 통과 기준 | 금지 해석 |
| --- | --- | --- | --- | --- |
| 1. challenge replay | 실패 재현과 lifecycle trade-off 비교 | `sbd_cases/{en,ko,zh}`의 reviewed case | 같은 case set baseline 대비 언어별/태그별 악화가 설명 가능해야 한다. | 운영 평균 품질, 보편 threshold 최적성 |
| 2. structural lifecycle check | threshold로 설명되지 않는 queue/revision 병목 검증 | challenge replay 중 queue/residue/exemplar가 큰 case와 전체 challenge set | `final_f1`뿐 아니라 queue residue, deferred replacement, boundary F1이 같은 방향으로 개선되어야 한다. | 특정 문구/언어 예외 규칙 채택 |
| 3. representative replay | 운영 평균 추정 | 시간/세션 단위 sampled case | sampling metadata와 expected final이 모두 있고, challenge 결과와 별도 표로 제시되어야 한다. | 실패 corpus 평균과의 직접 합산 |

구조 변경 실험은 threshold sweep과 다르게 취급한다. threshold sweep은 이미 존재하는 정책의 보수성 수준을 흔드는 실험이고, 구조 변경은 후보 소비 순서, revision 계열 판정, final 직전 boundary 보존처럼 lifecycle 상태 전이를 바꾸는 실험이다. 구조 변경은 다음 질문에 답해야 한다.

- 어떤 lifecycle counter가 병목이라고 판단했는가?
- 변경 후 해당 counter가 줄었는가, 아니면 다른 counter로 이동했는가?
- `final_f1_avg` 개선이 `final_precision_avg` 또는 `final_boundary_f1_avg` 하락으로 상쇄되지 않는가?
- `lifecycle_without_input_review`에서도 같은 결론이 유지되는가?
- representative corpus가 준비되면 운영 평균에서 같은 방향이 유지되는지 확인할 수 있는가?

이 기준을 만족하지 못하는 구조 변경은 논문 기여가 아니라 탐색 기록으로만 남긴다.

구조 실험 후보는 기존 CUDA benchmark report에서 다음 도구로 뽑는다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py select-structural-cases \
  .tmp/eval/dictation-ai-sbd/20260621-protocol-baseline.json \
  --limit 16 \
  --case-output .tmp/eval/dictation-ai-sbd/structural-lifecycle-cases.jsonl \
  --markdown-output .tmp/eval/dictation-ai-sbd/structural-lifecycle-cases.md
```

이 도구는 report의 `case_exemplar_summary`, `staged_queue_residue_summary`, per-case lifecycle metric을 사용해 queue/revision/boundary 병목 후보를 고른다. 출력 JSONL은 benchmark-compatible case 파일이지만 위치가 `.tmp`인 한 `exploratory` 입력으로 해석한다. 따라서 이 subset은 구조 변경 디버깅과 정성 분석용이며, 논문 성능 수치는 반드시 전체 challenge replay 또는 representative corpus에서 다시 확인한다.

구조 후보 subset을 사용할 때의 규칙:

- subset 평균을 논문 성능 수치로 쓰지 않는다.
- 구조 변경 전후의 counter 움직임을 빠르게 확인하는 용도로만 쓴다.
- 개선 후보가 보이면 같은 변경을 전체 `sbd_cases/{en,ko,zh}` challenge replay에서 `sat + cuda + float16`로 재실행한다.
- subset이 특정 언어에 치우칠 수 있으므로 언어별 ad-hoc 규칙의 근거로 쓰지 않는다.

## Corpus 역할

| corpus | 위치 | 목적 | 평균값 해석 |
| --- | --- | --- | --- |
| `challenge-replay` | `tests/eval/dictation_ai/sbd_cases/{en,ko,zh}/` | 실패 재현, 회귀 추적, lifecycle 튜닝 | 실패 중심 입력에서의 회수/경계/잔류 |
| `representative` | `tests/eval/dictation_ai/sbd_representative_cases/` | 운영 평균 추정 | 시간/세션 표본의 평균 품질 |
| `exploratory` | 명시 입력 경로 | 탐색, 임시 분석 | 논문 수치로 직접 쓰지 않음 |

`challenge-replay`와 `representative` 평균은 한 표에서 섞지 않는다. 파라미터 후보는 먼저 challenge replay에서 실패군 악화 여부를 확인하고, representative corpus가 준비되면 운영 평균 악화 여부를 별도로 확인한다.

`challenge-replay` 내부에서도 결과 해석용 strata를 분리한다. 이는 케이스를 제외하기 위한 장치가 아니라, 어떤 실패가 final lifecycle 실험의 직접 대상인지 표시하기 위한 장치다.

| stratum | 의미 | 논문 사용 |
| --- | --- | --- |
| `all_cases` | 입력된 challenge replay 전체 | 전체 실패 replay 기준선 |
| `lifecycle_focus` | missing/duplicate/final/fragment/no-end/queue/revision/stage/boundary 계열 진단 태그가 있는 케이스 | lifecycle 병목 분석의 주 대상 |
| `lifecycle_without_input_review` | lifecycle focus 중 입력 잔류/무음/화자 전환 검토 태그가 없는 케이스 | final lifecycle 구조 변경의 더 깨끗한 비교 보조 지표 |
| `input_contamination_review` | `audio-residual`, `no-speech`, `no-text`, `speaker-transition` 검토 태그가 있는 케이스 | raw input/source 검토 대상으로 분리, lifecycle 개선 근거로 직접 사용하지 않음 |

2026-06-21 기준 기존 실제 CUDA report 재분석에서는 `input_contamination_review=5/1113`으로 작다. 따라서 현재 낮은 `final_f1_avg`와 `final_boundary_f1_avg`는 입력 오염 대량 혼입이 아니라 lifecycle focus 자체의 난도로 해석한다. 다만 논문 결과표에는 `all_cases`와 함께 `lifecycle_without_input_review`, `input_contamination_review` 규모를 표시한다.

## Representative 수집 기준

Representative case는 실패 후보 그룹이 아니라 운영 로그의 표본이다.

허용 표본 단위:

- `time-window`
- `session-window`

각 case는 다음 metadata를 가져야 한다.

- `corpus_role=representative`
- `sampling_unit`
- `sampling_rule`
- `source_log`
- `source_started_at`
- `source_ended_at`
- `language`
- `stt_backend`
- `stt_model`
- `window_seconds`
- `step_seconds`
- `sentence_finalize_age`
- `review_packet_id`
- `expected_final_reviewed_by`
- `chunks`
- 사람이 확정한 `expected_final`

실패 유형 묶음, 수동 후보 그룹, tag cluster는 representative sampling unit으로 쓰지 않는다.

Representative case를 만들 때는 먼저 source log와 chunk/time 범위를 선택하고, 그 범위의 raw STT window와 final transcript 로그를 함께 검토한 뒤 사람이 `expected_final`을 확정한다. 운영 로그의 `Dictation AI transcript`는 현재 앱 로직의 출력이므로 그대로 정답으로 복사하지 않는다. 마찬가지로 `stt_raw`는 입력 window 가설이지 final 정답이 아니므로, representative `expected_final`의 자동 생성 근거로 쓰지 않는다.

첫 representative 표본을 만들기 전 점검할 항목:

- source log 파일 수와 보존 기간
- 선택 규칙이 fixed interval 또는 deterministic hash sampling처럼 재현 가능한지
- 선택된 구간의 시작/종료 chunk 또는 timestamp
- 선택된 구간의 `language`, STT backend/model, window/step/finalize age가 기록되는지
- 해당 구간의 `stt_raw`, `transcript`, `translation`, 성능/진단 로그가 모두 남아 있는지
- 사람이 확정한 `expected_final`이 앱 출력의 단순 복사가 아닌지

이 점검은 먼저 source audit으로 수행한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py representative-sources \
  .tmp/logs \
  --compact \
  --summary-output .tmp/eval/dictation-ai-sbd/representative-source-audit.json
```

source audit이 `can_seed_representative_candidates=true`를 보고하더라도 이는 로그에서 후보 구간을 고를 수 있다는 뜻이다. 정식 representative case가 되려면 선택된 구간마다 runtime metadata를 다시 확인하고, 사람이 `expected_final`을 확정해야 한다. 운영 로그의 `Dictation AI transcript`는 앱 출력이므로 정답으로 자동 승격하지 않는다.

source audit은 STT, SBD, 번역 backend/model marker를 분리 집계한다. 전체 로그 aggregate에 STT 설정 marker가 있더라도 회전 로그의 일부 구간에는 설정 시작 line이 없을 수 있으므로, representative case metadata는 선택된 시간/세션 구간을 기준으로 다시 확인한다.

source audit 이후에는 사람 검수용 source manifest를 만들 수 있다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py select-representative-sources \
  .tmp/eval/dictation-ai-sbd/representative-source-audit.json \
  --per-language 2 \
  --output .tmp/eval/dictation-ai-sbd/representative-source-review-manifest.json \
  --markdown-output .tmp/eval/dictation-ai-sbd/representative-source-review-manifest.md
```

이 manifest는 `session-window` 단위 후보 목록이며, `paper_evidence=false`, `case_generation=false`, `requires_human_expected_final=true`로 해석한다. 기본 선택은 runtime metadata가 있고 한 source 안의 STT backend/model, window, step, finalize age가 단일 값으로 해석되는 후보만 사용한다. 언어별 목표 수를 채우지 못하면 부족한 수를 그대로 기록하고, mixed-runtime source를 억지로 포함하지 않는다.

source manifest 이후에는 사람이 검토할 orientation packet을 만들 수 있다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py extract-review-packets \
  .tmp/eval/dictation-ai-sbd/representative-source-review-manifest.json \
  --output .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json \
  --markdown-output .tmp/eval/dictation-ai-sbd/representative-source-review-packets.md
```

review packet은 선택된 source 로그에서 raw STT window, final event, transcript, 성능 event를 균등 샘플링해 사람이 source 구간을 읽기 쉽게 만드는 중간 산출물이다. 이 단계도 `paper_evidence=false`, `case_generation=false`, `expected_final_generated=false`로 해석한다. `ready_packet_count`는 네 event 종류가 모두 1개 이상 있는 packet 수를 뜻하며, 부족한 packet은 `packet_readiness_blockers`에 남긴다. 정식 representative case는 packet을 참고해 사람이 구간과 `expected_final`을 확정한 뒤 별도 JSONL shard로 작성한다. 이때 `review_packet_id`와 `expected_final_reviewed_by`를 함께 남겨 앱 출력 복사가 아니라 사람 검토를 거친 case임을 검증 가능하게 한다.

review packet을 만든 뒤에는 별도 validator로 중간 산출물 계약을 확인한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py validate-review-packets \
  .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json \
  --summary-output .tmp/eval/dictation-ai-sbd/representative-source-review-packets.validation.json
```

validator는 packet version, manifest 선택 수와 언어별 선택 수, packet 수, ready packet 수, source 누락, readiness blocker 일치, packet별 non-case 계약을 확인한다. 이 검증이 통과해도 representative case가 만들어진 것은 아니며, 사람이 `expected_final`을 확정하기 전까지 논문 수치에는 포함하지 않는다.

검토 편의를 위해 ready review packet에서 manual draft JSONL을 만들 수 있다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py extract-representative-drafts \
  .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json \
  --jsonl-output .tmp/eval/dictation-ai-sbd/representative-case-drafts.jsonl \
  --summary-output .tmp/eval/dictation-ai-sbd/representative-case-drafts.summary.json \
  --markdown-output .tmp/eval/dictation-ai-sbd/representative-case-drafts.md
```

이 draft는 `expected_final=[]`, `expected_final_generated=false`, `draft_expected_final_required=true`, `paper_evidence=false`로 생성된다. 사람이 bounded window를 정하고 `expected_final`과 `expected_final_reviewed_by`를 채운 뒤 draft marker를 제거하기 전까지는 benchmark 입력이나 논문 근거가 아니다.

수작업 템플릿 품질은 `.tmp` draft 상태에서도 명시적으로 검증할 수 있다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py validate-cases \
  .tmp/eval/dictation-ai-sbd/representative-case-drafts.jsonl \
  --corpus-role representative \
  --allow-drafts \
  --review-packets .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json \
  --summary-output .tmp/eval/dictation-ai-sbd/representative-case-drafts.validation.json
```

이 명령은 draft를 논문 수치로 승격하지 않는다. draft의 `review_packet_id`, `source_log`, `language`, timestamp source range가 검증된 review packet과 맞는지 확인해 사람이 `expected_final`을 채우기 전 입력 품질을 확인한다.

사람이 `expected_final`과 `expected_final_reviewed_by`를 채우고 `draft_expected_final_required`를 제거한 뒤에는 다음 명령으로 정식 representative shard 승격을 검증한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py promote-representative-cases \
  .tmp/eval/dictation-ai-sbd/representative-case-drafts.jsonl \
  --review-packets .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json \
  --dry-run
```

현재 비어 있는 draft 그대로는 이 명령이 실패해야 정상이다. 승격 도구는 `expected_final`을 자동 생성하지 않고, 검증을 통과한 reviewed case만 `tests/eval/dictation_ai/sbd_representative_cases/{en,ko,zh}/reviewed-representative-{language}-{hash}.jsonl`로 저장한다.

source audit과 review packet 검증 뒤에는 follow-up readiness audit으로 다음 병목을 명시한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py followup-readiness \
  --source-audit .tmp/eval/dictation-ai-sbd/representative-source-audit.json \
  --review-packet-validation .tmp/eval/dictation-ai-sbd/representative-source-review-packets.validation.json \
  --representative-cases tests/eval/dictation_ai/sbd_representative_cases \
  --review-packets .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json \
  --representative-draft-validation .tmp/eval/dictation-ai-sbd/representative-case-drafts.validation.json \
  --summary-output .tmp/eval/dictation-ai-sbd/followup-readiness.json
```

이 audit의 representative status가 `blocked_on_human_expected_final`이면 source/packet은 준비되었지만 사람이 확정한 representative JSONL case가 없다는 뜻이다. `ready_for_pilot_representative_replay`가 되더라도 translation status가 `blocked_on_translation_replay_linkage`라면 운영 평균 finalization pilot만 가능하고, final-only sink의 번역 안정성 주장은 여전히 보류한다. translation status가 `ready_for_translation_replay_case_building`이면 final/transcript/translation이 같은 segment id로 연결된 로그가 있다는 뜻이며, 다음 단계는 번역 안정성 replay case를 구성하는 것이다.

사람이 `expected_final`을 확정해 representative JSONL case를 작성한 뒤에는 case validator에 review packet을 함께 넘겨 source 추적성을 확인한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py validate-cases \
  tests/eval/dictation_ai/sbd_representative_cases \
  --max-drafts 0 \
  --review-packets .tmp/eval/dictation-ai-sbd/representative-source-review-packets.json
```

이 검증은 각 case의 `review_packet_id`가 packet payload에 존재하는지, case의 `source_log`와 `language`가 packet의 source와 일치하는지 확인한다. case와 packet의 source range가 timestamp 형식이면 case range가 packet의 `source_window_filter` 범위 안에 있는지도 확인한다. 따라서 representative case가 운영 로그 transcript를 자동 복사한 자기참조 데이터가 아니라, 선택된 source packet을 사람이 검토해 만든 표본이라는 최소 추적성을 제공한다.

초기 representative 표본은 작게 시작할 수 있지만, 논문 수치로 승격하려면 표본 설계가 먼저 고정되어야 한다. 최소 기준은 다음과 같다.

- 표본 선택 규칙은 실행 전에 문서화한다.
- 표본 선택 이후 실패 여부를 보고 case를 제외하지 않는다.
- 언어별 case 수, source log 수, sampling rule 분포를 report에 남긴다.
- `--paper-evidence` 실행에서는 `--min-expected-final-cases`를 명시한다.
- challenge replay에서 채택한 파라미터가 representative 평균을 악화시키는지 별도 확인한다.
- validator와 benchmark report의 `representative_metadata.review_packet_count`, `review_packet_counts`, `expected_final_reviewer_counts`를 확인해 source 검토 흐름이 case에 연결되었는지 확인한다.

초기 운영 평균 추정은 큰 표본보다 재현 가능한 표본 선택 규칙을 우선한다. 표본 수가 작으면 결과는 `pilot representative`로 표시하고, 일반 운영 품질 주장은 보류한다.

## Translation Replay 승격 조건

final-only sink가 번역 안정성을 높인다는 주장은 현재 challenge replay만으로는 보류한다. 이 주장을 실험 결과로 승격하려면 다음 자료가 필요하다.

- final event timestamp
- final text와 translation request id의 연결
- translation output text
- 같은 source 구간에서 duplicate translation, delayed translation, missing translation을 계산할 수 있는 로그
- final이 아닌 staged/pending이 번역 큐에 들어가지 않았다는 sink 계약 검증

현재 로그 감사는 `segment_id` 기준 final/transcript/translation 연결을 확인한다. 번역이 켜진 세션의 final 중 실제 번역 출력까지 연결된 비율은 `segment_linkage.translation_enabled_final_translation_linked_ratio`로 본다. 이 값은 STT 정확도 지표가 아니라 final-only sink 소비율 지표다.

Translation replay는 SBD/finalization replay와 다른 실험이다. SBD replay는 `expected_final`과 final transcript의 유사성을 본다. Translation replay는 final 이벤트가 번역 입력으로 들어간 뒤 downstream churn이 줄었는지 본다. 따라서 translation replay가 준비되기 전에는 `final-only sink`를 시스템 계약과 문제 설정으로만 주장하고, 번역 품질 개선 수치로 주장하지 않는다.

## 실행 규칙

성능 근거는 실제 AI 경로만 인정한다.

```text
./.venv/bin/python tests/eval/dictation_ai/sbd_benchmark.py \
  --cases tests/eval/dictation_ai/sbd_cases \
  --device cuda \
  --compute-type float16
```

논문 근거용 파라미터 sweep은 다음 조건을 만족해야 한다.

- `sat + cuda + float16` 실행
- benchmark와 sweep 하위 job은 `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`로 실행해 캐시된 모델만 사용한다.
- benchmark report와 sweep summary의 `runtime_contract`로 `sat + cuda + float16`, `model_source=local-cache-only`, 오프라인 환경값을 확인한다.
- `--paper-evidence`
- `corpus_role`이 `challenge-replay` 또는 `representative`
- `representative`를 `--paper-evidence`로 실행할 때는 `--min-expected-final-cases`를 명시한다. 대표 표본의 규모 목표는 challenge replay의 1000건 기준을 암묵 공유하지 않는다.
- `representative`를 `--paper-evidence`로 실행할 때는 `--review-packets`도 명시해 case의 `review_packet_id`, `source_log`, `language`가 검증된 source packet과 연결되는지 확인한다.
- 같은 `--cases` 입력에서 baseline 포함
- `run_sbd_parameter_sweep.py`는 `--paper-evidence` 실행에서 `--include-baseline`이 없으면 실행을 거부한다.
- 한 번에 한 파라미터 축 비교
- `run_sbd_parameter_sweep.py`는 `--paper-evidence` 실행에서 서로 다른 파라미터 이름이 섞이면 실행을 거부한다.
- `summary.json`과 Markdown header의 `parameter_axes`로 비교 축을 확인한다.
- `summary.json`의 `corpus_role`, `evidence_summary.results`, `language_deltas`, `tag_deltas`, `adoption_review` 확인
- representative corpus는 case validator summary의 `representative_metadata.sampling_unit_counts`, `sampling_rule_counts`, `source_log_count`, `review_packet_count`, `expected_final_reviewer_counts`를 함께 확인한다.
- representative corpus는 case validator summary의 `representative_review_packet_validation.packet_count`, `ready_packet_count`, `matched_case_count`를 함께 확인한다.
- representative parameter sweep Markdown header의 `representative_sampling_units`, `representative_sampling_rules`, `representative_source_log_count`, `representative_review_packet_count`, `representative_reviewers`, `representative_review_packet_validation_*`로 사람이 읽는 요약에도 같은 표본 문맥과 사람 검토 흐름이 남는지 확인한다.
- `summary.json`과 Markdown header의 `evidence_protocol.experiment_stage`로 결과가 `challenge-replay`, `representative-replay`, `exploratory` 중 어떤 실험 단계인지 확인한다.
- `experiment_stage`는 성능 지표가 아니라 해석 범위 표시다. threshold sweep, structural lifecycle check, representative replay 결과를 같은 표에서 섞지 않기 위해 사용한다.
- `summary.json`의 `evidence_protocol.claim_scope_key`로 로그/표 후처리용 근거 범위 확인
- `summary.json`의 `evidence_protocol.claim_scope`로 사람이 읽는 논문 근거 사용 범위 확인
- `summary.json`과 Markdown header의 `supported_claims`, `unsupported_claims`, `deferred_claims`로 해당 결과가 지지하는 주장, 금지하는 주장, 후속 실험 전까지 보류할 주장을 확인
- `summary.json`과 Markdown header의 `evidence_protocol.required_evidence_fields`로 논문에 옮길 때 함께 보존해야 하는 최소 필드 확인
- `required_evidence_fields`에는 `evidence_protocol.experiment_stage`, `supported_claims`, `unsupported_claims`, `deferred_claims`가 포함된다.
- `required_evidence_fields`에는 `lifecycle_replay_contract.state_machine_parity`, `shared_decision_helpers`, `replayed_runtime_signals`, `missing_runtime_signals`도 포함된다. 구조 실험 결과를 인용할 때 benchmark replay가 운영 loop와 어느 정도 같은 판단 경로를 공유했고 어떤 runtime 신호를 재계산/누락했는지 함께 보존하기 위함이다.
- representative corpus의 `required_evidence_fields`에는 `case_summary.representative_metadata.sampling_unit_counts`, `sampling_rule_counts`, `source_log_count`, `review_packet_count`, `expected_final_reviewer_counts`와 `case_summary.representative_review_packet_validation.packet_count`, `ready_packet_count`, `matched_case_count`가 추가된다.
- benchmark report와 sweep `evidence_summary`의 `lifecycle_bottleneck_summary`로 `stage_replace_deferred`, `stage_queue_revision`, `no_end_marker`, 언어별 under/over-final 잔류를 확인
- `lifecycle_bottleneck_summary.replacement_decision_counts`, `deferred_replacement_decision_counts`, `quality_block_reason_counts`로 병목 원인별 분포를 확인
- `staged_queue_residue_summary`로 케이스 종료 시점에 남은 queue 후보의 case 수, 총량, 평균, 최대 길이, top queue residue case를 확인한다. 이 값은 final 품질 점수가 아니라 candidate lifecycle 구조 병목을 설명하는 보조 지표다.
- `queue_residue_strata_summary`로 queue 잔류를 `no_queue`, `queue_len_1`, `queue_len_2_to_4`, `queue_len_ge_5`로 나눠 본다. queue가 긴 구간에서 boundary F1과 revision/deferred count가 함께 나빠지는지 확인해, queue 용량 문제가 아니라 후보 소비/경계 보존 문제인지 판단한다.
- `case_exemplar_summary`로 평균 지표 뒤에 있는 대표 병목 case id와 queue/replacement/quality-block metric을 확인한다. 이 필드는 정성 분석과 다음 실험 후보 선정용이며, 그 자체를 성능 개선 지표로 쓰지 않는다.
- Markdown summary의 lifecycle count 표와 lifecycle delta 표를 함께 확인해 병목 규모와 변화량을 분리한다.
- draft case 없음

Mock, smoke, CPU, float32 결과는 기능 검증으로는 사용할 수 있지만 성능 근거로 쓰지 않는다.

`--dry-run`은 실행 계획 검증용이다. `--paper-evidence`와 함께 실행하더라도 실제 CUDA benchmark가 실행되지 않으므로 `paper_evidence=false`, `paper_evidence_eligible=false`로 해석한다. 이 경우 `paper_evidence_requested=true`는 사용자가 논문 근거용 조건을 요청했다는 기록일 뿐, 결과가 논문 근거라는 뜻이 아니다.

`missing_required_evidence_fields`는 `required_evidence_fields` 중 비어 있거나 없는 항목을 표시한다. dry-run에서는 실제 benchmark 결과가 없으므로 `evidence_summary.results`와 `evidence_summary.adoption_review_counts`가 누락으로 표시될 수 있다. 논문 근거로 인용할 실제 sweep summary는 이 값이 `none`이어야 한다.

기존 benchmark/sweep report를 최신 논문 근거 기준으로 다시 확인할 때는 `tests/eval/dictation_ai/sbd_benchmark.py validate-evidence`를 사용한다. 이 도구는 report 안에 저장된 오래된 `required_evidence_fields`를 그대로 믿지 않고 현재 evidence protocol 기준으로 누락 필드를 다시 계산한다. 디렉터리를 입력하면 하위 `summary.json`과 `summary.refreshed.json`을 재귀적으로 검사하므로 sweep 재고 조사에 사용할 수 있다. `--summary-only`는 전체 재고 기준 `experiment_stage_counts`, `claim_scope_key_counts`, `mixed_experiment_stage`, `mixed_claim_scope_key`와 complete subset 기준 `complete_experiment_stage_counts`, `complete_claim_scope_key_counts`, `complete_mixed_experiment_stage`, `complete_mixed_claim_scope_key`, 누락 필드별 count를 함께 출력한다. 이 출력은 오래된 exploratory/incomplete 결과가 섞여 있는지 보는 재고 감사용이다. `--allow-missing`은 과거 report 재고 조사에만 사용하고, 논문 표에 옮길 결과는 missing field가 없어야 한다.

`--complete-only`는 현재 기준을 모두 만족한 report 목록만 출력한다. 이 모드는 같은 디렉터리에 incomplete report가 남아 있어도 complete 목록 추출 자체를 실패시키지 않는다. `--complete-only`의 `experiment_stage_counts`, `claim_scope_key_counts`, `mixed_experiment_stage`, `mixed_claim_scope_key`는 complete report subset 기준으로 해석한다. 따라서 논문 표에 옮길 report 집합은 `--complete-only` 출력에서 `mixed_experiment_stage=false`, `mixed_claim_scope_key=false`인지 확인한 뒤 사용한다.

감사 출력의 각 report와 aggregate summary에는 `experiment_stage`와 `claim_scope_key`가 포함된다. 이 값은 complete report 재고가 모두 `challenge-replay`와 `failure-lifecycle-tradeoff`인지, representative 표본이나 exploratory 결과가 섞였는지 확인하기 위한 것이다. `summarize_sbd_evidence_reports.py`의 JSON summary는 `experiment_stage_counts`, `mixed_experiment_stage`, `claim_scope_key_counts`, `mixed_claim_scope_key`를 포함하고, Markdown 표도 `stage` 컬럼과 축별 대표 report를 포함한다. 여기서 축별 대표 report는 중복 parameter axis report 중 하나를 고른 `axis_representative_reports`이며, 운영 평균 표본을 뜻하는 `representative replay`와 다르다. 축별 후보 delta를 논문 초안에 옮기기 전에는 `mixed_experiment_stage=false`와 `mixed_claim_scope_key=false`인지 확인한다.

과거 sweep summary가 최신 claim field만 빠뜨렸고 하위 job JSON이 남아 있다면 `tests/eval/dictation_ai/sbd_benchmark.py refresh-sweep`로 summary와 Markdown을 현재 포맷으로 재생성할 수 있다. 디렉터리를 입력하면 하위 `summary.json`을 찾아 원본 옆 `summary.refreshed.json`을 만든다. 이 작업은 새 성능 수치를 만드는 것이 아니라, 이미 저장된 `sat + cuda + float16` job report를 현재 evidence protocol로 다시 묶는 것이다. 재생성한 결과도 반드시 `sbd_benchmark.py validate-evidence --complete-only`로 확인한 뒤 논문 표에 사용한다.

개별 `sbd_benchmark.py` report도 `evidence_protocol`을 포함한다. 단, benchmark 단독 실행은 `--paper-evidence` sweep gate를 통과한 것이 아니므로 `paper_evidence=false`일 수 있다. 이때 `paper_evidence_corpus_eligible=true`는 corpus 역할이 논문 근거 후보라는 뜻이고, 실제 논문 근거로 승격하려면 paper-evidence sweep 또는 같은 수준의 case threshold 검증을 함께 남긴다.

Representative corpus를 단독 `sbd_benchmark.py`로 실행할 때도 report의 `case_summary.representative_metadata`에 `sampling_unit_counts`, `sampling_rule_counts`, `source_log_count`, `source_log_counts`가 남아야 한다. `--review-packets`를 함께 지정하면 `case_summary.representative_review_packet_validation`도 report에 남는다. 이는 benchmark 단독 분석과 sweep 분석이 같은 표본 문맥과 review packet 추적성을 공유하기 위한 최소 조건이다.

## 지표 해석

`pass_rate`는 논문 성능 지표로 쓰지 않는다. 케이스가 늘면 난도와 실패 분포가 바뀌기 때문이다.

`--fail-on-regression`과 `--min-final-f1`은 로컬 실행 실패 여부를 빠르게 확인하기 위한 선택적 guard다. benchmark report에서는 `regression_guard.paper_metric=false`로 분리하며, `summary`의 논문 지표로 취급하지 않는다.

우선 지표:

- `final_precision_avg`
- `final_recall_avg`
- `final_f1_avg`
- `final_boundary_f1_avg`
- `finalized_per_stage_start`
- `pending_exact_match`
- `staged_exact_match`
- lifecycle counter

해석 보조:

- `evidence_protocol`
- `claim_scope_key`
- `claim_scope`
- `required_evidence_fields`
- `lifecycle_bottleneck_summary`
- `staged_queue_residue_summary`
- `language_summary`
- `tag_summary`
- `metric_deltas`
- `language_deltas`
- `tag_deltas`
- `interpretation_flags`
- `adoption_review`

`final_f1_avg`가 올라도 다음 신호가 있으면 기본값 채택 근거로 보지 않는다.

- `final_precision_avg` 하락이 큰 경우
- `final_boundary_f1_avg` 하락이 동반되는 경우
- 특정 언어의 final F1 또는 precision이 하락하는 경우
- `missing-final`, `stage-queue`, `duplicate-final`, `no-end-marker`, `cjk-internal-gap` 같은 핵심 실패 태그에서 precision/boundary가 악화되는 경우
- staged residue나 empty final이 의미 있게 증가하는 경우
- queue residue severity stratum에서 boundary F1이 낮아지거나 residual queue가 늘어나는 경우
- `all_cases` 평균 개선이 `lifecycle_without_input_review` stratum에서 유지되지 않는 경우
- 개선이 `input_contamination_review` 같은 raw input/source 검토 stratum에서만 나타나는 경우

## 파라미터 채택 기준

파라미터 변경은 다음을 모두 만족할 때만 checked-in 기본값 후보가 된다.

1. 같은 corpus baseline 대비 개선과 악화를 모두 기록했다.
2. 전체 평균뿐 아니라 언어별/태그별 delta를 확인했다.
3. `lifecycle_without_input_review`와 `input_contamination_review` strata를 확인했다.
4. `review-risk`가 있다면 악화 이유가 실험일지에 설명됐다.
5. 개선이 특정 실패군 하나의 보상인지, 일반 lifecycle 개선인지 구분했다.
6. 운영 계약을 흐리는 언어별 ad-hoc 규칙이나 regex 보정이 아니다.

현재 1113건 기준에서 확인된 방향은 다음과 같다.

- `SENTENCE_CONFIRM_CHUNKS=1`은 recall을 올리지만 precision과 중국어 품질을 낮춰 기본값 근거가 약하다.
- `SENTENCE_CONFIRM_CHUNKS=3`은 precision을 일부 올리지만 recall/final F1/boundary F1을 낮춰 기본값 근거가 약하다.
- `SENTENCE_CONFIRM_MAX_AGE_CHUNKS=2/4`는 최신 paper-evidence 계약에서도 전체/언어/핵심 태그 delta가 모두 0이라 age 상한 단독 튜닝 근거가 없다.
- `SHORT_NO_END_FRAGMENT_UNITS=3/5`는 기본값 4보다 전체 final F1이 낮아 기본값 변경 근거가 없다.
- `MAX_STAGED_SENTENCE_QUEUE=20`은 성능 개선축이라기보다 긴 window 후보 조기 폐기를 막는 보수적 하한이다.
- `MAX_STAGED_SENTENCE_QUEUE=12/30` 재분석에서도 clean lifecycle stratum 결론은 동일하다. 12는 drop oldest와 queue revision을 늘리고, 30은 20과 동일해 기본값 변경 근거가 없다.
- `REVISION_FALLBACK_COVERAGE_MIN=0.55`는 주변값 0.50/0.60/0.70보다 전체/언어/태그 delta가 안정적이어서 현재 기본값 근거가 있다.
- `SHORT_CJK_REPLACEMENT_HOLD_CHUNKS=0/1/3`은 현재 challenge replay에서 전체/언어/태그 delta가 모두 0이므로 성능 튜닝축으로 보지 않는다.
- `NO_TEXT_STALE_STAGE_SUPPRESS_CHUNKS=3/9`는 한국어 staged residue를 각각 -1/+1 움직이지만 final 품질 지표는 바꾸지 않아 기본값 변경 근거가 없다.
- `FORCED_SENTENCE_CONFIRM_CHUNKS=2/4`는 현재 challenge replay에서 전체/언어/태그 delta가 모두 0이므로 닫힌 튜닝축으로 본다.
- `FORCED_SENTENCE_CONFIRM_MAX_AGE_CHUNKS=3/5`도 전체/언어/태그 delta가 모두 0이므로 forced 계열은 현재 corpus에서 추가 미세조정하지 않는다.
- `SHORT_CJK_FINAL_UNITS=8`은 final F1을 +0.0004 올리지만 precision과 boundary가 함께 낮아지고, `12`는 recall/final F1/boundary를 낮춰 기본값 10을 유지한다.
- `CJK_REVISION_RATIO_MIN=0.70`은 중국어 staged residue를 2건 줄이지만 final 품질 지표를 바꾸지 않고, `0.85`는 중국어 precision/F1과 핵심 태그 precision을 낮춰 기본값 변경 근거가 없다.
- `CJK_CONFIRM_PRESERVE_RATIO_MIN=0.65`는 중국어 staged residue를 1건 줄이고 final F1을 +0.0002 올리지만 boundary/precision 변화가 없어 기본값 변경 근거가 약하다.

당시 12개 manifest 축의 종합 판단은 다음처럼 분류했다. 이후 delta 0으로 닫힌 `SENTENCE_CONFIRM_MAX_AGE_CHUNKS`, `FORCED_SENTENCE_CONFIRM_CHUNKS`, `FORCED_SENTENCE_CONFIRM_MAX_AGE_CHUNKS`, `SHORT_CJK_REPLACEMENT_HOLD_CHUNKS`는 운영 상수로만 유지하고 현재 `dictation_tuning_manifest()` sweep 후보에서는 제외한다.

| 분류 | 축 | 해석 |
| --- | --- | --- |
| 유지 근거 있음 | `REVISION_FALLBACK_COVERAGE_MIN=0.55` | 주변값 0.50/0.60/0.70보다 전체 final F1, precision, recall이 안정적이다. |
| trade-off 축 | `SENTENCE_CONFIRM_CHUNKS`, `SHORT_NO_END_FRAGMENT_UNITS`, `SHORT_CJK_FINAL_UNITS`, `MAX_STAGED_SENTENCE_QUEUE`, `CJK_REVISION_RATIO_MIN` | 일부 지표나 잔류를 줄여도 precision, recall, boundary, 언어별 품질 중 하나가 악화된다. |
| 닫힌 축 | `SENTENCE_CONFIRM_MAX_AGE_CHUNKS`, `FORCED_SENTENCE_CONFIRM_CHUNKS`, `FORCED_SENTENCE_CONFIRM_MAX_AGE_CHUNKS`, `SHORT_CJK_REPLACEMENT_HOLD_CHUNKS` | 현재 1113건 challenge replay에서 전체/언어/핵심 태그 지표를 움직이지 않는다. |
| 보류 축 | `NO_TEXT_STALE_STAGE_SUPPRESS_CHUNKS`, `CJK_CONFIRM_PRESERVE_RATIO_MIN` | final 품질 변화가 없거나 개선 폭이 너무 작아 기본값 변경 근거가 부족하다. |

따라서 후속 실험에서 단일 threshold를 더 세밀하게 흔드는 것은 우선순위가 낮다. 새 기본값 후보를 찾기보다, active staged 후보와 candidate queue가 같은 발화 구간의 revision을 어떻게 소비하는지 설명하는 구조 실험을 먼저 설계한다.

## 구조적 병목 해석

2026-06-21 기준선은 1113건 `challenge-replay`에서 `final_f1_avg=0.4832`, `final_boundary_f1_avg=0.1077`, `finalized_per_stage_start=0.7116`을 기록했다. 이 값은 threshold 하나를 더 흔들면 해결되는 단일 병목이라기보다, 후보 생성, staged 교체, queue 보류, no-end 품질 게이트가 동시에 작동한 결과다.

주요 lifecycle counter는 다음과 같다.

| counter | count | 해석 |
| --- | ---: | --- |
| `stage_start` | 5638 | SBD가 completed 후보를 충분히 많이 만든다. |
| `stage_replace` | 8273 | 후보 교체가 stage 생성보다 많아 같은 발화 구간의 revision 판단이 흔들린다. |
| `stage_replace_deferred` | 7551 | 새 후보가 와도 기존 후보를 확정/폐기하지 못해 queue 보류가 반복된다. |
| `stage_queue_enqueue` | 4257 | 생성순서 보존을 위해 보류 후보가 많이 쌓인다. |
| `stage_queue_revision` | 3961 | queue 안에서도 revision이 계속 발생한다. |
| `stage_candidate_quality_blocked` | 3963 | 후보가 만들어졌지만 final 품질 조건을 통과하지 못한다. |
| `stage_candidate_quality_no_end_marker` | 2280 | 종결 경계가 약한 fragment가 큰 비중을 차지한다. |
| `final_quality_no_end_marker` | 595 | final 직전에도 no-end 위험이 남아 있다. |

reason breakdown은 다음 실험 축을 좁히는 데 사용한다.

| 분해 축 | 주요 count | 해석 |
| --- | --- | --- |
| deferred replacement reason | `unconfirmed=4039`, `open_latin_clause=1620`, `unconfirmed_cjk=1527`, `open_korean_clause=365` | stage 보류는 단일 원인이 아니라 미확정 후보와 open clause가 섞인 결과다. |
| quality block reason | `no_end_marker=2280`, `short_no_end_fragment=2020`, `latin_only_for_zh=873`, `trailing_ellipsis=569`, `repeated_word_ngram=504` | 후보 생성 이후 final 소비를 막는 주된 이유는 no-end/short-fragment 계열이다. |

2026-06-22의 1223건 replay에서는 한국어 어미 suffix 기반 `open_korean_clause`를 폐기했다. 해당 규칙은 언어별 어미를 직접 예외로 둔 과거 흔적이었고, 제거 후 `open_korean_clause=301 -> 0`, `confirmed=4674 -> 4845`, `final_f1_avg=0.480155 -> 0.482404`, `final_boundary_f1_avg=0.111346 -> 0.112973`로 확인됐다. 따라서 이후 reason breakdown에서 한국어 열린 절은 별도 문법 예외가 아니라 일반 confirmation/revision lifecycle 결과로 해석한다.

`SHORT_NO_END_FRAGMENT_UNITS=3/5` 최신 lifecycle reason delta 재검증은 이 축을 기본값 개선 후보가 아니라 trade-off 설명 축으로 분류하게 한다. `3`은 `quality_blocked=-492`, `no_end_marker=-490`, `short_no_end_fragment=-489`로 차단을 줄이지만 `stage_replace_deferred=+404`, `stage_queue_revision=+198`이 늘고 final precision/F1이 하락했다. `5`는 `stage_replace_deferred=-416`, `stage_queue_revision=-235`로 churn을 줄이지만 `quality_blocked=+456`, `no_end_marker=+450`, `short_no_end_fragment=+449`가 늘고 recall/F1/boundary가 하락했다. 따라서 no-end fragment threshold는 현 기준에서 더 세밀하게 최적화할 축이 아니라, 보수성 수준을 설명하는 폐쇄된 축으로 본다.

Queue residue severity도 같은 결론을 보강한다.

| stratum | cases | final F1 | boundary F1 | queue revision | replace deferred | 해석 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| no queue | 745 | 0.515 | 0.116 | 983 | 2468 | 실패 replay 안에서도 상대적으로 안정된 구간 |
| queue len 1 | 186 | 0.397 | 0.086 | 797 | 1594 | 단일 잔류만으로도 final 품질이 낮아지는 구간 |
| queue len 2-4 | 148 | 0.434 | 0.107 | 1363 | 2302 | revision/deferred churn이 크게 누적되는 구간 |
| queue len >= 5 | 34 | 0.476 | 0.043 | 818 | 1187 | empty final은 아니지만 경계가 크게 무너지는 구간 |

따라서 queue residue는 단순히 queue 크기 부족으로 해석하지 않는다. 특히 queue len >= 5 stratum은 final을 일부 만들지만 boundary F1이 낮으므로, 후속 구조 실험은 residual queue와 boundary F1을 함께 보는 조건으로 설계한다.

언어별 실패 양상도 다르다.

| 언어 | 주요 신호 | 해석 |
| --- | --- | --- |
| 영어 | `overfinal=151`, `no_end_marker=1856`, `replace_deferred=4833` | long-context에서 문장 내용은 많이 나오지만 경계와 교체 보류가 흔들린다. |
| 한국어 | `underfinal=371`, `zero_actual_final_expected=64`, `pending_residue=342` | 보수적 확정이 recall 손실과 pending 잔류로 이어진다. |
| 중국어 | `quality_blocked=992`, `queue_residue=268`, `staged_residue=132` | 후보 품질 게이트와 queue 보류가 final 소비를 막는 비중이 크다. |

따라서 현재 설계의 의미는 유지된다. 불안정한 STT window hypothesis를 raw STT 정확도와 분리하고, SBD 후보와 final lifecycle을 별도 계층으로 계측하는 접근은 실패를 설명하는 데 유효하다. 다만 실험 방법은 다음처럼 재구성해야 한다.

- `final_f1_avg`를 단일 목표값으로 올리는 실험은 중단한다.
- `challenge-replay`는 실패 축별 회귀와 lifecycle trade-off를 보는 corpus로 고정한다.
- 운영 평균 주장은 representative corpus가 만들어진 뒤에만 한다.
- 다음 구조 실험은 threshold sweep이 아니라 `stage_replace_deferred`, `stage_queue_revision`, `no_end_marker`, recent-final memory가 어떤 final 누락/중복을 만드는지 직접 비교하는 작은 lifecycle 변경으로 제한한다.
- threshold 축은 새 로그 증상이 해당 축과 직접 연결되고, reason delta가 새로운 설명력을 줄 때만 재검증한다.

## 외부 문헌 사용 범위

외부 논문은 문제 설정과 비교군 근거로 사용한다. 앱의 파라미터 기본값과 성능 개선 여부는 앱 로그 replay 실험으로만 주장한다.

| 문헌 축 | 현재 사용 범위 |
| --- | --- |
| Whisper-Streaming | partial hypothesis와 committed prefix 분리의 비교 기준 |
| Incremental ASR 평가 | WER 외 latency, update/revoke, stability 지표 필요성 |
| SaT / punctuation | regex/ad-hoc 대신 모델 기반 SBD 후보와 right context를 쓰는 배경 |
| Speech translation segmentation | 번역 단위가 downstream 품질에 영향을 줄 수 있다는 비교 근거 |
| Qwen3-ASR / NLLB | STT/번역 backend 후보 배경 |

외부 논문을 근거로 `sentenceFinalizeAge`, queue 크기, no-end threshold 같은 앱 기본값을 직접 정당화하지 않는다.

## 후속 실험 우선순위

1. Representative corpus를 시간/세션 표본 기준으로 구축한다.
2. Final event timestamp와 translation output replay를 연결해 실제 지연과 번역 churn을 분리 측정한다.
3. Boundary F1이 낮은 long-context 케이스에서 active staged 소비와 candidate queue 정리 정책을 보수적으로 비교한다.
4. 같은 challenge corpus에서 단일 threshold 반복 튜닝을 계속하기보다, lifecycle counter가 지목하는 구조적 병목을 우선 검토한다.
5. 이미 0 delta 또는 review-risk로 닫힌 축은 논문 본문에서 “개선 실패를 통해 남은 병목을 좁힌 근거”로만 사용한다.

후속 실험의 실행 gate는 다음과 같다.

| 실험 | 시작 조건 | 논문 근거 승격 조건 | 중단/보류 조건 |
| --- | --- | --- | --- |
| 구조 변경 실험 | 병목 counter와 대상 case stratum이 먼저 정해져 있다. | 전체 challenge replay에서 `sat + cuda + float16`으로 재실행하고, final F1, boundary F1, precision, queue residue가 함께 해석 가능하다. | replay에 없는 runtime signal이 핵심 근거이거나 CPU/mock/smoke 결과뿐이면 보류한다. |
| parameter sweep | 닫히지 않은 manifest 축이고, 새 로그 증상이 해당 축과 직접 연결된다. | 한 축만 비교하고 `review-risk`, 언어별 delta, 태그별 delta가 설명되어 있다. | 0 delta 축을 더 세밀하게 반복하거나, 전체 평균만 오른 경우 중단한다. |
| representative replay | source log, sampling rule, review packet, 사람이 확정한 `expected_final`이 있다. | sampling metadata와 review 추적성이 validator로 확인되고 challenge 결과와 별도 표로 제시된다. | 운영 transcript를 정답으로 자동 복사했거나 failure 후보만 골랐으면 보류한다. |
| translation replay | final event, translation request id, translation output이 연결되어 있다. | duplicate translation, missing translation, delayed translation을 같은 source 구간에서 계산할 수 있다. | SBD/finalization 결과만 있고 번역 출력 연결이 없으면 보류한다. |

이 gate를 통과하지 못한 실험은 탐색 또는 실험일지 기록으로는 남길 수 있지만, 논문 결론이나 abstract의 성능 주장으로 승격하지 않는다.

## 반복 실험 판정 절차

후속 실험은 점수 상승을 먼저 목표로 두지 않는다. 각 반복은 먼저 어떤 가설을 검증하는지 정하고, 실행 뒤 가설 상태를 `유지`, `축소`, `폐기`, `보류` 중 하나로 업데이트한다. 이 판정이 실험일지에 남지 않으면 논문 근거로 승격하지 않는다.

| 판정 | 조건 | 후속 처리 |
| --- | --- | --- |
| `유지` | 같은 corpus와 runtime 계약에서 lifecycle counter와 핵심 지표가 같은 방향으로 움직이고, 언어별/태그별 치명적 회귀가 없다. | challenge replay 근거로 유지하고, representative 준비 시 같은 방향인지 재확인한다. |
| `축소` | 일부 지표는 좋아지지만 precision, boundary F1, 특정 언어/태그 stratum에서 trade-off가 크다. | 보편 개선 주장을 하지 않고 실패군별 조건부 결과로만 기록한다. |
| `폐기` | 효과가 0 delta이거나, 개선보다 회귀가 더 크거나, ad-hoc/언어별 예외를 요구한다. | 기본값 후보와 논문 중심 주장 후보에서 제거한다. |
| `보류` | challenge replay에서는 신호가 있으나 representative/translation replay가 없으면 주장 범위가 넘친다. | 후속 corpus 또는 timestamp/translation 연결이 준비될 때까지 시스템 계약 또는 연구 질문으로만 둔다. |

반복 실험의 최소 기록 항목은 다음과 같다.

- 검증한 가설과 기대한 counter 변화
- 사용 corpus role과 case 수
- runtime 계약: `sat + cuda + float16` 여부
- baseline과 candidate의 전체 지표, 언어별 delta, 핵심 태그별 delta
- `lifecycle_without_input_review`와 `input_contamination_review` strata 결과
- 채택/기각/보류 판정과 그 이유
- 논문에서 사용할 수 있는 주장과 사용할 수 없는 주장

이 절차에 따르면 현재 1113건 challenge replay와 23개 complete paper-evidence report는 `failure-lifecycle-tradeoff` 가설을 유지하는 근거다. 반면 운영 평균 품질, 실제 latency, 번역 churn 개선은 representative corpus와 translation replay가 없으므로 계속 `보류` 상태다. 따라서 다음 반복의 우선순위는 새 threshold 후보를 찾는 것이 아니라, 구조적 병목을 설명하는 작은 lifecycle 변경을 만들고 같은 판정 절차로 검증하는 것이다.

`summarize_sbd_evidence_reports.py`는 complete evidence report를 축별로 요약할 때 이 판정을 자동 산출한다. JSON/Markdown summary의 `hypothesis_status_counts`와 representative axis report의 `hypothesis_status`는 논문 가설에 대한 현재 판정이다. 단, `폐기`는 현재 baseline을 버린다는 뜻이 아니라 해당 candidate axis를 새 기본값 후보나 논문 중심 개선 주장으로 쓰지 않는다는 뜻이다.

## 구조 실험 preflight

구조 변경 실험은 threshold sweep보다 위험하다. 따라서 구조 변경 전에는 먼저 벤치 replay가 운영 생명주기와 같은 판단 경로를 충분히 공유하는지 확인한다.

현재 운영 루프는 `SentenceCandidateCommitBufferNode`로 active staged 후보와 candidate queue를 관리한다. 반면 `sbd_benchmark.py`는 replay 속도를 위해 자체 `LifecycleState`와 queue helper를 갖고 있다. 두 경로는 같은 transcript helper를 대부분 공유하지만, 운영 루프가 STT stability 분석값을 queue revision에 넘기는 반면 현재 replay case는 해당 stability context를 보존하지 않는다. 따라서 stable-internal signal에 의존하는 구조 변경은 현재 challenge replay만으로 논문 근거가 되기 어렵다.

구조 실험 후보는 다음 조건을 만족해야 한다.

- 앱 루프와 벤치 루프가 같은 helper 또는 동등한 판단식을 사용한다.
- replay case에 없는 runtime signal을 핵심 근거로 삼지 않는다.
- structural subset에서 신호를 보더라도 논문 수치로 쓰지 않고, 전체 challenge replay에서 `sat + cuda + float16`으로 재검증한다.
- sandbox에서 CUDA가 보이지 않아 실행하지 못한 결과를 CPU/mock/smoke로 대체하지 않는다.
- 실행 불가 시 실험일지에는 실패 원인과 보류 판정을 남기고, 해당 실험을 paper evidence로 승격하지 않는다.

이 기준에 따르면 다음 구조 실험은 새 언어별 규칙이 아니라, 운영/벤치 양쪽이 공유하는 active staged 소비 순서, candidate queue 정리, no-end fragment 처리, recent-final memory의 일반 정책 중 하나로 제한한다.

Benchmark report는 이 판단을 위해 `lifecycle_replay_contract`를 포함한다. 이 계약은 운영 loop의 상태 소유자와 replay 상태 소유자, 공유 decision helper, replay에 없는 runtime signal을 함께 기록한다. `state_machine_parity=partial`이면 구조 변경 결과를 바로 논문 근거로 승격하지 않고, 어떤 판단식이 공유되고 어떤 신호가 빠졌는지 먼저 확인한다.
