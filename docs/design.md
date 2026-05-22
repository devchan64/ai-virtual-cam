# ai-virtual-cam 설계문서

## 공통 설계 원칙

- 설정값 우선: 실행 단계에서는 저장된 `~/.avc/setting.json` 값을 그대로 사용한다.
- 자동 폴백 금지: 설정값이 유효하지 않거나 장치/포맷 초기화에 실패하면 자동 대체를 시도하지 않는다.
- 즉시 실패: 실행 불가 상태에서는 즉시 예외를 발생시키고 종료한다.
- 오류 정보 표준화: 실패 시 설정값, 실패 원인, 권장 조치를 함께 출력한다.

## 플랫폼 정책

- Linux: Docker + `v4l2loopback` 경로 (`outputCamera.backend=v4l2loopback`)
- macOS: OBS Virtual Camera 경로만 지원 (`pyvirtualcam`)
- CMIO 관련 기능은 폐기

## Linux Docker 설계

- 호스트 책임:
  - `v4l2loopback` 모듈 로드 및 `/dev/videoN` 생성
  - X11 소켓(`/tmp/.X11-unix`)과 `DISPLAY` 제공
  - PulseAudio/PipeWire 런타임 소켓(`/run/user/<uid>`) 제공
- 컨테이너 책임:
  - `config` GUI 실행 및 `~/.avc/setting.json` 저장
  - `serve` 파이프라인 실행
  - 설정값/장치 검증 실패 시 즉시 종료
- 분리 원칙:
  - `config`와 `serve`를 별도 compose 서비스로 둔다
  - 둘 다 같은 설정 디렉터리 볼륨을 공유한다
  - 장치 경로는 호스트/컨테이너에서 동일한 절대 경로를 유지한다
  - 컨테이너 실행에 필요한 마운트/환경(`AVC_INPUT_DEVICE`, `AVC_OUTPUT_DEVICE`, `~/.avc`)가 누락되면 즉시 실패한다

## Linux `v4l2loopback` 정책

- 가상 카메라 생성/제거는 호스트 `./bin/avc config` 전용 기능이다.
- 생성 기본 옵션은 `exclusive_caps=1`, `devices=1`, `max_buffers=2`를 사용한다.
- 옵션/포맷 적용 실패 시 자동 폴백 또는 자동 복구를 시도하지 않고 즉시 종료한다.
- 재실행 전 사용자는 `config`에서 장치 상태를 재생성/검증해야 한다.

## 실행 진입점

```bash
./bin/avc <command>
```

## 오디오 믹서

- 목적: 마이크 입력 게이트 동작(attack/hold/release + hysteresis) 정의 및 실시간 스트림에 연결
- 현재 단계: 상태머신/설정 스키마/실행 진입(`audio-mixer`) 기반으로 음성 스트림 게이트 처리 동작
- 현재 버전은 실제 오디오 입력-출력 스트림을 연결해 게이트 처리된 신호를 출력으로 라우팅 (`sounddevice` 기반)
- 노이즈 억제 정책: `thresholdDb` + `minVoiceBandRatio` 동시 만족 시에만 게이트 개방

## macOS 메모

- `./bin/avc setup`에서 OBS 설치 수행
- OBS에서 Virtual Camera를 1회 시작해야 카메라 목록 노출
