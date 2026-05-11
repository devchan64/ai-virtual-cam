# ai-virtual-cam 설계문서

## 개요

`ai-virtual-cam`은 Linux 환경에서 USB 카메라 영상을 입력받아 인물 분리/배경 합성/크롭을 수행한 뒤 가상 카메라로 출력한다.

## 지원 플랫폼

- Linux (Debian/Ubuntu)

## 런타임 계약

- 입력 장치: `/dev/video0`
- 출력 장치: `/dev/video10`
- 출력 백엔드: `opencv`

## 호스트 요구사항

- Docker
- NVIDIA GPU (TensorRT 경로 사용 시)
- NVIDIA Container Toolkit
- `v4l2loopback`

## 파이프라인

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

## 설정 원칙

- 설정은 단일 JSON(SSOT)로 관리
- 실패 조건은 즉시 종료(Fail-Fast)
