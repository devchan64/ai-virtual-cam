# ai-virtual-cam

`ai-virtual-cam`은 USB 카메라 영상을 입력받아 인물 분리/배경 합성 후 출력하는 파이프라인입니다.

## Onboarding Entry Point

```bash
./bin/avc <command>
```

## 플랫폼 지원 정책

- Linux: `v4l2loopback` 기반 가상 카메라
- macOS: **OBS 경로만 지원**
- CMIO 관련 기능은 폐기됨

## macOS 정책

- macOS 출력 backend는 `pyvirtualcam` + OBS Virtual Camera 경로를 사용합니다.
- `./bin/avc setup` 실행 시 OBS Studio 설치를 진행합니다.
- OBS 실행 후 Virtual Camera를 1회 시작해야 회의 앱 카메라 목록에 노출됩니다.

## 빠른 시작

```bash
./bin/avc setup
./bin/avc config --output ~/.avc/setting.json
./bin/avc serve --config ~/.avc/setting.json
```

## 설정 예시 (macOS OBS)

```json
{
  "inputCamera": { "devicePath": "0", "width": 1280, "height": 720, "fps": 30, "crop": { "x": 0, "y": 0, "width": 1280, "height": 720 }, "softwareZoom": 1.2 },
  "outputCamera": { "devicePath": "virtual-cam", "backend": "pyvirtualcam", "width": 1280, "height": 720, "fps": 30 },
  "segmentation": { "backend": "selfie", "threshold": 0.65, "edgeSmoothness": 0.5, "blendFeather": 0.35, "selfie": { "modelSelection": 1, "temporalSmoothing": 0.25 } },
  "background": { "mode": "chroma", "chromaColor": [0, 0, 0] },
  "crop": { "margin": 0.25, "panSmoothing": 0.85, "upperBodyBias": 0.35, "upperBodyRatio": 0.60, "zoom": 1.2, "panPidKp": 0.35, "panPidKi": 0.01, "panPidKd": 0.12 }
}
```
