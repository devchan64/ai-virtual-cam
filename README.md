# ai-virtual-cam

`ai-virtual-cam`은 USB 카메라 영상을 입력받아 인물 영역을 분리하고, 배경 합성 후 결과를 출력하는 Linux 전용 파이프라인입니다.

## Onboarding Entry Point

공식 실행 진입점:

```bash
./bin/avc <command>
```

## 지원 범위

- Linux (Debian/Ubuntu)
- Docker + NVIDIA Container Toolkit
- `v4l2loopback` 기반 가상 카메라 출력

## 미지원 범위

- macOS
- Windows

## 빠른 시작

```bash
./bin/avc setup
./bin/avc config --output ~/.avc/setting.json
./bin/avc serve --config ~/.avc/setting.json
```

## Runtime Contract

- Input: `/dev/video0`
- Output: `/dev/video10`

## 출력 백엔드

- `opencv`만 지원

## 설정 예시

```json
{
  "inputCamera": { "devicePath": "/dev/video0", "width": 1280, "height": 720, "fps": 30, "crop": { "x": 0, "y": 0, "width": 1280, "height": 720 } },
  "outputCamera": { "devicePath": "/dev/video10", "backend": "opencv", "width": 1280, "height": 720, "fps": 30 },
  "segmentation": { "backend": "selfie", "threshold": 0.65, "edgeSmoothness": 0.5, "blendFeather": 0.35, "selfie": { "modelSelection": 1, "temporalSmoothing": 0.25 } },
  "background": { "mode": "chroma", "chromaColor": [0, 0, 0] },
  "crop": { "margin": 0.25, "smoothing": 0.85 }
}
```

## 문서

- 설계 문서: [docs/design.md](/Users/simchangbo/ws/ai-virtual-cam/docs/design.md)
