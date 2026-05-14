# ai-virtual-cam 설계문서

## 플랫폼 정책

- Linux: Docker + `v4l2loopback` 경로 (`outputCamera.backend=v4l2loopback`)
- macOS: OBS Virtual Camera 경로만 지원 (`pyvirtualcam`)
- CMIO 관련 기능은 폐기

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
