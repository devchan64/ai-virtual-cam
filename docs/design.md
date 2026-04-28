# ai-virtual-cam 설계문서

## 1. 개요

`ai-virtual-cam`은 Linux USB 카메라 영상을 입력받아 인물 영역을 실시간으로 분리하고, 배경을 크로마키 색상 또는 사용자 지정 배경으로 합성한 뒤, 최종 영상을 V4L2 가상 카메라로 출력하는 CUDA 가속 영상 파이프라인이다.

```text
USB Camera
 → AI Person Segmentation
 → Chroma / Background Composite
 → Person-aware Crop
 → Resize / FPS Control
 → Virtual Camera
 → Zoom / Meet / Teams
```

## 2. 목표

- 실시간 인물 기반 가상 카메라 생성
- CUDA GPU 기반 추론 가속
- Docker 기반 실행환경 격리
- `v4l2loopback` 기반 화상회의 앱 연동
- 사용자 배경 이미지/영상 합성 지원
- 병합영역 crop 후 출력 재구성

## 3. 비목표

- OBS 플러그인
- Windows / macOS 지원
- 영상 편집 기능
- 클라우드 기반 추론

## 4. 시스템 아키텍처

```text
[Host Linux]
 ├─ NVIDIA Driver
 ├─ NVIDIA Container Toolkit
 ├─ v4l2loopback (/dev/video10)
 ├─ USB Camera (/dev/video0)
 └─ Docker Container
     └─ ai-virtual-cam
         ├─ Capture
         ├─ Segmentation
         ├─ Mask Processing
         ├─ Compose
         ├─ Crop
         └─ Virtual Cam Output
```

## 5. 런타임 계약

### Host

필수:

- Linux
- NVIDIA GPU
- Docker
- `v4l2loopback`

Fail-Fast:

- GPU 없음 → 종료
- 카메라 없음 → 종료
- 가상카메라 없음 → 종료

### Device

- Input: `/dev/video0`
- Output: `/dev/video10`

## 6. 파이프라인

```text
capture
 → segment
 → refine
 → bounds
 → compose
 → crop
 → resize
 → output
```

## 7. 모듈

### Capture

- 카메라 프레임 수집

### Segmentation

- 인물 마스크 생성

### Mask Processing

- `threshold`, `smoothing`

### Bounds

- `bbox` 계산 및 smoothing

### Background

- `chroma`, `image`, `video`

### Compose

- mask 기반 합성

### Output

- 가상 카메라 출력

## 8. 설정 SSOT

```yaml
inputCamera:
  devicePath: /dev/video0
  width: 1280
  height: 720
  fps: 30

outputCamera:
  devicePath: /dev/video10
  width: 1280
  height: 720
  fps: 30

segmentation:
  backend: tensorrt
  threshold: 0.65

background:
  mode: chroma
  chromaColor: [0,255,0]

crop:
  margin: 0.25
  smoothing: 0.85
```

## 9. Repo 구조

```text
ai-virtual-cam/
 ├─ config/
 ├─ scripts/
 ├─ src/
 │   ├─ app/
 │   ├─ domain/
 │   ├─ pipeline/
 │   ├─ adapter/
 │   └─ utils/
 └─ models/
```

## 10. 개발 단계

### Phase 1

- 카메라 입력
- segmentation
- chroma 출력
- 가상카메라

### Phase 2

- 배경 이미지
- crop

### Phase 3

- TensorRT
- 영상 배경

## 11. 핵심 원칙

- Host는 device 관리
- Container는 AI 처리
- 설정은 SSOT
- 실패는 즉시 종료
