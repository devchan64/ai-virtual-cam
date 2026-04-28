# ai-virtual-cam

`ai-virtual-cam`은 Linux USB 카메라 영상을 입력받아 인물 영역을 실시간으로 분리하고, 배경을 크로마키 색상 또는 사용자 지정 배경으로 합성한 뒤, 최종 영상을 V4L2 가상 카메라로 출력하는 CUDA 가속 영상 파이프라인입니다.

상세 설계는 [docs/design.md](./docs/design.md)에서 확인할 수 있습니다.

## Overview

```text
USB Camera
 → AI Person Segmentation
 → Chroma / Background Composite
 → Person-aware Crop
 → Resize / FPS Control
 → Virtual Camera
 → Zoom / Meet / Teams
```

## Goals

- 실시간 인물 기반 가상 카메라 생성
- CUDA GPU 기반 추론 가속
- Docker 기반 실행환경 격리
- `v4l2loopback` 기반 화상회의 앱 연동
- 사용자 배경 이미지/영상 합성 지원
- 병합 영역 crop 후 출력 재구성

## Non-Goals

- OBS 플러그인 제공
- Windows / macOS 지원
- 영상 편집 기능 제공
- 클라우드 기반 추론 제공

## Architecture

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

## Runtime Contract

### Host Requirements

필수 구성요소:

- Linux
- NVIDIA GPU
- Docker
- `v4l2loopback`

Fail-fast 원칙:

- GPU 없음 → 즉시 종료
- 카메라 없음 → 즉시 종료
- 가상 카메라 없음 → 즉시 종료

### Device Contract

- Input: `/dev/video0`
- Output: `/dev/video10`

## Pipeline

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

## Modules

### Capture

- 카메라 프레임 수집

### Segmentation

- 인물 마스크 생성

### Mask Processing

- `threshold`, `smoothing`

### Bounds

- `bbox` 계산 및 smoothing

### Background

- `chroma`, `image`, `video` 배경 지원

### Compose

- 마스크 기반 foreground/background 합성

### Output

- 가상 카메라 출력

## Configuration

설정은 SSOT(Single Source of Truth) 원칙을 따릅니다.

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

## Repository Layout

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

## Development Phases

### Phase 1

- 카메라 입력
- segmentation
- chroma 출력
- 가상 카메라 출력

### Phase 2

- 배경 이미지 지원
- crop 지원

### Phase 3

- TensorRT 최적화
- 영상 배경 지원

## Core Principles

- Host는 device를 관리합니다.
- Container는 AI 처리를 담당합니다.
- 설정은 SSOT로 유지합니다.
- 실패 조건은 즉시 종료합니다.

## Planned Use Cases

- Zoom, Google Meet, Microsoft Teams 등 화상회의 앱에서 AI 기반 가상 카메라 사용
- 실시간 인물 분리 기반 크로마키 출력
- 사용자 지정 이미지/영상 배경 합성

## Status

현재 이 저장소는 초기 설계 단계이며, 본 README는 시스템 방향과 구현 범위를 정리한 문서입니다.
