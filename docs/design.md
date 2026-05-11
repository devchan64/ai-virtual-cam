# ai-virtual-cam 설계문서

## 플랫폼 정책

- Linux: Docker + `v4l2loopback` 경로 (`outputCamera.backend=v4l2loopback`)
- macOS: OBS Virtual Camera 경로만 지원 (`pyvirtualcam`)
- CMIO 관련 기능은 폐기

## 실행 진입점

```bash
./bin/avc <command>
```

## macOS 메모

- `./bin/avc setup`에서 OBS 설치 수행
- OBS에서 Virtual Camera를 1회 시작해야 카메라 목록 노출
