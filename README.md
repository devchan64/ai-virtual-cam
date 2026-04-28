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

개발용 샘플 설정은 [config/settings.example.json](/Users/simchangbo/ws/ai-virtual-cam/config/settings.example.json)에 포함되어 있습니다.

## Host Bootstrap

Ubuntu/Debian 계열 호스트에서는 아래 스크립트로 기본 의존성을 설치할 수 있습니다.

```bash
sudo ./scripts/install-host-deps.sh
```

스크립트가 처리하는 범위:

- Docker Engine 설치
- NVIDIA Container Toolkit 설치 및 Docker runtime 연결
- `v4l2loopback` 설치 및 `/dev/video10` 가상 카메라 구성
- `/dev/video0`, `/dev/video10` 기준 런타임 계약 검증

## Container Runtime

초기 런타임 환경은 [Dockerfile](/Users/simchangbo/ws/ai-virtual-cam/Dockerfile)로 제공합니다. 이 이미지는 CUDA 런타임, Python 3, FFmpeg, GStreamer, V4L2 유틸리티를 포함하며 컨테이너 시작 시 GPU 및 장치 마운트 상태를 검증합니다.

빌드:

```bash
docker build -t ai-virtual-cam:dev .
```

예시 실행:

```bash
docker run --rm -it \
  --gpus all \
  --device /dev/video0:/dev/video0 \
  --device /dev/video10:/dev/video10 \
  -e REQUIRE_INPUT_DEVICE=1 \
  -e REQUIRE_OUTPUT_DEVICE=1 \
  ai-virtual-cam:dev
```

기본 엔트리포인트는 [scripts/container-entrypoint.sh](/Users/simchangbo/ws/ai-virtual-cam/scripts/container-entrypoint.sh)이며, 현재는 런타임 계약 검증 후 전달된 명령을 실행합니다.

## Config CLI

사용자 설정 JSON은 [scripts/create-config.py](/Users/simchangbo/ws/ai-virtual-cam/scripts/create-config.py)로 생성할 수 있습니다. 이 도구는 카메라 인터페이스 선택, 입력/출력 해상도, 카메라 크롭, 배경 모드, 배경 이미지 크롭, segmentation 옵션을 대화형으로 수집합니다.

카메라 목록 조회:

```bash
python3 scripts/create-config.py --list-cameras
```

설정 파일 생성:

```bash
python3 scripts/create-config.py --output config/settings.json
```

현재 구현된 backend:

- `mock`: 개발용 파이프라인 smoke test
- `tensorrt`: 인터페이스만 존재, 미구현
- `onnxruntime`: 인터페이스만 존재, 미구현

## Run

로컬 실행:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m src.app.main --config config/settings.example.json --max-frames 30
```

현재 구현 범위:

- JSON 설정 로드와 fail-fast 검증
- OpenCV 기반 입력 캡처
- 개발용 segmentation backend
- 마스크 refine
- chroma 또는 이미지 배경 합성
- person-aware crop 후 출력 리사이즈
- OpenCV `VideoWriter` 기반 출력

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
