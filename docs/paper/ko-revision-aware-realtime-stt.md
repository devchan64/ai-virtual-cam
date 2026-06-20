# 다국어 실시간 음성 전사에서 리비전 인지 확정 계층의 설계와 평가

## 초록

실시간 음성 전사(automatic speech recognition, ASR) 시스템은 낮은 지연시간과 높은 전사 정확도를 동시에 요구한다. 그러나 스트리밍 또는 준스트리밍 환경에서 ASR 모델은 매 입력 윈도우마다 부분 가설(partial hypothesis)을 재작성하며, 이 과정에서 중복 출력, 문장 누락, 확정 지연, 번역 입력 중복이 발생한다. 본 연구는 실시간 전사 및 번역 파이프라인에서 원시 ASR 가설(raw ASR hypothesis), 문장 경계 검출(sentence boundary detection), 리비전 생명주기(revision lifecycle), final-only 번역 입력 제어를 분리해 계측하는 후처리 구조를 제안한다. 특히 한국어, 영어, 중국어 환경에서 문맥 윈도우(context window) 길이와 확정 단위(commit unit)의 상호작용을 분석하고, 긴 문맥이 전사 안정성을 개선할 수 있는 동시에 사용자 화면의 최종 전사(final transcript) 갱신을 늦출 수 있음을 운영 로그와 텍스트 벤치마크 기반으로 관찰한다.

본 논문의 기여는 세 가지다. 첫째, 실시간 ASR 출력의 불안정성을 단순 UI 문제가 아니라 리비전 인지 확정 문제로 모델링한다. 둘째, 중복 증폭(duplicate amplification), 확정 누락(missing final), 확정 지연(finalization latency), pending overrun, replacement churn을 분리한 평가 지표를 제시한다. 셋째, 다국어 실시간 전사 시스템에서 STT 모델, 문장 경계 모델, 확정 정책, 번역 sink를 독립 축으로 검증해야 한다는 운영 근거를 제시한다.

## 1. 서론

최근 대형 음성 인식 모델과 다국어 번역 모델의 발전으로 로컬 환경에서도 실시간 전사 및 번역 기능을 구현할 수 있게 되었다. 하지만 실시간 전사 애플리케이션에서 실제 사용자에게 표시되는 품질은 모델의 오프라인 전사 정확도만으로 설명되지 않는다. 동일한 오디오 구간이 여러 슬라이딩 윈도우(sliding window)에 반복 포함되기 때문에 ASR 모델은 매번 비슷하지만 조금씩 다른 문장을 생성한다. 이 결과를 그대로 화면에 표시하면 중복 문장, 소실된 문장, 되돌려지는 표현, 번역 중복이 발생한다.

본 연구는 이러한 문제를 "리비전 인지 확정 계층(revision-aware finalization layer)"의 설계 문제로 본다. 핵심 질문은 다음과 같다.

- 부분 전사(partial transcript)가 계속 바뀌는 상황에서 어떤 텍스트를 최종 전사로 확정할 것인가?
- 긴 문맥 윈도우가 전사 안정성을 높일 때, 확정 지연과 긴 문장 생성 문제를 어떻게 제어할 것인가?
- STT 오류, 문장 경계 오류, 확정 정책 오류, 번역 오류를 어떻게 분리해 측정할 것인가?
- 한국어, 영어, 중국어처럼 언어 구조가 다른 입력에서 동일한 후처리 정책이 유지 가능한가?

## 2. 문제 정의

실시간 전사 파이프라인은 오디오 입력을 일정 간격(step)으로 읽고, 최근 일정 길이의 문맥 윈도우를 ASR 모델에 전달한다. 모델 출력은 최신 윈도우의 전체 전사 가설이며, 이미 표시된 전사와 새 출력 사이의 차이를 계산해야 한다.

본 연구에서는 텍스트 상태를 다음 계층으로 구분한다.

- `raw`: 최신 ASR 윈도우에서 나온 원시 전사 가설
- `pending`: 아직 경계 또는 안정성이 부족한 후보 구간
- `staged`: 문장 경계 모델이 completed 후보로 제안했지만 재확인 전인 후보
- `final`: 사용자 화면과 번역 큐에 append-only로 반영되는 최종 전사 이벤트
- `suppressed/revised`: 중복, 품질 문제, stale revision으로 폐기되거나 다음 윈도우에서 갱신된 후보

이 구조에서 실패는 네 가지로 나눌 수 있다.

- STT 실패: 원시 ASR이 잘못된 언어, 단어, 의미를 출력한다.
- 문장 경계 실패: 완료된 문장과 미완성 문장을 올바르게 분리하지 못한다.
- 확정 실패: 동일 문장을 중복 확정하거나, 다른 문장을 하나의 리비전으로 오인하거나, 긴 문장을 지나치게 늦게 확정한다.
- sink 실패: final이 아닌 staged/pending 후보가 전사 창 또는 번역 큐로 전달되어 중복 표시나 premature translation을 만든다.

## 3. 관련 연구

Whisper 계열 모델은 강력한 오프라인 전사 성능을 보이지만, 본래 저지연 스트리밍 모델로 설계된 것은 아니다. Whisper-Streaming 계열 연구는 local agreement policy와 self-adaptive latency를 사용해 여러 윈도우에서 합의된 부분만 확정하는 접근을 취한다. 이 방향은 본 연구의 리비전 인지 확정 계층과 문제의식이 유사하다.

문장 경계 검출은 일반 텍스트 분절(sentence segmentation)과 ASR punctuation restoration 연구에서 다루어진다. 그러나 실시간 ASR의 partial transcript는 매 chunk마다 이전 가설을 재작성하므로, 일반 문장 분절 모델을 그대로 적용하면 staged 후보의 교체와 폐기가 증가할 수 있다.

중국어와 같은 CJK 언어는 공백 기반 단어 경계가 없고 동음 후보가 많아 긴 문맥의 언어 모델링 효과가 더 중요할 수 있다. 본 연구의 운영 로그에서도 중국어는 짧은 윈도우에서 의미 보존이 흔들리고, 긴 윈도우에서 원시 STT 안정성이 개선되는 경향을 보였다. 반면 긴 윈도우는 final transcript 갱신 지연과 긴 문장 확정을 증가시켰다.

원문 논문을 기준으로 본 연구에 직접 연결되는 근거는 다음과 같다.

| 근거 축 | 원문 요약 | 본 연구에서의 사용 |
| --- | --- | --- |
| [Whisper](https://arxiv.org/abs/2212.04356) | Whisper 원 논문은 대규모 다국어/멀티태스크 약지도 학습으로 zero-shot 전사와 번역 일반화가 가능함을 보인다. 다만 이 논문은 실시간 partial revision 문제를 해결하는 시스템 논문은 아니다. | `faster-whisper + large-v3`를 영어/한국어 운영 후보로 쓰되, raw window 결과를 바로 final로 쓰지 않는 전제다. |
| [Whisper-Streaming](https://arxiv.org/abs/2307.14743) | Whisper-Streaming은 Whisper가 실시간 전사용으로 설계되지 않았기 때문에 local agreement와 self-adaptive latency를 얹어 확정 prefix와 미확정 hypothesis를 분리한다. | 본 연구의 `raw/pending/staged/final` 분리와 여러 window에서 재관측된 후보만 final로 소비하는 정책의 직접 비교 기준이다. |
| [Incremental ASR 평가](https://arxiv.org/abs/2302.12049) | incremental ASR 평가는 WER만으로는 부족하며 latency와 이미 인식된 단어의 update/revoke를 함께 봐야 한다고 제안한다. | `final_f1`, `final_boundary_f1`, replacement churn, staged residue, recent final echo를 분리해 보는 이유다. |
| [Segment Any Text](https://arxiv.org/abs/2406.16678) | SaT는 punctuation 의존도를 낮추고 여러 도메인/언어에서 문장 분절을 수행하도록 설계되었다. | regex/ad-hoc 문장 분할을 운영 경로에서 제외하고 SaT를 completed/pending 후보 생성기로 쓰는 근거다. |
| [Streaming punctuation](https://arxiv.org/abs/2210.05756) | 긴 받아쓰기에서는 WER가 좋아도 pause, 느린 발화, punctuation/segmentation 문제가 남으며, bounded right context와 dynamic window가 필요하다고 보고한다. | punctuation/right-context를 final trigger가 아니라 SBD 후보와 boundary confidence의 보조 신호로 쓰는 근거다. |
| [Qwen3-ASR](https://arxiv.org/abs/2601.21337) | Qwen3-ASR 보고서는 0.6B/1.7B 모델이 52개 언어/방언 ASR을 지원하고, 공개 벤치 외 실제 사용 시나리오 품질 차이를 별도로 평가해야 한다고 강조한다. | 중국어에서 `qwen3-asr-transformers + qwen3-asr-0.6b`를 운영 후보로 두고, STT 품질과 final lifecycle 품질을 분리 평가하는 근거다. |
| [WeNet](https://arxiv.org/abs/2102.01547) | WeNet은 streaming/non-streaming E2E ASR을 통합하고 chunk size로 latency를 제어하는 구조를 제시한다. | Whisper식 sliding window 후처리와 native streaming ASR 접근을 구분하는 비교군이다. |
| [NLLB](https://arxiv.org/abs/2207.04672) | NLLB는 다국어 번역을 200개 언어 규모로 확장하고 FLORES-200, human evaluation, toxicity benchmark로 평가한다. | 번역 품질은 STT/SBD/finalization과 다른 축이므로 final event만 번역 sink로 넘기는 계약의 배경이다. |

## 4. 시스템 설계

제안 시스템은 다음 단계로 구성된다.

1. 오디오 입력 source에서 `AudioEvidence` 생성
2. 언어별 STT backend로 `RecognitionHypothesis` 생성
3. STT 가설과 `UncommittedContext`를 문장 후보로 해석
4. SaT 기반 문장 경계와 punctuation/right-context 신호로 `SentenceCandidateSet` 생성
5. revision-aware commit buffer에서 후보 age, revision 계열, recent final, 품질 플래그를 평가
6. 조건을 만족한 후보만 `CommittedTranscriptEvent(final=true)`로 발행
7. 전사 창과 번역 sink는 final 이벤트만 소비

핵심 정책은 final transcript를 append-only로 유지하는 것이다. 이미 확정된 문장은 UI와 번역 큐에서 되돌리지 않는다. 대신 확정 전 후보는 다음 윈도우에서 계속 갱신될 수 있다.

## 5. 리비전 생명주기

리비전 생명주기는 staged 후보가 final transcript가 되기까지의 상태 전이를 정의한다.

- `stage_start`: 새 후보가 staged 상태로 진입한다.
- `stage_revision`: 다음 윈도우의 후보가 기존 staged 후보의 리비전으로 판정된다.
- `stage_replace`: 다음 후보가 리비전이 아닌 별도 후보로 판정된다.
- `stage_replace_deferred`: 기존 후보가 확정 기준에 도달하지 못해 새 후보를 candidate buffer에 보류한다.
- `stage_queue_enqueue` / `stage_queue_promote`: 생성순서 보존을 위해 보류 후보를 queue에 넣고, 앞 후보 정리 뒤 순서대로 승격한다.
- `stage_finalize_before_replace`: 새 completed 후보가 들어오기 전에 관찰 횟수 기준을 통과한 기존 staged 후보를 먼저 확정한다.
- `finalize_recent_echo_suppressed`: 이미 final로 확정한 문장과 유사한 대체 후보가 같은 위치에서 다시 등장해 중복 출력을 억제한다.
- `finalized`: 후보가 final transcript로 확정된다.
- `candidate_duplicate_suppressed`: 이미 committed된 내용과 중복되어 출력하지 않는다.

일반 후보는 여러 chunk에서 재확인된 뒤 확정된다. 현재 운영 계약은 `sentenceFinalizeAge`로 staged 후보의 관찰 횟수를 정의하고, 영어/한국어/중국어 기본값 모두 3회를 기준으로 한다. 미확정 replacement는 기존 후보를 즉시 삭제하지 않고 candidate buffer에 보류한다. 같은 revision 계열에서 나중 후보가 final로 소비되면 이전 미소비 후보는 stale revision으로 폐기한다. STT text가 없는 chunk는 age 증가 근거로 쓰지 않고, 반복 no-text 구간의 미확정 후보는 final이 아니라 stale 후보로 폐기할 수 있다.

## 6. 문맥 윈도우와 확정 단위

문맥 윈도우는 STT 모델에 전달되는 오디오 범위를 의미한다. 긴 문맥 윈도우는 모델이 더 많은 문맥을 보고 동음어와 문장 구조를 판단하게 해 전사 안정성을 높일 수 있다. 그러나 final transcript는 사용자가 보는 텍스트이므로 낮은 지연과 적절한 문장 길이가 필요하다.

운영 관측에서는 중국어 `windowSeconds=30`이 raw STT 안정성을 높이는 경향을 보였지만, final transcript가 긴 문장으로 묶이고 갱신이 늦어지는 문제가 관측되었다. 이후 원문창이 raw STT가 아니라 staged 후보를 표시하던 문제를 수정하면서 작은 윈도우 품질에 대한 해석을 재검토했다. 현재 기본 계약은 STT 언어별로 분리하며, 영어는 `windowSeconds=20`, 한국어는 `windowSeconds=10`, 중국어는 `windowSeconds=15`를 기준으로 한다. `stepSeconds=1`, `maxNewTokens=192`, `sentenceFinalizeAge=3`은 세 언어 공통 기준으로 둔다.

## 7. 평가 설계와 지표

본 연구의 실험 단위는 공개 코퍼스의 오프라인 ASR 점수가 아니라, 실제 애플리케이션에서 반복 관측된 실시간 실패 구간이다. 운영 로그에서 확정 누락, 중복 확정, 문장 파괴, staged queue 잔류, no-end fragment final, 최근 final echo가 보이는 구간을 수집하고, 각 구간의 연속 STT window 출력과 기대 final 문장을 `tests/eval/dictation_ai/sbd_text_cases.sample.jsonl`에 누적한다. 이 샘플은 `tests/eval/dictation_ai/sbd_benchmark.py`가 replay하며, 실제 SaT 모델을 `cuda + float16`으로 실행해 문장 후보 생성과 revision lifecycle을 함께 평가한다. 런타임 임계값은 `src/app/dictation_pipeline_settings.py`에 모아 관리하고, 값 변경은 벤치 결과와 함께 실험일지에 기록한다.

실험은 세 계층을 분리한다.

1. `RecognitionHypothesis` 품질: STT backend가 window 단위로 생성한 raw text와 segment 품질을 본다.
2. `SentenceCandidateSet` 품질: SaT 기반 SBD가 completed/pending 후보를 어떤 순서와 경계로 생성하는지 본다.
3. `CommittedTranscriptEvent` 품질: 후보가 age, revision 유사도, recent final memory, candidate queue를 거쳐 final-only sink로 소비되는지 본다.

이 설계에서 벤치마크는 품질 게이트가 아니라 성능 추적 하네스다. 관측 케이스가 늘면 난도가 바뀌므로 `pass_rate`는 논문 지표로 쓰지 않는다. 대신 `final_precision`, `final_recall`, `final_f1`, `final_boundary_f1`, `finalized_per_stage_start`, `pending_exact_match`, `staged_exact_match`, lifecycle metric count를 함께 본다. 특히 `final_f1`은 기대 문장 내용 회수율을 보여주지만, 문장 경계가 사용자에게 읽히는 단위와 맞는지는 `final_boundary_f1`이 별도로 보여준다.

주요 지표는 다음과 같다.

| 지표 | 의미 |
| --- | --- |
| `revision` | 이전 partial/final 문장이 새 STT 윈도우에서 올바르게 갱신되는지 |
| `distinct` | 서로 다른 문장을 잘못된 revision으로 병합하지 않는지 |
| `collapse` | 같은 의미의 인접 반복 문구를 줄이는지 |
| `replacement` | staged 후보 교체 시 교체/확정/중복 억제 결정이 의도와 맞는지 |
| `pending` | 긴 pending이 확정되지 않는 사유를 추적하는지 |
| `coalesce` | 중국어 completed 후보를 같은 STT 윈도우 관찰 단위로 병합하고 영어/한국어 경계 단위는 보존하는지 |
| `duplicate_suppression` | 이미 확정된 문장의 재출력을 억제하는지 |
| `final_quality` | final 후보가 CJK 반복 n-gram, 내부 공백, 과도한 fragment 같은 품질 위험을 갖는지 |
| `pending_quality` | pending 버퍼가 반복 누적되거나 장기 보류되는지 |
| `runtime_metrics` | 중복 억제, delta trim, final quality, queue residue를 분리 계측하는지 |
| `sink_contract` | 전사 창과 번역 sink가 final 이벤트만 소비하는지 |

운영 벤치마크는 품질 게이트가 아니라 성능 추적 자료다. 2026-06-20 기준 로그 기반 SBD 벤치마크는 164개 케이스를 포함하며, 실제 `sat + cuda + float16` 경로에서 `final_f1_avg=0.705`, `final_precision_avg=0.775`, `final_recall_avg=0.688`, `final_boundary_f1_avg=0.280`, `finalized_per_stage_start=0.684`를 기록했다. 이 결과는 내용 회수 F1과 문장 경계 F1이 자주 분리됨을 보여준다. 예를 들어 여러 영어 로그 케이스는 `final_f1`이 0.8 이상이어도 `final_boundary_f1=0.0`이었고, 이는 실제 사용자 품질을 final F1만으로 판단할 수 없다는 근거가 된다.

평가 시 raw STT window 결과와 revision lifecycle을 거친 final transcript를 분리한다. raw STT는 모델 전사 품질을, final transcript는 사용자에게 표시되는 실시간 자막 품질을 나타낸다. 정답 전사 코퍼스가 준비되면 CER/WER와 deletion/duplicate insertion rate를 보조 지표로 추가할 수 있지만, 현재 운영 판단은 로그 기반 의심 사례와 벤치 추적 지표를 중심으로 한다.

## 8. 운영 관측

한국어와 영어에서는 `faster-whisper + large-v3` 기반 전사가 현재 운영 후보로 유지된다. 중국어에서는 Whisper/faster-whisper의 의미 보존과 문장 구조가 부족했고, `qwen3-asr-transformers + qwen3-asr-0.6b`가 더 나은 후보로 관측되었다. FunASR 계열은 처리 속도는 빠르지만 의미 보존, stage churn, 확정률에서 불리했다.

2026-06-14 중국어 30분 모니터링에서는 stage replace/unconfirmed replacement가 많이 발생했고, 계산 시간보다 후보 생명주기가 병목으로 나타났다. `windowSeconds=30`은 raw STT 흔들림을 줄였지만, 긴 문장 확정과 final 지연을 증가시켰다. 2026-06-16 로그에서는 한 STT chunk 안의 후속 completed 후보가 첫 관찰 후보를 `next_completed`로 즉시 final 확정시키는 사례가 관측되어, 중국어 multi-completed 후보를 하나의 관찰 단위로 병합하고 교체 직전 확정에 `sentenceFinalizeAge` 기준을 적용했다.

2026-06-15 로그에서는 pending 텍스트와 다음 STT 윈도우가 같은 CJK 구간을 내부 중간부터 다시 내보내는 현상이 관측되었다. 한때 pending/new 접합 보정으로 분류했지만, 학술적 근거가 부족해 운영 요구사항에서는 제외했다. 현재는 STT/backend 품질, 문장 경계, revision lifecycle 지표로 분리해 관측한다.

2026-06-20 영어 장시간 로그에서는 확정 누락과 중복 확정의 원인이 단일 임계값보다 active staged와 queue 후보 소비 순서, no-end fragment 품질, terminal tail split, recent final delta trim의 상호작용에 있음을 확인했다. `MAX_STAGED_SENTENCE_QUEUE`를 12에서 20으로 늘린 실험은 replacement rate/North Korea/underpopulation 케이스에서 `stage_queue_drop_oldest=8`을 0으로 낮추고 해당 케이스 `final_f1`을 0.500에서 0.621로 개선했다. 전체 평균은 `final_f1_avg`가 약 0.700에서 0.701로 소폭 개선되는 수준이었으므로, 큐 한도 증가는 유지하되 stale 후보 잔류를 계속 관찰하는 보수적 변경으로 분류했다.

같은 날 추가한 UFO/aliens, accelerating launches/launched mass, Optimus surgeons/Zimbabwe, supply chain/medicine, chimps/Raptor 등 케이스는 공통적으로 내용 회수와 boundary 품질이 분리되는 양상을 보였다. 일부 케이스는 false positive 없이 주요 내용을 회수했지만 후반 문장이 staged queue에 남았고, 일부 케이스는 `So what fraction of all that of accelerating launches.`처럼 앞뒤 문맥이 섞인 final을 만들었다. 따라서 최신 실험 판단은 “final F1 상승”보다 “boundary/staged residue와 중복 억제의 균형”을 함께 보는 방향으로 정리된다.

## 9. 논의

실시간 전사의 품질은 raw ASR 정확도만으로 판단할 수 없다. 사용자가 보는 품질은 final transcript가 언제, 어떤 단위로, 얼마나 중복 없이 확정되는지에 크게 좌우된다. 특히 번역을 포함하는 시스템에서는 확정되지 않은 문장을 번역하면 번역 중복과 번역 되돌림이 발생한다. 따라서 번역은 final transcript 중심으로 수행하고, provisional translation은 별도 정책으로 분리해야 한다.

실험은 문맥 길이와 확정 단위의 분리가 중요함을 보여준다. 긴 문맥은 STT에 유리하지만 finalization latency와 stale staged 후보에는 불리할 수 있다. 그러므로 긴 STT context를 쓰더라도 final commit unit은 문장 후보, revision 계열, candidate age, recent final memory를 통해 별도로 제어해야 한다.

## 10. 한계

현재 연구는 운영 로그 기반 관측과 텍스트 replay 벤치가 중심이며, 동일 오디오 replay 기반 통제 실험은 제한적이다. 정답 전사 코퍼스가 없어 CER/WER 기반 정량 평가는 아직 보조 지표로만 논의된다. 또한 사용자 체감 지연, 가독성, 번역 만족도에 대한 사용자 연구는 포함하지 않았다. 본 논문의 실험 결과는 현재 애플리케이션의 운영 로그와 벤치 샘플에서 관측된 실패 유형과 개선 근거로 해석해야 한다.

## 11. 결론

본 연구는 다국어 실시간 전사 및 번역 시스템에서 리비전 인지 확정 계층의 필요성을 제시했다. STT 모델의 원시 가설, 문장 경계 검출, 확정 생명주기, final-only sink 계약은 서로 다른 실패 원인을 갖기 때문에 분리 평가되어야 한다. 특히 긴 문맥은 STT 안정성을 높일 수 있지만 final transcript 지연과 긴 문장 확정 문제를 유발한다. 따라서 실시간 전사 시스템은 문맥 윈도우와 확정 단위를 분리하고, 중복 억제와 리비전 생명주기를 명시적으로 계측해야 한다.

## 참고 문헌

상세 참고 문헌은 [받아쓰기 AI 참조 레퍼런스 모음](../2026-06-16-dictation-ai-reference-index.md)에 통합한다. 실시간 처리 파이프라인 기준은 [받아쓰기 AI 실시간 처리 파이프라인 기준](../2026-06-16-dictation-ai-realtime-pipeline.md)을 따른다. 핵심 근거는 다음과 같다.

- Radford et al., [Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356). Whisper 계열 모델을 로컬 다국어 ASR backend로 쓰는 배경 근거다.
- Macháček et al., [Turning Whisper into Real-Time Transcription System](https://arxiv.org/abs/2307.14743) 및 Whisper-Streaming demo paper. Whisper가 본래 실시간 모델은 아니며, local agreement와 adaptive latency가 필요하다는 비교 기준이다.
- Whetten et al., [Evaluating Automatic Speech Recognition in an Incremental Setting](https://arxiv.org/abs/2302.12049). 실시간 ASR을 WER만이 아니라 latency와 already-recognized-word update로 평가해야 한다는 근거다.
- Frohmann et al., [Segment Any Text](https://arxiv.org/abs/2406.16678). punctuation 의존도가 낮은 다국어 문장 분절 모델을 SBD 후보 생성기로 쓰는 근거다.
- Behre et al., [Streaming Punctuation for Long-form Dictation with Transformers](https://arxiv.org/abs/2210.05756). 긴 받아쓰기에서 bounded right context와 punctuation/segmentation 품질을 분리해 보는 근거다.
- Shi et al., [Qwen3-ASR Technical Report](https://arxiv.org/abs/2601.21337). 중국어 STT 후보로 Qwen3-ASR 0.6B/1.7B 계열을 비교하는 근거다.
- Yao et al., [WeNet: Production oriented Streaming and Non-streaming End-to-End Speech Recognition Toolkit](https://arxiv.org/abs/2102.01547). native streaming/non-streaming E2E ASR 비교군이다.
- NLLB Team et al., [No Language Left Behind](https://arxiv.org/abs/2207.04672). final-only 번역 sink에서 사용하는 NLLB 계열 번역 backend의 배경 근거다.
