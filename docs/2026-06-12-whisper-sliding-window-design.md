# Whisper 슬라이딩 윈도우 STT 설계

작성일: 2026-06-12

## 배경

현재 Whisper STT는 설정된 청크 길이만큼 오디오를 모은 뒤, 해당 청크를 한 번 전사하고 결과를 출력한다.

```text
chunkSeconds 수집 -> Whisper STT -> 전사 결과 출력 -> 번역
```

이 방식은 구조가 단순하지만 다음 문제가 있다.

- 청크를 짧게 잡으면 문맥이 부족해 STT 정확도가 떨어질 수 있다.
- 청크를 길게 잡으면 결과 출력 지연이 커진다.
- 청크 경계에서 문장이 잘리면 전사/번역 결과가 불안정해진다.
- 번역까지 매번 전체 문장에 연결하면 중복 번역이나 반복 생성이 발생할 수 있다.

## 목표

- STT 갱신 주기는 짧게 유지한다.
- Whisper에는 더 긴 문맥을 제공한다.
- 모달에는 중복 없이 확정된 새 텍스트만 출력한다.
- 번역은 확정된 새 텍스트만 수행한다.
- 설정값이 유효하지 않으면 자동 폴백 없이 실패한다.

## 제안 구조

기존 단일 청크 설정을 다음 세 설정으로 분리한다.

```json
{
  "stepSeconds": 1.0,
  "windowSeconds": 4.0,
  "commitLagSeconds": 1.0
}
```

- `stepSeconds`: STT 갱신 주기. 1초마다 새 결과를 계산한다.
- `windowSeconds`: Whisper에 입력할 최근 오디오 문맥 길이. 최근 3~4초를 입력한다.
- `commitLagSeconds`: 윈도우 끝부분을 바로 확정하지 않고 보류하는 시간. 경계에서 바뀔 수 있는 단어를 안정화한다.

추천 초기값:

```json
{
  "stepSeconds": 1.0,
  "windowSeconds": 4.0,
  "commitLagSeconds": 1.0,
  "beamSize": 3,
  "maxNewTokens": 96
}
```

## 처리 흐름

```text
오디오 입력
  -> ring buffer에 계속 저장
  -> 매 stepSeconds마다 최근 windowSeconds 추출
  -> Whisper STT 실행
  -> 이전 윈도우 결과와 비교
  -> 확정된 새 텍스트만 출력
  -> 확정된 새 텍스트만 번역
```

현재 방식:

```text
0.0s ~ 3.0s -> 전사 -> 출력
3.0s ~ 6.0s -> 전사 -> 출력
```

개선 방식:

```text
0.0s ~ 4.0s -> 전사 -> 일부 확정
1.0s ~ 5.0s -> 전사 -> 새 확정분 출력
2.0s ~ 6.0s -> 전사 -> 새 확정분 출력
```

## 내부 상태

작업자는 다음 상태를 유지한다.

```text
audio_ring_buffer
last_window_text
committed_text
recent_committed_fragments
```

- `audio_ring_buffer`: 최근 `windowSeconds` 이상의 오디오를 저장한다.
- `last_window_text`: 직전 윈도우의 전체 STT 결과다.
- `committed_text`: 이미 모달에 출력된 누적 텍스트다.
- `recent_committed_fragments`: 반복/중복 억제를 위한 최근 출력 조각이다.

## 확정 텍스트 계산

초기 구현은 문자열 overlap 기반으로 한다.

예:

```text
previous: "Folks, I was one of the first people"
current:  "the first people in the United States to take delivery"
new:      "in the United States to take delivery"
```

처리 원칙:

- 이전 윈도우 결과와 현재 윈도우 결과의 가장 긴 겹침을 찾는다.
- 겹치는 앞부분은 이미 처리된 문맥으로 본다.
- 겹치지 않는 새 부분만 `candidate_text`로 만든다.
- `commitLagSeconds`에 해당하는 끝부분은 즉시 확정하지 않는다.

정교한 구현이 필요해지면 `word_timestamps=true`를 사용해 시간 기준으로 확정 구간을 계산한다. 초기 구현에서는 비용과 복잡도를 줄이기 위해 문자열 기반으로 시작한다.

## 번역 정책

번역은 전체 윈도우 결과가 아니라 확정된 새 텍스트만 대상으로 한다.

```text
잘못된 방식: current_window_text 전체 번역
권장 방식: new_committed_text만 번역
```

이유:

- 슬라이딩 윈도우는 같은 문맥을 여러 번 포함한다.
- 전체 결과를 매번 번역하면 중복 번역이 생긴다.
- NLLB 번역 모델은 긴 반복 입력에서 반복 생성이 발생할 수 있다.

## 설정 스키마

`whisper` 블록에 다음 키를 추가한다.

```json
{
  "stepSeconds": 1.0,
  "windowSeconds": 4.0,
  "commitLagSeconds": 1.0
}
```

검증 규칙:

- `stepSeconds`: `0.5 <= value <= 5.0`
- `windowSeconds`: `1.0 <= value <= 15.0`
- `commitLagSeconds`: `0.0 <= value < windowSeconds`
- `stepSeconds <= windowSeconds`

기존 `chunkSeconds`는 호환성을 위해 유지한다.

- 새 설정이 없으면 `windowSeconds = chunkSeconds`로 읽는다.
- 새 설정 저장 시에는 `stepSeconds`, `windowSeconds`, `commitLagSeconds`를 명시한다.
- `chunkSeconds`는 당분간 README와 config check에서 legacy key로 설명한다.

## GUI 변경

Whisper 탭에 다음 슬라이더를 추가한다.

- `갱신 주기(초)` -> `stepSeconds`
- `문맥 길이(초)` -> `windowSeconds`
- `확정 지연(초)` -> `commitLagSeconds`

기존 `청크 길이(초)`는 다음 중 하나로 정리한다.

1. `문맥 길이(초)`로 이름을 바꾸고 내부 키를 `windowSeconds`로 연결한다.
2. legacy 호환을 위해 한동안 표시하되 비권장 설명을 붙인다.

초기 구현에서는 혼란을 줄이기 위해 1번을 권장한다.

## 로그

기존 성능 로그는 다음 정보를 포함하도록 확장한다.

```text
Whisper 성능: step=1.0s window=4.0s audio=4.00s stt=0.62s stt_rtf=0.16 committed_chars=32 preview_chars=18 beam=3 max_tokens=96
```

필드:

- `step`: 갱신 주기
- `window`: STT 입력 문맥 길이
- `audio`: 실제 Whisper 입력 오디오 길이
- `stt`: STT 처리 시간
- `stt_rtf`: real-time factor
- `committed_chars`: 이번 턴에 확정 출력한 글자 수
- `preview_chars`: 보류 중인 미확정 글자 수

## 실패 정책

- 설정값 범위가 유효하지 않으면 실행 단계에서 즉시 실패한다.
- `stepSeconds > windowSeconds`는 자동 보정하지 않는다.
- `commitLagSeconds >= windowSeconds`는 자동 보정하지 않는다.
- 설정 오류에는 설정값, 실패 원인, 권장 조치를 함께 출력한다.

## 구현 단계

1. `WhisperConfig`에 `stepSeconds`, `windowSeconds`, `commitLagSeconds` 추가
2. `src/domain/whisper_defaults.py`에 기본값 추가
3. `config_builder`와 config GUI 저장/로드 경로 연결
4. GUI Whisper 탭 슬라이더 추가
5. `_transcribe_loop`를 ring buffer 기반으로 변경
6. 문자열 overlap 기반 delta 계산 함수 추가
7. 번역 입력을 `new_committed_text`로 제한
8. 성능 로그 확장
9. 단위 테스트 추가
10. README에 운영 가이드 업데이트

## 테스트 계획

단위 테스트:

- 설정 기본값 로드
- 설정 범위 검증
- `chunkSeconds` legacy 호환
- 문자열 overlap delta 계산
- 중복 출력 억제
- 빈 delta에서는 번역 미실행

수동 테스트:

- `stepSeconds=1.0`, `windowSeconds=4.0`, `commitLagSeconds=1.0`
- `beamSize=3`, `maxNewTokens=96`
- 영어 STT + 한국어 NLLB 번역
- 한국어 STT + 영어 NLLB 번역
- 무음 구간에서 이전 문장 반복 여부 확인
- 로그의 `stt_rtf`가 1.0보다 충분히 낮은지 확인

## 기대 효과

- 1초 단위 갱신으로 체감 응답성을 유지한다.
- 4초 문맥 입력으로 짧은 청크보다 STT 정확도를 높인다.
- 확정 delta만 출력해 모달 중복을 줄인다.
- 확정 delta만 번역해 NLLB 반복 생성 가능성을 낮춘다.
