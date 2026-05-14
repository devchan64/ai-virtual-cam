# ai-virtual-cam

`ai-virtual-cam`은 카메라 입력을 받아 인물 세그멘테이션, 배경 합성, 소프트웨어 프레이밍(줌/패닝/틸트) 후 가상카메라로 송출하는 프로젝트입니다.

## 시작하기

### 1) 설치

```bash
./bin/avc setup
```

- Linux: 런타임 의존성 + Docker/NVIDIA Toolkit(옵션) 설치
- macOS: OBS Studio + BlackHole 2ch + Python 런타임 의존성 설치

Python 의존성만 재동기화:

```bash
./bin/avc env sync
```

- `.venv`를 생성/재사용하고 `requirements.lock` 기준으로 정확히 설치합니다.

### 2) 설정

```bash
./bin/avc config
```

- 저장 경로: `~/.avc/setting.json`
- 영상: 입력 카메라, 출력 해상도/FPS, 세그멘테이션, 배경, 프레이밍
- 오디오: `audio.enabled`, 입/출력 장치, 게이트/노이즈캔슬

macOS 오디오 권장:

- `inputDevice`: 실제 마이크 장치명
- `outputDevice`: `BlackHole 2ch`
- `default` 대신 실제 장치명 저장 권장

### 3) 실행

```bash
./bin/avc serve
```

Docker 실행(선택):

```bash
./bin/avc serve --docker --config ~/.avc/setting.json
```

- 로컬 Python 대신 Docker 컨테이너에서 `serve`를 실행합니다.
- Linux 호스트는 `Dockerfile.linux`, macOS 호스트는 `Dockerfile.darwin-host`를 사용합니다.
- Linux에서는 `--gpus all`로 실행됩니다.

macOS 전용 Docker 실행 명령:

```bash
./bin/avc docker-macos serve --config ~/.avc/setting.json
```

- 기본 이미지: `devchan64/ai-virtual-cam:macos-latest`
- 기본 Dockerfile: `Dockerfile.darwin-host`

### 4) 회의 앱 연결

- 카메라: `OBS Virtual Camera`(macOS) 또는 Linux 가상 카메라(`/dev/videoN`)
- 마이크(macOS): `BlackHole 2ch`
- 스피커 모니터링이 필요하면 macOS `Audio MIDI 설정`에서 `다중 출력 기기` 구성

### 5) 점검

```bash
./bin/avc doctor
```

Docker에서 설정 GUI 실행(선택):

```bash
./bin/avc config --docker --output ~/.avc/setting.json
```

- X11 `DISPLAY`가 설정된 환경에서만 동작합니다.
- Docker 이미지가 없으면 호스트 OS에 맞는 Dockerfile로 자동 빌드합니다.

macOS 전용 설정 GUI 실행 명령:

```bash
./bin/avc docker-macos config --output ~/.avc/setting.json
```

- macOS에서는 카메라/오디오 장치 탐색 정확성을 위해 `config`를 호스트 런타임으로 실행합니다.

## 명령어

모든 사용자 실행은 `./bin/avc` 단일 진입점으로 통일합니다.

```bash
./bin/avc <command>
```

- `setup`: 현재 OS 의존성 설치
- `env`: Python 환경 동기화 (`env sync`)
- `config`: GUI 설정 생성기(프리뷰 포함)
- `serve`: 저장된 설정으로 스트리밍 실행
- `docker-macos`: macOS 전용 Docker 실행(serve/config)
- `audio-mixer`: 마이크 게이트 기반 가상 오디오 믹서 실행 (Linux: 실시간 입력/출력 스트림)
- `doctor`: 기본 런타임 점검

## 프로젝트 개요

핵심 목적:

- 영상 품질 개선: 세그멘테이션 + 배경 합성 + 소프트웨어 프레이밍
- 오디오 제어: 게이트 기반 입력 제어
- 운영 원칙: 설정값 우선, 자동 폴백 최소화, 실패 시 원인 명확화

핵심 구성:

- `scripts/config/create-config-gui.py`: GUI 설정기
- `src/app/main.py`: 메인 스트리밍 실행
- `src/pipeline/*`: 영상 처리 파이프라인
- `src/audio/*`: 오디오 게이트/믹서 및 OS별 런타임
- `src/adapter/output/*`: 가상 카메라 출력 어댑터

## 플랫폼별 동작

- Linux: OBS 비의존 `v4l2loopback` 경로
- macOS: OBS Virtual Camera(`pyvirtualcam`) 경로
- macOS 오디오 루프백: BlackHole 장치 사용 권장
- CMIO 관련 기능은 폐기

### Docker 배포 정책

- Dockerfile을 플랫폼별로 분리해 운영합니다.
  - Linux: `Dockerfile.linux`
  - macOS: `Dockerfile.darwin-host`
- Docker 이미지는 운영 목적에 맞게 플랫폼 태그를 분리해 배포합니다.

### Docker 태그 규칙

권장 저장소:

- `devchan64/ai-virtual-cam`

권장 태그:

1. `linux-latest`
- 최신 안정 Linux 이미지

2. `linux-vX.Y.Z`
- 릴리즈 버전 고정 태그
- 예: `linux-v0.3.0`

3. `linux-<git-sha>`
- 빌드 추적용 태그
- 예: `linux-a1b2c3d`

4. `macos-latest`
- 최신 안정 macOS용 Docker 빌드 이미지

5. `macos-vX.Y.Z`
- macOS 릴리즈 버전 고정 태그
- 예: `macos-v0.3.0`

운영 권장:

- Linux 배포 시 `linux-latest` + `linux-vX.Y.Z`를 함께 푸시
- macOS 배포 시 `macos-latest` + `macos-vX.Y.Z`를 함께 푸시
- 장애 대응/롤백 대비를 위해 `linux-<git-sha>` 태그도 병행

수동 배포 예시:

```bash
docker build -f Dockerfile.linux -t devchan64/ai-virtual-cam:linux-latest .
docker tag devchan64/ai-virtual-cam:linux-latest devchan64/ai-virtual-cam:linux-v0.1.0
docker tag devchan64/ai-virtual-cam:linux-latest devchan64/ai-virtual-cam:linux-$(git rev-parse --short HEAD)

docker push devchan64/ai-virtual-cam:linux-latest
docker push devchan64/ai-virtual-cam:linux-v0.1.0
docker push devchan64/ai-virtual-cam:linux-$(git rev-parse --short HEAD)

docker build -f Dockerfile.darwin-host -t devchan64/ai-virtual-cam:macos-latest .
docker tag devchan64/ai-virtual-cam:macos-latest devchan64/ai-virtual-cam:macos-v0.1.0

docker push devchan64/ai-virtual-cam:macos-latest
docker push devchan64/ai-virtual-cam:macos-v0.1.0
```

### macOS 필수 체크

- `setup`으로 OBS/BlackHole 설치
- OBS에서 `Virtual Camera`를 최소 1회 Start/Stop
- 브라우저/회의앱이 먼저 켜져 있었다면 완전 종료 후 재실행

```bash
sudo systemextensionsctl list | grep -Ei "obs|camera|virtual"
pluginkit -m -A -D | grep -Ei "obs|virtual.?camera|cameraextension|coremedia"
```

### Linux 가상 카메라 생성

- `config`의 `가상 카메라 생성/제거`는 `sudo modprobe` 권한 필요
- GUI는 `sudo -n`(비대화식)으로 실행되어, 권한 없으면 즉시 실패/안내
- 기본 생성 옵션: `exclusive_caps=1`, `devices=1`, `max_buffers=2`
- 실패 시 `exclusive_caps=0` 순차 폴백

권한 준비 후 실행:

```bash
sudo -v
./bin/avc config
```

## 운영 정책

- `설정 우선` 원칙으로 동작
- `output.device`, `audio.inputDevice`, `audio.outputDevice`, `outputCamera` 해상도/FPS/픽셀 포맷은 실행 시점에 그대로 사용
- 오디오 디바이스는 저장/로드/실행 시 자동 정규화하지 않음
- 장치/포맷 초기화 실패 시 자동 대체 없이 즉시 종료
- 에러 로그에는 실패 설정값, 원인, 권장 조치 포함

Linux `v4l2loopback` 복구 정책:

- 시작 시 장치 상태가 stale하면 1회 자동 복구 시도
- `v4l2loopback-ctl set-caps/set-fps`, `v4l2-ctl set-fmt` 재적용 후 재시도
- 실패 시 `sudo -n` 기반 모듈 재생성(`modprobe -r/load`) 1회 시도
- 최종 실패 시 즉시 종료, `config`에서 가상 카메라 재생성 필요

문제 발생 시 `config`에서 수정 후 재저장하고 `serve` 재실행하세요.

## 오디오 운영 가이드

오디오 활성화:

```bash
./bin/avc config       # 오디오 탭에서 Audio mixer true/false 설정
./bin/avc serve        # audio.enabled 값을 그대로 사용
```

오디오 게이트 정책:

- `thresholdDb` + `minVoiceBandRatio`를 함께 사용
- 음악/환경소음으로 게이트가 잘못 열리는 상황을 억제
- `thresholdDb`, `hysteresisDb`, `minVoiceBandRatio`를 GUI에서 조정 가능
- `게이트 자동 튜닝`으로 무음/발화 기준값 추천 적용
- 노이즈캔슬 backend:
  - macOS: `none`, `rnnoise`
  - Linux: `none`, `rnnoise`, `deepfilternet`

### macOS 오디오 가상장치(BlackHole)

설치/준비:

1. `./bin/avc setup` 실행 (BlackHole 2ch 설치 포함)
2. 필요 시 OBS Virtual Camera를 1회 Start/Stop

`config` 설정:

1. `inputDevice`: 실제 마이크 장치명 선택
2. `outputDevice`: `BlackHole 2ch` 선택
3. `default` 대신 실제 장치명 저장 권장

회의 앱 연결:

1. 회의 앱 마이크 입력 장치를 `BlackHole 2ch`로 선택
2. 모니터링이 필요하면 macOS `Audio MIDI 설정`에서 `다중 출력 기기`(BlackHole + 스피커) 구성

검증/장애 대응:

1. `serve` 오류에 `available=[...]`가 나오면 해당 정확한 장치명을 `audio.outputDevice`에 설정
2. 장치 미노출 시 `config` 재실행으로 목록 재조회
3. 반영 지연 시 재부팅
4. 필요 시 `brew reinstall --cask blackhole-2ch`

### Linux 오디오 가상장치(PulseAudio)

- `config`는 오디오 장치 값을 `setting.json`에 원본 ID 그대로 저장
  - 예: `alsa_input...__source`, `ai-virtual-cam`
- 오디오 경로(GStreamer):
  - 레벨 모니터: `input src -> level -> fakesink`
  - 출력 스트림: `input src` 또는 `audiotestsrc wave=silence` -> `pulsesink`
- 설정값이 런타임에서 열 수 없으면 자동 변환/폴백 없이 종료

권장 운영 절차:

1. `config` 오디오 탭에서 입력(source)/출력(sink)을 명시 선택
2. `serve` 실행 후 게이트 transition 로그 확인
3. source/sink가 바뀌었으면 `config` 재저장 후 재실행

## 문제 해결

- `OBS Virtual Camera가 준비되지 않았습니다`:
  OBS에서 Virtual Camera를 1회 시작 후 `./bin/avc serve` 재실행
- GUI 실행 시 `tkinter` 오류:
  `./bin/avc setup`으로 `.venv`/Tk 의존성 재설치
- `No module named cv2`:
  `./bin/avc setup`으로 공통 `.venv` 의존성 재정렬
- `audio output device open failed: ... No output device matching 'BlackHole 2ch'`:
  - `config` 재실행 후 오디오 장치 목록 재선택/저장
  - 에러의 `available=[...]`에 표시된 실제 장치명을 `audio.outputDevice`에 설정
  - macOS 재부팅 후 재시도
  - 필요 시 `brew reinstall --cask blackhole-2ch`

## GUI 기능

- 배경 모드 선택: 블러, 크로마, 이미지
- 크로마 컬러피커
- 세그멘테이션 실시간 조정: threshold, edge/blend, selfie 옵션
- 프레이밍 실시간 조정: margin, zoom/pan/tilt smoothing, PID, X/Y 오프셋
- 프리뷰 창에서 처리 결과 확인
- 카메라 입력 모드 후보 기반(해상도/FPS 세트)
- `오디오 게이트 테스트`, `오디오 기본값 복원`, `비디오 기본값 복원`

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

Linux 출력 예시:

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
