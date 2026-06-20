# 다국어 실시간 음성 전사에서 리비전 인지 확정 계층의 설계와 평가

## 초록

실시간 음성 전사(automatic speech recognition, ASR) 시스템은 낮은 지연시간과 높은 전사 정확도를 동시에 요구한다. 그러나 스트리밍 또는 준스트리밍 환경에서 ASR 모델은 매 입력 윈도우마다 부분 가설(partial hypothesis)을 재작성하며, 이 과정에서 중복 출력, 문장 누락, 확정 지연, 번역 입력 중복이 발생한다. 본 연구는 실시간 전사 및 번역 파이프라인에서 원시 ASR 정확도(raw ASR accuracy), 문장 경계 검출(sentence boundary detection), 리비전 생명주기(revision lifecycle), 번역 품질(translation quality)을 분리해 계측하는 후처리 구조를 제안한다. 특히 한국어, 영어, 중국어 환경에서 문맥 윈도우(context window) 길이와 확정 단위(commit unit)의 상호작용을 분석하고, 중국어처럼 공백 기반 단어 경계가 약한 CJK 언어에서 긴 문맥이 전사 안정성을 개선하는 동시에 사용자 화면의 최종 전사(final transcript) 갱신을 늦출 수 있음을 운영 로그 기반으로 관찰한다.

본 논문의 기여는 세 가지다. 첫째, 실시간 ASR 출력의 불안정성을 단순 UI 문제가 아니라 리비전 인지 확정 문제로 모델링한다. 둘째, 중복 증폭(duplicate amplification), 확정 지연(finalization latency), pending overrun, replacement churn, translation quality를 분리한 평가 지표를 제시한다. 셋째, 다국어 실시간 전사 시스템에서 STT 모델, 문장 경계 모델, 확정 정책, 번역 모델을 독립 축으로 검증해야 한다는 운영 근거를 제시한다.

## 1. 서론

최근 대형 음성 인식 모델과 다국어 번역 모델의 발전으로 로컬 환경에서도 실시간 전사 및 번역 기능을 구현할 수 있게 되었다. 하지만 실시간 전사 애플리케이션에서 실제 사용자에게 표시되는 품질은 모델의 오프라인 전사 정확도만으로 설명되지 않는다. 동일한 오디오 구간이 여러 슬라이딩 윈도우(sliding window)에 반복 포함되기 때문에 ASR 모델은 매번 비슷하지만 조금씩 다른 문장을 생성한다. 이 결과를 그대로 화면에 표시하면 중복 문장, 소실된 문장, 되돌려지는 표현, 번역 중복이 발생한다.

본 연구는 이러한 문제를 "리비전 인지 확정 계층(revision-aware finalization layer)"의 설계 문제로 본다. 핵심 질문은 다음과 같다.

- 부분 전사(partial transcript)가 계속 바뀌는 상황에서 어떤 텍스트를 최종 전사로 확정할 것인가?
- 긴 문맥 윈도우가 전사 안정성을 높일 때, 확정 지연과 긴 문장 생성 문제를 어떻게 제어할 것인가?
- STT 오류, 문장 경계 오류, 확정 정책 오류, 번역 오류를 어떻게 분리해 측정할 것인가?
- 한국어, 영어, 중국어처럼 언어 구조가 다른 입력에서 동일한 후처리 정책이 유지 가능한가?

## 2. 문제 정의

실시간 전사 파이프라인은 오디오 입력을 일정 간격(step)으로 읽고, 최근 일정 길이의 문맥 윈도우를 ASR 모델에 전달한다. 모델 출력은 최신 윈도우의 전체 전사 가설이며, 이미 표시된 전사와 새 출력 사이의 차이를 계산해야 한다.

본 연구에서는 텍스트 상태를 다음 세 계층으로 구분한다.

- `hypothesis_text`: 최신 ASR 윈도우에서 나온 원시 전사 가설
- `pending_text`: 아직 확정되지 않아 다음 윈도우에서 재작성될 수 있는 후보 구간
- `confirmed_text`: 사용자 화면과 번역 큐에 append-only로 반영되는 최종 전사

이 구조에서 실패는 네 가지로 나눌 수 있다.

- STT 실패: 원시 ASR이 잘못된 언어, 단어, 의미를 출력한다.
- 문장 경계 실패: 완료된 문장과 미완성 문장을 올바르게 분리하지 못한다.
- 확정 실패: 동일 문장을 중복 확정하거나, 다른 문장을 하나의 리비전으로 오인하거나, 긴 문장을 지나치게 늦게 확정한다.
- 번역 실패: 확정된 원문은 적절하더라도 번역 모델이 고유명사, 도메인 용어, 구어체를 잘못 번역한다.

## 3. 관련 연구

Whisper 계열 모델은 강력한 오프라인 전사 성능을 보이지만, 본래 저지연 스트리밍 모델로 설계된 것은 아니다. Whisper-Streaming 계열 연구는 local agreement policy와 self-adaptive latency를 사용해 여러 윈도우에서 합의된 부분만 확정하는 접근을 취한다. 이 방향은 본 연구의 리비전 인지 확정 계층과 문제의식이 유사하다.

문장 경계 검출은 일반 텍스트 분절(sentence segmentation)과 ASR punctuation restoration 연구에서 다루어진다. 그러나 실시간 ASR의 partial transcript는 매 chunk마다 이전 가설을 재작성하므로, 일반 문장 분절 모델을 그대로 적용하면 staged 후보의 교체와 폐기가 증가할 수 있다.

중국어와 같은 CJK 언어는 공백 기반 단어 경계가 없고 동음 후보가 많아 긴 문맥의 언어 모델링 효과가 더 중요할 수 있다. 본 연구의 운영 로그에서도 중국어는 짧은 윈도우에서 의미 보존이 흔들리고, 긴 윈도우에서 원시 STT 안정성이 개선되는 경향을 보였다. 반면 긴 윈도우는 final transcript 갱신 지연과 긴 문장 확정을 증가시켰다.

## 4. 시스템 설계

제안 시스템은 다음 단계로 구성된다.

1. 오디오 입력 버퍼링
2. 슬라이딩 문맥 윈도우 생성
3. 언어별 STT backend 실행
4. stable window 추출
5. 기존 confirmed 텍스트와 새 stable 텍스트의 delta 계산
6. 문장 경계 검출
7. staged 후보 생성 및 리비전 판정
8. 확정 조건 충족 시 final transcript 출력
9. final transcript만 번역 큐로 전달

핵심 정책은 final transcript를 append-only로 유지하는 것이다. 이미 확정된 문장은 UI와 번역 큐에서 되돌리지 않는다. 대신 확정 전 후보는 다음 윈도우에서 계속 갱신될 수 있다.

## 5. 리비전 생명주기

리비전 생명주기는 staged 후보가 final transcript가 되기까지의 상태 전이를 정의한다.

- `stage_start`: 새 후보가 staged 상태로 진입한다.
- `stage_revision`: 다음 윈도우의 후보가 기존 staged 후보의 리비전으로 판정된다.
- `stage_replace`: 다음 후보가 리비전이 아닌 별도 후보로 판정된다.
- `stage_replaced_unconfirmed`: 기존 staged 후보가 확정 기준에 도달하지 못한 상태에서 새 관찰 후보로 교체된다.
- `stage_finalize_before_replace`: 새 completed 후보가 들어오기 전에 관찰 횟수 기준을 통과한 기존 staged 후보를 먼저 확정한다.
- `finalize_recent_echo_suppressed`: 이미 final로 확정한 문장과 유사한 대체 후보가 같은 위치에서 다시 등장해 중복 출력을 억제한다.
- `finalized`: 후보가 final transcript로 확정된다.
- `candidate_duplicate_suppressed`: 이미 committed된 내용과 중복되어 출력하지 않는다.

일반 후보는 여러 chunk에서 재확인된 뒤 확정된다. 현재 운영 계약은 `sentenceFinalizeAge`로 staged 후보의 관찰 횟수를 정의하고, 기본값 3회를 기준으로 한다. 중국어에서 한 STT 윈도우가 여러 completed 후보를 반환하면 하나의 관찰 단위로 병합해 같은 chunk 안 후속 후보가 첫 관찰 후보를 즉시 확정시키지 않도록 한다. 강제 확정은 pending 길이와 pending 관측 횟수가 임계치를 넘을 때만 제한적으로 사용한다. 한국어의 열린 절(open Korean clause), 중국어의 짧은 CJK fragment, 문장부호 없는 후보는 확정 조건을 더 보수적으로 적용한다.

## 6. 문맥 윈도우와 확정 단위

문맥 윈도우는 STT 모델에 전달되는 오디오 범위를 의미한다. 긴 문맥 윈도우는 모델이 더 많은 문맥을 보고 동음어와 문장 구조를 판단하게 해 전사 안정성을 높일 수 있다. 그러나 final transcript는 사용자가 보는 텍스트이므로 낮은 지연과 적절한 문장 길이가 필요하다.

운영 관측에서는 중국어 `windowSeconds=30`이 raw STT 안정성을 높이는 경향을 보였지만, final transcript가 긴 문장으로 묶이고 갱신이 늦어지는 문제가 관측되었다. 이후 원문창이 raw STT가 아니라 staged 후보를 표시하던 문제를 수정하면서 작은 윈도우 품질에 대한 해석을 재검토했다. 현재 기본 계약은 STT 언어별로 분리하며, 영어는 `windowSeconds=20`, 한국어는 `windowSeconds=10`, 중국어는 `windowSeconds=15`를 기준으로 한다. 공통으로 `stepSeconds=1`, `sentenceFinalizeAge=3`, `maxNewTokens=192`를 시작점으로 둔다.

## 7. 평가 지표

본 연구는 단위 테스트의 성공 여부를 품질 통과 기준으로 보지 않는다. 테스트는 운영 로그에서 관측된 실패 사례를 재현하고, 각 도메인의 추적 지표를 출력하는 성능 추적 하네스로 사용한다.

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
| `runtime_metrics` | 중복 억제, delta trim, final quality, translation skip을 분리 계측하는지 |
| `translation_quality` | 번역 출력의 고유명사/도메인 용어/환각 회귀를 추적하는지 |

향후 정답 전사 코퍼스가 준비되면 `CER`, `WER`, deletion rate, duplicate insertion rate, finalization latency, revokes per second를 추가한다. 중국어는 WER보다 CER을 우선한다. 평가 시 raw STT window 결과와 revision lifecycle을 거친 final transcript를 분리한다. raw STT는 모델 전사 품질을, final transcript는 사용자에게 표시되는 실시간 자막 품질을 나타낸다.

## 8. 운영 관측

한국어와 영어에서는 Whisper large-v3 기반 전사가 상대적으로 안정적이었다. 중국어에서는 Whisper/faster-whisper의 의미 보존과 문장 구조가 부족했고, Qwen3-ASR 0.6B가 더 나은 후보로 관측되었다. FunASR 계열은 처리 속도는 빠르지만 의미 보존, stage churn, 확정률에서 불리했다.

2026-06-14 중국어 30분 모니터링에서는 stage replace/unconfirmed replacement가 많이 발생했고, 계산 시간보다 후보 생명주기가 병목으로 나타났다. `windowSeconds=30`은 raw STT 흔들림을 줄였지만, 긴 문장 확정과 final 지연을 증가시켰다. 2026-06-16 로그에서는 한 STT chunk 안의 후속 completed 후보가 첫 관찰 후보를 `next_completed`로 즉시 final 확정시키는 사례가 관측되어, 중국어 multi-completed 후보를 하나의 관찰 단위로 병합하고 교체 직전 확정에 `sentenceFinalizeAge` 기준을 적용했다.

2026-06-15 로그에서는 pending 텍스트와 다음 STT 윈도우가 같은 CJK 구간을 내부 중간부터 다시 내보내는 현상이 관측되었다. 한때 pending/new 접합 보정으로 분류했지만, 학술적 근거가 부족해 운영 요구사항에서는 제외한다. 현재는 STT/backend 품질, 문장 경계, revision lifecycle 지표로 분리해 관측한다.

## 9. 논의

실시간 전사의 품질은 raw ASR 정확도만으로 판단할 수 없다. 사용자가 보는 품질은 final transcript가 언제, 어떤 단위로, 얼마나 중복 없이 확정되는지에 크게 좌우된다. 특히 번역을 포함하는 시스템에서는 확정되지 않은 문장을 번역하면 번역 중복과 번역 되돌림이 발생한다. 따라서 번역은 final transcript 중심으로 수행하고, provisional translation은 별도 정책으로 분리해야 한다.

중국어 실험은 문맥 길이와 확정 단위의 분리가 중요함을 보여준다. 긴 문맥은 STT에 유리하지만 finalization latency에는 불리하다. 그러므로 긴 STT context를 쓰더라도 final commit unit은 더 짧게 유지하는 계층이 필요하다.

## 10. 한계

현재 연구는 운영 로그 기반 관측이 중심이며, 동일 오디오 replay 기반 통제 실험이 충분하지 않다. 정답 전사 코퍼스가 없어 CER/WER 기반 정량 평가는 아직 제한적이다. 또한 사용자 체감 지연, 가독성, 번역 만족도에 대한 사용자 연구가 포함되어 있지 않다.

향후 연구에서는 동일 오디오셋에 대해 언어별 기준값과 비교값을 분리해 평가한다. 영어는 20초, 한국어는 10초, 중국어는 15초 기준선을 중심으로 비교한다. Whisper, Qwen3-ASR, streaming ASR 후보를 같은 조건에서 replay 평가하고, 번역 품질은 STT/확정 품질과 분리해 별도 평가셋으로 측정한다.

## 11. 결론

본 연구는 다국어 실시간 전사 및 번역 시스템에서 리비전 인지 확정 계층의 필요성을 제시했다. STT 모델의 원시 정확도, 문장 경계 검출, 확정 생명주기, 번역 품질은 서로 다른 실패 원인을 갖기 때문에 분리 평가되어야 한다. 특히 CJK 언어에서는 긴 문맥이 STT 안정성을 높일 수 있지만 final transcript 지연과 긴 문장 확정 문제를 유발한다. 따라서 실시간 전사 시스템은 문맥 윈도우와 확정 단위를 분리하고, 중복 억제와 리비전 생명주기를 명시적으로 계측해야 한다.

## 참고 문헌

상세 참고 문헌은 [받아쓰기 AI 참조 레퍼런스 모음](../2026-06-16-dictation-ai-reference-index.md)에 통합한다. 실시간 처리 파이프라인 기준은 [받아쓰기 AI 실시간 처리 파이프라인 기준](../2026-06-16-dictation-ai-realtime-pipeline.md)을 따른다. 핵심 근거는 다음과 같다.

- Whisper-Streaming: local agreement policy와 self-adaptive latency
- WhisperPipe: overlapping context window와 dynamic buffering
- CarelessWhisper: encoder-decoder ASR의 causal streaming 전환 한계
- Segment Any Text / wtpsplit SaT: 다국어 문장 분절
- Streaming punctuation: 긴 받아쓰기에서 dynamic decoding window와 bounded lookahead 기반 문장부호/경계 후보
- Speech translation segmentation: VAD/pause 기반 세그먼트가 문장/번역 단위와 불일치할 수 있다는 근거
- Turn-taking / VAP: 발화 종료 보조 feature로만 사용하고 프레젠테이션 세그먼트 final의 주 결정 기준으로 사용하지 않는 비교군
- Qwen3-ASR Technical Report 및 모델 카드
- WeNet streaming/non-streaming E2E ASR
