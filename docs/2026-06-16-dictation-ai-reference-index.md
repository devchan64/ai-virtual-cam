# 받아쓰기 AI 참조 레퍼런스 모음

## 목적

이 문서는 받아쓰기 AI 설계, 실시간 전사/번역, 문장 경계 처리, 중국어 STT, 번역 백엔드, 품질 지표에 관련된 외부 논문과 모델 자료를 한곳에 모은다.

상세 설계 판단과 운영 실험 기록은 다음 문서를 함께 본다.

- [받아쓰기 AI 설계 및 실험 노트](2026-06-16-dictation-ai-design-experiment-notes.md)
- [받아쓰기 AI 실험일지](2026-06-16-dictation-ai-experiment-log.md)
- [받아쓰기 AI 계약과 기본값](2026-06-16-dictation-ai-contract-defaults.md)
- [다국어 실시간 음성 전사 리비전 인지 확정 계층 초안](paper/ko-revision-aware-realtime-stt.md)

## 실시간 Whisper / Streaming ASR

이 묶음은 Whisper 계열 오프라인 ASR을 실시간 또는 준실시간 전사 경로로 쓰기 위한 근거다. 받아쓰기 AI에서는 raw ASR 결과를 바로 final로 내보내지 않고, 여러 윈도우에서 안정적으로 재관측된 구간만 확정하는 `confirmed`/`hypothesis` 분리와 local agreement 정책의 근거로 사용한다.

- [Turning Whisper into Real-Time Transcription System](https://arxiv.org/abs/2307.14743): Whisper에 local agreement와 self-adaptive latency를 얹어 실시간 전사처럼 동작시키는 대표 기준선이다.
- [Whisper-Streaming: Turning Whisper into Real-Time Transcription System](https://aclanthology.org/2023.ijcnlp-demo.3/): 위 접근의 데모/시스템 관점 자료이며, 확정 prefix와 미확정 hypothesis 분리의 운영 근거로 본다.
- [Simul-Whisper](https://www.isca-archive.org/interspeech_2024/wang24ea_interspeech.pdf): 동시성 환경에서 지연과 안정성의 균형을 보는 참고 자료다.
- [WhisperKit](https://openreview.net/pdf?id=6lC3MPFbVg): 온디바이스 Whisper 실행과 streaming UX 적용성을 볼 때 참고한다.
- [Adapting Whisper for Streaming Speech Recognition via Two-Pass Decoding](https://arxiv.org/abs/2506.12154): 1차 빠른 가설과 2차 보정의 구조를 검토할 때 참고한다.
- [WhisperRT](https://arxiv.org/abs/2508.12301): Whisper 기반 저지연 실행 후보군 비교용으로 둔다.
- [WhisperPipe: A Resource-Efficient Streaming Architecture for Real-Time Automatic Speech Recognition](https://arxiv.org/abs/2604.25611): overlapping context window와 buffering 설계 비교용이다.
- [CarelessWhisper: Turning Whisper into a Causal Streaming Model](https://arxiv.org/abs/2508.12301): causal streaming 전환 접근과 한계를 검토할 때 본다.
- [Whisper: Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356): Whisper 자체의 원 모델 배경 자료다.
- [M2R-Whisper: Multi-stage and Multi-scale Retrieval Augmentation for Enhancing Whisper](https://arxiv.org/abs/2409.11889): Whisper 품질 보강 계열 후속 후보로 둔다.

## ASR 모델 / 툴킷

이 묶음은 Whisper 외의 ASR 구조와 툴킷을 비교하기 위한 자료다. 현재 운영 기본값을 곧바로 바꾸기 위한 목록이 아니라, 중국어/다국어 STT 품질이나 streaming native 모델을 재검토할 때 비교 축으로 사용한다.

- [Conformer: Convolution-augmented Transformer for Speech Recognition](https://arxiv.org/abs/2005.08100): modern ASR encoder 구조의 대표 참고 자료다.
- [wav2vec 2.0: A Framework for Self-Supervised Learning of Speech Representations](https://arxiv.org/abs/2006.11477): self-supervised speech representation 기반 ASR 계열의 배경 자료다.
- [RNN-Transducer: Sequence Modeling with RNN-T for Streaming ASR](https://arxiv.org/abs/1211.3711): streaming ASR의 고전적 기준 구조로, Whisper식 후처리와 다른 native streaming 접근 비교에 쓴다.
- [FunASR: A Fundamental End-to-End Speech Recognition Toolkit](https://arxiv.org/abs/2305.11013): 중국어/다국어 ASR 실험 후보였던 FunASR 계열의 시스템 자료다.
- [FunASR GitHub README](https://github.com/modelscope/FunASR): 실제 설치, 모델, streaming 지원 범위 확인용이다.
- [FunAudioLLM: Voice Understanding and Generation Foundation Models for Natural Interaction Between Humans and LLMs](https://arxiv.org/abs/2407.04051): SenseVoice 등 음성 이해 모델 계열의 배경 자료다.
- [SenseVoice GitHub README](https://github.com/FunAudioLLM/SenseVoice): SenseVoice 계열 모델 사용 가능성과 제약 확인용이다.
- [SenseVoiceSmall Hugging Face Model Card](https://huggingface.co/FunAudioLLM/SenseVoiceSmall): 경량 모델 후보의 입출력, 언어 지원, 라이선스 확인용이다.
- [WeNet: Production oriented Streaming and Non-streaming End-to-End Speech Recognition Toolkit](https://arxiv.org/abs/2102.01547): streaming/non-streaming E2E ASR 툴킷 비교군이다.
- [A Comparative Study of LLM-based ASR and Whisper in Low Resource and Code Switching Scenario](https://arxiv.org/abs/2412.00721): 저자원/코드스위칭 환경에서 Whisper와 LLM 기반 ASR를 비교할 때 참고한다.

## 중국어 / CJK STT와 오류 보정

이 묶음은 중국어 raw STT 품질, 고유명사/동음어 오류 검토용이다. 운영 판단에서는 STT 모델 품질과 revision lifecycle 품질을 분리해 보고, 언어별 정규식/접합 보정이 아니라 모델/백엔드 비교와 오류 계측을 우선한다.

Qwen3-ASR vLLM streaming, Dolphin-CN-Dialect, WeNet의 프로젝트 내 세부검증 판단은 [받아쓰기 AI 중국어 STT 후보 세부검증 리포트](2026-06-16-dictation-ai-chinese-stt-candidate-validation.md)에 둔다.

- [Qwen3-ASR Technical Report](https://arxiv.org/abs/2601.21337): 중국어 품질 우선 후보인 Qwen3-ASR 계열의 주요 기술 배경이다.
- [Qwen3-ASR-0.6B Hugging Face Model Card](https://huggingface.co/Qwen/Qwen3-ASR-0.6B): 현재 중국어 시작점 후보의 모델 카드다.
- [Qwen3-ASR-1.7B Hugging Face Model Card](https://huggingface.co/Qwen/Qwen3-ASR-1.7B): 더 큰 Qwen3-ASR 후보의 품질/성능 비교용이다.
- [Dolphin-CN-Dialect: Where Chinese Dialects Matter](https://arxiv.org/abs/2605.08961): 중국어 방언 대응 모델 후보를 추적할 때 본다.
- [FormalASR: End-to-End Spoken Chinese to Formal Text](https://arxiv.org/abs/2605.19266): 구어 중국어를 문서형 텍스트로 정규화하는 방향의 참고 자료다.
- [ASR-EC Benchmark: Evaluating Large Language Models on Chinese ASR Error Correction](https://arxiv.org/abs/2412.03075): 중국어 ASR error correction 평가 축을 볼 때 사용한다.
- [Large Language Model Should Understand Pinyin for Chinese ASR Error Correction](https://arxiv.org/abs/2409.13262): pinyin 정보를 활용한 중국어 오류 보정 가능성을 검토한다.
- [Pinyin Regularization in Error Correction for Chinese Speech Recognition with Large Language Models](https://arxiv.org/abs/2407.01909): 동음어/발음 기반 오류 보정 후보군이다.
- [Full-text Error Correction for Chinese Speech Recognition with Large Language Model](https://arxiv.org/abs/2409.07790): 전체 전사 텍스트 단위 보정 접근의 참고 자료다.
- [PARCO: Phoneme-Augmented Robust Contextual ASR via Contrastive Entity Disambiguation](https://arxiv.org/abs/2509.04357): 발음 정보와 entity disambiguation을 결합한 contextual ASR 후보군이다.
- [PAC: Pronunciation-Aware Contextualized Large Language Model-based Automatic Speech Recognition](https://arxiv.org/abs/2509.12647): pronunciation-aware contextual ASR 접근을 검토할 때 둔다.

## 문장 경계 / 세그먼테이션 / Punctuation

이 묶음은 regex 기반 문장 분할을 운영 경로에서 폐기하고, 다국어 모델 기반 SBD와 bounded lookahead punctuation을 우선하는 근거다. 받아쓰기 AI에서는 SBD 결과를 즉시 final로 쓰지 않고 staged 후보 생성과 재관측 확인의 입력으로만 사용한다.

- [Segment Any Text: A Universal Approach for Robust, Efficient and Adaptable Sentence Segmentation](https://arxiv.org/abs/2406.16678): SaT 계열 문장 분절 모델의 주요 참고 자료다.
- [Segment Any Text: A Universal Approach for Robust, Efficient and Adaptable Sentence Segmentation](https://aclanthology.org/2024.emnlp-main.665/): SaT의 학회 버전 링크다.
- [wtpsplit GitHub README](https://github.com/segment-any-text/wtpsplit): SaT/wtpsplit 런타임 사용법과 모델 옵션 확인용이다.
- [Where's the Point? Self-Supervised Multilingual Punctuation-Agnostic Sentence Segmentation](https://aclanthology.org/2023.acl-long.398/): punctuation이 없거나 불안정한 텍스트의 다국어 분절 근거다.
- [PySBD: Pragmatic Sentence Boundary Disambiguation](https://arxiv.org/abs/2010.09657): rule-based SBD 비교군으로 둔다.
- [Streaming Punctuation: A Novel Punctuation Technique Leveraging Bidirectional Context for Continuous Speech Recognition](https://arxiv.org/abs/2301.03819): streaming ASR에서 문장부호를 경계 score 보조 신호로 쓰는 근거다.
- [Streaming Punctuation for Long-form Dictation with Transformers](https://arxiv.org/abs/2210.05756): 긴 받아쓰기에서 lookahead와 지연의 균형을 볼 때 참고한다.
- [Online Punctuation Restoration using ELECTRA Model for streaming ASR Systems](https://www.isca-archive.org/interspeech_2023/polacek23_interspeech.html): online punctuation restoration 모델 비교군이다.
- [Efficient Punctuation Restoration via Weighted Lookahead Scoring Method for Streaming ASR Systems](https://arxiv.org/abs/2606.05179): weighted lookahead 기반 punctuation 후보군이다.
- [Punctuation Restoration for Singaporean Spoken Languages: English, Malay, and Mandarin](https://arxiv.org/abs/2212.05356): 영어/중국어가 섞이는 구어 punctuation 복원 참고 자료다.
- [A Small and Fast BERT for Chinese Medical Punctuation Restoration](https://arxiv.org/abs/2308.12568): 중국어 punctuation restoration 경량 모델 참고 자료다.

## Speech Translation 세그먼테이션 / VAD 비교군

이 묶음은 프레젠테이션 긴 발화에서 VAD나 pause 기반 segmentation을 운영 구현 목표에서 제외하는 근거다. final 결정은 텍스트 안정성, SBD, punctuation/right context, 중복 억제, revision lifecycle을 결합한다.

- [Speech Segmentation Optimization using Segmented Bilingual Speech Corpus for End-to-end Speech Translation](https://www.isca-archive.org/interspeech_2022/fukuda22b_interspeech.pdf): speech translation에서 segmentation 품질이 번역에 미치는 영향을 보는 기준 자료다.
- [Dynamic Boundary Detection for Speech Translation](https://www.apsipa.org/proceedings/2017/CONTENTS/papers2017/13DecWednesday/Poster%202/WP-P2.20.pdf): pause 기반 경계의 한계와 dynamic boundary 판단을 검토할 때 사용한다.
- [Dynamic Sentence Boundary Detection for Simultaneous Translation](https://aclanthology.org/2020.autosimtrans-1.1.pdf): 동시 번역에서 sentence boundary를 동적으로 잡는 접근이다.
- [Multi-pass sentence-end detection of lecture speech](https://www.isca-archive.org/interspeech_2014/hasan14_interspeech.pdf): lecture speech처럼 긴 발화에서 sentence-end detection이 별도 문제임을 보여준다.
- [Enriching Speech Recognition with Automatic Detection of Sentence Boundaries and Disfluencies](https://www.sri.com/wp-content/uploads/2021/12/enriching_speech_recognition_with_automatic.pdf): sentence boundary와 disfluency detection을 ASR 후처리로 결합하는 배경 자료다.
- [Prosody-Based Automatic Segmentation of Speech into Sentences and Topics](https://www.sri.com/wp-content/uploads/2021/12/prosody-based_automatic_segmentation_of_speech_into_sente.pdf): prosody 기반 segmentation을 보조 신호로 볼 때 참고한다.
- [Optimizing Sentence Segmentation for Speech Translation](https://aclanthology.org/2002.iwslt-1.15.pdf): 번역 품질 관점에서 sentence segmentation 최적화를 다룬 초기 자료다.
- [Don't Discard Fixed-Window Audio Segmentation in Speech-to-Text Translation](https://aclanthology.org/2022.wmt-1.13.pdf): fixed-window segmentation이 항상 폐기 대상은 아니라는 비교군이다.
- [Long-Form Speech Translation through Segmentation with Finite-State Decoding Constraints on Large Language Models](https://aclanthology.org/2023.findings-emnlp.19.pdf): long-form speech translation에서 LLM 제약 기반 segmentation을 보는 후속 후보군이다.

## Turn-taking / 발화 종료 보조 신호

이 묶음은 대화형 turn end 예측을 프레젠테이션 받아쓰기 운영 경로에서 제외하는 근거다. 발표형 긴 발화는 대화 turn-taking과 다르므로, VAP/TurnGPT 계열은 구현 후보가 아니라 비교군으로만 분류한다.

- [Real-time and Continuous Turn-taking Prediction Using Voice Activity Projection](https://arxiv.org/abs/2401.04868): VAP 기반 실시간 turn-taking prediction의 대표 자료다.
- [Multilingual Turn-taking Prediction Using Voice Activity Projection](https://aclanthology.org/2024.lrec-main.1036/): 다국어 turn-taking prediction 적용성을 볼 때 참고한다.
- [Turn-Taking Prediction for Natural Conversational Speech](https://www.isca-archive.org/interspeech_2022/chang22_interspeech.pdf): 자연 대화의 turn-taking 예측 비교군이다.
- [TurnGPT: a Transformer-based Language Model for Predicting Turn-taking in Spoken Dialog](https://aclanthology.org/2021.findings-acl.205/): 텍스트/언어모델 기반 turn-taking 예측 후보군이다.

## 평가 지표 / Latency / Scoring

이 묶음은 받아쓰기 AI의 품질을 unittest 성공/실패가 아니라 STT 품질, finalization latency, revision instability, duplicate insertion, translation quality로 분리 계측하는 근거다. 현재 추적 테스트의 `revision`, `distinct`, `collapse`, `runtime_metrics`, `translation_quality` 같은 지표를 해석할 때 참고한다.

- [NIST SCTK, the NIST Scoring Toolkit](https://github.com/usnistgov/SCTK): WER 등 표준 ASR scoring 도구 참고용이다.
- [Assessing Latency in ASR Systems: A Methodological Perspective for Real-Time Use](https://arxiv.org/abs/2409.05674): 실시간 ASR latency 측정 방법론을 정리할 때 본다.
- [Dynamic Latency for CTC-Based Streaming Automatic Speech Recognition With Emformer](https://arxiv.org/abs/2203.15613): dynamic latency와 streaming ASR trade-off 비교군이다.
- [Benchmarking LF-MMI, CTC and RNN-T Criteria for Streaming ASR](https://arxiv.org/abs/2011.04785): streaming ASR criterion별 비교 자료다.
- [Evaluating Automatic Speech Recognition in an Incremental Setting](https://arxiv.org/abs/2302.12049): incremental ASR 환경의 평가 관점을 제공한다.
- [Word Error Rate Estimation Without ASR Output: e-WER2](https://arxiv.org/abs/2008.03403): 정답/출력 조건이 제한적인 품질 추정 참고 자료다.
- [Assessing ASR Model Quality on Disordered Speech using BERTScore](https://arxiv.org/abs/2209.10591): WER 외 의미 기반 품질 평가 가능성을 볼 때 참고한다.
- [Analyzing the Quality and Stability of a Streaming End-to-End On-Device Speech Recognizer](https://www.isca-archive.org/interspeech_2020/shangguan20_interspeech.pdf): streaming 출력 안정성 지표인 UPWR/UPSR 계열을 참고한다.

## 번역 모델 / 백엔드

이 묶음은 final transcript만 번역 큐에 넣는 정책과, 중국어-한국어 번역 품질 병목을 STT/확정 품질과 분리 평가하기 위한 자료다. 현재 기본 후보는 NLLB 600M이며, 품질 개선은 문자열 휴리스틱보다 모델/백엔드 비교와 회귀 샘플 확장으로 진행한다.

- [No Language Left Behind: Scaling Human-Centered Machine Translation](https://arxiv.org/abs/2207.04672): NLLB 계열 번역 모델의 원 논문이다.
- [facebook/nllb-200-distilled-600M Model Card](https://huggingface.co/facebook/nllb-200-distilled-600M): 현재 실시간 기본 번역 후보의 모델 카드다.
- [facebook/nllb-200-distilled-1.3B Model Card](https://huggingface.co/facebook/nllb-200-distilled-1.3B): 같은 NLLB 계열에서 품질 향상 후보로 둔다.
- [facebook/nllb-200-3.3B Model Card](https://huggingface.co/facebook/nllb-200-3.3B): 더 큰 NLLB 비교군이며 VRAM/지연 비용 확인이 필요하다.
- [Beyond English-Centric Multilingual Machine Translation](https://arxiv.org/abs/2010.11125): M2M100 계열의 배경 자료다.
- [facebook/m2m100_1.2B Model Card](https://huggingface.co/facebook/m2m100_1.2B): 영어 중심 우회가 아닌 many-to-many 번역 비교 후보로 둔다.
- [SeamlessM4T: Massively Multilingual & Multimodal Machine Translation](https://arxiv.org/abs/2308.11596): speech/text translation을 함께 다루는 후속 후보군이다.
- [Seamless: Multilingual Expressive and Streaming Speech Translation](https://arxiv.org/abs/2312.05187): streaming speech translation 방향을 볼 때 참고한다.
- [facebook/seamless-m4t-v2-large Model Card](https://huggingface.co/facebook/seamless-m4t-v2-large): SeamlessM4T v2 large 모델의 실제 도입 비용 확인용이다.
- [Tower: An Open Multilingual Large Language Model for Translation-Related Tasks](https://arxiv.org/abs/2402.17733): LLM 기반 번역 후보군의 배경 자료다.
- [Unbabel/TowerInstruct-7B-v0.2 Model Card](https://huggingface.co/Unbabel/TowerInstruct-7B-v0.2): TowerInstruct 모델 도입 가능성 확인용이다.
- [X-ALMA: Plug & Play Modules and Adaptive Rejection for Quality Translation at Scale](https://arxiv.org/abs/2410.03115): 고품질 LLM 번역 후보군이다.
- [haoranxu/X-ALMA-13B-Group6 Model Card](https://huggingface.co/haoranxu/X-ALMA-13B-Group6): 중국어/한국어 포함 그룹의 모델 카드 확인용이다.
