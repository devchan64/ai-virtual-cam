# ai-virtual-cam

`ai-virtual-cam`은 카메라 입력을 받아 인물 세그멘테이션, 배경 합성, 소프트웨어 프레이밍(줌/패닝/틸트) 후 가상카메라로 송출하는 프로젝트입니다.

## 공식 진입점

모든 사용자 실행은 `./bin/avc` 단일 진입점으로 통일합니다.

```bash
./bin/avc <command>
```

지원 명령:

- `setup`: 현재 OS 의존성 설치
- `config`: CLI 설정 생성기
- `config-gui`: GUI 설정 생성기(프리뷰 포함)
- `serve`: 저장된 설정으로 스트리밍 실행
- `audio-mixer`: 마이크 게이트 기반 가상 오디오 믹서 실행 (Linux: 실시간 입력/출력 스트림)
- `doctor`: 기본 런타임 점검

## 플랫폼 정책

- Linux: OBS 비의존 자체 경로(`v4l2loopback`) 사용
- macOS: OBS Virtual Camera 경로만 지원(`pyvirtualcam`)
- CMIO 관련 기능은 폐기

## 빠른 시작

```bash
./bin/avc setup
./bin/avc config-gui
./bin/avc serve
```

오디오 활성화 선택:

```bash
./bin/avc config-gui   # 오디오 탭에서 Audio mixer true/false 설정
./bin/avc serve        # audio.enabled 값을 그대로 사용
```

오디오 게이트 정책:

- 레벨(`thresholdDb`)만으로 열지 않고, 음성 대역 비율(`minVoiceBandRatio`) 조건을 함께 사용
- 음악/주변소음처럼 음성 유사도가 낮은 입력은 게이트를 열지 않도록 설계
- 사용자 음색에 맞게 `thresholdDb`, `hysteresisDb`, `minVoiceBandRatio`를 `config-gui`에서 조정 가능
- 오디오 탭의 `게이트 자동 튜닝`으로 무음/발화 측정 후 게이트 추천값 자동 적용
- 오디오 탭에서 노이즈캔슬 속성(`denoise.enabled/backend/strength`) 저장 지원
- `audio-mixer`는 게이트 처리된 오디오를 출력 장치로 전달합니다.
- 노이즈캔슬 backend는 OS별로 분리 선택:
  - macOS: `none`, `rnnoise`
  - Linux: `none`, `rnnoise`, `deepfilternet`

기본 설정 파일 경로:

- `~/.avc/setting.json`

## GUI 설정기 주요 기능

- 배경 모드 선택: 블러, 크로마, 이미지
- 크로마 컬러피커 지원 (기본 컬러: 블랙)
- 세그멘테이션 실시간 조정: threshold, edge/blend, selfie 옵션
- 프레이밍 실시간 조정: margin, zoom/pan/tilt smoothing, PID, X/Y 오프셋
- 프리뷰 창에서 처리 결과 확인 (출력 기준 50% 축소 표시)
- 카메라 입력 모드는 장치 후보 기반(해상도/FPS 세트)

## macOS 사용 시 필수 사항

- `setup`에서 OBS Studio 설치를 수행합니다.
- OBS를 실행하고 `Virtual Camera`를 최소 1회 시작해야 회의 앱에서 카메라가 보입니다.
- 브라우저/회의앱이 먼저 실행 중이었다면 완전 종료 후 재실행이 필요할 수 있습니다.
- 시스템 확장 활성 여부는 아래로 확인할 수 있습니다.

```bash
sudo systemextensionsctl list | grep -Ei "obs|camera|virtual"
pluginkit -m -A -D | grep -Ei "obs|virtual.?camera|cameraextension|coremedia"
```

## 자주 발생하는 문제

- `OBS Virtual Camera가 준비되지 않았습니다`:
  OBS 실행 후 `Virtual Camera`를 한 번 시작하고 다시 `./bin/avc serve`를 실행하세요.
- GUI 실행 시 `tkinter` 오류:
  `./bin/avc setup`로 `.venv` 및 Tk 의존성을 설치한 뒤 다시 실행하세요.
- `No module named cv2`:
  `./bin/avc setup`로 공통 `.venv` 의존성을 다시 맞추세요.

## 설정 예시

```json
{
  "inputCamera": {
    "devicePath": "0",
    "width": 1280,
    "height": 720,
    "fps": 30,
    "crop": { "x": 0, "y": 0, "width": 1280, "height": 720 },
    "softwareZoom": 1.2
  },
  "outputCamera": {
    "devicePath": "virtual-cam",
    "backend": "pyvirtualcam",
    "width": 1280,
    "height": 720,
    "fps": 30
  },
  "segmentation": {
    "backend": "selfie",
    "threshold": 0.65,
    "edgeSmoothness": 0.5,
    "blendFeather": 0.35,
    "selfie": { "modelSelection": 1, "temporalSmoothing": 0.25 }
  },
  "background": {
    "mode": "chroma",
    "chromaColor": [0, 0, 0]
  },
  "crop": {
    "margin": 0.25,
    "panSmoothing": 0.85,
    "tiltSmoothing": 0.85,
    "zoomSmoothing": 0.8,
    "upperBodyBias": 0.0,
    "upperBodyRatio": 0.6,
    "upperBodyEdgeSmoothing": 0.35,
    "zoom": 1.2,
    "panPidKp": 0.35,
    "panPidKi": 0.01,
    "panPidKd": 0.12,
    "tiltPidKp": 0.35,
    "tiltPidKi": 0.01,
    "tiltPidKd": 0.12,
    "panTargetOffsetX": 0.0,
    "panTargetOffsetY": 0.0
  }
}
```

Linux 예시 출력 설정:

```json
{
  "outputCamera": {
    "devicePath": "/dev/video10",
    "backend": "v4l2loopback",
    "width": 1280,
    "height": 720,
    "fps": 30
  }
}
```
