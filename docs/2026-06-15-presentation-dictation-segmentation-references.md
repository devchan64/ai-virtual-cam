# 프레젠테이션 실시간 전사/번역 세그먼트 설계 참고 문헌

## 목적

이 문서는 실시간 프리젠테이션 발표용 받아쓰기 AI와 실시간 번역 기능을 통합하기 위한 문장/세그먼트 구분 설계 근거를 정리한다. 목표는 긴 발화의 raw ASR 결과에서 번역 가능한 유효 세그먼트를 찾고, STT 결과가 다음 윈도우에서 수정되는 상황에서도 중복 final, premature translation, 긴 pending overrun을 줄이는 것이다.

## 핵심 판단

- VAD는 음성/비음성 구간을 찾는 데 유용하지만, 프레젠테이션의 긴 발화에서 번역 단위 또는 문장 경계를 직접 결정하는 주 신호로 쓰기에는 적합하지 않다.
- 세그먼트 결정은 ASR 텍스트, SaT/SBD 모델, streaming punctuation, 토큰/문자 비교 기반 local agreement, 세그먼트 상태관리의 결합으로 수행한다.
- VAD/무음 길이/발화 종료 예측은 세그먼트 final score에 작은 가중치로 들어가는 보조 feature로 제한한다.
- 실시간 번역은 final 세그먼트만 대상으로 하고, staged/partial 세그먼트는 다음 ASR 윈도우에서 수정될 수 있으므로 번역 큐에 넣지 않는다.

## 왜 VAD만으로 세그먼트를 결정하지 않는가

Fukuda et al.은 long speech를 speech translation에 넣기 위해 segmentation이 필수라고 설명하면서도, WebRTC VAD 같은 pause-based segmentation은 흔하지만 pause가 sentence boundary와 반드시 일치하지 않고, 매우 짧은 pause로 연결된 문장은 VAD가 탐지하기 어렵다고 지적한다. 따라서 VAD는 세그먼트 후보 생성에는 참고할 수 있어도 번역 단위 확정의 단독 기준이 될 수 없다.

Zhou et al.의 simultaneous translation용 dynamic sentence boundary 연구도 prosodic pause 기반 segmentation은 대화처럼 명확한 silence가 있는 상황에서는 유효할 수 있지만, lecture 같은 long speech audio에서는 잘 동작하지 않는다고 정리한다. 프레젠테이션 발표는 이 lecture scenario에 가깝기 때문에, VAD 기반 chunking을 운영 경로의 주 segmentation 정책으로 쓰지 않는다.

Hasan et al.은 lecture transcripts의 sentence-end detection을 별도 문제로 다루며, 강의 발화에서 sentence end를 자동 탐지하려면 단순 무음 구간이 아니라 domain과 punctuation/lexical cue를 고려해야 함을 보여준다. Liu et al.도 sentence boundary detection에서 prosody가 유용한 보조 정보가 될 수 있지만 lexical/syntactic information과 함께 써야 함을 논의한다. 즉, 음향 cue는 단독 결정자가 아니라 텍스트 기반 SBD를 보강하는 feature다.

## 제안 파이프라인

```text
오디오 입력
  ↓
ASR
  - faster-whisper / Qwen3-ASR 등
  - sliding window raw transcript 생성
  ↓
정규화 및 접합
  - 이전 pending tail과 새 raw의 overlap 비교
  - CJK no-space 구간은 문자 n-gram/prefix overlap 비교
  - 최근 final echo 억제
  ↓
SBD / SaT
  - Segment Any Text / wtpsplit 기반 다국어 문장 경계 후보
  - 문장부호가 없는 ASR raw에서도 boundary 후보 생성
  ↓
Streaming punctuation
  - period/question/comma probability를 boundary score에 추가
  - free-form rewrite가 아니라 token boundary scoring 방식 우선
  ↓
세그먼트 상태관리
  - pending: 아직 미완성 tail
  - staged: 완료 후보이나 재확인 필요
  - final: 번역/복사용 출력 대상
  - suppressed: 최근 final echo 또는 중복 후보
  - revised: 다음 ASR 윈도우에서 교체된 후보
  ↓
실시간 번역
  - final 세그먼트만 번역 큐에 투입
```

## 운영 흐름 요약

프레젠테이션 실시간 전사/번역의 핵심 흐름은 다음 네 단계로 단순화한다.

```text
Streaming ASR
  ↓
Stable Token Detection
  ↓
Semantic Boundary Detection
  ↓
Translation Trigger
```

- `Streaming ASR`: 오디오 슬라이딩 윈도우에서 raw transcript를 계속 생성한다. 이 단계의 출력은 다음 윈도우에서 수정될 수 있으므로 화면/번역용 final로 직접 사용하지 않는다.
- `Stable Token Detection`: 여러 ASR 윈도우 사이에서 유지되는 토큰/문자 구간을 찾는다. 영어/한국어는 토큰 similarity와 문자 similarity를 함께 보고, CJK는 문자 n-gram과 prefix/suffix overlap을 우선한다. 이 단계는 Whisper-Streaming 계열의 local agreement를 세그먼트 단위로 확장한 역할을 한다.
- `Semantic Boundary Detection`: 안정 토큰 구간 위에서 SaT/SBD, streaming punctuation, right context를 결합해 의미적으로 완료된 세그먼트 후보를 찾는다. VAD는 여기서 주 결정자가 아니라 pause/silence 보조 feature로만 사용한다.
- `Translation Trigger`: semantic boundary 후보가 staged 상태에서 충분히 재관측되고 최근 final echo가 아니면 final로 승격한다. 번역은 이 final 세그먼트가 발생했을 때만 시작한다.

이 흐름에서는 “음성이 멈췄는가”보다 “토큰이 안정되었는가”와 “의미 경계가 확인되었는가”가 먼저다. 따라서 VAD는 Translation Trigger를 직접 발생시키지 않고, Semantic Boundary Detection의 confidence를 보정하는 보조 신호로 제한한다.

## 주요 키워드별 설계 메모

### ASR

ASR은 raw transcript 후보를 제공하지만, 실시간 슬라이딩 윈도우에서는 같은 발화가 다음 윈도우에서 다시 쓰이거나 수정된다. 따라서 ASR 출력의 문장부호와 segment boundary를 그대로 final로 신뢰하지 않는다. Whisper-Streaming 계열의 local agreement policy처럼 여러 윈도우에서 안정적으로 유지되는 prefix/segment를 확정하는 계층이 필요하다.

### SaT / SBD

Segment Any Text(SaT)는 문장부호가 없거나 noisy한 텍스트에서도 robust sentence segmentation을 목표로 하는 다국어 SBD 모델이다. 프레젠테이션 전사에서는 SaT/wtpsplit을 문장 경계 후보 생성 baseline으로 사용하고, 마지막 segment는 기본적으로 pending으로 보수 처리한다.

### Streaming punctuation

Streaming punctuation은 raw ASR의 readability와 boundary score를 개선한다. 긴 받아쓰기에서는 미래 문맥을 너무 적게 보면 마침표를 늦게 또는 잘못 찍고, 너무 오래 기다리면 final latency가 커진다. 따라서 dynamic decoding window와 bounded lookahead 방식이 적합하다. LLM free-form generation은 원문 rewrite와 alignment 붕괴 위험이 있으므로, token boundary별 punctuation/scoring 방식이 우선이다.

### 토큰 비교와 local agreement

세그먼트 final 여부는 단일 chunk의 SBD 결과가 아니라 여러 ASR window에서 같은 후보가 유지되는지로 판단한다.

- 영어/한국어: 토큰 similarity와 문자 similarity를 함께 비교한다.
- 중국어/CJK: 공백 기반 토큰이 약하므로 문자 n-gram, prefix/suffix overlap, 내부 prefix overlap을 우선한다.
- 최근 final과 높은 유사도를 보이는 후보는 echo로 보고 suppressed 상태로 이동한다.

### 세그먼트의 구분

세그먼트는 번역 가능한 의미 단위여야 한다. 문장부호만으로 `final`을 결정하지 않고 다음 조건을 결합한다.

- SaT/SBD boundary confidence
- punctuation end probability
- local agreement 관측 횟수
- right context에서 새 문장 시작 징후
- 최근 final과의 중복 여부
- VAD/silence 또는 turn-taking score는 보조 feature

### 세그먼트 상태관리

실시간 전사/번역에서는 세그먼트 lifecycle을 명시적으로 관리한다.

| 상태 | 의미 | 번역 큐 투입 |
| --- | --- | --- |
| `pending` | 마지막 미완성 tail 또는 판단 보류 구간 | 아니오 |
| `staged` | 완료 문장 후보이나 다음 윈도우 재확인 필요 | 아니오 |
| `final` | 복사/번역 가능한 확정 문장 | 예 |
| `suppressed` | 최근 final echo 또는 중복 후보 | 아니오 |
| `revised` | 다음 raw 결과에서 교체된 staged 후보 | 아니오 |

## 참고 문헌

1. Ryo Fukuda, Katsuhito Sudoh, Satoshi Nakamura. “Speech Segmentation Optimization using Segmented Bilingual Speech Corpus for End-to-end Speech Translation.” Interspeech 2022. https://www.isca-archive.org/interspeech_2022/fukuda22b_interspeech.pdf
2. Nina Zhou, Xuancong Wang, AiTi Aw. “Dynamic Boundary Detection for Speech Translation.” APSIPA ASC 2017. https://www.apsipa.org/proceedings/2017/CONTENTS/papers2017/13DecWednesday/Poster%202/WP-P2.20.pdf
3. Ruiqing Zhang, Chuanqi Tan, Tiejun Zhao, et al. “Dynamic Sentence Boundary Detection for Simultaneous Translation.” AutoSimTrans 2020. https://aclanthology.org/2020.autosimtrans-1.1.pdf
4. Md Kamrul Hasan, et al. “Multi-pass sentence-end detection of lecture speech.” Interspeech 2014. https://www.isca-archive.org/interspeech_2014/hasan14_interspeech.pdf
5. Yang Liu, et al. “Enriching Speech Recognition with Automatic Detection of Sentence Boundaries and Disfluencies.” IEEE TASLP 2006. https://www.sri.com/wp-content/uploads/2021/12/enriching_speech_recognition_with_automatic.pdf
6. Elizabeth Shriberg, Andreas Stolcke, et al. “Prosody-Based Automatic Segmentation of Speech into Sentences and Topics.” Speech Communication 2000. https://www.sri.com/wp-content/uploads/2021/12/prosody-based_automatic_segmentation_of_speech_into_sente.pdf
7. Ulf Hermjakob, Kevin Knight, Hal Daumé III. “Optimizing Sentence Segmentation for Speech Translation.” IWSLT 2002. https://aclanthology.org/2002.iwslt-1.15.pdf
8. Gabriel Papi, Marco Gaido, Matteo Negri, Marco Turchi. “Don’t Discard Fixed-Window Audio Segmentation in Speech-to-Text Translation.” WMT 2022. https://aclanthology.org/2022.wmt-1.13.pdf
9. Parth Vyas, Bowen Shi, Matthew Wiesner, et al. “Long-Form Speech Translation through Segmentation with Finite-State Decoding Constraints on Large Language Models.” Findings of EMNLP 2023. https://aclanthology.org/2023.findings-emnlp.19.pdf
10. Shubham Toshniwal, Tara N. Sainath, Ron J. Weiss, et al. “Streaming Punctuation for Long-form Dictation with Transformers.” arXiv 2022. https://arxiv.org/abs/2210.05756
11. Martin Poláček, et al. “Online Punctuation Restoration using ELECTRA Model for streaming ASR Systems.” Interspeech 2023. https://www.isca-archive.org/interspeech_2023/polacek23_interspeech.html
12. “Efficient Punctuation Restoration via Weighted Lookahead Scoring Method for Streaming ASR Systems.” arXiv 2026. https://arxiv.org/html/2606.05179v1
13. Saeed Madad, et al. “A light-weight and efficient punctuation and word casing prediction model for on-device streaming ASR.” arXiv 2024. https://arxiv.org/abs/2407.13142
14. Benjamin Minixhofer, Jonas Pfeiffer, Ivan Vulić. “Where’s the Point? Self-Supervised Multilingual Punctuation-Agnostic Sentence Segmentation.” arXiv 2023. https://arxiv.org/abs/2305.18893
15. Benjamin Minixhofer, et al. “Segment Any Text: A Universal Approach for Robust, Efficient and Adaptable Sentence Segmentation.” EMNLP 2024. https://aclanthology.org/2024.emnlp-main.665/
16. Macháček, et al. “Whisper-Streaming: Turning Whisper into Real-Time Transcription System.” IJCNLP-AACL 2023. https://aclanthology.org/2023.ijcnlp-demo.3/
17. Erik Ekstedt, Gabriel Skantze. “Real-time and Continuous Turn-taking Prediction Using Voice Activity Projection.” arXiv 2024. https://arxiv.org/abs/2401.04868
18. Erik Ekstedt, Gabriel Skantze. “Multilingual Turn-taking Prediction Using Voice Activity Projection.” LREC-COLING 2024. https://aclanthology.org/2024.lrec-main.1036/
19. Chao-Wei Huang, et al. “Turn-Taking Prediction for Natural Conversational Speech.” Interspeech 2022. https://www.isca-archive.org/interspeech_2022/chang22_interspeech.pdf
20. Sean Ekstedt, Gabriel Skantze. “TurnGPT: a Transformer-based Language Model for Predicting Turn-taking in Spoken Dialog.” Findings of ACL 2021. https://aclanthology.org/2021.findings-acl.205/
