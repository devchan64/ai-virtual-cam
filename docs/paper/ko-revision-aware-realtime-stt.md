# SBD 라이프사이클 기반 실시간 STT 확정문장 처리 분석

## 부제

로그 기반 failure replay와 revision-aware lifecycle 계측을 통한 방법론 정리

## 초록

실시간 음성 전사(automatic speech recognition, ASR) 모델은 스트리밍 또는 준스트리밍 환경에서 매 입력 윈도우마다 부분 가설(partial hypothesis)을 재작성한다. 본 연구의 관심사는 raw STT 정확도 자체를 개선하는 것이 아니라, SBD(sentence boundary detection)와 revision-aware lifecycle을 이용해 흔들리는 partial hypothesis를 어떤 확정문장(final sentence)으로 처리할 것인가라는 방법론을 분석하는 것이다. 이를 위해 원시 ASR 가설(raw ASR hypothesis), 문장 경계 검출(sentence boundary detection), 리비전 생명주기(revision lifecycle), final-only sink 계약을 분리 계측하는 분석 틀을 정리한다. 특히 한국어, 영어, 중국어 환경에서 문맥 윈도우(context window) 길이와 확정 단위(commit unit)의 상호작용을 추적하고, 긴 문맥이 원시 STT 가설을 더 안정적으로 만들 수 있는 동시에 최종 전사(final transcript) 갱신을 늦출 수 있음을 운영 로그와 텍스트 벤치마크 기반으로 관찰한다. 최신 challenge replay 기준선은 reviewed `sbd_predicted_cases/` 815건을 실제 `sat + cuda + float16` 경로로 재생한 결과이며, 핵심 지표인 `final_f1_avg=0.666`과 `final_recall_avg=0.786`을 기록했다. 기존 `final_boundary_f1_avg=0.136`은 exact boundary-offset에 과도하게 민감해 본래 의도를 훼손하는 지표로 판단했고, 대신 `boundary_granularity_adjusted_f1_avg`를 분절 granularity 보정 진단 축으로 추가했다. 재현 정보와 근거 기록은 부록에 정리한다.

본 연구의 기여는 세 가지다. 첫째, 실시간 ASR 출력의 불안정성을 단순 UI 문제가 아니라 SBD 기반 확정문장 처리 문제로 모델링한다. 둘째, 중복 증폭(duplicate amplification), 확정 누락(missing final), 확정 지연의 대리 신호(candidate age, staged residue), pending overrun, replacement churn을 분리한 평가 지표를 정리한다. 셋째, 다국어 실시간 전사 시스템에서 SBD 후보 생성과 revision-aware lifecycle 소비를 분리해 해석해야 한다는 방법론적 근거를 남긴다. 본문은 완성된 범용 해법을 제안하기보다, SBD 라이프사이클 기반 확정문장 처리의 병목과 trade-off를 보수적으로 정리하는 데 초점을 둔다.

## 1. 서론

최근 대형 음성 인식 모델과 다국어 번역 모델의 발전으로 로컬 환경에서도 실시간 전사 및 번역 기능을 구현할 수 있게 되었다. 하지만 실시간 전사 애플리케이션에서 실제 사용자에게 표시되는 품질은 모델의 오프라인 전사 정확도만으로 설명되지 않는다. 동일한 오디오 구간이 여러 슬라이딩 윈도우(sliding window)에 반복 포함되기 때문에 ASR 모델은 매번 비슷하지만 조금씩 다른 문장을 생성한다. 이 결과를 그대로 화면에 표시하면 중복 문장, 소실된 문장, 되돌려지는 표현, 번역 중복이 발생한다.

본 연구는 이러한 문제를 "리비전 인지 확정 계층(revision-aware finalization layer)"의 failure analysis 문제로 본다. 핵심 질문은 다음과 같다.

- 부분 전사(partial transcript)가 계속 바뀌는 상황에서 어떤 텍스트를 최종 전사로 확정할 것인가?
- 긴 문맥 윈도우가 전사 안정성을 높일 때, 확정 지연과 긴 문장 생성 문제를 어떻게 제어할 것인가?
- STT 오류, 문장 경계 오류, 확정 정책 오류, 번역 오류를 어떻게 분리해 측정할 것인가?
- 한국어, 영어, 중국어처럼 언어 구조가 다른 입력에서 동일한 후처리 정책이 유지 가능한가?

현재까지의 실험은 이 질문 중 일부에만 답한다. 유지할 수 있는 중심 가설은 "불안정한 STT window hypothesis를 확정문장으로 처리하려면 SBD 후보 생성과 revision-aware lifecycle 소비를 분리한 계층이 필요하다"는 것이다. 본 연구는 raw STT 정확도 개선을 주장하지 않으며, 현재 challenge replay만으로 운영 평균 품질이나 번역 품질 개선도 일반화하지 않는다. 따라서 본문은 최적 방법 제안보다 SBD 라이프사이클 기반 확정문장 처리의 병목을 정리하는 분석에 초점을 둔다.

| 가설 | 상태 | 본 문서에서의 처리 |
| --- | --- | --- |
| partial hypothesis와 final transcript를 분리하지 않으면 중복/누락이 발생한다. | 유지 | 운영 로그와 challenge replay의 실패 유형으로 제시한다. |
| SBD 후보와 final lifecycle은 별도 계층으로 평가해야 한다. | 유지 | 핵심 지표 `final_f1`과 분절 보정 경계 진단 `boundary_granularity_adjusted_f1`, lifecycle counter, staged residue를 분리한다. |
| 단일 threshold 튜닝으로 목표 품질을 달성할 수 있다. | 축소 | parameter sweep과 구조 실험 모두에서 대부분 trade-off 또는 국소 개선에 머물렀음을 보고한다. |
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

본 연구에 직접 연결되는 외부 근거는 다음과 같다. 운영 로그에서 관측한 중복 확정, 확정 누락, age/window 기본값, 벤치 수치는 외부 문헌이 아니라 프로젝트 실험일지와 커밋 기록을 근거로 해석한다. 따라서 아래 표는 구현 세부를 정당화하기 위한 인용 목록이 아니라, 문제 설정과 비교 기준을 뒷받침하는 최소 배경 문헌만 남긴 것이다.

| 근거 축 | 원문 요약 | 본 연구에서의 사용 |
| --- | --- | --- |
| [Whisper](https://arxiv.org/abs/2212.04356) | Whisper 원문은 대규모 다국어/멀티태스크 약지도 학습으로 zero-shot 전사와 번역 일반화가 가능함을 보인다. 다만 이 문헌은 실시간 partial revision 문제를 해결하는 시스템 연구는 아니다. | `faster-whisper + large-v3`를 영어/한국어 운영 후보로 쓰되, raw window 결과를 바로 final로 쓰지 않는 전제다. |
| [Whisper-Streaming](https://arxiv.org/abs/2307.14743) | Whisper-Streaming은 Whisper가 실시간 전사용으로 설계되지 않았기 때문에 local agreement와 self-adaptive latency를 얹어 확정 prefix와 미확정 hypothesis를 분리한다. | 본 연구의 `raw/pending/staged/final` 분리와 여러 window에서 재관측된 후보만 final로 소비하는 정책의 직접 비교 기준이다. |
| [Incremental ASR 평가](https://arxiv.org/abs/2302.12049) | incremental ASR 평가는 WER만으로는 부족하며 latency와 이미 인식된 단어의 update/revoke를 함께 봐야 한다고 제안한다. | `final_f1`, `final_boundary_f1`, replacement churn, staged residue, recent final echo를 분리해 보는 이유다. |
| [Segment Any Text](https://arxiv.org/abs/2406.16678) | SaT는 punctuation 의존도를 낮추고 여러 도메인/언어에서 문장 분절을 수행하도록 설계되었다. | regex/ad-hoc 문장 분할을 운영 경로에서 제외하고 SaT를 completed/pending 후보 생성기로 쓰는 근거다. |
| [Streaming punctuation](https://arxiv.org/abs/2210.05756) | 긴 받아쓰기에서는 WER가 좋아도 pause, 느린 발화, punctuation/segmentation 문제가 남으며, bounded right context와 dynamic window가 필요하다고 보고한다. | punctuation/right-context를 final trigger가 아니라 SBD 후보와 boundary confidence의 보조 신호로 쓰는 근거다. |
| [Qwen3-ASR](https://arxiv.org/abs/2601.21337) | Qwen3-ASR 보고서는 0.6B/1.7B 모델이 52개 언어/방언 ASR을 지원하고, 공개 벤치 외 실제 사용 시나리오 품질 차이를 별도로 평가해야 한다고 강조한다. | 중국어에서 `qwen3-asr-transformers + qwen3-asr-0.6b`를 운영 후보로 두고, STT 품질과 final lifecycle 품질을 분리 평가하는 근거다. |
| [NLLB](https://arxiv.org/abs/2207.04672) | NLLB는 다국어 번역을 200개 언어 규모로 확장하고 FLORES-200, human evaluation, toxicity benchmark로 평가한다. | 번역 backend 후보의 배경 근거다. final-only sink 계약 자체는 프로젝트 파이프라인과 실험일지를 근거로 설명한다. |
| [Optimizing Sentence Segmentation for Speech Translation](https://isl.iar.kit.edu/downloads/803_Interspeech-2007_Rao.pdf) | speech translation에서 segment length를 MT 시스템에 맞게 최적화하면 BLEU가 개선될 수 있고, ASR WER가 번역 성능에 비선형적으로 영향을 준다고 보고한다. | 번역 단위가 downstream 품질에 영향을 준다는 비교 근거다. 현재 파이프라인의 VAD/pause 기반 구현 근거나 최적 segment length 근거로 쓰지는 않는다. |

## 4. 분석 대상 파이프라인

분석 대상 파이프라인은 다음 단계로 구성된다.

1. 오디오 입력 source에서 `AudioEvidence` 생성
2. 언어별 STT backend로 `RecognitionHypothesis` 생성
3. STT 가설과 `UncommittedContext`를 문장 후보로 해석
4. SaT 기반 문장 경계와 punctuation/right-context 신호로 `SentenceCandidateSet` 생성
5. revision-aware commit buffer에서 후보 age, revision 계열, recent final, 품질 플래그를 평가
6. 조건을 만족한 후보만 `CommittedTranscriptEvent(final=true)`로 발행
7. 전사 창과 번역 sink는 final 이벤트만 소비

이 방법의 핵심은 SBD를 단순 문장 분할 보조기가 아니라 lifecycle manager의 입력 계층으로 둔다는 점이다. STT backend는 매 윈도우마다 흔들리는 raw hypothesis를 출력하고, SBD는 이 raw text를 `completed`와 `pending` 후보 집합으로 바꾼다. 이후 lifecycle manager는 SBD가 만든 후보를 바로 확정하지 않고, 후보 age, revision 계열, queue 순서, recent final memory, 품질 플래그를 함께 평가한 뒤 final event만 내보낸다. 즉 본 방법은 "STT -> SBD -> lifecycle manager -> final-only sink"의 계층 구조로 요약할 수 있다.

핵심 정책은 final transcript를 append-only로 유지하는 것이다. 이미 확정된 문장은 UI와 번역 큐에서 되돌리지 않는다. 대신 확정 전 후보는 다음 윈도우에서 계속 갱신될 수 있다.

구현 범위는 의도적으로 좁게 둔다. 운영 경로는 오디오 윈도우에서 STT 가설을 만들고, 모델 기반 SBD로 문장 후보를 만든 뒤, revision-aware buffer가 final 이벤트만 발행하는 구조다. VAD/silence 기반 확정, 언어별 정규식 분기, CJK 문자열 접합, 단어별 예외 규칙은 현재 구현 기여에 포함하지 않는다. 이 제외 기준은 단순화를 위한 것이 아니라, 일부 로그 케이스에 맞춘 규칙이 다른 언어와 다른 발화에서 중복 확정 또는 확정 누락을 늘릴 수 있다는 실험 판단에 따른 것이다.

## 5. SBD 기반 리비전 생명주기

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

여기서 `staged`는 SBD가 `completed`로 제안한 문장이지만 아직 충분히 확인되지 않은 상태를 뜻한다. `pending`은 SBD가 종결 경계가 약하다고 본 조각이며, 다음 윈도우의 후보와 함께 다시 해석된다. 따라서 SBD는 단순 경계 모델이 아니라 lifecycle이 다루는 후보 생성기 역할을 하며, lifecycle은 SBD 출력의 안정성을 시간축 위에서 다시 판정하는 계층이다.

일반 후보는 여러 chunk에서 재확인된 뒤 확정된다. 기본 확정 규칙은 `sentenceFinalizeAge`로 staged 후보의 관찰 횟수를 정의하고, 영어·한국어·중국어 모두 3회를 기준으로 둔다. 미확정 replacement는 기존 후보를 즉시 삭제하지 않고 candidate buffer에 보류한다.

리비전 계열 판정은 완전 문자열 일치가 아니라 token-sentence 유사도, 공통 token run, coverage를 함께 사용한다. 새 후보가 같은 발화 구간으로 보이더라도 confirmation을 보존할 수 없는 reset 대상으로 판정되면 active staged 후보를 즉시 덮지 않고 candidate buffer에서 반복 관측을 기다린다. candidate buffer의 오래된 후보가 짧은 과거 prefix를 끌고 온 상태라면, 같은 본문 coverage가 더 높은 새 후보를 preferred revision으로 보아 prefix 오염 final을 줄인다. active staged 후보가 과거 prefix 뒤에 새 문장의 앞부분만 가진 형태이고 queue 후보가 그 앞부분에서 시작해 suffix를 이어가면, 같은 revision 계열로 보아 queue 후보를 우선한다.

짧은 CJK staged 후보가 replacement와 충돌할 때는 max age 직후 active를 폐기하지 않고 별도 hold window를 두어 confirmation과 revision의 반복 관측 기회를 보존한다. recent final memory는 이미 final된 prefix의 의미 있는 suffix만 회수하고, 이미 final된 동일 token-sentence와 긴 문장의 tail echo를 다시 확정하지 않는다. 같은 revision 계열에서 더 나중 후보가 final로 소비되면 이전 미소비 후보는 stale revision으로 폐기한다. STT text가 없는 chunk는 age 증가 근거로 쓰지 않으며, 반복 no-text 구간의 미확정 후보는 final이 아니라 stale 후보로 정리한다.

## 6. 문맥 윈도우와 확정 단위

문맥 윈도우는 STT 모델에 전달되는 오디오 범위를 의미한다. 긴 문맥 윈도우는 모델이 더 많은 문맥을 보고 동음어와 문장 구조를 판단하게 해 전사 안정성을 높일 수 있다. 그러나 final transcript는 사용자가 보는 텍스트이므로 낮은 지연과 적절한 문장 길이가 필요하다.

예비 관측에서는 중국어 `windowSeconds=30`이 raw STT 안정성을 높이는 경향을 보였지만, final transcript가 긴 문장으로 묶이고 갱신이 늦어지는 문제가 관측되었다. 이후 운영 UI가 raw STT가 아니라 staged 후보를 표시하던 문제를 수정하면서 작은 윈도우 품질에 대한 해석을 재검토했다. 현재 기본 계약은 STT 언어별로 분리하며, 영어는 `windowSeconds=20`, 한국어는 `windowSeconds=10`, 중국어는 `windowSeconds=15`를 기준으로 한다. `stepSeconds=1`, `maxNewTokens=192`, `sentenceFinalizeAge=3`은 세 언어 공통 기준으로 둔다.

현재 관찰을 더 세분하면, 짧은 문장은 작은 윈도우에서도 비교적 빠르게 소비되는 반면, 긴 문장은 소비 누락이나 잘못된 병합이 남는 경향이 있다. 이 경우 병목은 단순히 SBD가 경계를 만들지 못해서라기보다, 윈도우 내부 문맥이 부족한 상태에서 lifecycle이 인접 소절을 하나의 revision 계열로 과도하게 묶거나, 반대로 확정 근거가 부족해 장기 보류하는 데서 생길 수 있다. 따라서 긴 문장 strata에서는 윈도우 확대가 문맥 보강 효과를 통해 소비 누락과 오병합을 완화할 가능성이 있다.

다만 윈도우 확대는 항상 순이익이 아니다. 긴 문장의 raw STT 안정성을 높이는 대신, 확정 지연과 과도한 장문 병합을 함께 키울 수 있다. 따라서 후속 검증은 "윈도우를 키우면 전체 평균이 좋아지는가"보다, "긴 문장 strata의 누락과 오병합이 줄어드는가, 그리고 그 대가로 짧은 문장 strata의 빠른 소비가 얼마나 희생되는가"를 함께 봐야 한다.

## 7. 평가 설계와 지표

본 연구의 평가는 공개 ASR benchmark가 아니라 failure-enriched challenge replay를 대상으로 한다. 입력은 reviewed `sbd_predicted_cases/`이며, 각 케이스는 source `chunks`만을 근거로 `expected_final`을 정리한 텍스트 replay 샘플이다. 따라서 이 평가는 운영 평균 품질이나 raw STT 정확도를 재는 실험이 아니라, 같은 실패 입력 집합에서 SBD 후보 생성과 lifecycle 소비 규칙이 어떤 trade-off를 만드는지 비교하는 실험이다.

평가 지표는 세 계층으로 나뉜다. 첫째, `RecognitionHypothesis`는 raw STT 가설의 품질을 본다. 둘째, `SentenceCandidateSet`은 SBD가 `completed/pending` 후보를 어떤 경계와 순서로 생성하는지 본다. 셋째, `CommittedTranscriptEvent`는 후보가 age, revision 유사도, candidate queue, recent final memory를 거쳐 final-only sink로 소비되는지 본다. 정량 지표의 중심은 최종 문장 유사도를 보는 `final_precision`, `final_recall`, `final_f1`이다. `boundary_granularity_adjusted_f1`은 final 내용과 순서가 맞을 때 `1:N` 분할과 `N:1` 병합의 연속 구간 매칭을 허용하는 보정 경계 진단 지표다. 기존 `final_boundary_f1`는 exact boundary-offset에 과도하게 민감해 핵심 지표에서 제외한다. 그 외 `finalized_per_stage_start`, `staged_exact_match`, `stage_replace_deferred`, `stage_queue_revision` 같은 lifecycle counter를 함께 본다.

이 설계의 목적은 단일 평균 점수 최적화가 아니라 실패 유형 분해다. 따라서 한 파라미터는 우선 `final_f1`과 관련 recall/precision에서 평가하고, `boundary_granularity_adjusted_f1`을 통해 분절 granularity mismatch와 실제 lifecycle 실패를 분리한다. 기존 `final_boundary_f1`는 exact 경계 민감도 확인용 raw diagnostic으로만 남기고, 채택 판단의 중심에서 제외한다. 또한 현재 challenge replay는 failure-enriched corpus이므로, 여기서 얻은 평균을 제품 전체 평균 품질로 일반화하지 않는다.

동시에 현재 파이프라인의 긍정적 특성도 별도 축으로 계측해야 한다. 실제 운영 관찰에서는 긴 문장에서 경계 오류와 소비 지연이 남아 있지만, 짧은 문장과 짧은 소절은 비교적 빠르게 소비되는 경우가 많고, 소비 누락과 중복 소비도 대체로 억제되는 것으로 보인다. 따라서 후속 분석은 병목 지표와 함께 "짧은 문장을 얼마나 빠르고 안정적으로 확정하는가"를 직접 보여주는 지표를 둬야 한다.

이를 위해 다음과 같은 분석 축을 추가로 둔다.

- `short_final_recall`: 짧은 정답 문장 집합에서 최종 확정이 누락되지 않고 회수된 비율
- `short_final_precision`: 짧은 정답 문장 집합에서 조기 확정이 중복 또는 오확정으로 붕괴하지 않은 비율
- `short_duplicate_suppression_rate`: 짧은 문장에서 동일 의미 후보의 반복 확정 없이 한 번만 소비된 비율
- `short_missing_final_rate`: 짧은 문장에서 staged 진입 후 최종 확정 없이 소실된 비율
- `short_boundary_granularity_adjusted_f1`: 짧은 문장에서 분절 granularity 차이를 보정한 경계 진단 지표
- `short_finalized_per_stage_start`: 짧은 후보가 staged에 진입한 뒤 실제 final로 소비되는 비율
- `short_stage_age_to_final`: 짧은 후보가 `stage_start`에서 `finalized`까지 도달하는 관찰 횟수의 분포
- `short_queue_bypass_rate`: 짧은 후보가 장기 queue residue 없이 active staged에서 바로 소비되는 비율
- `short_replace_deferred_rate`: 짧은 후보에서 `stage_replace_deferred`가 얼마나 적게 발생하는지 보는 비율

이 지표들은 긴 문장 병목과 별개로, 현재 구조가 짧은 문장을 빠르게 소비하고 동시에 누락과 중복 소비를 얼마나 잘 억제하는지 검증하기 위한 것이다. 구현상으로는 `expected_final` 길이, token 수, chunk 수, staged age를 기준으로 짧은 문장 strata를 정의하고, 전체 평균과 분리해 해석한다.

긴 문장 strata에 대해서는 다음 지표를 별도 둔다.

- `long_final_recall`: 긴 정답 문장에서 최종 확정 누락 없이 회수된 비율
- `long_merge_error_rate`: 서로 다른 소절이나 문장이 하나의 final로 과병합된 비율
- `long_boundary_granularity_adjusted_f1`: 긴 문장에서 분절 granularity 차이를 보정한 경계 진단 지표
- `long_stage_age_to_final`: 긴 후보가 확정되기까지 필요한 관찰 횟수의 분포
- `long_replace_deferred_rate`: 긴 후보에서 `stage_replace_deferred`가 얼마나 자주 발생하는지 보는 비율
- `long_queue_residue_rate`: 긴 후보가 종료 시점까지 queue에 남는 비율

이 긴 문장 지표는 윈도우 크기 실험과 직접 연결된다. 즉 `windowSeconds`를 단계적으로 키우면서 `long_missing_final_rate`와 `long_merge_error_rate`가 실제로 줄어드는지, 동시에 `short_stage_age_to_final`과 `short_duplicate_suppression_rate`가 얼마나 유지되는지를 함께 비교해야 한다.

## 8. 결과

최신 기준선은 reviewed `sbd_predicted_cases/` 815건을 실제 `sat + cuda + float16` 경로로 재생한 결과이며, 핵심 지표 `final_precision_avg=0.614`, `final_recall_avg=0.786`, `final_f1_avg=0.666`을 기록했다. `boundary_granularity_adjusted_f1_avg`는 final 내용과 순서가 맞는 split/merge granularity mismatch를 분리해 해석하기 위한 보조 진단 수치다. 반면 `final_boundary_f1_avg=0.136`은 exact boundary-offset raw diagnostic으로만 남긴다. 이 기준선은 SBD가 문장 후보를 충분히 생성하더라도, lifecycle 소비 단계에서 후보 교체와 queue 잔류가 계속 병목이 될 수 있음을 보여준다.

| 조건 | cases | final precision | final recall | final F1 | boundary F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| challenge replay baseline | 815 | 0.614 | 0.786 | 0.666 | 0.136 |
| same-chunk tail merge `max_tail_units=4` | 815 | 0.615 | 0.788 | 0.668 | 0.136 |
| same-chunk tail merge `max_tail_units=6` | 815 | 0.617 | 0.791 | 0.670 | 0.136 |
| same-chunk tail merge `max_tail_units=8` | 815 | 0.617 | 0.789 | 0.669 | 0.137 |

현재 결과는 전면적으로 부정적이라고 보기 어렵다. 핵심 지표 `final_recall_avg=0.786`과 `final_f1_avg=0.666`은 failure-enriched challenge replay에서도 적지 않은 내용 회수가 일어나고 있음을 보여준다. 이는 파이프라인이 최소한 일부 후보를 빠르게 소비하고 있다는 긍정 신호로 읽을 수 있다. 특히 운영 관찰상 짧은 문장에서는 소비 누락과 중복 소비가 대체로 억제되고 있다는 점을 고려하면, 전체 평균은 긴 문장 병목 때문에 짧은 문장 strata의 강점을 충분히 드러내지 못할 수 있다.

핵심 관찰은 세 가지다. 첫째, 핵심 품질 지표는 final 문장 유사도다. baseline의 `final_f1_avg=0.666`은 failure-enriched replay에서도 내용 회수가 적지 않음을 보여준다. 둘째, exact boundary raw diagnostic인 `final_boundary_f1_avg`는 본래 의도를 훼손할 정도로 granularity mismatch에 민감하므로 채택 판단의 중심 지표에서 제외한다. 대신 `boundary_granularity_adjusted_f1`를 통해 내용과 순서가 맞는 split/merge를 pure failure와 분리해 본다. 셋째, 현재 기준선은 짧은 문장 또는 짧은 소절의 빠른 소비, 누락 억제, 중복 억제와 긴 문장의 경계 붕괴를 한 평균 안에 함께 담고 있어, 긍정 신호가 과소해석될 수 있다. 예를 들어 same-chunk tail merge는 일부 한국어 residue 사례를 줄였지만 전체 기준선의 안정적 대안으로는 채택되지 않았다.

## 9. 결과 해석

이 결과는 SBD 기반 lifecycle 관리의 의미를 두 가지로 보여준다. 첫째, SBD가 없는 경우 raw STT window를 직접 final로 소비하게 되어 중복 확정과 경계 파괴가 즉시 증가한다. 둘째, SBD만으로도 충분하지 않다. SBD는 후보를 만들 뿐이고, 실제 안정성은 lifecycle manager가 후보를 언제 보류하고, 언제 교체하고, 언제 final로 소비하는지에 달려 있다.

따라서 현재 병목은 SBD 후보 부족보다 `stage_replace_deferred`, `stage_queue_revision`, `staged residue`처럼 후보 소비 규칙에 더 가깝다. 이 해석은 문장 경계 품질이 낮은 케이스에서 특히 뚜렷하다. 여러 케이스에서 내용 자체는 회수되지만, 후속 문장이 queue에 남거나 앞뒤 문맥이 합쳐져 final-only 번역 단위로는 불안정한 문장이 된다. 다시 말해, 본 연구의 핵심 방법은 "SBD로 후보를 만들고, revision-aware lifecycle로 그 후보를 시간축에서 검증한 뒤, final-only sink로 제한적으로 소비하는 구조"에 있다.

파라미터 실험 역시 같은 결론을 지지한다. confirmation 횟수, no-end fragment threshold, staged queue 한도, CJK revision similarity 같은 축은 대부분 precision/recall/boundary trade-off를 만들었다. 따라서 현재 근거는 "세밀한 threshold 조정이 해답"이라는 주장보다, 후보 생성과 소비를 분리한 lifecycle 구조가 더 중요하다는 주장에 가깝다.

다만 이 해석은 긴 문장 병목을 중심으로 한 것이다. 별도 strata 분석을 추가하면, 현재 구조가 짧은 문장과 짧은 소절을 빠르게 소비하고 소비 누락과 중복 소비도 비교적 잘 억제한다는 긍정 결과가 드러날 가능성이 높다. 따라서 후속 분석의 핵심은 병목을 부정적으로 반복 진술하는 것이 아니라, "어떤 길이와 어떤 revision 조건에서 소비가 잘 되고, 어디서부터 급격히 무너지는가"를 분기점 중심으로 계량하는 일이다.

같은 맥락에서 긴 문장 strata는 윈도우 크기와 직접 연결해 해석해야 한다. 현재 관찰상 긴 문장에서는 문장 경계가 약해질 때 내용 회수보다 소비 누락과 오병합이 먼저 문제로 드러난다. 이는 더 긴 문맥이 있으면 완화될 수 있는 유형의 오류이므로, 후속 실험은 `windowSeconds` 증가가 긴 문장 strata의 `long_final_recall`과 `long_merge_error_rate`에 미치는 영향을 우선 확인해야 한다.

## 10. 논의

실시간 전사의 품질은 raw ASR 정확도만으로 설명되지 않는다. 사용자가 보는 것은 final transcript이며, 이 품질은 어떤 문장이 언제 final로 확정되는지에 크게 좌우된다. 특히 번역이 연결된 시스템에서는 문장 경계 오류와 premature final이 그대로 downstream 오류로 전파된다. 이런 점에서 SBD 기반 lifecycle 관리는 단순 후처리가 아니라, STT와 downstream consumer 사이의 독립 계층으로 다뤄져야 한다.

동시에 현재 결과는 보수적으로 읽어야 한다. challenge replay는 실패 사례 중심 입력이므로 운영 평균 품질을 대표하지 않는다. 또한 text replay는 실제 audio timestamp latency나 translation request/output linkage를 포함하지 않으므로, 번역 품질 개선이나 end-to-end runtime equivalence를 직접 증명하지 않는다. 본문이 지지하는 범위는 SBD 기반 후보 생성과 revision-aware lifecycle 관리가 finalization failure를 분석하고 비교하는 데 유효한 구조라는 점까지다.

## 11. 한계

현재 연구는 운영 로그 기반 관측과 텍스트 replay 벤치가 중심이며, 동일 오디오 replay 기반 통제 실험은 제한적이다. 정답 전사 코퍼스가 없어 CER/WER 기반 정량 평가는 아직 보조 지표로만 논의된다. 또한 사용자 체감 지연, 가독성, 번역 만족도에 대한 사용자 연구는 포함하지 않았다. benchmark는 운영 loop의 일부 decision helper와 window text 기반 stable analysis를 공유하지만, 실제 audio timestamp latency와 translation request/output linkage를 포함하지 않는다. 따라서 본 연구의 실험 결과는 운영 loop 전체와 동일한 end-to-end 검증이 아니라, 현재 애플리케이션의 운영 로그와 벤치 샘플에서 재현된 failure lifecycle 분석으로 읽어야 한다.

벤치마크 샘플은 실패 사례 중심으로 수집되므로 일반 발화 전체의 평균 품질을 대표하지 않는다. 최신 815개 reviewed sample도 중복 확정, 확정 누락, no-end fragment, staged queue residue 같은 어려운 케이스를 의도적으로 포함한다. 따라서 이 벤치의 `final_f1_avg`는 공개 ASR benchmark의 WER처럼 모델 일반 성능을 뜻하지 않는다.

외부 문헌은 본 연구의 배경과 비교 기준으로만 사용한다. 운영 기본값, age/window 선택, queue 한도, 폐기한 보정 로직은 프로젝트 실험일지와 벤치 결과가 근거다. VAD, turn-taking, prosody 기반 segmentation, speech translation segmentation 자료는 현재 파이프라인의 직접 구현 근거가 아니며, 범위 밖 비교군으로만 해석한다. historical set 분화, replay parity, 가설 기각 이력은 본문보다 부록 C의 근거 기록으로 분리해 둔다.

## 12. 결론

본 연구는 다국어 실시간 전사 및 번역 시스템에서 리비전 인지 확정 계층을 별도 분석 대상으로 다뤄야 함을 보였다. STT 모델의 원시 가설, 문장 경계 검출, 확정 생명주기, final-only sink 계약은 서로 다른 실패 원인을 갖기 때문에 분리 평가되어야 한다. 특히 긴 문맥은 STT 안정성을 높일 수 있지만 final transcript 지연과 긴 문장 확정 문제를 유발할 수 있다. 따라서 실시간 전사 시스템은 문맥 윈도우와 확정 단위를 분리하고, 중복 억제와 리비전 생명주기를 명시적으로 계측하는 편이 타당하다.

현재 구현은 실패 중심 입력에서 재현 가능한 기준선으로 읽는 편이 타당하다. 최신 815건 challenge replay 기준에서 핵심 품질 지표인 내용 회수 F1은 0.666이다. exact boundary raw diagnostic인 `final_boundary_f1_avg=0.136`은 동일 내용의 분절 granularity 차이까지 엄격하게 감점하므로, 이제 핵심 판단 지표로 사용하지 않는다. 대신 `boundary_granularity_adjusted_f1`를 통해 split-final과 merge-final의 허용 가능한 granularity drift를 분리하고, 그 뒤에도 남는 잔여 실패를 queue residue, staged replacement/deferred, same-chunk completed tail 소비 문제로 해석한다. 따라서 현재 결론은 언어별 ad-hoc 규칙 추가보다 active staged 소비, candidate queue 정리, no-end fragment 처리, recent final memory의 일반 정책을 보수적으로 검증해야 한다는 데 머문다.

동시에 현재 결과는 짧은 문장 소비에 관한 긍정적 가설도 남긴다. failure-enriched challenge replay에서도 내용 회수 지표가 완전히 낮지 않다는 점은, 파이프라인이 모든 구간에서 실패하는 것이 아니라 특정 길이와 특정 revision 조건 이후에 주로 무너진다는 뜻일 수 있다. 특히 짧은 문장 strata에서는 빠른 확정성뿐 아니라 소비 누락과 중복 소비 억제도 별도 강점으로 검증할 필요가 있다. 따라서 다음 단계는 전체 평균을 반복 해석하는 대신, 짧은 문장 strata의 빠른 확정성, 누락 억제, 중복 억제와 긴 문장 strata의 경계 붕괴를 분리 계측하는 것이다.

긴 문장 strata에 대해서는 윈도우 확대가 유효한 다음 실험 가설로 남는다. 만약 더 긴 문맥이 같은 발화의 후행 단서를 충분히 제공한다면, 긴 문장에서 관찰된 소비 누락과 오병합은 완화될 수 있다. 반대로 짧은 문장의 빠른 소비성이 눈에 띄게 악화된다면, 이는 윈도우 확대의 비용으로 해석해야 한다. 따라서 다음 단계는 길이 strata별 소비 품질과 윈도우 크기 사이의 교환관계를 직접 계량하는 것이다.

## 부록 A. 재현 정보

- 기준선 코퍼스: reviewed `tests/eval/dictation_ai/sbd_predicted_cases/`
- 기준선 규모: 815 cases
- 실행 경로: `sat + cuda + float16`
- 최신 재계측 기준 code `HEAD`: `bc1e0be`
- 샘플 정의 기준 커밋: `db5c712`
- 재계측 절차: `paper-baseline-recheck`

이 부록의 목적은 본문 수치의 provenance를 남기는 것이다. 본문 해석은 기준선 수치와 방법론에 집중하고, 세부 실행 기준은 이 부록에서 분리해 관리한다.

## 부록 B. 해석 범위

- challenge replay는 failure-enriched corpus이므로 운영 평균 품질을 대표하지 않는다.
- text replay는 audio timestamp latency와 translation request/output linkage를 직접 포함하지 않는다.
- representative replay와 translation replay는 후속 과제로 남아 있으며, 본문 수치는 해당 범위까지 일반화하지 않는다.

## 부록 C. 근거 기록 메모

- historical set과 refined set은 동일 모집단이 아니며, 각 수치는 해당 시점의 case-definition과 가설 검증 목적에 종속된다.
- `57`건 refined set, `1020/1027`건 clean set, `1113/1223`건 historical set은 최신 `815`건 reviewed challenge replay와 직접 비교용 절대 수치가 아니다.
- complete evidence package의 `lifecycle_replay_summary`에서는 23개 report가 모두 `state_machine_parity=partial`로 기록되어, 현재 replay가 운영 loop 전체와 동일한 end-to-end 검증이 아님을 보여준다.
- fragment revision replay, same-chunk tail merge 등 폐기된 구조 실험은 병목 위치를 좁히는 근거로만 남기고, 현재 운영 경로의 채택 근거로 사용하지 않는다.
- 커밋 로그와 실험일지는 본문 주장보다 부록 성격의 provenance로 취급하며, 본문에서는 최신 reviewed challenge replay와 현재 파이프라인 계약만 직접 인용한다.

## 참고 문헌

상세 참고 문헌 분류와 원문 확인 결과는 [받아쓰기 AI 레퍼런스 원문 확인 컨텍스트](../2026-06-20-dictation-ai-reference-context.md)에 둔다. 실시간 처리 파이프라인 기준은 [받아쓰기 AI 실시간 처리 파이프라인 기준](../2026-06-16-dictation-ai-realtime-pipeline.md)을 따르고, challenge replay와 representative corpus를 나누어 해석하는 실험 규칙은 [받아쓰기 AI 실험 프로토콜](../2026-06-21-dictation-ai-experiment-protocol.md)을 따른다. 핵심 근거는 다음과 같다.

- Radford et al., [Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356). Whisper 계열 모델을 로컬 다국어 ASR backend로 쓰는 배경 근거다.
- Macháček et al., [Turning Whisper into Real-Time Transcription System](https://arxiv.org/abs/2307.14743) 및 Whisper-Streaming demo paper. Whisper가 본래 실시간 모델은 아니며, local agreement와 adaptive latency가 필요하다는 비교 기준이다.
- Whetten et al., [Evaluating Automatic Speech Recognition in an Incremental Setting](https://arxiv.org/abs/2302.12049). 실시간 ASR을 WER만이 아니라 latency와 already-recognized-word update로 평가해야 한다는 근거다.
- Frohmann et al., [Segment Any Text](https://arxiv.org/abs/2406.16678). punctuation 의존도가 낮은 다국어 문장 분절 모델을 SBD 후보 생성기로 쓰는 근거다.
- Behre et al., [Streaming Punctuation for Long-form Dictation with Transformers](https://arxiv.org/abs/2210.05756). 긴 받아쓰기에서 bounded right context와 punctuation/segmentation 품질을 분리해 보는 근거다.
- Shi et al., [Qwen3-ASR Technical Report](https://arxiv.org/abs/2601.21337). 중국어 STT 후보로 Qwen3-ASR 0.6B/1.7B 계열을 비교하는 근거다.
- NLLB Team et al., [No Language Left Behind](https://arxiv.org/abs/2207.04672). NLLB 계열 번역 backend의 배경 근거다.
- Rao et al., [Optimizing Sentence Segmentation for Speech Translation](https://isl.iar.kit.edu/downloads/803_Interspeech-2007_Rao.pdf). speech translation에서 segment length가 downstream 번역 품질에 영향을 줄 수 있다는 비교 근거다.
