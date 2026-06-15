# 받아쓰기 AI 참조 레퍼런스 모음

## 목적

이 문서는 받아쓰기 AI 설계, 실시간 전사/번역, 문장 경계 처리, 중국어 STT, 번역 백엔드, 품질 지표에 관련된 외부 논문과 모델 자료를 한곳에 모은다.

상세 설계 판단은 다음 문서를 함께 본다.

- [받아쓰기 AI 기능 설계](2026-06-13-dictation-ai-feature-design.md)
- [프레젠테이션 실시간 전사/번역 세그먼트 설계 참고](2026-06-15-presentation-dictation-segmentation-references.md)
- [다국어 실시간 음성 전사 리비전 인지 확정 계층 초안](paper/ko-revision-aware-realtime-stt.md)

## 실시간 Whisper / Streaming ASR

- [Turning Whisper into Real-Time Transcription System](https://arxiv.org/abs/2307.14743)
- [Whisper-Streaming: Turning Whisper into Real-Time Transcription System](https://aclanthology.org/2023.ijcnlp-demo.3/)
- [Simul-Whisper](https://www.isca-archive.org/interspeech_2024/wang24ea_interspeech.pdf)
- [WhisperKit](https://openreview.net/pdf?id=6lC3MPFbVg)
- [Adapting Whisper for Streaming Speech Recognition via Two-Pass Decoding](https://arxiv.org/abs/2506.12154)
- [WhisperRT](https://arxiv.org/abs/2508.12301)
- [WhisperPipe: A Resource-Efficient Streaming Architecture for Real-Time Automatic Speech Recognition](https://arxiv.org/abs/2604.25611)
- [CarelessWhisper: Turning Whisper into a Causal Streaming Model](https://arxiv.org/abs/2508.12301)
- [Whisper: Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356)
- [M2R-Whisper: Multi-stage and Multi-scale Retrieval Augmentation for Enhancing Whisper](https://arxiv.org/abs/2409.11889)

## ASR 모델 / 툴킷

- [Conformer: Convolution-augmented Transformer for Speech Recognition](https://arxiv.org/abs/2005.08100)
- [wav2vec 2.0: A Framework for Self-Supervised Learning of Speech Representations](https://arxiv.org/abs/2006.11477)
- [RNN-Transducer: Sequence Modeling with RNN-T for Streaming ASR](https://arxiv.org/abs/1211.3711)
- [FunASR: A Fundamental End-to-End Speech Recognition Toolkit](https://arxiv.org/abs/2305.11013)
- [FunASR GitHub README](https://github.com/modelscope/FunASR)
- [FunAudioLLM: Voice Understanding and Generation Foundation Models for Natural Interaction Between Humans and LLMs](https://arxiv.org/abs/2407.04051)
- [SenseVoice GitHub README](https://github.com/FunAudioLLM/SenseVoice)
- [SenseVoiceSmall Hugging Face Model Card](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)
- [WeNet: Production oriented Streaming and Non-streaming End-to-End Speech Recognition Toolkit](https://arxiv.org/abs/2102.01547)
- [A Comparative Study of LLM-based ASR and Whisper in Low Resource and Code Switching Scenario](https://arxiv.org/abs/2412.00721)

## 중국어 / CJK STT와 오류 보정

- [Qwen3-ASR Technical Report](https://arxiv.org/abs/2601.21337)
- [Qwen3-ASR-0.6B Hugging Face Model Card](https://huggingface.co/Qwen/Qwen3-ASR-0.6B)
- [Qwen3-ASR-1.7B Hugging Face Model Card](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)
- [Dolphin-CN-Dialect: Where Chinese Dialects Matter](https://arxiv.org/abs/2605.08961)
- [FormalASR: End-to-End Spoken Chinese to Formal Text](https://arxiv.org/abs/2605.19266)
- [ASR-EC Benchmark: Evaluating Large Language Models on Chinese ASR Error Correction](https://arxiv.org/abs/2412.03075)
- [Large Language Model Should Understand Pinyin for Chinese ASR Error Correction](https://arxiv.org/abs/2409.13262)
- [Pinyin Regularization in Error Correction for Chinese Speech Recognition with Large Language Models](https://arxiv.org/abs/2407.01909)
- [Full-text Error Correction for Chinese Speech Recognition with Large Language Model](https://arxiv.org/abs/2409.07790)
- [PARCO: Phoneme-Augmented Robust Contextual ASR via Contrastive Entity Disambiguation](https://arxiv.org/abs/2509.04357)
- [PAC: Pronunciation-Aware Contextualized Large Language Model-based Automatic Speech Recognition](https://arxiv.org/abs/2509.12647)

## 문장 경계 / 세그먼테이션 / Punctuation

- [Segment Any Text: A Universal Approach for Robust, Efficient and Adaptable Sentence Segmentation](https://arxiv.org/abs/2406.16678)
- [Segment Any Text: A Universal Approach for Robust, Efficient and Adaptable Sentence Segmentation](https://aclanthology.org/2024.emnlp-main.665/)
- [wtpsplit GitHub README](https://github.com/segment-any-text/wtpsplit)
- [Where's the Point? Self-Supervised Multilingual Punctuation-Agnostic Sentence Segmentation](https://aclanthology.org/2023.acl-long.398/)
- [PySBD: Pragmatic Sentence Boundary Disambiguation](https://arxiv.org/abs/2010.09657)
- [Streaming Punctuation: A Novel Punctuation Technique Leveraging Bidirectional Context for Continuous Speech Recognition](https://arxiv.org/abs/2301.03819)
- [Streaming Punctuation for Long-form Dictation with Transformers](https://arxiv.org/abs/2210.05756)
- [Online Punctuation Restoration using ELECTRA Model for streaming ASR Systems](https://www.isca-archive.org/interspeech_2023/polacek23_interspeech.html)
- [Efficient Punctuation Restoration via Weighted Lookahead Scoring Method for Streaming ASR Systems](https://arxiv.org/abs/2606.05179)
- [Punctuation Restoration for Singaporean Spoken Languages: English, Malay, and Mandarin](https://arxiv.org/abs/2212.05356)
- [A Small and Fast BERT for Chinese Medical Punctuation Restoration](https://arxiv.org/abs/2308.12568)

## Speech Translation 세그먼테이션 / VAD 비교군

- [Speech Segmentation Optimization using Segmented Bilingual Speech Corpus for End-to-end Speech Translation](https://www.isca-archive.org/interspeech_2022/fukuda22b_interspeech.pdf)
- [Dynamic Boundary Detection for Speech Translation](https://www.apsipa.org/proceedings/2017/CONTENTS/papers2017/13DecWednesday/Poster%202/WP-P2.20.pdf)
- [Dynamic Sentence Boundary Detection for Simultaneous Translation](https://aclanthology.org/2020.autosimtrans-1.1.pdf)
- [Multi-pass sentence-end detection of lecture speech](https://www.isca-archive.org/interspeech_2014/hasan14_interspeech.pdf)
- [Enriching Speech Recognition with Automatic Detection of Sentence Boundaries and Disfluencies](https://www.sri.com/wp-content/uploads/2021/12/enriching_speech_recognition_with_automatic.pdf)
- [Prosody-Based Automatic Segmentation of Speech into Sentences and Topics](https://www.sri.com/wp-content/uploads/2021/12/prosody-based_automatic_segmentation_of_speech_into_sente.pdf)
- [Optimizing Sentence Segmentation for Speech Translation](https://aclanthology.org/2002.iwslt-1.15.pdf)
- [Don't Discard Fixed-Window Audio Segmentation in Speech-to-Text Translation](https://aclanthology.org/2022.wmt-1.13.pdf)
- [Long-Form Speech Translation through Segmentation with Finite-State Decoding Constraints on Large Language Models](https://aclanthology.org/2023.findings-emnlp.19.pdf)

## Turn-taking / 발화 종료 보조 신호

- [Real-time and Continuous Turn-taking Prediction Using Voice Activity Projection](https://arxiv.org/abs/2401.04868)
- [Multilingual Turn-taking Prediction Using Voice Activity Projection](https://aclanthology.org/2024.lrec-main.1036/)
- [Turn-Taking Prediction for Natural Conversational Speech](https://www.isca-archive.org/interspeech_2022/chang22_interspeech.pdf)
- [TurnGPT: a Transformer-based Language Model for Predicting Turn-taking in Spoken Dialog](https://aclanthology.org/2021.findings-acl.205/)

## 평가 지표 / Latency / Scoring

- [NIST SCTK, the NIST Scoring Toolkit](https://github.com/usnistgov/SCTK)
- [Assessing Latency in ASR Systems: A Methodological Perspective for Real-Time Use](https://arxiv.org/abs/2409.05674)
- [Dynamic Latency for CTC-Based Streaming Automatic Speech Recognition With Emformer](https://arxiv.org/abs/2203.15613)
- [Benchmarking LF-MMI, CTC and RNN-T Criteria for Streaming ASR](https://arxiv.org/abs/2011.04785)
- [Evaluating Automatic Speech Recognition in an Incremental Setting](https://arxiv.org/abs/2302.12049)
- [Word Error Rate Estimation Without ASR Output: e-WER2](https://arxiv.org/abs/2008.03403)
- [Assessing ASR Model Quality on Disordered Speech using BERTScore](https://arxiv.org/abs/2209.10591)
- [Analyzing the Quality and Stability of a Streaming End-to-End On-Device Speech Recognizer](https://www.isca-archive.org/interspeech_2020/shangguan20_interspeech.pdf)

## 번역 모델 / 백엔드

- [No Language Left Behind: Scaling Human-Centered Machine Translation](https://arxiv.org/abs/2207.04672)
- [facebook/nllb-200-distilled-600M Model Card](https://huggingface.co/facebook/nllb-200-distilled-600M)
- [facebook/nllb-200-distilled-1.3B Model Card](https://huggingface.co/facebook/nllb-200-distilled-1.3B)
- [facebook/nllb-200-3.3B Model Card](https://huggingface.co/facebook/nllb-200-3.3B)
- [Beyond English-Centric Multilingual Machine Translation](https://arxiv.org/abs/2010.11125)
- [facebook/m2m100_1.2B Model Card](https://huggingface.co/facebook/m2m100_1.2B)
- [SeamlessM4T: Massively Multilingual & Multimodal Machine Translation](https://arxiv.org/abs/2308.11596)
- [Seamless: Multilingual Expressive and Streaming Speech Translation](https://arxiv.org/abs/2312.05187)
- [facebook/seamless-m4t-v2-large Model Card](https://huggingface.co/facebook/seamless-m4t-v2-large)
- [Tower: An Open Multilingual Large Language Model for Translation-Related Tasks](https://arxiv.org/abs/2402.17733)
- [Unbabel/TowerInstruct-7B-v0.2 Model Card](https://huggingface.co/Unbabel/TowerInstruct-7B-v0.2)
- [X-ALMA: Plug & Play Modules and Adaptive Rejection for Quality Translation at Scale](https://arxiv.org/abs/2410.03115)
- [haoranxu/X-ALMA-13B-Group6 Model Card](https://huggingface.co/haoranxu/X-ALMA-13B-Group6)
