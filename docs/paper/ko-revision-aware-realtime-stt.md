# 불안정한 실시간 STT 스트림의 final-only 번역 입력 안정화

## 부제

로그 기반 실패 replay, SaT/CUDA 문장 경계 벤치, revision-aware lifecycle 계측을 통한 보수적 분석 사례

## 초록

실시간 음성 전사(automatic speech recognition, ASR) 모델은 스트리밍 또는 준스트리밍 환경에서 매 입력 윈도우마다 부분 가설(partial hypothesis)을 재작성한다. 본 연구의 관심사는 raw STT 정확도 자체를 개선하는 것이 아니라, 부정확하고 흔들리는 STT 가설을 사람이 속기하듯 잠깐 보류하고 반복 관측된 문장 단위만 순서대로 확정해 final-only 번역 입력으로 안정화하는 것이다. 이를 위해 원시 ASR 가설(raw ASR hypothesis), 문장 경계 검출(sentence boundary detection), 리비전 생명주기(revision lifecycle), final-only 번역 입력 제어를 분리해 계측하는 후처리 구조를 제안한다. 특히 한국어, 영어, 중국어 환경에서 문맥 윈도우(context window) 길이와 확정 단위(commit unit)의 상호작용을 분석하고, 긴 문맥이 원시 STT 가설을 더 안정적으로 만들 수 있는 동시에 사용자 화면의 최종 전사(final transcript) 갱신을 늦출 수 있음을 운영 로그와 텍스트 벤치마크 기반으로 관찰한다. 1223개 로그 기반 failure-enriched replay 케이스를 실제 `sat + cuda + float16` 경로로 평가한 최신 challenge 기준선은 `final_f1_avg=0.482`, `final_precision_avg=0.575`, `final_recall_avg=0.449`, `final_boundary_f1_avg=0.113`이다.

본 논문의 기여는 세 가지다. 첫째, 실시간 ASR 출력의 불안정성을 단순 UI 문제가 아니라 리비전 인지 확정 문제로 모델링한다. 둘째, 중복 증폭(duplicate amplification), 확정 누락(missing final), 확정 지연의 대리 신호(candidate age, staged residue), pending overrun, replacement churn을 분리한 평가 지표를 제시한다. 셋째, 다국어 실시간 전사 시스템에서 STT 모델, 문장 경계 모델, 확정 정책, 번역 sink를 독립 축으로 검증해야 한다는 운영 근거를 제시한다. 이 결과는 완성된 범용 해법이나 운영 평균 성능 개선 주장이 아니라, 운영 로그 기반 실패 사례를 벤치마크로 누적하며 파이프라인의 병목을 보수적으로 분석하는 사례 연구로 해석해야 한다.

## 1. 서론

최근 대형 음성 인식 모델과 다국어 번역 모델의 발전으로 로컬 환경에서도 실시간 전사 및 번역 기능을 구현할 수 있게 되었다. 하지만 실시간 전사 애플리케이션에서 실제 사용자에게 표시되는 품질은 모델의 오프라인 전사 정확도만으로 설명되지 않는다. 동일한 오디오 구간이 여러 슬라이딩 윈도우(sliding window)에 반복 포함되기 때문에 ASR 모델은 매번 비슷하지만 조금씩 다른 문장을 생성한다. 이 결과를 그대로 화면에 표시하면 중복 문장, 소실된 문장, 되돌려지는 표현, 번역 중복이 발생한다.

본 연구는 이러한 문제를 "리비전 인지 확정 계층(revision-aware finalization layer)"의 설계 문제로 본다. 핵심 질문은 다음과 같다.

- 부분 전사(partial transcript)가 계속 바뀌는 상황에서 어떤 텍스트를 최종 전사로 확정할 것인가?
- 긴 문맥 윈도우가 전사 안정성을 높일 때, 확정 지연과 긴 문장 생성 문제를 어떻게 제어할 것인가?
- STT 오류, 문장 경계 오류, 확정 정책 오류, 번역 오류를 어떻게 분리해 측정할 것인가?
- 한국어, 영어, 중국어처럼 언어 구조가 다른 입력에서 동일한 후처리 정책이 유지 가능한가?

현재까지의 실험은 이 질문 중 일부에만 답한다. 유지할 수 있는 중심 가설은 "불안정한 STT window hypothesis를 final-only 번역 입력으로 만들려면 revision-aware lifecycle과 계층별 지표가 필요하다"는 것이다. 본 연구는 raw STT 정확도 개선은 주장하지 않는다. 반대로 "운영 평균 품질이 개선되었다", "번역 품질이 개선되었다"는 주장도 현재 challenge replay만으로는 보류한다.

| 가설 | 상태 | 본 논문에서의 처리 |
| --- | --- | --- |
| partial hypothesis와 final transcript를 분리하지 않으면 중복/누락이 발생한다. | 유지 | 운영 로그와 challenge replay의 실패 유형으로 제시한다. |
| SBD 후보와 final lifecycle은 별도 계층으로 평가해야 한다. | 유지 | `final_f1`, `final_boundary_f1`, lifecycle counter, staged residue를 분리 지표로 둔다. |
| 단일 threshold 튜닝으로 목표 품질을 달성할 수 있다. | 축소 | 12개 parameter axis 결과를 통해 대부분 trade-off 또는 0 delta였음을 보고한다. |
| failure-enriched challenge replay 평균을 운영 평균으로 볼 수 있다. | 폐기 | challenge replay와 representative corpus를 분리하는 이유로 설명한다. |
| final-only sink가 번역 안정성을 높인다. | 보류 | 시스템 목표와 문헌 배경으로 제시하되, translation replay 전에는 성능 주장으로 쓰지 않는다. |

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

아래 표는 논문 초안에서 직접 인용 가능한 최소 근거만 둔다. 운영 로그에서 관측한 중복 확정, 확정 누락, age/window 기본값, 벤치 수치는 외부 논문이 아니라 프로젝트 실험일지를 근거로 해석한다. 레퍼런스 컨텍스트 문서의 다른 항목은 비교군 또는 후속 후보이며, 원문 확인 없이 본 논문의 핵심 주장 근거로 승격하지 않는다.

| 근거 축 | 원문 요약 | 본 연구에서의 사용 |
| --- | --- | --- |
| [Whisper](https://arxiv.org/abs/2212.04356) | Whisper 원 논문은 대규모 다국어/멀티태스크 약지도 학습으로 zero-shot 전사와 번역 일반화가 가능함을 보인다. 다만 이 논문은 실시간 partial revision 문제를 해결하는 시스템 논문은 아니다. | `faster-whisper + large-v3`를 영어/한국어 운영 후보로 쓰되, raw window 결과를 바로 final로 쓰지 않는 전제다. |
| [Whisper-Streaming](https://arxiv.org/abs/2307.14743) | Whisper-Streaming은 Whisper가 실시간 전사용으로 설계되지 않았기 때문에 local agreement와 self-adaptive latency를 얹어 확정 prefix와 미확정 hypothesis를 분리한다. | 본 연구의 `raw/pending/staged/final` 분리와 여러 window에서 재관측된 후보만 final로 소비하는 정책의 직접 비교 기준이다. |
| [Incremental ASR 평가](https://arxiv.org/abs/2302.12049) | incremental ASR 평가는 WER만으로는 부족하며 latency와 이미 인식된 단어의 update/revoke를 함께 봐야 한다고 제안한다. | `final_f1`, `final_boundary_f1`, replacement churn, staged residue, recent final echo를 분리해 보는 이유다. |
| [Segment Any Text](https://arxiv.org/abs/2406.16678) | SaT는 punctuation 의존도를 낮추고 여러 도메인/언어에서 문장 분절을 수행하도록 설계되었다. | regex/ad-hoc 문장 분할을 운영 경로에서 제외하고 SaT를 completed/pending 후보 생성기로 쓰는 근거다. |
| [Streaming punctuation](https://arxiv.org/abs/2210.05756) | 긴 받아쓰기에서는 WER가 좋아도 pause, 느린 발화, punctuation/segmentation 문제가 남으며, bounded right context와 dynamic window가 필요하다고 보고한다. | punctuation/right-context를 final trigger가 아니라 SBD 후보와 boundary confidence의 보조 신호로 쓰는 근거다. |
| [Qwen3-ASR](https://arxiv.org/abs/2601.21337) | Qwen3-ASR 보고서는 0.6B/1.7B 모델이 52개 언어/방언 ASR을 지원하고, 공개 벤치 외 실제 사용 시나리오 품질 차이를 별도로 평가해야 한다고 강조한다. | 중국어에서 `qwen3-asr-transformers + qwen3-asr-0.6b`를 운영 후보로 두고, STT 품질과 final lifecycle 품질을 분리 평가하는 근거다. |
| [NLLB](https://arxiv.org/abs/2207.04672) | NLLB는 다국어 번역을 200개 언어 규모로 확장하고 FLORES-200, human evaluation, toxicity benchmark로 평가한다. | 번역 backend 후보의 배경 근거다. final-only sink 계약 자체는 프로젝트 파이프라인과 실험일지를 근거로 설명한다. |
| [Optimizing Sentence Segmentation for Speech Translation](https://isl.iar.kit.edu/downloads/803_Interspeech-2007_Rao.pdf) | speech translation에서 segment length를 MT 시스템에 맞게 최적화하면 BLEU가 개선될 수 있고, ASR WER가 번역 성능에 비선형적으로 영향을 준다고 보고한다. | 번역 단위가 downstream 품질에 영향을 준다는 비교 근거다. 현재 파이프라인의 VAD/pause 기반 구현 근거나 최적 segment length 근거로 쓰지는 않는다. |

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

구현 범위는 의도적으로 좁게 둔다. 운영 경로는 오디오 윈도우에서 STT 가설을 만들고, 모델 기반 SBD로 문장 후보를 만든 뒤, revision-aware buffer가 final 이벤트만 발행하는 구조다. VAD/silence 기반 확정, 언어별 정규식 분기, CJK 문자열 접합, 단어별 예외 규칙은 현재 구현 기여에 포함하지 않는다. 이 제외 기준은 단순화를 위한 것이 아니라, 일부 로그 케이스에 맞춘 규칙이 다른 언어와 다른 발화에서 중복 확정 또는 확정 누락을 늘릴 수 있다는 실험 판단에 따른 것이다.

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

일반 후보는 여러 chunk에서 재확인된 뒤 확정된다. 현재 운영 계약은 `sentenceFinalizeAge`로 staged 후보의 관찰 횟수를 정의하고, 영어/한국어/중국어 기본값 모두 3회를 기준으로 한다. 미확정 replacement는 기존 후보를 즉시 삭제하지 않고 candidate buffer에 보류한다. 리비전 계열 판단 기준은 완전 문자열 일치가 아니라 token-sentence(토큰센텐스) 유사도, 공통 token run, coverage다. 다만 새 후보가 같은 발화 구간으로 보이더라도 token-sentence 기준상 confirmation을 보존할 수 없는 reset 대상이면 active staged 후보를 즉시 덮지 않고 candidate buffer에서 반복 관측을 기다린다. candidate buffer의 오래된 후보가 짧은 과거 prefix를 끌고 온 상태라면 같은 본문 coverage가 높은 새 후보를 preferred revision으로 보아 prefix 오염 final을 줄인다. active staged 후보가 과거 prefix 뒤에 새 문장의 앞부분만 가진 형태이고 queue 후보가 그 앞부분에서 시작해 suffix를 이어가면, 같은 token-sentence revision으로 보아 queue 후보를 우선한다. 짧은 CJK staged 후보가 replacement와 충돌할 때는 max age 직후 active를 폐기하지 않고 별도 hold window를 두어 confirmation/revision 반복 관측 기회를 보존한다. recent final memory는 이미 final된 prefix의 의미 있는 suffix만 회수하고, 이미 final된 동일 token-sentence와 긴 문장의 fuzzy tail echo를 다시 확정하지 않는다. 같은 revision 계열에서 나중 후보가 final로 소비되면 이전 미소비 후보는 stale revision으로 폐기한다. STT text가 없는 chunk는 age 증가 근거로 쓰지 않고, 반복 no-text 구간의 미확정 후보는 final이 아니라 stale 후보로 폐기할 수 있다.

## 6. 문맥 윈도우와 확정 단위

문맥 윈도우는 STT 모델에 전달되는 오디오 범위를 의미한다. 긴 문맥 윈도우는 모델이 더 많은 문맥을 보고 동음어와 문장 구조를 판단하게 해 전사 안정성을 높일 수 있다. 그러나 final transcript는 사용자가 보는 텍스트이므로 낮은 지연과 적절한 문장 길이가 필요하다.

운영 관측에서는 중국어 `windowSeconds=30`이 raw STT 안정성을 높이는 경향을 보였지만, final transcript가 긴 문장으로 묶이고 갱신이 늦어지는 문제가 관측되었다. 이후 원문창이 raw STT가 아니라 staged 후보를 표시하던 문제를 수정하면서 작은 윈도우 품질에 대한 해석을 재검토했다. 현재 기본 계약은 STT 언어별로 분리하며, 영어는 `windowSeconds=20`, 한국어는 `windowSeconds=10`, 중국어는 `windowSeconds=15`를 기준으로 한다. `stepSeconds=1`, `maxNewTokens=192`, `sentenceFinalizeAge=3`은 세 언어 공통 기준으로 둔다.

## 7. 평가 설계와 지표

본 연구의 실험 단위는 공개 코퍼스의 오프라인 ASR 점수가 아니라, 실제 애플리케이션에서 반복 관측된 실시간 실패 구간이다. 운영 로그에서 확정 누락, 중복 확정, 문장 파괴, staged queue 잔류, no-end fragment final, 최근 final echo가 보이는 구간을 수집하고, 각 구간의 연속 STT window 출력과 기대 final 문장을 `tests/eval/dictation_ai/sbd_cases/{en,ko,zh}/` 아래 언어별 JSONL shard로 누적한다. 여기서 `chunks`는 실제 STT 컨텍스트 윈도우 처리 결과이며, 실험 목표는 이 입력으로부터 문장 경계와 final lifecycle을 산출해 확정한 `expected_final`과 유사한 final 문장이 도출되는지 평가하는 것이다. 이 케이스 집합은 `tests/eval/dictation_ai/sbd_benchmark.py`가 replay하며, 실제 SaT 모델을 `cuda + float16`으로 실행해 문장 후보 생성과 revision lifecycle을 함께 평가한다. 런타임 임계값은 `src/app/dictation_pipeline_settings.py`에 모아 관리하고, 값 변경은 벤치 결과와 함께 실험일지에 기록한다.

현재까지의 실험 설계는 일부만 유효하다. 유효한 부분은 failure-enriched challenge replay를 통해 같은 입력 집합에서 final lifecycle 정책의 trade-off를 반복 측정하는 구조다. 이 구조는 확정 누락, 중복 확정, staged residue, boundary mismatch처럼 실제 운영에서 관측된 실패를 재현하고, 파라미터나 로직 변경이 어떤 증상을 줄이거나 늘리는지 비교하는 데 적합하다. 반대로 이 구조만으로 일반 사용자 발화 전체의 평균 품질, raw STT 정확도, 번역 품질, 실제 지연 시간을 주장하는 것은 부적절하다. 따라서 논문 실험은 "점수 목표를 정하고 threshold를 올리는 실험"이 아니라 `challenge replay`와 `representative operating sample`을 분리해, 실패 재현과 운영 평균 추정을 다른 표에서 해석하는 구조로 재구성해야 한다.

이 재구성은 논문 주제를 좁히기 위한 것이다. 현재 자료는 "STT 모델의 정확도를 개선했다"거나 "운영 평균 품질을 증명했다"는 논문에는 부족하다. 대신 "불안정한 STT window 가설을 final-only 번역 입력으로 소비하기 위해 어떤 중간 상태와 지표가 필요한가"라는 시스템 실험에는 유효하다. 그러므로 본 논문의 실험 방법은 세 단계로 정리한다.

1. 실패 재현: 운영 로그에서 수집한 challenge replay로 중복 확정, 확정 누락, boundary mismatch, staged residue가 재현되는지 확인한다.
2. 축별 비교: 한 번에 한 lifecycle 파라미터 또는 구조 변경만 baseline과 비교하고, 전체 평균과 언어별/태그별 delta를 함께 기록한다.
3. 주장 분리: challenge replay 결과는 failure lifecycle trade-off로만 해석하고, 운영 평균/실제 지연/번역 churn은 representative corpus와 translation replay가 준비된 뒤 별도 실험으로 다룬다.

참조 논문과 비교했을 때 본 연구의 위치도 이 범위로 제한한다. Whisper-Streaming과 incremental ASR 평가는 partial hypothesis와 committed output을 분리해야 한다는 직접 비교 기준을 제공한다. SaT와 streaming punctuation 연구는 rule/regex보다 모델 기반 경계 후보와 right context가 필요하다는 배경을 제공한다. Speech translation segmentation 연구는 번역 단위가 downstream 품질에 영향을 줄 수 있음을 보여준다. 그러나 이 문헌들은 현재 앱의 `sentenceFinalizeAge`, queue 크기, CJK similarity threshold를 직접 정당화하지 않는다. 그 값들은 앱 로그 replay에서 관측한 trade-off로만 설명한다.

대표 표본 실험은 아직 준비 단계다. 운영 로그 source audit과 review packet은 사람이 참조 전사를 작성할 수 있는 후보를 제공하지만, 그 자체가 정답 corpus는 아니다. 정식 representative case는 사람이 `expected_final`을 확정하고 reviewer metadata를 남긴 JSONL shard만 인정한다. 따라서 review packet 5개가 준비된 현재 상태는 "운영 평균 실험 가능"이 아니라 "수작업 대표 표본 작성 가능"으로 해석한다. 이 게이트를 통과하기 전까지 본문 결과와 초록의 수치는 challenge replay 범위로만 제한한다.

| 판정 | 현재 자료로 가능한 주장 | 현재 자료로 부족한 주장 | 필요한 후속 자료 |
| --- | --- | --- | --- |
| 유지 | partial hypothesis를 바로 final로 소비하면 중복/누락이 발생하므로 revision-aware lifecycle이 필요하다. | 전체 사용자 입력에서 평균적으로 얼마나 좋아지는지 | 시간/세션 기준 representative corpus |
| 유지 | `final_f1`과 `final_boundary_f1`은 분리해서 봐야 한다. | 문장 경계 품질이 번역 BLEU나 사용자 만족도를 얼마나 개선하는지 | final timestamp와 번역 output replay |
| 유지 | 단일 threshold 조정보다 언어별/태그별 residual과 lifecycle counter가 채택 판단에 더 유용하다. | 특정 임계값이 보편적으로 최적인지 | 같은 corpus에서 축별 sweep과 representative 확인 |
| 유지 | STT backend, SBD 후보, final lifecycle, final-only sink를 분리 계측해야 한다. | raw STT 모델 자체의 우열이나 일반 ASR 정확도 | 별도 ASR 참조 전사와 CER/WER 평가 |
| 폐기 | 실패 case 평균을 운영 평균처럼 해석한다. | challenge set의 `final_f1_avg`를 제품 품질 평균으로 제시한다. | corpus role이 분리된 결과표 |

실험 프로토콜은 다음 원칙을 따른다.

- 벤치는 실제 `sat + cuda + float16` 경로로만 실행한다. mock, smoke, CPU 실행은 성능 근거로 쓰지 않는다.
- 샘플은 성공해야 하는 단위 테스트가 아니라 로그에서 관측된 실패 현상을 재현하는 성능 추적 자료다.
- 케이스는 앱 로그의 연속 STT window에서 수집하고, `expected_final`을 확정한 JSONL만 benchmark 입력으로 사용한다. 케이스의 저장 그룹은 언어이며, 파일명 해시는 큰 컨텍스트 입력을 작은 shard로 나누기 위한 저장 단위다. 수집/검토/승격 자동화 도구는 현재 연구 범위에서 폐기하고, 케이스 데이터 자체만 `tests/eval/dictation_ai/sbd_cases/` 아래에 보관한다.
- 케이스가 많아지면 JSONL 파일과 하위 디렉터리로 분할한다. 벤치는 단일 파일, 여러 파일, glob, 디렉터리를 입력받아 재귀적으로 로딩하고, 중복 case id와 draft marker는 실패로 처리한다.
- pending/staged 전용 benchmark case는 `expected_final=[]`일 수 있으므로, finalization 목표 수량은 비어 있지 않은 `expected_final` 케이스 수로 별도 검증한다.
- 성능 수치는 reviewed JSONL을 실제 `sat + cuda + float16` 벤치 또는 parameter sweep으로 실행한 결과만 사용한다. 수집 과정의 운영 편의 지표는 논문 성능 수치로 사용하지 않는다.
- 케이스를 추가하면 평균 점수가 낮아질 수 있으므로, `pass_rate`나 단일 평균값만으로 개선 여부를 판단하지 않는다.
- 파라미터 변경은 같은 reviewed 샘플 집합에서 한 번에 한 축만 비교하고, 변경 전후의 lifecycle metric을 함께 기록한다. 논문 근거로 채택하려면 변경값, 영향을 받는 실패 유형, 개선 지표, 악화 지표를 함께 남긴다.
- 모델/STT 품질, SBD 후보 품질, final lifecycle 품질, 번역 sink 계약을 서로 다른 실패 축으로 본다.

파라미터 sweep은 `AVC_DICTATION_*` 환경변수로 수행한다. 실험 가능한 값은 `dictation_tuning_manifest()`에 등록된 실효 축으로 제한한다. 현재 manifest는 `MAX_STAGED_SENTENCE_QUEUE`, `STAGED_QUEUE_MAX_PROMOTION_AGE_CHUNKS`, `SENTENCE_CONFIRM_CHUNKS`, `SHORT_CJK_FINAL_UNITS`, `SHORT_NO_END_FRAGMENT_UNITS`, revision similarity 계열처럼 final lifecycle에 직접 영향을 주고 replay에서 delta가 관측되는 축을 중심으로 유지한다. `SENTENCE_CONFIRM_MAX_AGE_CHUNKS`, forced confirmation 계열, `SHORT_CJK_REPLACEMENT_HOLD_CHUNKS`처럼 현재 challenge replay에서 delta가 없거나 config 계약에 가려지는 축은 운영 상수로만 유지하고 sweep 후보에서 제외한다. STT 모델을 바꾸거나 언어별 문구 규칙을 추가하는 것은 이 논문의 lifecycle 튜닝 실험으로 보지 않는다. 운영 기본값은 단일 벤치 수치가 아니라 다수 로그 케이스에서 같은 방향의 개선이 반복될 때만 checked-in 상수로 반영한다. 외부 문헌은 partial hypothesis/final 분리, incremental ASR 안정성 평가, SBD 후보 생성의 근거로 쓰고, 개별 임계값 자체는 앱 로그 replay 실험으로만 정당화한다. 벤치 리포트에는 `dictation_tuning_protocol`과 `dictation_tuning_manifest`를 함께 저장해 실험 규칙, 각 파라미터의 env 이름, 기본값, 현재값, scope, 의도, 근거 분류를 결과와 함께 추적한다.

따라서 케이스 수집과 파라미터 채택은 별도 단계다. 앱 로그에서 관측한 실패 구간은 `expected_final`을 확인한 뒤 reviewed benchmark case로만 보관한다. 그 뒤 같은 reviewed case 집합에서 `AVC_DICTATION_*` override를 사용해 값을 바꿔 실행하고, `final_f1_avg`, `final_precision_avg`, `final_recall_avg`, `final_boundary_f1_avg`, `finalized_per_stage_start`와 주요 lifecycle counter를 함께 비교한다. draft 상태의 케이스는 논문 성능 수치에 포함하지 않는다.

파라미터 비교 실행은 `run_sbd_parameter_sweep.py`로 표준화한다. 이 도구는 `dictation_tuning_manifest`에 등록된 파라미터만 `NAME=VALUE` 형식으로 받아 `AVC_DICTATION_*` 환경변수로 전달하고, manifest의 `min_value`/`max_value` 범위를 벗어난 값은 실행 전에 거부한다. 항상 같은 `--cases` 입력을 사용해 `sbd_benchmark.py --device cuda --compute-type float16`을 반복 실행한다. 탐색 sweep은 현재 reviewed case 집합에서 수행할 수 있지만, 논문 근거용 sweep은 `--paper-evidence` 모드로 실행한다. 이 모드는 실행 전에 draft marker가 남은 케이스를 거부하고, 검토한 `expected_final` 케이스가 1000건에 도달했는지 확인한다. 실행 요약에는 `dictation_tuning_protocol`, manifest, 각 job의 env override, 출력 리포트 경로, corpus role, 핵심 metric, 언어별 `language_summary`, 실패 증상 태그별 `tag_summary`, baseline 대비 `metric_deltas`, `language_deltas`, `tag_deltas`가 함께 남는다. 또한 논문/실험일지에 직접 옮길 수 있도록 전체 metric, 언어별 delta, 주요 실패 태그 delta만 축약한 `evidence_summary`를 별도로 저장한다. 이 축약 요약은 전체 final F1 상승이 특정 언어의 precision 하락이나 주요 실패군의 boundary 악화를 가리는지 먼저 확인하기 위한 해석 장치다. `interpretation_flags`는 final F1 상승과 precision 하락이 동시에 나타나는 경우, 언어별 final F1 또는 precision 회귀, 주요 실패 태그의 precision/boundary 회귀를 자동으로 표시하고, `interpretation_flag_counts`는 한 sweep 안에서 같은 위험 신호가 몇 개 parameter 후보에서 반복됐는지 집계한다. `adoption_review`는 자동 채택/기각 판정이 아니라, 위험 flag가 있는 후보를 `review-risk`로 표시해 수동 해석을 요구하는 보수적 상태값이며, `adoption_review_counts`는 sweep 전체에서 검토 위험 후보가 몇 개인지 보여준다. 따라서 sweep 결과는 논문에서 "임계값 자체가 문헌에서 왔다"는 근거가 아니라, 문헌으로 정한 문제 설정 안에서 앱 로그 replay가 어떤 값을 지지했는지 보여주는 실험 기록으로 해석한다. 결과를 논문 표로 옮길 때는 `paper_evidence`, `corpus_role`, `experiment_stage`, `claim_scope_key`, `claim_scope`, `supported_claims`, `unsupported_claims`, `deferred_claims`, `runtime_contract`를 함께 확인한다. 현재 challenge replay 결과의 `experiment_stage`는 `challenge-replay`, `claim_scope_key`는 `failure-lifecycle-tradeoff`이고 설명용 `claim_scope`는 `failure-mode lifecycle trade-off only`이다. 향후 representative 결과는 `representative-replay` 및 `operating-average-finalization`으로 별도 표에서 해석한다. representative 결과는 `case_summary.representative_metadata`의 sampling unit, sampling rule, source log 분포를 함께 보존해야 한다. `evidence_protocol.required_evidence_fields`는 논문 표나 실험일지에 수치를 옮길 때 함께 보존해야 하는 최소 문맥을 나열한다. 이 필드가 가리키는 `paper_evidence`, `paper_evidence_eligible`, `corpus_role`, `experiment_stage`, `claim_scope_key`, `supported_claims`, `unsupported_claims`, `deferred_claims`, `runtime_contract`, `expected_final_case_count`, `parameter_axes`, `evidence_summary.results`, `evidence_summary.adoption_review_counts`가 함께 남아 있지 않은 결과는 정식 논문 근거로 승격하지 않는다. 실제 논문 근거용 summary는 `missing_required_evidence_fields=none`이어야 하며, dry-run처럼 `evidence_summary.results`가 없는 출력은 실행 계획 검증으로만 사용한다. 과거 report는 당시 저장된 필드 목록이 아니라 현재 `validate_sbd_evidence_report.py` 기준으로 다시 검사한 뒤 인용한다. 통합 readiness audit의 `checks.methodology`도 함께 확인해 complete report의 `experiment_stage`와 `claim_scope_key`가 challenge-only 논문 범위에 섞이지 않았는지 확인한다.

최신 challenge replay paper-evidence 케이스 집합은 1223건이며, 비어 있지 않은 `expected_final` 케이스는 1219건이다. 언어 분포는 영어 429건, 한국어 462건, 중국어 332건이다. 케이스는 `tests/eval/dictation_ai/sbd_cases/{en,ko,zh}/reviewed-context-{language}-{hash}.jsonl` shard에 저장한다. 파일명 해시는 큰 컨텍스트 입력을 작은 JSONL로 나누기 위한 저장 단위일 뿐 실험 의미를 갖지 않는다. 이 분포는 일반 발화 전체의 무작위 표본이 아니라, 실시간 전사에서 문제가 반복된 구간을 의도적으로 모은 failure-enriched challenge set이다.

따라서 현재 실험 설계의 의미는 공개 ASR benchmark처럼 모델 일반 성능을 측정하는 데 있지 않다. 같은 실패 입력 집합에서 finalization policy가 어떤 실패를 줄이고 어떤 실패를 늘리는지 재현 가능하게 비교하는 것이 목적이다. 이 설계에서 유효한 주장은 `raw STT`, `SBD 후보`, `revision lifecycle`, `final-only sink`를 분리 계측해야 한다는 점과, 단일 threshold 튜닝보다 lifecycle counter와 증상 태그별 delta가 파라미터 채택 판단에 더 유용하다는 점이다. 반대로 현재 벤치만으로 일반 사용자 전체 평균 품질, raw STT 정확도 개선, 번역 BLEU 개선, 실제 오디오 latency 개선을 주장하지 않는다.

후속 실험은 세 축으로 재구성한다. 첫째, 현재 1223건 집합은 challenge replay corpus로 유지해 회귀와 실패 유형별 튜닝 근거로 쓴다. 둘째, threshold sweep으로 설명되지 않는 queue/revision 병목은 구조 변경 실험으로 분리한다. 이때 `final_f1`만 보지 않고 queue residue, deferred replacement, boundary F1이 같은 방향으로 움직이는지 확인한다. 셋째, 논문 주장을 넓히려면 운영 로그에서 시간 구간 또는 세션 단위로 층화 추출한 representative corpus를 `tests/eval/dictation_ai/sbd_representative_cases/` 아래에 별도로 만든다. representative case는 관측된 실패 구간을 골라 담는 방식이 아니라 fixed interval, session window, deterministic hash sampling처럼 재현 가능한 선택 규칙을 metadata로 남겨야 한다. 표본 단위는 `time-window` 또는 `session-window`로 제한하고, 실패 유형 묶음이나 수동 후보 그룹은 representative 표본 단위로 쓰지 않는다. 가능하면 동일 오디오 replay와 사람이 작성한 참조 전사, final event timestamp를 연결해 latency, deletion, duplicate insertion, translation-side churn을 추가 평가한다. 이 축들을 섞으면 평균 점수의 의미가 흐려지므로, challenge set의 낮은 `final_f1_avg`, 구조 변경의 lifecycle counter 변화, representative set의 운영 평균은 별도 표로 보고해야 한다.

2026-06-21 기준 운영 로그 source audit에서는 `.tmp/logs/avc-whisper.log*` 95개 파일, 682,671라인, `stt_raw=64,918`, `finalize_event=11,464`, `transcript=32,950`이 확인되어 representative 후보 구간을 seed할 수 있는 상태로 판단했다. 엄격 집계에서도 STT 설정 marker는 `stt_backend_counts={faster-whisper:44, qwen3-asr-transformers:15}`, `stt_model_counts={large-v3:44, qwen3-asr-0.6b:13, qwen3-asr-1.7b:2}`로 분리 확인됐다. 그러나 이 결과는 case 자동 생성 근거가 아니다. 로그에는 현재 앱이 출력한 transcript와 final event가 들어 있고, 일부 회전 로그는 선택 구간 안에 loop-start 설정 line이 없을 수 있다. 따라서 representative corpus로 승격하려면 선택된 시간/세션 구간마다 STT/SBD/번역 runtime metadata를 다시 확인하고 사람이 `expected_final`을 별도로 확정해야 한다. 현재 논문에서 운영 평균 품질 주장은 여전히 보류한다.

이후 deterministic session-window manifest를 만들었을 때 runtime-homogeneous 조건을 만족하는 후보는 영어 3개, 한국어 3개, 중국어 1개였고, 언어별 최대 2개 선택 기준에서 총 5개 source만 검수 큐에 올랐다. 이 5개 source에서 review packet을 생성했을 때 source 누락은 없었고, source별 `stt_raw`는 698-819개, final event는 144-220개 범위로 남아 있었다. 또한 5개 packet 모두 raw STT, final event, transcript, performance event를 포함해 `ready_packet_count=5`로 확인됐다. packet validator 기준 총 event는 `raw_chunks=3789`, `final_events=911`, `transcripts=2942`, `performance_events=3851`이며, `not_ready_packet_count=0`, `missing_source_log_count=0`이었다. 다만 review packet의 interpretation은 `paper_evidence=false`, `case_generation=false`, `expected_final_generated=false`, `claim_scope=human review orientation packet only`다. 실제 `tests/eval/dictation_ai/sbd_representative_cases/`는 아직 README만 있으며 JSONL case가 없기 때문에 `validate_sbd_case_files.py`는 `no SBD case files matched`로 실패한다. 이는 representative corpus 구축이 가능한 상태이지만 아직 표본 수와 사람이 확정한 `expected_final`이 부족하다는 의미다. review packet은 사람이 구간을 읽기 쉽게 만드는 중간 산출물일 뿐, 운영 평균 수치나 정답 case로 사용하지 않는다. 정식 representative case로 승격할 때는 `review_packet_id`와 `expected_final_reviewed_by`를 필수 metadata로 남겨 사람이 확정한 expected final이라는 추적성을 확보한다.

이 재구성은 기존 실험을 폐기하는 것이 아니라 역할을 다시 배치하는 것이다. challenge replay는 논문 중심 실험으로 유지하지만 성능 일반화 자료가 아니라 실패 재현 자료로만 사용한다. threshold sweep은 기본값 채택/기각 근거로 축소하고, 논문 기여는 불안정한 STT hypothesis를 final-only sink로 보내기 전 어떤 상태와 지표를 분리해야 하는지 보여주는 데 둔다.

현재까지의 결과를 기준으로 실험 방법은 다음처럼 과감하게 축소한다. 첫째, 1223건 challenge replay는 유지하되 "운영 평균"이 아니라 "실패 중심 구조 분석"으로만 해석한다. 둘째, threshold sweep은 더 높은 `final_f1_avg`를 찾는 주 실험에서 제외하고, 이미 존재하는 정책의 채택/기각 기록으로만 남긴다. 셋째, 논문 중심 결과는 `final_f1_avg` 단독 상승이 아니라 `final_boundary_f1`, `stage_replace_deferred`, `stage_queue_revision`, queue residue, no-end quality block이 함께 보여주는 lifecycle 병목 분석으로 옮긴다. 넷째, 운영 품질이나 번역 안정성을 주장하려면 representative replay와 translation replay를 새 실험으로 분리한다.

따라서 본 논문의 방법론은 다음 판정표를 기준으로 읽어야 한다. 이 표는 기존 실험을 성공/실패로 단순 분류하기 위한 것이 아니라, 각 자료가 어떤 주장까지 감당할 수 있는지 제한하기 위한 장치다.

| 자료/실험 | 유지 판정 | 논문에서 맡는 역할 | 제외하는 역할 |
| --- | --- | --- | --- |
| 운영 로그 사례 | 유지 | 문제 정의와 실패 유형 식별 | 정답 전사 또는 운영 평균 수치 |
| 1223건 challenge replay | 유지 | 실패 재현, lifecycle 병목 분석, 구조 변경 전후 비교 | 제품 전체 품질 평균, raw STT 성능 평가 |
| parameter sweep | 축소 | 기본값 후보의 채택/기각 근거와 부정 결과 | 보편 최적 threshold 탐색 |
| structural lifecycle check | 강화 | queue/revision/no-end/boundary 병목 개선 후보 검증 | 언어별 예외 규칙 또는 특정 문구 보정 |
| representative replay | 신규 필요 | 운영 평균 품질과 실제 지연 추정 | 실패 corpus 평균의 보정값 |
| translation replay | 신규 필요 | final-only sink가 번역 churn을 줄이는지 검증 | SBD replay 결과만으로 번역 품질 주장 |

이 판정은 수동 문서 표에만 의존하지 않는다. 표준 evidence package인 `.tmp/eval/dictation-ai-sbd/parameter-sweeps/complete-paper-evidence-summary.json`과 Markdown summary는 `paper_claim_matrix`와 `lifecycle_replay_summary`를 포함한다. `paper_claim_matrix`는 각 논문 주장에 대해 `사용 가능`, `보류`, `사용 금지` 상태와 필요한 후속 증거를 남긴다. `lifecycle_replay_summary`는 complete report 전체의 replay parity와 runtime-only 누락 신호를 집계한다. 기존 complete 23개 report는 모두 `state_machine_parity=partial`이며, 당시 report 계약 기준으로는 stable analysis와 실제 audio timestamp latency, translation request/output linkage가 누락 신호로 기록되어 있다. 현재 text replay는 `stable_analysis.stable_internal_ratio`, `stable_analysis.stable_internal_chars`, `stable_analysis.stable_overlap_source`를 window text에서 재계산하지만, audio timestamp latency와 translation request/output linkage는 여전히 포함하지 않는다. 새 evidence 계약은 `lifecycle_replay_contract.replayed_runtime_signals`도 필수 문맥으로 요구하므로 기존 23개 report는 최신 validator 기준에서 재실행 후보다. 따라서 abstract나 결론의 표현을 바꿀 때는 먼저 이 matrix와 replay summary를 확인해, challenge replay가 지지하지 않는 운영 평균 품질, raw STT 정확도, 번역 품질 개선, 운영 loop와 동일한 runtime 검증 주장이 섞이지 않도록 한다. 특히 `paper_claim_matrix.runtime_loop_equivalence`가 `사용 금지`인 동안에는 text replay 결과를 end-to-end runtime 검증으로 표현하지 않는다.

| 실험 축 | 현재 판단 | 논문에서의 역할 |
| --- | --- | --- |
| Challenge replay | 유지 | 실패 중심 입력에서 revision lifecycle의 trade-off를 측정한다. |
| Threshold sweep | 축소 | 기본값 채택/기각 근거로만 사용하고, 핵심 기여로 주장하지 않는다. |
| Structural lifecycle check | 강화 | queue/revision/boundary 병목을 설명하는 다음 주요 실험으로 둔다. |
| Representative replay | 신규 필요 | 운영 평균 품질, 실제 지연, 일반화 가능성을 검증한다. |
| Translation replay | 신규 필요 | final-only sink가 downstream 번역 churn을 줄이는지 검증한다. |

이 배치에서 현재 실험이 지지하는 결론과 지지하지 않는 결론은 명확히 갈린다.

| 구분 | 결론 |
| --- | --- |
| 지지 | partial hypothesis와 final transcript를 분리하지 않으면 중복/누락/문장 파괴가 발생한다. |
| 지지 | 내용 회수율과 문장 경계 품질은 별도로 측정해야 한다. 1113건 기준선에서 `final_f1_avg=0.483`, `final_boundary_f1_avg=0.108`로 격차가 크다. |
| 지지 | 12개 parameter axis 대부분이 0 delta 또는 trade-off를 보였으므로, 단일 threshold 미세조정보다 lifecycle 구조 분석이 더 의미 있다. |
| 보류 | final-only sink가 번역 품질을 개선했다는 주장. translation replay 전까지는 시스템 계약으로만 둔다. |
| 보류 | 운영 평균 품질. representative corpus가 사람이 확정한 `expected_final`과 함께 준비된 뒤에만 주장한다. |
| 지지하지 않음 | raw STT 정확도 개선, 특정 threshold의 보편 최적성, failure corpus 평균을 제품 품질 평균으로 제시하는 해석. |

재구성한 실험 질문은 다음처럼 corpus와 지표를 분리해 해석한다.

| 실험 질문 | 주 corpus | 주요 지표 | 해석 기준 |
| --- | --- | --- | --- |
| 흔들리는 STT 가설에서 final-only 입력을 안정화할 수 있는가? | challenge replay | `final_f1`, `final_precision`, `final_recall`, duplicate/staged residue | 같은 case set에서 lifecycle 변경 전후의 trade-off를 비교한다. |
| 문장 경계 품질은 내용 회수율과 독립적으로 실패하는가? | challenge replay, representative | `final_boundary_f1`, pending/staged exact, `no-end-marker` tag delta | `final_f1`이 올라도 boundary F1이 낮으면 번역 단위 안정화로 해석하지 않는다. |
| 파라미터 변경은 일반 개선인가, 특정 실패군의 보상인가? | challenge replay | `language_deltas`, `tag_deltas`, lifecycle counter | 전체 평균만 오르고 특정 언어/태그의 precision 또는 boundary가 크게 나빠지면 채택하지 않는다. |
| 운영 평균 품질을 주장할 수 있는가? | representative | final event rate, duplicate insertion, deletion, latency, translation-side churn | failure-enriched case와 분리된 표본에서만 일반 운영 품질로 해석한다. |
| final-only sink가 번역 안정성을 높이는가? | representative + translation output | translation churn, duplicate translation, delayed final translation | 현재 수치만으로는 주장하지 않고 후속 번역 평가가 필요하다. |

전체 평균은 파라미터 후보를 빠르게 비교하기 위한 첫 지표지만, 채택 판단은 언어별 residual과 실패 증상 태그별 residual을 함께 본다. 벤치 리포트와 sweep summary의 `language_summary`는 언어별 final F1, boundary F1, staged residue, empty final, expected final이 있는데 boundary F1이 0인 케이스 수를 기록한다. `tag_summary`는 언어/로그/주제 태그를 제외하고 진단 태그만 사용해 같은 지표를 `missing-final`, `duplicate-final`, `stage-queue`, `no-end-marker` 같은 로그 관측 증상별로 다시 묶어, 전체 평균 개선이 특정 실패군의 악화를 가리는지 확인하게 한다. 따라서 한 파라미터가 전체 final F1을 올리더라도 특정 언어의 precision이나 주요 실패군의 boundary 품질을 크게 낮추면 운영 기본값으로 채택하지 않는다.

실험은 세 계층을 분리한다.

1. `RecognitionHypothesis` 품질: STT backend가 window 단위로 생성한 raw text와 segment 품질을 본다.
2. `SentenceCandidateSet` 품질: SaT 기반 SBD가 completed/pending 후보를 어떤 순서와 경계로 생성하는지 본다.
3. `CommittedTranscriptEvent` 품질: 후보가 age, revision 유사도, recent final memory, candidate queue를 거쳐 final-only sink로 소비되는지 본다.

이 설계에서 벤치마크는 품질 게이트가 아니라 성능 추적 하네스다. 관측 케이스가 늘면 난도가 바뀌므로 `pass_rate`는 논문 지표로 쓰지 않는다. 대신 `final_precision`, `final_recall`, `final_f1`, `final_boundary_f1`, `finalized_per_stage_start`, `pending_exact_match`, `staged_exact_match`, lifecycle metric count를 함께 본다. 특히 `final_f1`은 기대 문장 내용 회수율을 보여주지만, 문장 경계가 사용자에게 읽히는 단위와 맞는지는 `final_boundary_f1`이 별도로 보여준다. 언어별/태그별 residual summary는 평균값의 해석 보조 지표이며, 신규 케이스가 추가될 때 어떤 실패 증상이 늘었는지 추적하는 용도로 사용한다.

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

로그 기반 실패 유형은 다음처럼 정리된다.

| 실패 유형 | 대표 증상 | 관측/개선 지표 |
| --- | --- | --- |
| 확정 누락 | 기대 문장이 pending 또는 staged queue에 남고 final로 소비되지 않는다. | `final_recall`, `staged_exact_match`, `stage_queue_*`, `stage_replace_decision_unconfirmed` |
| 중복 확정 | 이미 final로 소비한 문장과 유사한 문장이 다시 final로 나온다. | `candidate_duplicate_suppressed`, `finalize_recent_echo_suppressed`, `duplicate-final` 태그 |
| 문장 파괴 | 앞뒤 문맥이 섞이거나 terminal tail이 잘려 final 문장이 된다. | `final_boundary_f1`, `final_quality_no_end_marker`, `mixed-context-final` 태그 |
| no-end 조각 final | 종결 경계가 약한 fragment가 final로 소비되고 번역은 생략된다. | `final_quality_no_end_marker`, `translation-skip` 태그 |
| queue 잔류 | active staged가 오래 유지되어 후속 completed 후보가 소비되지 않는다. | `stage_queue_enqueue`, `stage_queue_promote`, `stage_queue_revision`, `staged-residue` 태그 |

Challenge replay 벤치마크는 품질 게이트가 아니라 실패 재현 기반 성능 추적 자료다. 최신 paper-evidence SBD 벤치마크는 1223개 케이스를 포함하며, 실제 `sat + cuda + float16` 경로에서 다음 결과를 기록했다. 164건 기준 결과는 초기 파일럿 벤치로 남기고, 1113건 기준 결과는 이전 paper-evidence 기준선으로 보존한다.

| 조건 | cases | finalized | stage_start | finalized/stage | final precision | final recall | final F1 | boundary F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1223건 challenge replay baseline | 1223 | 5042 | 8552 | 0.590 | 0.575 | 0.449 | 0.482 | 0.113 |
| 1113건 challenge replay baseline | 1113 | 4012 | 5638 | 0.712 | 0.602 | 0.440 | 0.483 | 0.108 |
| 1113건 이전 fallback coverage 기준선 | 1113 | 3986 | 5658 | 0.704 | 0.597 | 0.435 | 0.478 | 0.109 |
| 혼합 age 샘플 | 164 | 809 | 1183 | 0.684 | 0.775 | 0.688 | 0.705 | 0.280 |
| 중국어만 age 3 | 164 | 800 | 1158 | 0.691 | 0.771 | 0.678 | 0.699 | 0.280 |
| 전체 age 3 | 164 | 791 | 1143 | 0.692 | 0.754 | 0.656 | 0.676 | 0.268 |
| aged staged 순서 확정 | 164 | 840 | 1143 | 0.735 | 0.744 | 0.678 | 0.688 | 0.298 |

1223건 기준선은 164건 파일럿보다 낮다. 이는 최신 케이스 집합이 실패 중심 로그를 대량 확장했고, 특히 확정 누락과 boundary mismatch를 많이 포함하기 때문이다. 따라서 164건, 1113건, 1223건 결과를 같은 난도에서의 성능 변화로 직접 비교하지 않는다. 같은 케이스 집합 안에서 파라미터와 로직 변경을 비교할 때만 개선 여부를 판단한다.

전체 age 3 기준은 언어별 예외를 줄이고 보수적인 확정 기준을 유지하는 계약과 일치한다. 164건 파일럿에서는 혼합 age 샘플 대비 `final_f1_avg`가 0.029 낮아졌고, 하락은 주로 recall 감소에서 나타났다. 따라서 `sentenceFinalizeAge=3`은 즉시 운영 불가 수준의 장애는 아니지만, 확정 누락 비용을 동반하는 기준선으로 보아야 한다.

이후 aged staged 후보가 교체 보류 중에도 final 품질 조건을 만족하면 폐기하지 않고 생성순서대로 먼저 확정하도록 lifecycle을 수정했다. 이 변경은 raw STT를 고치는 것이 아니라, 속기처럼 미확정 문장을 보류했다가 충분히 관측된 순서대로 소비하는 정책이다. 결과적으로 `final_f1_avg`는 `0.676 -> 0.688`, `final_recall_avg`는 `0.656 -> 0.678`, `final_boundary_f1_avg`는 `0.268 -> 0.298`로 개선됐다. 반면 `final_precision_avg`는 `0.754 -> 0.744`로 낮아져, 확정 누락을 줄이는 대신 false final 위험이 일부 증가할 수 있음을 보여준다. 이 trade-off 때문에 해당 변경은 공격적 최적화가 아니라 생성순서 소비 계약에 맞춘 보수적 개선으로 분류한다.

이 결과는 내용 회수 F1과 문장 경계 F1이 자주 분리됨을 보여준다. 예를 들어 여러 영어 로그 케이스는 `final_f1`이 0.8 이상이어도 `final_boundary_f1=0.0`이었고, 이는 실제 사용자 품질을 final F1만으로 판단할 수 없다는 근거가 된다.

평가 시 raw STT window 결과와 revision lifecycle을 거친 final transcript를 분리한다. raw STT는 모델 전사 품질을, final transcript는 사용자에게 표시되는 실시간 자막 품질을 나타낸다. 정답 전사 코퍼스가 준비되면 CER/WER와 deletion/duplicate insertion rate를 보조 지표로 추가할 수 있지만, 현재 운영 판단은 로그 기반 의심 사례와 벤치 추적 지표를 중심으로 한다. `pass_rate`는 관측 케이스가 늘어날수록 난도가 바뀌기 때문에 논문 결과 지표로 사용하지 않는다.

## 8. 운영 관측

한국어와 영어에서는 `faster-whisper + large-v3` 기반 전사가 현재 운영 후보로 유지된다. 중국어에서는 Whisper/faster-whisper의 의미 보존과 문장 구조가 부족했고, `qwen3-asr-transformers + qwen3-asr-0.6b`가 더 나은 후보로 관측되었다. FunASR 계열은 처리 속도는 빠르지만 의미 보존, stage churn, 확정률에서 불리했다.

2026-06-14 중국어 30분 모니터링에서는 stage replace/unconfirmed replacement가 많이 발생했고, 계산 시간보다 후보 생명주기가 병목으로 나타났다. `windowSeconds=30`은 raw STT 흔들림을 줄였지만, 긴 문장 확정과 final 지연을 증가시켰다. 2026-06-16 로그에서는 한 STT chunk 안의 후속 completed 후보가 첫 관찰 후보를 `next_completed`로 즉시 final 확정시키는 사례가 관측되어, 중국어 multi-completed 후보를 하나의 관찰 단위로 병합하고 교체 직전 확정에 `sentenceFinalizeAge` 기준을 적용했다.

2026-06-15 로그에서는 pending 텍스트와 다음 STT 윈도우가 같은 CJK 구간을 내부 중간부터 다시 내보내는 현상이 관측되었다. 한때 pending/new 접합 보정으로 분류했지만, 학술적 근거가 부족해 운영 요구사항에서는 제외했다. 현재는 STT/backend 품질, 문장 경계, revision lifecycle 지표로 분리해 관측한다.

2026-06-20 영어 장시간 로그에서는 확정 누락과 중복 확정의 원인이 단일 임계값보다 active staged와 queue 후보 소비 순서, no-end fragment 품질, terminal tail split, recent final delta trim의 상호작용에 있음을 확인했다. `MAX_STAGED_SENTENCE_QUEUE`를 12에서 20으로 늘린 실험은 replacement rate/North Korea/underpopulation 케이스에서 `stage_queue_drop_oldest=8`을 0으로 낮추고 해당 케이스 `final_f1`을 0.500에서 0.621로 개선했다. 전체 평균은 `final_f1_avg`가 약 0.700에서 0.701로 소폭 개선되는 수준이었으므로, 큐 한도 증가는 유지하되 stale 후보 잔류를 계속 관찰하는 보수적 변경으로 분류했다.

같은 날 추가한 UFO/aliens, accelerating launches/launched mass, Optimus surgeons/Zimbabwe, supply chain/medicine, chimps/Raptor 등 케이스는 공통적으로 내용 회수와 boundary 품질이 분리되는 양상을 보였다. 일부 케이스는 false positive 없이 주요 내용을 회수했지만 후반 문장이 staged queue에 남았고, 일부 케이스는 `So what fraction of all that of accelerating launches.`처럼 앞뒤 문맥이 섞인 final을 만들었다. 따라서 최신 실험 판단은 “final F1 상승”보다 “boundary/staged residue와 중복 억제의 균형”을 함께 보는 방향으로 정리된다.

이 실험 과정에서 중요하게 폐기한 경로도 있다. CJK pending tail 접합, 내부 overlap delta, 언어별 정규식 보정, mock/smoke/CPU 벤치, 단어별 예외 규칙은 현재 논문에서 구현 기여로 주장하지 않는다. 이들은 일부 케이스에서 수치 개선처럼 보일 수 있었지만, 일반 파이프라인의 근거가 약하거나 운영 계약을 흐리는 위험이 있어 실험일지에서 폐기 판단으로 남겼다.

## 9. 결과 해석

최신 기준선은 다섯 가지 결론을 제공한다.

첫째, 리비전 인지 계층은 raw STT와 final transcript를 분리해야 하는 문제를 드러낸다. 같은 raw window가 반복될 때 STT backend는 문장을 수정하거나 앞부분을 재출력한다. 이를 즉시 final로 소비하면 중복 확정과 번역 중복이 발생한다. 반대로 과도하게 보수적으로 잡으면 staged queue가 남고 확정 누락이 증가한다.

둘째, `sentenceFinalizeAge=3` 통일은 언어별 예외를 줄이는 대신 recall 비용을 만든다. 전체 age 3 기준에서 `finalized_per_stage_start`는 0.692로 혼합 age 기준보다 높지만, `final_recall_avg`는 0.656으로 낮다. 이는 stage 수가 줄고 보수적으로 소비되는 경향이 확정 누락으로 이어질 수 있음을 의미한다. 따라서 향후 개선은 age를 단순히 낮추는 방식보다 active staged, candidate queue, recent final memory의 소비 규칙을 보강하는 방향이어야 한다.

셋째, 생성순서대로 소비 가능한 staged 후보를 폐기하지 않는 정책은 확정 누락을 줄이는 데 효과가 있었다. `stage_unconfirmed_replacement_suppressed=102`였던 기준선에서 해당 경로를 `stage_age_finalize`로 전환하자 final 수는 791에서 840으로 늘었고 recall과 boundary F1이 함께 개선됐다. 하지만 precision이 하락했으므로, 이 정책은 최근 final memory와 no-end fragment 품질 게이트를 함께 관찰해야 한다.

넷째, boundary 품질은 내용 회수율과 독립적으로 관리해야 한다. 최신 1223건 기준선의 `final_f1_avg=0.482`에 비해 `final_boundary_f1_avg=0.113`은 더 낮다. 여러 케이스에서 기대 문장 내용은 일부 회수되지만 문장 경계가 합쳐지거나 잘리고, 일부 후속 문장은 staged queue에 잔류한다. 실시간 번역 시스템에서는 문장 경계 오류가 번역 단위 오류로 전파되므로 boundary F1과 staged residue를 별도 지표로 유지해야 한다.

다섯째, 성능 개선 시도는 “수치가 오른다”보다 “어떤 실패를 줄이고 어떤 실패를 늘릴 수 있는가”로 해석해야 한다. 예를 들어 queue 한도를 늘리면 일부 긴 영어 케이스의 recall은 개선되지만, 오래된 후보가 더 오래 남아 stale staged 위험이 증가할 수 있다. 반대로 no-end fragment를 강하게 차단하면 문장 파괴는 줄 수 있지만, 짧고 실제로 완결된 응답의 recall을 잃을 수 있다. 따라서 본 연구의 파라미터 튜닝은 공격적 최적화가 아니라 실패 유형 간 trade-off를 기록하는 보수적 절차다.

1113건 기준 파라미터 sweep도 이 해석을 지지한다. 이전 fallback coverage 기준에서 `SENTENCE_CONFIRM_CHUNKS=1`은 final F1을 올렸지만 precision을 낮추고 final 후보 수를 크게 늘렸다. `REVISION_FALLBACK_COVERAGE_MIN=0.55`를 반영한 최신 기준선에서도 `SENTENCE_CONFIRM_CHUNKS=1`은 `final_f1_avg`를 `0.483 -> 0.495`로 올렸지만 `final_precision_avg`를 `0.602 -> 0.565`로 낮췄다. 언어별 `language_summary`로 보면 영어와 한국어 final F1은 오르지만, 중국어 precision은 `0.708 -> 0.556`으로 크게 낮아지고 중국어 final F1도 `0.540 -> 0.511`로 하락한다. 반대로 `SENTENCE_CONFIRM_CHUNKS=3`은 precision을 올리지만 recall, final F1, boundary F1을 낮췄다. no-end fragment threshold, staged queue 한도, age 상한, forced confirmation, CJK 짧은 final 게이트, CJK revision similarity, stale suppression을 각각 한 축씩 재검증해도 대부분 0 delta이거나 precision/recall/boundary trade-off를 만들었다. `REVISION_FALLBACK_COVERAGE_MIN=0.55`만 주변값 대비 precision, recall, final F1을 함께 소폭 개선해 checked-in 기본값으로 반영했다. 기존 실제 CUDA job report를 당시 evidence protocol로 refresh한 결과, complete paper-evidence summary는 23개 report였고 모두 `paper_evidence=true`, `sat + cuda + float16`, `missing_required_evidence_fields=none` 조건을 만족했다. 이후 evidence 계약에 `lifecycle_replay_contract.replayed_runtime_signals`가 필수 필드로 추가되었으므로, 이 23개 report는 현재 validator 기준에서 재실행 후보로 분류된다. 따라서 아래 수치는 기존 CUDA sweep의 해석 근거로 남기되, 최신 계약의 새 논문 표에 직접 옮기려면 같은 case set을 최신 코드로 재생성해야 한다. 당시 complete subset의 `mixed_experiment_stage=false`, `mixed_claim_scope_key=false`도 확인되어 이 23개 report는 모두 `challenge-replay`와 `failure-lifecycle-tradeoff` 범위로만 해석한다. 다만 중복 report를 축별 대표로 접으면 고유 parameter axis는 12개로 해석한다. 23개 report의 후보 45개 중 25개는 `review-risk`였고, 고유 축 대표 report 기준으로는 후보 25개 중 11개가 `review-risk`였다. 축별 결론도 6개는 `no-effect-or-tiny`, 2개는 `baseline-preferred-tradeoff`, 2개는 `tradeoff-gain`, 2개는 `tradeoff-or-regression`으로 나뉜다. 이를 논문 가설 상태로 다시 묶으면 `유지=2`, `축소=2`, `폐기=8`이다. 여기서 `유지`는 candidate 축을 새 개선 주장으로 채택한다는 뜻이 아니라, 주변 후보가 기준선보다 낫지 않아 현재 기준선 또는 현재 lifecycle 가설을 유지한다는 뜻이다. 위험 없는 후보 대부분도 0 delta 또는 매우 작은 delta였으므로, 단일 threshold를 더 촘촘히 흔드는 방식은 현재 challenge replay에서 우선순위가 낮다.

이 12개 축을 종합하면 채택 근거가 있는 축은 `REVISION_FALLBACK_COVERAGE_MIN=0.55` 하나다. `SENTENCE_CONFIRM_CHUNKS`, `SHORT_NO_END_FRAGMENT_UNITS`, `SHORT_CJK_FINAL_UNITS`, `MAX_STAGED_SENTENCE_QUEUE`, `CJK_REVISION_RATIO_MIN`은 trade-off 축으로 남고, age/forced/CJK replacement hold 계열은 현재 corpus에서 사실상 닫힌 축이다. `CJK_CONFIRM_PRESERVE_RATIO_MIN=0.65`처럼 소폭 개선되는 후보도 final F1 +0.0002 수준으로 작아 논문 주장을 지탱하기 어렵다. 따라서 실험 방법은 "threshold 최적화"가 아니라 "어떤 생명주기 조건이 failure replay에서 병목이 되는지 분류하고, 구조 변경이 그 병목을 줄이는지 확인하는 절차"로 해석해야 한다.

최신 lifecycle reason delta는 no-end fragment 축의 해석을 더 분명히 한다. `SHORT_NO_END_FRAGMENT_UNITS=3`은 `quality_blocked`, `no_end_marker`, `short_no_end_fragment` count를 약 490건 줄였지만 `stage_replace_deferred=+404`, `stage_queue_revision=+198`을 만들고 final precision/F1을 낮췄다. 반대로 `SHORT_NO_END_FRAGMENT_UNITS=5`는 deferred replacement와 queue revision을 줄였지만 no-end/short-fragment 차단을 약 450건 늘리고 recall/F1/boundary를 낮췄다. 즉 이 threshold는 보수성 수준을 조절하는 축이지, 현재 failure corpus에서 안정적인 성능 개선축이 아니다. 따라서 후속 실험은 no-end threshold를 더 세밀하게 탐색하는 방식보다, 같은 문장 후보가 생성순서 안에서 어떤 revision 계열로 소비되거나 보류되는지 설명하는 lifecycle 구조 검증으로 옮겨야 한다.

기준선 lifecycle counter는 이 결론을 더 분명히 한다. `stage_start=5638`로 SBD 후보는 충분히 생성되지만, `stage_replace=8273`, `stage_replace_deferred=7551`, `stage_queue_enqueue=4257`, `stage_queue_revision=3961`, `stage_candidate_quality_blocked=3963`이 함께 크게 나타난다. 이는 병목이 문장 후보 부족보다는 후보가 같은 발화 구간의 revision인지, 생성순서대로 소비 가능한지, no-end fragment를 final로 볼 수 있는지 판단하는 lifecycle 소비 규칙에 있음을 뜻한다. 특히 새 revision을 발견했다는 이유만으로 active staged 후보의 age/confirmation을 즉시 reset하면, 이미 관측되던 후보 대신 충분히 반복되지 않은 token-sentence 변형이 premature final로 나갈 수 있다. 따라서 reset은 token-sentence 유사도와 반복 관측으로 보수적으로 다뤄야 하며, 현재 근거는 문장 후보가 같은 발화 구간인지 판단하는 일반 revision lifecycle 로직과 representative corpus 기반 검증이 더 중요한 다음 개선 축임을 가리킨다.

Challenge replay 내부에서도 raw 입력 검토 대상과 lifecycle 실험 대상을 분리해 해석해야 한다. 기존 실제 CUDA 기준선을 새 `evidence_strata_summary`로 재분석하면 `input_contamination_review`는 5건에 불과했고, `lifecycle_without_input_review` 1108건의 `final_f1_avg=0.482`, `final_boundary_f1_avg=0.106`으로 전체 1113건 평균과 거의 같다. 따라서 낮은 기준선은 입력 오염 케이스가 대량으로 섞였기 때문이 아니라, 대부분의 실패 중심 케이스가 실제로 staged queue, deferred replacement, no-end fragment, boundary mismatch 같은 lifecycle 병목을 포함하기 때문으로 해석한다. 다만 입력 잔류, 무음, 화자 전환 검토 태그가 있는 케이스는 raw input/source 문제를 분리하기 위해 별도 stratum으로 표기하고, final lifecycle 개선 효과의 직접 근거로 쓰지 않는다.

같은 strata 기준은 파라미터 기각에도 사용된다. `SHORT_NO_END_FRAGMENT_UNITS=3`과 `5`의 기각 결론은 전체 평균에서만 나타난 것이 아니라 `lifecycle_without_input_review`에서도 동일하게 유지되었다. `3`은 clean lifecycle stratum에서 `final_f1_avg=-0.0040`, `precision=-0.0074`, `staged_residue=+13`을 만들었고, `5`는 `staged_residue=-21`을 만들지만 `final_f1_avg=-0.0024`, `recall=-0.0036`, `boundary_f1=-0.0008`을 동반했다. 이는 threshold 단일 조정의 한계를 입력 오염 때문으로 돌릴 수 없으며, 실제 lifecycle 소비 규칙의 trade-off로 봐야 함을 보강한다.

대표 병목 사례도 같은 결론을 뒷받침한다. `case_exemplar_summary`로 기준선의 상위 병목 케이스를 보면, 영어 long-context 구간에서 `stage_queue_revision`과 `stage_replace_deferred`가 동시에 크게 나타나는 사례가 반복된다. 예를 들어 Optimus/surgeon/Zimbabwe 구간은 `stage_queue_revision=64`, `stage_replace_deferred=85`, `final_boundary_f1=0.0`이고, supply-chain/medicine 구간은 `stage_queue_revision=137`, `stage_replace_deferred=154`, `final_boundary_f1=0.0`이다. 두 사례 모두 final F1은 완전히 낮지 않지만 문장 경계가 맞지 않아 final-only 번역 단위로는 불안정하다. 이는 후속 개선이 단일 confirmation threshold보다 active staged와 candidate queue의 소비 규칙, 그리고 final 직전 boundary 품질 보존을 겨냥해야 함을 보여준다.

Queue 한도 실험도 이 방향을 지지한다. `MAX_STAGED_SENTENCE_QUEUE=12`는 clean lifecycle stratum에서 `stage_queue_drop_oldest=+19`, `stage_queue_revision=+18`을 만들고 final F1, recall, boundary F1을 모두 소폭 낮췄다. `MAX_STAGED_SENTENCE_QUEUE=30`은 baseline 20과 지표 및 lifecycle count가 동일했다. 따라서 현재 기본값 20은 점수를 올리는 최적값이라기보다 긴 window 후보를 조기 폐기하지 않기 위한 보수적 하한이며, 20 이상으로 키워도 대표 병목 사례의 queue/replacement churn을 해결하지 못한다.

Queue residue profile은 이 결론을 정량적으로 보강한다. 기준선에서는 1113건 중 368건, 즉 약 33%가 종료 시점에 staged queue residue를 남겼고 queue residue 총량은 823개, residue가 있는 케이스의 평균 queue 길이는 2.24, 최대 길이는 16이었다. `MAX_STAGED_SENTENCE_QUEUE=12`는 최대 길이를 12로 낮추지만 총 queue residue를 827개로 늘리고 `stage_queue_drop_oldest=+19`를 만들었다. `MAX_STAGED_SENTENCE_QUEUE=30`은 기준선과 동일했다. 따라서 문제는 queue 용량이 아니라 queue 안 후보를 언제 같은 revision 계열로 소비하고 언제 final 직전 boundary를 보존할지에 있다.

Top queue residue 사례도 같은 방향을 가리킨다. 가장 긴 residue는 Optimus/surgeon/Zimbabwe 영어 long-context 케이스로 queue 길이 16, `stage_queue_revision=64`, `stage_replace_deferred=85`, `final_boundary_f1=0.0`이다. 그다음 ultracapacitor/PhD 케이스와 chimps/pyramids/raptor 케이스도 queue 길이 10이며 boundary F1이 낮다. 중국어 draft/duplicate supper 케이스도 queue 길이 8-10 범위로 나타난다. 이 사례들은 queue residue가 특정 언어 하나의 예외가 아니라, 긴 context와 CJK revision 모두에서 final 직전 소비 규칙이 불안정할 때 나타나는 구조 신호임을 보여준다.

Queue residue를 심각도별로 나누면 실험 설계의 의미가 더 분명해진다. 기준선에서 queue가 없는 745건의 `final_f1_avg=0.515`, `final_boundary_f1_avg=0.116`인 반면, queue 길이 1인 186건은 `final_f1_avg=0.397`, `final_boundary_f1_avg=0.086`이다. queue 길이 2-4인 148건은 `stage_queue_revision=1363`, `stage_replace_deferred=2302`를 보이고, queue 길이 5 이상인 34건은 `empty_final_count=0`이지만 `final_boundary_f1_avg=0.043`에 그친다. 즉 긴 queue residue는 단순히 final을 하나도 만들지 못한 실패가 아니라, 일부 내용을 final로 내보내면서도 경계가 무너지고 후보가 소비되지 못한 실패다. 따라서 후속 실험은 전체 final F1을 조금 올리는 임계값 탐색보다, queue severity stratum에서 boundary F1과 residual queue를 동시에 줄이는 구조 변경을 우선해야 한다.

## 10. 논의

실시간 전사의 품질은 raw ASR 정확도만으로 판단할 수 없다. 사용자가 보는 품질은 final transcript가 언제, 어떤 단위로, 얼마나 중복 없이 확정되는지에 크게 좌우된다. 특히 번역을 포함하는 시스템에서는 확정되지 않은 문장을 번역하면 번역 중복과 번역 되돌림이 발생한다. 따라서 번역은 final transcript 중심으로 수행하고, provisional translation은 별도 정책으로 분리해야 한다. 다만 이 논문에서 final-only sink는 아직 번역 품질 개선 결과가 아니라 시스템 계약이다. 번역 안정성 주장은 final event timestamp, translation request id, translation output을 연결한 translation replay가 준비된 뒤에만 별도 수치로 승격한다.

실험은 문맥 길이와 확정 단위의 분리가 중요함을 보여준다. 긴 문맥은 STT에 유리하지만 candidate age, staged residue, stale staged 후보에는 불리할 수 있다. 그러므로 긴 STT context를 쓰더라도 final commit unit은 문장 후보, revision 계열, candidate age, recent final memory를 통해 별도로 제어해야 한다. 실제 시간 기준 finalization latency는 final event timestamp가 연결된 representative corpus에서 별도로 측정해야 한다.

본 연구의 실용적 의미는 “가장 높은 단일 점수”보다 “실패 유형을 구분해 재현 가능한 벤치로 남기는 것”에 있다. 실제 로그에서 수집한 케이스는 특정 문구를 고치는 유닛 테스트가 아니라, 중복 확정과 확정 누락이 어떤 생명주기 조건에서 재현되는지 보는 성능 추적 자료다. 그래서 벤치 샘플이 늘면 평균 점수가 낮아질 수 있으며, 그 자체가 회귀를 뜻하지는 않는다. 중요한 것은 같은 기준선에서 파라미터와 로직 변경의 방향성을 비교하는 것이다.

## 11. 한계

현재 연구는 운영 로그 기반 관측과 텍스트 replay 벤치가 중심이며, 동일 오디오 replay 기반 통제 실험은 제한적이다. 정답 전사 코퍼스가 없어 CER/WER 기반 정량 평가는 아직 보조 지표로만 논의된다. 또한 사용자 체감 지연, 가독성, 번역 만족도에 대한 사용자 연구는 포함하지 않았다. 기존 complete evidence package의 `lifecycle_replay_summary`도 23개 report가 모두 `state_machine_parity=partial`임을 보여준다. 즉 benchmark는 운영 loop의 일부 decision helper와 window text 기반 stable analysis를 공유하지만, 실제 audio timestamp latency와 translation request/output linkage를 포함하지 않는다. 본 논문의 실험 결과는 현재 애플리케이션의 운영 로그와 벤치 샘플에서 관측된 실패 유형과 개선 근거로 해석해야 하며, 운영 loop 전체와 동일한 end-to-end 검증으로 읽지 않는다.

벤치마크 샘플은 실패 사례 중심으로 수집되므로 일반 발화 전체의 평균 품질을 대표하지 않는다. 특히 최신 1223개 샘플은 중복 확정, 확정 누락, no-end fragment, staged queue residue 같은 어려운 케이스를 의도적으로 포함한다. 따라서 이 벤치의 `final_f1_avg`는 공개 ASR benchmark의 WER처럼 모델 일반 성능을 뜻하지 않는다.

외부 논문은 본 연구의 배경과 비교 기준으로만 사용한다. 운영 기본값, age/window 선택, queue 한도, 폐기한 보정 로직은 프로젝트 실험일지와 벤치 결과가 근거다. VAD, turn-taking, prosody 기반 segmentation, speech translation segmentation 자료는 현재 파이프라인의 직접 구현 근거가 아니며, 범위 밖 비교군으로만 해석한다.

Rao et al.의 speech translation segmentation 연구는 번역 단위가 downstream BLEU에 영향을 줄 수 있음을 보여주지만, 이 논문은 Arabic broadcast speech와 SMT 시스템의 segment length 최적화에 관한 연구다. 본 연구의 대상은 사용자 화면에 append-only로 표시되는 다국어 실시간 final transcript와 final-only 번역 sink이므로, 해당 논문을 현재 SBD/finalization 구현의 직접 근거로 사용하지 않는다.

## 12. 결론

본 연구는 다국어 실시간 전사 및 번역 시스템에서 리비전 인지 확정 계층의 필요성을 제시했다. STT 모델의 원시 가설, 문장 경계 검출, 확정 생명주기, final-only sink 계약은 서로 다른 실패 원인을 갖기 때문에 분리 평가되어야 한다. 특히 긴 문맥은 STT 안정성을 높일 수 있지만 final transcript 지연과 긴 문장 확정 문제를 유발한다. 따라서 실시간 전사 시스템은 문맥 윈도우와 확정 단위를 분리하고, 중복 억제와 리비전 생명주기를 명시적으로 계측해야 한다.

현재 구현은 완성된 답이라기보다 실패 중심 입력에서 재현 가능한 기준선이다. 최신 1223건 challenge replay 기준에서 내용 회수 F1은 0.482이고 boundary F1은 0.113이다. 이 격차는 실시간 전사 품질을 STT 정확도 하나로 설명할 수 없음을 보여준다. 잔여 실패는 특히 영어 long-context 케이스의 boundary F1과 staged residue에 집중되어 있으며, lifecycle counter는 단순 큐 한도보다 staged replacement/deferred와 boundary 후보 품질이 더 직접적인 병목임을 가리킨다. 다만 현재 replay case는 STT 단계의 boundary confidence를 보존하지 않고, SaT/SBD의 boundary count와 right-context count만 보존한다. 또한 complete evidence package의 replay parity는 `partial`이므로, 현재 결론은 운영 loop 전체 검증이 아니라 공유 decision helper를 사용하는 text replay 기반 failure lifecycle 분석이다. 이 count들은 좋은 케이스와 나쁜 케이스 모두에서 크게 나타나므로 단순 threshold 정책의 근거로 쓰기 어렵다. 향후 개선은 언어별 ad-hoc 규칙보다 active staged 소비, candidate queue 정리, no-end fragment 처리, recent final memory의 일반 정책을 보수적으로 검증하고, representative/translation replay로 runtime-only 신호를 보강하는 방향으로 진행해야 한다.

## 참고 문헌

상세 참고 문헌 분류와 원문 확인 결과는 [받아쓰기 AI 논문 레퍼런스 원문 확인 컨텍스트](../2026-06-20-dictation-ai-reference-context.md)에 둔다. 실시간 처리 파이프라인 기준은 [받아쓰기 AI 실시간 처리 파이프라인 기준](../2026-06-16-dictation-ai-realtime-pipeline.md)을 따르고, challenge replay와 representative corpus를 나누어 해석하는 실험 규칙은 [받아쓰기 AI 실험 프로토콜](../2026-06-21-dictation-ai-experiment-protocol.md)을 따른다. 핵심 근거는 다음과 같다.

- Radford et al., [Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356). Whisper 계열 모델을 로컬 다국어 ASR backend로 쓰는 배경 근거다.
- Macháček et al., [Turning Whisper into Real-Time Transcription System](https://arxiv.org/abs/2307.14743) 및 Whisper-Streaming demo paper. Whisper가 본래 실시간 모델은 아니며, local agreement와 adaptive latency가 필요하다는 비교 기준이다.
- Whetten et al., [Evaluating Automatic Speech Recognition in an Incremental Setting](https://arxiv.org/abs/2302.12049). 실시간 ASR을 WER만이 아니라 latency와 already-recognized-word update로 평가해야 한다는 근거다.
- Frohmann et al., [Segment Any Text](https://arxiv.org/abs/2406.16678). punctuation 의존도가 낮은 다국어 문장 분절 모델을 SBD 후보 생성기로 쓰는 근거다.
- Behre et al., [Streaming Punctuation for Long-form Dictation with Transformers](https://arxiv.org/abs/2210.05756). 긴 받아쓰기에서 bounded right context와 punctuation/segmentation 품질을 분리해 보는 근거다.
- Shi et al., [Qwen3-ASR Technical Report](https://arxiv.org/abs/2601.21337). 중국어 STT 후보로 Qwen3-ASR 0.6B/1.7B 계열을 비교하는 근거다.
- NLLB Team et al., [No Language Left Behind](https://arxiv.org/abs/2207.04672). NLLB 계열 번역 backend의 배경 근거다.
- Rao et al., [Optimizing Sentence Segmentation for Speech Translation](https://isl.iar.kit.edu/downloads/803_Interspeech-2007_Rao.pdf). speech translation에서 segment length가 downstream 번역 품질에 영향을 줄 수 있다는 비교 근거다.
