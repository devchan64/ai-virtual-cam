# 받아쓰기 AI 논문 레퍼런스 원문 확인 컨텍스트

## 목적

이 문서는 폐기한 `2026-06-16-dictation-ai-reference-index.md`의 외부 자료를 원문 기준으로 다시 분류해, 논문 초안에서 잘못된 근거를 인용하지 않도록 한다. 분류 기준은 다음과 같다.

- 직접 인용 가능: 현재 논문 초안의 핵심 주장에 직접 연결할 수 있는 원문이다.
- 비교군: 관련 분야의 배경 또는 대안 구조를 설명할 때만 인용한다. 현재 파이프라인의 필수 구현 근거로 쓰지 않는다.
- 제외: 현재 실험/설계와 직접 관련이 약하거나, 구현 후보가 아니거나, 원문 확보가 불완전해 논문 초안의 근거로 쓰지 않는다.

운영 로그, 벤치 수치, `windowSeconds`, `sentenceFinalizeAge`, queue/revision 파라미터 튜닝은 외부 논문이 아니라 `2026-06-16-dictation-ai-experiment-log.md`를 근거로 해석한다.

## 원문 확보 상태

- 기준 문서: 폐기 전 `docs/2026-06-16-dictation-ai-reference-index.md`
- 다운로드 위치: `.tmp/dictation-ai-reference-sources/`
- 확인 시각: 2026-06-20 KST
- 다운로드 실행 기준: title/url 항목 79개, URL 기준 75개
- 다운로드 결과: 57개 PDF, 21개 HTML/페이지, 1개 실패
- 실패 항목: `Optimizing Sentence Segmentation for Speech Translation`의 ACL 2002 PDF 링크는 404로 원문 PDF를 받지 못했다.

`.tmp` 아래 원문 파일은 추적하지 않는다. 이 문서에는 원문 확인을 바탕으로 한 분류와 요약만 남긴다.

## 직접 인용 가능

| 자료 | 요약 | 인용 가능한 주장 | 인용하면 안 되는 주장 |
| --- | --- | --- | --- |
| [Whisper: Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356) | 대규모 다국어/멀티태스크 약지도 학습으로 Whisper가 여러 ASR/translation benchmark에서 zero-shot 일반화를 보인다는 원 모델 논문이다. | faster-whisper/Whisper 계열을 영어/한국어 STT backend 후보로 쓰는 배경. | Whisper가 실시간 partial revision, sentence finalization, 중복 억제를 해결한다는 근거로 쓰면 안 된다. |
| [Turning Whisper into Real-Time Transcription System](https://arxiv.org/abs/2307.14743) | Whisper가 본래 실시간 모델이 아니므로 LocalAgreement와 self-adaptive latency로 streaming-like 전사 시스템을 만든다. 확정 prefix와 미확정 hypothesis 분리가 핵심이다. | raw hypothesis와 final transcript를 분리하고 여러 window에서 재관측된 후보만 확정하는 설계의 직접 비교 기준. | 현재 앱의 queue/recent-final/no-end 정책 세부값을 정당화하는 근거로 쓰면 안 된다. |
| [Evaluating Automatic Speech Recognition in an Incremental Setting](https://arxiv.org/abs/2302.12049) | incremental ASR은 WER뿐 아니라 latency, 이미 인식된 단어의 update/revoke를 함께 평가해야 함을 보이고 Revokes per Second 같은 안정성 지표를 제안한다. | final F1, boundary F1, replacement churn, staged residue, duplicate/revision metric을 분리해 보는 평가 방향. | 현재 벤치의 `final_f1_avg` 목표값이나 pass/fail 기준을 외부적으로 보증하는 근거로 쓰면 안 된다. |
| [Segment Any Text](https://arxiv.org/abs/2406.16678) | SaT는 punctuation 의존도를 낮추고 다양한 언어/도메인에서 효율적인 sentence segmentation을 목표로 한다. | regex/ad-hoc 분할을 운영 경로에서 제외하고 SaT를 SBD 후보 생성기로 쓰는 근거. | SaT 결과를 곧바로 final로 확정해도 된다는 근거로 쓰면 안 된다. |
| [Streaming Punctuation for Long-form Dictation with Transformers](https://arxiv.org/abs/2210.05756) | 긴 받아쓰기에서는 WER가 좋아도 pause, 느린 발화, punctuation/segmentation 문제가 남고, real-time 제약 속에서 제한된 right context를 써야 함을 다룬다. | punctuation/right-context를 경계 후보 보조 신호로 보는 근거. | punctuation만으로 문장 final을 확정하거나 VAD/silence를 필수 경계로 쓰는 근거로 쓰면 안 된다. |
| [Qwen3-ASR Technical Report](https://arxiv.org/abs/2601.21337) | Qwen3-ASR 0.6B/1.7B가 52개 언어/방언 ASR을 지원하며, 공개 벤치 외 실제 시나리오 품질 차이를 별도 평가해야 한다고 설명한다. | 중국어 STT 후보로 Qwen3-ASR을 검토하고, STT 품질과 final lifecycle 품질을 분리 평가하는 근거. | Qwen3-ASR이 현재 앱의 중국어 확정 누락/중복 문제를 해결한다는 근거로 쓰면 안 된다. |
| [No Language Left Behind](https://arxiv.org/abs/2207.04672) | NLLB는 200개 언어 규모 번역 모델과 FLORES-200, human evaluation, toxicity benchmark 기반 평가를 제시한다. | NLLB 계열을 번역 backend 후보로 두고 STT/SBD/finalization과 번역 품질을 분리하는 배경. | final-only 번역 sink 계약 자체의 학술 근거로 쓰면 안 된다. final-only 계약은 프로젝트 파이프라인과 실험일지가 근거다. |

## 비교군

### Whisper streaming/저지연 변형

| 자료 | 요약 | 사용 위치 |
| --- | --- | --- |
| [Whisper-Streaming demo paper](https://aclanthology.org/2023.ijcnlp-demo.3/) | Whisper-Streaming 구현과 데모 시스템 관점의 자료다. LocalAgreement 기반 streaming UX를 설명한다. | 위 arXiv 논문의 시스템/데모 보조 인용. |
| [Simul-Whisper](https://www.isca-archive.org/interspeech_2024/wang24ea_interspeech.pdf) | Whisper의 cross-attention alignment를 활용해 chunk-based streaming ASR을 시도하고, chunk boundary의 불안정성을 다룬다. | Whisper를 streaming으로 바꾸는 다른 접근 비교. |
| [WhisperKit](https://openreview.net/pdf?id=6lC3MPFbVg) | 온디바이스 Whisper 실행과 배포/최적화 관점의 자료다. | 로컬 실행/UX 비교. 현재 Linux CUDA pipeline의 직접 근거는 아니다. |
| [Adapting Whisper for Streaming Speech Recognition via Two-Pass Decoding](https://arxiv.org/abs/2506.12154) | 빠른 1차 가설과 2차 보정을 결합하는 streaming adaptation 계열이다. | two-pass 구조 비교. |
| [WhisperRT](https://arxiv.org/abs/2508.12301) | Whisper 기반 저지연 실행 후보군이다. | 향후 backend 비교 후보. |
| [WhisperPipe](https://arxiv.org/abs/2604.25611) | overlapping context window와 buffering을 활용한 resource-efficient streaming architecture다. | 현재 sliding window 구조와 buffering 비교. |
| [CarelessWhisper](https://arxiv.org/abs/2508.12301) | Whisper를 causal streaming 모델로 전환하는 접근이다. | causal 전환 가능성 비교. |
| [M2R-Whisper](https://arxiv.org/abs/2409.11889) | multi-stage/multi-scale retrieval augmentation으로 Whisper 품질 보강을 시도한다. | STT backend 품질 보강 후속 후보. |

### ASR 모델/툴킷 비교

| 자료 | 요약 | 사용 위치 |
| --- | --- | --- |
| [Conformer](https://arxiv.org/abs/2005.08100) | convolution과 Transformer를 결합한 ASR encoder 구조다. | ASR 구조 배경. 현재 앱의 finalization 근거는 아니다. |
| [wav2vec 2.0](https://arxiv.org/abs/2006.11477) | self-supervised speech representation 기반 ASR 접근이다. | Whisper 외 ASR 배경 비교. |
| [RNN-Transducer](https://arxiv.org/abs/1211.3711) | streaming ASR에서 널리 쓰인 RNN-T 구조의 기초 자료다. | native streaming ASR와 sliding-window 후처리의 차이를 설명할 때. |
| [FunASR](https://arxiv.org/abs/2305.11013) | end-to-end speech recognition toolkit이며 중국어/다국어 모델 후보를 제공한다. | 중국어 backend 후보 비교. 실험 결론은 프로젝트 실험일지에 의존한다. |
| [FunASR GitHub README](https://github.com/modelscope/FunASR) | 설치/모델/streaming 지원 범위 확인용 프로젝트 문서다. | 구현 후보 조사 자료. 학술 근거로는 쓰지 않는다. |
| [FunAudioLLM](https://arxiv.org/abs/2407.04051) | SenseVoice 등 음성 이해/생성 foundation model 계열을 설명한다. | SenseVoice 후보군 배경. |
| [SenseVoice GitHub README](https://github.com/FunAudioLLM/SenseVoice) | SenseVoice 사용법과 모델 범위 확인용 프로젝트 문서다. | 구현 후보 조사 자료. |
| [SenseVoiceSmall Model Card](https://huggingface.co/FunAudioLLM/SenseVoiceSmall) | 경량 모델의 언어 지원, 입출력, 라이선스 확인용이다. | 도입 조건 확인. |
| [WeNet](https://arxiv.org/abs/2102.01547) | streaming/non-streaming E2E ASR을 통합하고 chunk size로 latency를 제어하는 production-oriented toolkit이다. | native streaming ASR 비교군. 현재 Whisper sliding-window finalization의 핵심 근거는 아니다. |
| [LLM-based ASR and Whisper comparison](https://arxiv.org/abs/2412.00721) | 저자원/코드스위칭 환경에서 Whisper와 LLM 기반 ASR을 비교하는 자료다. PDF는 확보하지 못했고 arXiv abstract page만 확인했다. | 후속 모델 비교 후보. 핵심 근거로 쓰지 않는다. |

### 중국어/CJK STT와 오류 보정

| 자료 | 요약 | 사용 위치 |
| --- | --- | --- |
| [Qwen3-ASR-0.6B Model Card](https://huggingface.co/Qwen/Qwen3-ASR-0.6B) | Qwen3-ASR 0.6B의 모델 사용 조건과 라이선스, 지원 범위 확인용이다. | 운영 backend 도입 조건 확인. |
| [Qwen3-ASR-1.7B Model Card](https://huggingface.co/Qwen/Qwen3-ASR-1.7B) | 더 큰 Qwen3-ASR 후보의 도입 조건 확인용이다. | 성능/VRAM 비교 후보. |
| [Dolphin-CN-Dialect](https://arxiv.org/abs/2605.08961) | 중국어 방언 ASR에 초점을 둔 모델/데이터 자료다. | 방언 입력 확장 검토. 현재 기본 pipeline 근거는 아니다. |
| [FormalASR](https://arxiv.org/abs/2605.19266) | 구어 중국어를 formal text로 변환하는 end-to-end 방향의 자료다. | 중국어 후처리/정규화 후속 후보. |
| [ASR-EC Benchmark](https://arxiv.org/abs/2412.03075) | 중국어 ASR error correction에 대한 LLM 평가 benchmark다. | STT 오류 보정 평가 축 비교. |
| [LLM Should Understand Pinyin](https://arxiv.org/abs/2409.13262) | pinyin 정보를 중국어 ASR 오류 보정에 활용하는 접근이다. | 동음어 오류 보정 후보. |
| [Pinyin Regularization](https://arxiv.org/abs/2407.01909) | 중국어 음가 정보를 error correction에 반영하는 방법이다. | 발음 기반 보정 후보. |
| [Full-text Error Correction for Chinese ASR](https://arxiv.org/abs/2409.07790) | 전체 전사 텍스트 단위의 중국어 ASR 오류 보정 접근이다. | STT 후처리 후보. 현재 운영 경로에는 넣지 않는다. |
| [PARCO](https://arxiv.org/abs/2509.04357) | phoneme 정보와 entity disambiguation을 결합한 contextual ASR 접근이다. | 고유명사/문맥 ASR 비교 후보. |
| [PAC](https://arxiv.org/abs/2509.12647) | pronunciation-aware contextual LLM 기반 ASR 접근이다. | 발음-aware contextual ASR 비교 후보. |

### 문장 경계와 punctuation 비교

| 자료 | 요약 | 사용 위치 |
| --- | --- | --- |
| [SaT EMNLP version](https://aclanthology.org/2024.emnlp-main.665/) | SaT의 학회 버전 페이지다. | arXiv SaT 원문 보조 링크. |
| [wtpsplit README](https://github.com/segment-any-text/wtpsplit) | SaT/wtpsplit 모델과 런타임 사용법 확인용이다. | 구현 옵션 확인. |
| [Where's the Point?](https://aclanthology.org/2023.acl-long.398/) | punctuation이 없거나 불안정한 다국어 텍스트의 sentence segmentation을 다룬다. | punctuation-agnostic SBD 비교군. |
| [PySBD](https://arxiv.org/abs/2010.09657) | rule-based sentence boundary disambiguation 라이브러리 논문이다. | regex/rule-based SBD 비교군. 운영 기본 근거는 아니다. |
| [Streaming Punctuation 2023](https://arxiv.org/abs/2301.03819) | bidirectional context를 streaming punctuation에 활용하는 방법이다. | punctuation 보조 신호 비교. |
| [Online Punctuation Restoration using ELECTRA](https://www.isca-archive.org/interspeech_2023/polacek23_interspeech.html) | streaming ASR용 online punctuation restoration 자료다. | punctuation 모델 비교군. |
| [Weighted Lookahead Punctuation](https://arxiv.org/abs/2606.05179) | lookahead scoring으로 streaming punctuation을 개선하는 접근이다. | bounded right context 비교 후보. |
| [Punctuation Restoration for Singaporean Spoken Languages](https://arxiv.org/abs/2212.05356) | 영어, 말레이어, 중국어 구어 punctuation restoration을 다룬다. | 다국어 punctuation 비교. |
| [Small and Fast BERT for Chinese Medical Punctuation](https://arxiv.org/abs/2308.12568) | 중국어 medical domain punctuation restoration 경량 모델이다. | 중국어 punctuation 특화 비교. |

### Speech translation segmentation와 long-form segmentation 비교

이 묶음은 현재 파이프라인의 필수 구현 근거가 아니다. translation 또는 lecture speech에서 segmentation이 별도 문제라는 배경을 설명할 때만 제한적으로 쓴다.

| 자료 | 요약 | 사용 위치 |
| --- | --- | --- |
| [Speech Segmentation Optimization using Segmented Bilingual Speech Corpus](https://www.isca-archive.org/interspeech_2022/fukuda22b_interspeech.pdf) | speech translation에서 segmentation 단위가 번역 품질에 영향을 준다는 자료다. | final-only 번역 sink의 배경 비교. |
| [Dynamic Boundary Detection for Speech Translation](https://www.apsipa.org/proceedings/2017/CONTENTS/papers2017/13DecWednesday/Poster%202/WP-P2.20.pdf) | speech translation에서 pause 기반 경계의 한계와 dynamic boundary를 다룬다. | pause/VAD를 핵심 근거로 쓰지 않기 위한 비교. |
| [Dynamic Sentence Boundary Detection for Simultaneous Translation](https://aclanthology.org/2020.autosimtrans-1.1.pdf) | simultaneous translation에서 문장 경계를 동적으로 예측한다. | 동시 번역 비교군. |
| [Multi-pass sentence-end detection of lecture speech](https://www.isca-archive.org/interspeech_2014/hasan14_interspeech.pdf) | lecture speech의 sentence-end detection을 다룬다. | 발표형 긴 발화의 경계 검출 배경. |
| [Enriching Speech Recognition with Sentence Boundaries and Disfluencies](https://www.sri.com/wp-content/uploads/2021/12/enriching_speech_recognition_with_automatic.pdf) | ASR 출력에 sentence boundary와 disfluency detection을 결합한다. | ASR 후처리 비교군. |
| [Prosody-Based Automatic Segmentation](https://www.sri.com/wp-content/uploads/2021/12/prosody-based_automatic_segmentation_of_speech_into_sente.pdf) | prosody 기반 sentence/topic segmentation 자료다. | 현재는 prosody/VAD 미사용이므로 범위 밖 비교. |
| [Don't Discard Fixed-Window Audio Segmentation](https://aclanthology.org/2022.wmt-1.13.pdf) | speech-to-text translation에서 fixed-window audio segmentation이 여전히 유효할 수 있음을 보인다. | fixed window 전략 비교. |
| [Long-Form Speech Translation through Segmentation](https://aclanthology.org/2023.findings-emnlp.19.pdf) | LLM 제약 기반 long-form speech translation segmentation을 다룬다. | long-form ST/LLM 비교 후보. |

### 평가 지표와 streaming stability

| 자료 | 요약 | 사용 위치 |
| --- | --- | --- |
| [NIST SCTK](https://github.com/usnistgov/SCTK) | WER 등 ASR scoring 도구다. | 정답 전사 코퍼스가 준비될 때의 보조 평가 도구. |
| [Assessing Latency in ASR Systems](https://arxiv.org/abs/2409.05674) | real-time ASR latency 측정 방법론을 논의한다. | 지연 측정 설계 비교. |
| [Dynamic Latency for CTC-Based Streaming ASR](https://arxiv.org/abs/2203.15613) | Emformer/CTC streaming ASR의 dynamic latency를 다룬다. | native streaming latency 비교. |
| [Benchmarking LF-MMI, CTC and RNN-T](https://arxiv.org/abs/2011.04785) | streaming ASR criterion별 성능/지연 비교 자료다. | ASR 모델 구조 비교. |
| [e-WER2](https://arxiv.org/abs/2008.03403) | ASR output 없이 WER를 추정하는 방법이다. | 제한적 품질 추정 비교군. 현재 벤치의 핵심 지표는 아니다. |
| [BERTScore for Disordered Speech ASR](https://arxiv.org/abs/2209.10591) | WER 외 의미 기반 품질 평가 가능성을 다룬다. | final similarity 계열 지표의 배경 비교. |
| [Streaming E2E On-Device ASR Stability](https://www.isca-archive.org/interspeech_2020/shangguan20_interspeech.pdf) | partial hypothesis instability를 word/segment 수준에서 계측하고 stable partial 개념을 다룬다. | staged/final stability 지표 비교. |

### 번역 모델 비교

| 자료 | 요약 | 사용 위치 |
| --- | --- | --- |
| [NLLB distilled 600M Model Card](https://huggingface.co/facebook/nllb-200-distilled-600M) | 현재 기본 후보의 모델 사용 조건 확인용이다. | 구현/라이선스 확인. |
| [NLLB distilled 1.3B Model Card](https://huggingface.co/facebook/nllb-200-distilled-1.3B) | 더 큰 distilled NLLB 후보의 조건 확인용이다. | 품질/VRAM 비교 후보. |
| [NLLB 3.3B Model Card](https://huggingface.co/facebook/nllb-200-3.3B) | 큰 NLLB 모델 도입 비용 확인용이다. | 후속 번역 품질 비교. |
| [M2M100](https://arxiv.org/abs/2010.11125) | 영어 중심 우회 없이 many-to-many multilingual translation을 목표로 한다. | NLLB 외 번역 backend 비교. |
| [m2m100_1.2B Model Card](https://huggingface.co/facebook/m2m100_1.2B) | M2M100 모델 사용 조건 확인용이다. | backend 후보 확인. |
| [SeamlessM4T](https://arxiv.org/abs/2308.11596) | speech/text translation을 함께 다루는 multilingual/multimodal translation 모델이다. | speech translation backend 후속 후보. |
| [Seamless](https://arxiv.org/abs/2312.05187) | multilingual expressive and streaming speech translation 방향의 자료다. | streaming speech translation 비교. 현재 final-only text translation 계약의 근거는 아니다. |
| [seamless-m4t-v2-large Model Card](https://huggingface.co/facebook/seamless-m4t-v2-large) | 실제 모델 도입 조건과 비용 확인용이다. | backend 후보 확인. |
| [Tower](https://arxiv.org/abs/2402.17733) | translation-related task용 open multilingual LLM이다. | LLM 번역 후보 비교. |
| [TowerInstruct Model Card](https://huggingface.co/Unbabel/TowerInstruct-7B-v0.2) | TowerInstruct 사용 조건 확인용이다. | backend 후보 확인. |
| [X-ALMA](https://arxiv.org/abs/2410.03115) | plug-and-play module과 adaptive rejection을 쓰는 고품질 LLM 번역 계열이다. | 고품질 LLM 번역 후보. |
| [X-ALMA-13B-Group6 Model Card](https://huggingface.co/haoranxu/X-ALMA-13B-Group6) | 중국어/한국어 포함 그룹 모델 조건 확인용이다. | backend 후보 확인. |

## 제외 또는 직접 인용 금지

| 자료 | 판단 | 이유 |
| --- | --- | --- |
| [Optimizing Sentence Segmentation for Speech Translation](https://aclanthology.org/2002.iwslt-1.15.pdf) | 제외 | 링크된 PDF가 404로 원문을 확보하지 못했다. 원문 확보 전에는 인용하지 않는다. |
| [Real-time and Continuous Turn-taking Prediction Using VAP](https://arxiv.org/abs/2401.04868) | 직접 인용 금지 | 대화 turn-taking 예측 자료다. 현재 발표형 받아쓰기 pipeline의 필수 구현 근거가 아니다. |
| [Multilingual Turn-taking Prediction Using VAP](https://aclanthology.org/2024.lrec-main.1036/) | 직접 인용 금지 | 다국어 turn-taking 자료지만 현재 파이프라인에서 VAD/turn end 예측을 쓰지 않는다. |
| [Turn-Taking Prediction for Natural Conversational Speech](https://www.isca-archive.org/interspeech_2022/chang22_interspeech.pdf) | 직접 인용 금지 | 자연 대화 turn-taking 자료다. 발표형 긴 발화 SBD/finalization과 문제 설정이 다르다. |
| [TurnGPT](https://aclanthology.org/2021.findings-acl.205/) | 직접 인용 금지 | 대화 turn-taking language model이다. 현재 실험의 확정 누락/중복 판단 근거로 쓰지 않는다. |
| 모델 카드와 GitHub README 전반 | 학술 인용 금지 | 구현 가능성, 라이선스, 모델명, 지원 범위 확인용이다. 논문 핵심 주장 근거로 쓰지 않는다. |

## 논문 초안 반영 원칙

- 관련 연구 섹션의 핵심 인용은 직접 인용 가능 목록으로 제한한다.
- 비교군은 “대안 접근” 또는 “향후 후보”로만 쓴다.
- 제외 항목은 현재 논문 초안의 참고문헌에 넣지 않는다.
- 외부 논문은 일반 원칙과 분야 배경을 설명하고, 앱의 실제 성능 개선 여부는 반드시 실험일지와 벤치 결과로만 주장한다.
- 원문을 다시 확인하지 않은 문헌은 reference index에 남아 있더라도 논문 초안의 근거로 승격하지 않는다.
