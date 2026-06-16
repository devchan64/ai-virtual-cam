# 받아쓰기 AI 중국어 STT 후보 세부검증 리포트

## 문서 상태

이 문서는 받아쓰기 AI 중국어 STT 후속 후보인 Qwen3-ASR vLLM streaming, Dolphin-CN-Dialect, WeNet의 세부검증 판단을 분리해 정리한다. 기준 설계와 운영 기본값은 [받아쓰기 AI 설계 및 실험 노트](2026-06-16-dictation-ai-design-experiment-notes.md)를 따르고, 설정 계약과 허용값은 [받아쓰기 AI 계약과 기본값](2026-06-16-dictation-ai-contract-defaults.md)을 따른다.

이 문서는 후보별 검증 리포트다. 각 후보는 모델 적합성, 실시간 처리 구조, 런타임 통합 비용, 현재 운영 판단으로 평가한다.

## 현재 기준 판단

중국어 STT 운영 우선값은 `qwen3-asr-transformers`와 `qwen3-asr-0.6b`다. 2026-06-14 운영 로그 기준 Qwen3-ASR 0.6B는 FunASR Paraformer보다 느렸지만 의미 보존, 문장 구조, 확정률에서 더 나은 후보로 관측되었다. `faster-whisper` 중국어 경로는 운영 품질 후보가 아니라 baseline으로 둔다.

Qwen3-ASR vLLM streaming, Dolphin-CN-Dialect, WeNet은 현재 운영 기본값이 아니다. 세 후보는 중국어 raw STT 안정성, streaming latency, 방언/코드스위칭 대응, 별도 ASR service 구조를 검토하기 위한 후속 후보로 남긴다.

## 검증 관점

후보를 볼 때 가장 먼저 분리해야 하는 것은 raw STT 품질과 받아쓰기 AI 후처리 품질이다. STT 후보가 좋은 텍스트를 내더라도 sliding window, pending 접합, staged confirmation, final 확정 정책이 불안정하면 사용자 출력은 흔들린다. 반대로 후처리가 좋아도 raw STT가 의미를 잃으면 final 품질은 회복하기 어렵다.

| 관점 | 의미 |
| --- | --- |
| raw STT 품질 | 중국어 의미 보존, 문장 구조, 동음어/고유명사/가격 표현 안정성 |
| 실시간성 | `stt_rtf`, `total_rtf`, TTFT, effective latency, final latency |
| streaming 구조 | partial/final 이벤트, session id, stream reset, backpressure 표현 가능성 |
| 런타임 통합 | shared `.venv` 충돌 여부, GPU 메모리 정책, 모델 캐시/다운로드 계약 |
| 운영 정합성 | Fail-Fast 정책, config/serve 책임 분리, 자동 fallback 금지 |

## Qwen3-ASR vLLM Streaming

Qwen3-ASR vLLM streaming은 현재 중국어 운영 후보인 Qwen3-ASR transformers 경로의 지연 개선 후보다. Qwen3-ASR 계열은 중국어, 영어, 한국어를 포함한 다국어와 중국어 방언 지원을 전제로 하고, 모델 카드 기준 offline/streaming 통합 추론과 transformers/vLLM 백엔드를 제공한다. 현재 프로젝트에서는 `qwen3-asr-transformers`와 `qwen3-asr-0.6b`를 중국어 품질 우선 경로로 보고 있으며, vLLM streaming은 같은 모델 계열을 더 낮은 TTFT와 별도 서비스 구조로 운영할 수 있는지 확인하는 후속 실험이다.

운영 로그 관측은 Qwen3-ASR 0.6B가 FunASR Paraformer보다 느리지만 의미 보존과 문장 구조가 더 자연스럽고 확정률도 상대적으로 높다는 방향을 보였다. 이 판단은 vLLM streaming 자체의 검증 결과가 아니라 Qwen3-ASR 계열을 중국어 품질 우선 후보로 볼 근거다. vLLM streaming은 별도 검증 없이는 transformers 경로의 품질 판단을 그대로 승계하지 않는다.

가장 큰 제약은 런타임 격리다. `qwen3-asr-vllm-streaming`은 공유 `.venv`에서 vLLM 의존성이 `mediapipe`/`protobuf`와 충돌하므로 현재 setup/serve 경로에 넣지 않는다. 이 후보를 도입하려면 in-process STT backend가 아니라 별도 ASR service로 분리해야 한다. 그 경우 config GUI와 serve는 model-ready, download-ready, process-ready 상태를 명확히 구분해야 하고, 실패 시 다른 STT backend로 자동 전환하지 않아야 한다.

vLLM streaming이 실제 후보가 되려면 partial/final 이벤트 계약도 먼저 정해야 한다. 받아쓰기 AI의 final은 모델의 final 이벤트를 그대로 사용자 final로 쓰는 구조가 아니라 staged confirmation과 revision lifecycle을 통과해야 한다. 따라서 streaming backend는 raw partial, raw final, stream reset, session id, backpressure를 구분해서 내보내고, 받아쓰기 AI 후처리는 기존 final-only 번역 계약을 유지해야 한다.

현재 판단은 보류다. Qwen3-ASR transformers 0.6B가 중국어 기본 시작점이고, vLLM streaming은 공유 런타임에 넣지 않는다. 격리 런타임과 ASR service 계약이 준비된 뒤에만 다시 비교한다.

## Dolphin-CN-Dialect

Dolphin-CN-Dialect는 중국어/방언 중심 STT 후보로 추적한다. 이 후보의 검증 가치는 표준 중국어만이 아니라 방언, 대만 만다린, 코드스위칭, 음식명/지명/가격 표현처럼 실제 발표나 회의에서 자주 흔들리는 표현을 비교하는 데 있다. 중국어 문자 단위 처리와 영어 subword 처리를 구분하는 접근은 공백 없는 중국어 텍스트와 영어 혼합 발화가 동시에 등장하는 받아쓰기 AI 시나리오와 맞닿아 있다.

다만 현재 프로젝트에는 Dolphin-CN-Dialect의 실행 경로가 없다. 모델 파일 확보, 로컬 캐시 구조, 다운로드 UX, 라이선스 확인, CUDA 또는 다른 가속 추론 경로, Python adapter가 모두 미정이다. 이 상태에서 GUI 후보나 기본값으로 올리면 사용자는 선택 가능한 모델처럼 보지만 실제 serve 경로에서는 Fail-Fast 기준을 만족하지 못한다.

Dolphin-CN-Dialect는 Qwen3-ASR보다 통합 불확실성이 크다. 따라서 현재 목적은 운영 기본값 대체가 아니라 중국어 방언/코드스위칭 품질 비교군을 확보하는 것이다. replay 비교에서는 표준 만다린만으로 판단하지 않고, 대만 만다린, 중영 혼합, 고유명사, 서비스명, 가격/수량 표현을 포함해야 한다. 이 비교는 raw STT 품질 자체와 staged/final 확정 품질을 분리해서 기록해야 한다.

현재 판단은 2차 품질 후보다. 런타임과 모델 캐시 계약이 정리되기 전까지는 설정 계약, 다운로드 대상, GUI 선택지에 넣지 않는다.

## WeNet

WeNet은 중국어 streaming/non-streaming E2E ASR 구조 비교군이다. dynamic chunk와 CTC/attention rescoring 기반으로 latency와 정확도를 조절할 수 있으므로, Qwen3-ASR vLLM streaming이 메모리나 운영 비용 때문에 막히는 경우 native streaming 구조를 비교하는 데 의미가 있다.

WeNet의 장점은 streaming ASR 구조가 명확하다는 점이다. 받아쓰기 AI가 필요로 하는 partial/final, chunk, latency, rescoring 개념을 모델 구조 차원에서 비교할 수 있다. Whisper식 sliding window 후처리와 달리 native streaming ASR가 제공하는 안정성 신호를 어떻게 revision lifecycle에 연결할 수 있는지 검증할 수 있다.

제약은 통합 비용이다. 현재 프로젝트에는 WeNet 의존성, 모델 다운로드, 모델 캐시, Python adapter, GPU 실행 경로가 없다. 또한 WeNet이 제공하는 streaming 안정성이 곧바로 Qwen3-ASR 계열의 문맥 품질을 대체한다는 보장은 없다. 중국어 의미 보존, 긴 문장 구조, 고유명사 처리, 코드스위칭 품질은 별도 replay로 확인해야 한다.

현재 판단은 구조 비교군이다. Qwen3-ASR vLLM streaming을 별도 서비스로 가져가기 어렵거나, streaming 이벤트 계약을 더 명확히 비교해야 할 때 WeNet을 검토한다. 운영 기본값으로 두지 않고, 먼저 adapter와 모델 캐시 계약을 설계한 뒤 raw STT 품질과 final latency를 비교한다.

## 운영 반영 기준

세 후보 모두 바로 기본값으로 승격하지 않는다. 현재 기본값은 중국어 `qwen3-asr-transformers + qwen3-asr-0.6b`이며, 후속 후보는 동일 입력 replay와 운영 로그 지표에서 기본값보다 나은 근거가 생겨야 한다.

후보가 더 빠르다는 이유만으로 채택하지 않는다. 중국어 받아쓰기 AI에서는 의미 보존, 문장 구조, final 생성률, stage churn, 번역 입력 안정성이 함께 좋아야 한다. `stt_rtf`가 낮아도 final latency가 커지거나 `stage_replaced_unconfirmed`, `raw_without_final`, `revision_changed`가 늘면 사용자 체감 품질은 나빠질 수 있다.

후보가 도입되더라도 자동 fallback은 허용하지 않는다. 설정한 backend가 실행 불가능하면 실패 원인, 설정값, 권장 조치를 출력하고 중지한다. 공유 `.venv`와 충돌하는 backend는 별도 격리 런타임으로만 다룬다.
