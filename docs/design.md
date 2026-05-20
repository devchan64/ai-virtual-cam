# ai-virtual-cam 설계문서

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
  - 설정값 검증 실패 시 즉시 종료
- 분리 원칙:
  - `config`와 `serve`를 별도 compose 서비스로 둔다
  - 둘 다 같은 설정 디렉터리 볼륨을 공유한다
  - 장치 경로는 호스트/컨테이너에서 동일한 절대 경로를 유지한다
  - `serve`는 `AVC_OUTPUT_DEVICE`가 반드시 필요하다

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
