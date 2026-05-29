# ai-virtual-cam

`ai-virtual-cam`은 카메라 입력을 받아 인물 세그멘테이션, 배경 합성, 소프트웨어 프레이밍(줌/패닝/틸트) 후 가상카메라로 송출하는 프로젝트입니다.

## 시작하기

### 1) 설치

```bash
./bin/avc setup
```

- Linux: 런타임 의존성 설치
- Linux Docker 사용 시 `docker`, `docker compose`, `xauth`, `xhost` 포함
- macOS: OBS Studio + BlackHole 2ch + Python 런타임 의존성 설치

Linux Docker 메모:

- 기존 `docker-ce`/`docker-compose-plugin` 환경이 있으면 `setup`은 이를 재사용하고 `docker.io`로 덮어쓰지 않습니다.

Python 의존성만 재동기화:

```bash
./bin/avc env sync
```

- `.venv`를 생성/재사용하고 `requirements.lock` 기준으로 정확히 설치합니다.
- Linux의 `deepfilternet`는 기본 미설치입니다. 필요하면 `AVC_INSTALL_DEEPFILTERNET=1 ./bin/avc env sync`로 별도 시도하세요.

### 2) 설정

```bash
./bin/avc config
```

- 저장 경로: `~/.avc/setting.json`
- 언어 선택: GUI 하단 `Language`에서 `ko`/`en` 선택
- 시작 언어 지정: `./bin/avc config --lang ko` 또는 `./bin/avc config --lang en`
- 영상: 입력 카메라, 출력 해상도/FPS, 세그멘테이션, 배경, 프레이밍
- 화질/비식별: 세그멘테이션 경계 기반 화질 보정, `비식별 처리(눈가림)` 옵션
- 오디오: `audio.enabled`, 입/출력 장치, 게이트/노이즈캔슬
- 선택한 언어는 `setting.json`의 `meta.language`에 저장됩니다.

설정 GUI 샘플:

- 샘플 파일: [`docs/images/config-preview-sample-anon.png`](docs/images/config-preview-sample-anon.png)
- 설명: `화질` 탭에서 `비식별 처리(눈가림)` 옵션을 활성화한 상태의 미리보기 예시입니다.

![config gui sample](docs/images/config-preview-sample-anon.png)

macOS 오디오 권장:

- `inputDevice`: 실제 마이크 장치명
- `outputDevice`: `BlackHole 2ch`
- `default` 대신 실제 장치명 저장 권장

### 3) 실행

```bash
./bin/avc serve
```

### Linux Docker 실행

호스트 준비:

- `v4l2loopback` 장치는 호스트에서 먼저 생성해야 합니다.
- 가상 카메라 생성/제거는 반드시 호스트 `./bin/avc config`에서 수행해야 합니다. (`docker config`에서는 생성/제거 불가)
- `config` GUI는 X11 전달이 필요합니다.
- PulseAudio/PipeWire를 쓸 경우 사용자 런타임 디렉터리(`/run/user/<uid>`)가 컨테이너에 마운트됩니다.
- `./bin/avc setup`은 Docker/Compose/X11 유틸까지 설치하지만, `docker` 그룹 반영을 위해 재로그인이 필요할 수 있습니다.
- `docker build` 전에 `docker info` 또는 `docker ps`가 일반 사용자로 동작해야 합니다.

이미지 빌드:

```bash
./bin/avc docker build
```

빌드 동작:

- Compose 파일 `docker/linux/compose.yml` 기준으로 Linux 런타임 이미지를 빌드합니다.
- 기본 이미지 태그는 `ai-virtual-cam-linux:latest`입니다.
- 빌드 시점에는 카메라/X11/Pulse 장치가 실제로 연결돼 있을 필요는 없습니다.

빌드 전 점검:

```bash
docker --version
docker compose version
docker ps
```

`docker ps`가 권한 오류로 실패하면:

```bash
sudo systemctl restart docker
sudo usermod -aG docker $USER
newgrp docker
```

`/var/run/docker.sock` 권한이 비정상일 때 확인:

```bash
ls -l /var/run/docker.sock
```

- 일반적으로 `root docker` 소유여야 합니다.
- `nobody:nogroup` 등으로 잘못 잡혀 있으면 Docker daemon 상태를 먼저 복구하세요.

GUI 설정:

```bash
xhost +si:localuser:$USER
./bin/avc docker config
```

- `docker config`는 설정값을 우선 사용합니다. 설정값이 없거나 유효하지 않으면 즉시 실패하며, 자동 대체 장치를 선택하지 않습니다.
- 설정은 로컬 `~/.avc/setting.json`에 저장됩니다.

스트리밍 실행:

```bash
./bin/avc docker serve
```

Docker Hub 이미지 사용:

```bash
docker pull devchan64/ai-virtual-cam:latest
docker pull devchan64/ai-virtual-cam:2026.05.26
```

- `docker serve`는 `setting.json`의 입력/출력 장치 값을 우선 사용합니다. 설정값이 없거나 장치를 열 수 없으면 즉시 실패합니다.
- `serve`는 항상 로컬 `~/.avc/setting.json` 존재 여부를 먼저 확인하고 없으면 즉시 실패합니다.
- `./bin/avc docker build` 로그는 `.tmp/docker-build-<UTC_TIMESTAMP>.log`로 저장됩니다.

운영 원칙:

- `config`와 `serve` 모두 `~/.avc/setting.json`을 동일하게 사용
- 장치 경로는 컨테이너 내부에서도 호스트와 동일한 절대 경로로 마운트
- 초기 설정 예시는 입력 `/dev/video0`, 출력 `/dev/video10`이며, 실제 실행은 저장된 설정값 기준으로 동작
- 가상 카메라 생성/삭제는 호스트 `config` 전용 기능
- `config`는 `DISPLAY` 또는 X11 소켓이 없으면 즉시 실패

### 4) 회의 앱 연결

- 카메라: `OBS Virtual Camera`(macOS) 또는 Linux 가상 카메라(`/dev/videoN`)
- 마이크(macOS): `BlackHole 2ch`
- 스피커 모니터링이 필요하면 macOS `Audio MIDI 설정`에서 `다중 출력 기기` 구성

### 5) 점검

```bash
./bin/avc doctor
```


## 명령어

모든 사용자 실행은 `./bin/avc` 단일 진입점으로 통일합니다.

```bash
./bin/avc <command>
```

- `setup`: 현재 OS 의존성 설치
- `env`: Python 환경 동기화 (`env sync`)
- `config`: GUI 설정 생성기(프리뷰 포함)
- `serve`: 저장된 설정으로 스트리밍 실행
- `docker`: Linux Docker 기반 `config`/`serve` 실행
- `audio-mixer`: 마이크 게이트 기반 가상 오디오 믹서 실행 (Linux: 실시간 입력/출력 스트림)
- `doctor`: 기본 런타임 점검

가상장치 스펙 테스트:

```bash
./bin/avc test
AVC_RUN_DEVICE_INTEGRATION_TEST=1 ./bin/avc test
```

- 기본 `./bin/avc test`는 안전 가드로 통합 테스트를 skip 합니다.
- 실제 통합 테스트는 `AVC_RUN_DEVICE_INTEGRATION_TEST=1`일 때만 실행됩니다.
- 통합 테스트는 테스트 전용 가상장치(`/dev/video42`, `ai-virtual-cam-test`, `ai-virtual-cam-test-mic`)를 생성/검증/삭제합니다.

## 개발 환경(기준)

- OS: Ubuntu 22.04.5 LTS
- Kernel: Linux 6.8.0-111-generic (x86_64)
- Python: 3.10.12
- Docker: 28.0.0
- Docker Compose: v2.33.0
- GPU: Intel Iris Xe Graphics (TigerLake-LP GT2)
- FFmpeg: 4.4.2 (Ubuntu 22.04 패키지)

참고:

- 위 정보는 최근 문서 업데이트 시점의 실제 개발/검증 환경 기준입니다.
- 환경이 다르면 장치명, 성능, 세그멘테이션/오디오 동작 특성이 달라질 수 있습니다.

## 프로젝트 개요

핵심 목적:

- 영상 품질 개선: 세그멘테이션 + 배경 합성 + 소프트웨어 프레이밍
- 비식별 처리: 얼굴 검출 기반 눈가림(옵션)
- 화질 보정: 얼굴 추적 없이 세그멘테이션 마스크 경계(edge band) 기준으로 적용
- 오디오 제어: 게이트 기반 입력 제어
- 운영 원칙: 설정값 우선, 자동 폴백 금지, 실패 시 원인 명확화

핵심 구성:

- `scripts/config/create-config-gui.py`: GUI 설정기
- `src/app/main.py`: 메인 스트리밍 실행
- `src/pipeline/*`: 영상 처리 파이프라인
- `src/audio/*`: 오디오 게이트/믹서 및 OS별 런타임
- `src/adapter/output/*`: 가상 카메라 출력 어댑터

## 플랫폼별 동작

- Linux: OBS 비의존 `v4l2loopback` 경로
- Linux Docker: 호스트 `v4l2loopback` + 컨테이너 실행 경로
- macOS: OBS Virtual Camera(`pyvirtualcam`) 경로
- macOS 오디오 루프백: BlackHole 장치 사용 권장
- CMIO 관련 기능은 폐기

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
- 옵션 적용 실패 시 자동 폴백 없이 즉시 실패하고 재설정이 필요
- Docker 실행은 가상 카메라 생성을 대체하지 않음. 장치는 호스트에서 먼저 준비해야 함.
- Docker `config`에서 가상 카메라 생성/제거를 시도하지 말고, 호스트 `./bin/avc config`에서 먼저 생성/검증 후 Docker `serve`를 실행하세요.

수동 생성 명령(호스트):

```bash
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="ai-virtual-cam" exclusive_caps=1
```

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
- 비식별 처리는 `faceEnhance.deidentify.enabled=true`로 활성화하며, 미리보기/serve 출력 모두에 동일 적용

### 현재 미완성 상태

- GPU 기반 모델 검증은 제한적입니다.
  - 현재는 CPU 경로 위주 동작 중심으로 검증되어 있으며, GPU(CUDA/ROCm/Metal)별 동작 안정성 및 성능 기준이 누적되지 않았습니다.
  - 동일 모델/백엔드로 `selfie_ensemble` 또는 `onnxruntime` GPU 경로 성능 비교 로그가 충분하지 않습니다.
  - GPU 환경에서는 추후 실제 회의 앱 동작, 발열/메모리 스파이크, 프레임 드랍 데이터 수집을 추가해야 합니다.
- Windows 인터페이스는 현재 미완성입니다.
  - `avc` 단일 엔트리포인트/GUI/장치 제어의 Windows UX 및 가이드가 충분히 정리되지 않았습니다.
  - 현재는 우선 Linux/macOS 중심의 사용성 기준으로 유지되고 있습니다.
- macOS 인터페이스는 현재 미완성입니다.
  - macOS 특화 UI/권한 가이드(OBS/BlackHole 및 장치 선택 UX)는 개선 여지가 큽니다.
  - `gui` 내 설정 동작 흐름은 기본 동작은 되지만, 플랫폼별 사용성 정리는 아직 진행 단계입니다.

Linux `v4l2loopback` 실패 처리 정책:

- 장치 상태가 비정상이거나 포맷 적용에 실패하면 자동 복구를 시도하지 않고 즉시 종료
- 오류 로그에 실패한 장치/포맷 설정값, 실패 원인, 권장 조치(`config`에서 가상 카메라 재생성 후 재실행)를 함께 출력

문제 발생 시 `config`에서 수정 후 재저장하고 `serve` 재실행하세요.

Linux Docker 정책:

- 컨테이너는 `AVC_INPUT_DEVICE`, `AVC_OUTPUT_DEVICE`, `~/.avc` 마운트가 정확히 들어와야만 실행
- 누락 시 자동 탐색/대체 없이 즉시 종료
- X11, Pulse/PipeWire 소켓도 누락 시 즉시 종료 또는 기능 실패로 반환

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
- 세그멘테이션 실시간 조정: threshold, edge/blend, selfie 옵션, 백엔드별 추가 엔진 옵션(폼 기반)
- 프레이밍 실시간 조정: margin, zoom/pan/tilt smoothing, PID, X/Y 오프셋
- 프리뷰 창에서 처리 결과 확인
- 카메라 입력 모드 후보 기반(해상도/FPS 세트)
- 화질 탭: 감마/오프셋/채도/강도 보정(세그멘테이션 경계 기준 적용)
- `오디오 게이트 테스트`, 각 탭별 기본값 복원 버튼
- 탭 순서: `입출력 -> 세그멘테이션 -> 배경 -> 프레이밍 -> 화질 -> 오디오`
- `faceEnhance` 구키(`brightness`, `blend`, `minSizeRatio`, `edgeDither`) 하위호환은 지원하지 않음

## 설정 예시

```json
{
  "meta": {
    "language": "ko"
  },
  "inputCamera": {
    "devicePath": "/dev/video0",
    "width": 1280,
    "height": 720,
    "fps": 30,
    "crop": { "x": 0, "y": 0, "width": 1280, "height": 720 },
    "softwareZoom": 1.0
  },
  "outputCamera": {
    "devicePath": "/dev/video10",
    "backend": "v4l2loopback",
    "width": 640,
    "height": 480,
    "fps": 30
  },
  "segmentation": {
    "backend": "selfie_ensemble",
    "threshold": 0.6,
    "edgeSmoothness": 0.5,
    "blendFeather": 0.35,
    "selfie": { "modelSelection": 0, "temporalSmoothing": 0.25 },
    "engineOptions": {
      "selfie_ensemble": {
        "modelBlend": 0.6,
        "temporalAlpha": 0.55,
        "maskBlur": 5,
        "morphOpen": 3,
        "morphClose": 5,
        "maskGamma": 0.9
      }
    }
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
  },
  "faceEnhance": {
    "enabled": true,
    "gamma": 1.1,
    "offset": 10.0,
    "saturation": 1.1,
    "strength": 0.55,
    "minRegionRatio": 0.12,
    "edgeNoise": 0.25,
    "deidentify": {
      "enabled": true
    }
  },
  "audio": {
    "enabled": true,
    "inputDevice": "alsa_input.pci-0000_00_1f.3-platform-skl_hda_dsp_generic.HiFi__hw_sofhdadsp_6__source",
    "outputDevice": "ai-virtual-cam",
    "sampleRate": 48000,
    "channels": 1,
    "frameMs": 20,
    "denoise": {
      "enabled": true,
      "backend": "none",
      "strength": 0.5
    },
    "gate": {
      "enabled": true,
      "thresholdDb": -40.0,
      "hysteresisDb": 4.0,
      "attackMs": 30,
      "holdMs": 160,
      "releaseMs": 2000,
      "openGain": 1.0,
      "closedGain": 0.0,
      "minVoiceBandRatio": 0.5
    }
  }
}
```

Linux 출력 예시:

```json
{
  "outputCamera": {
    "devicePath": "/dev/video10",
    "backend": "v4l2loopback",
    "width": 640,
    "height": 480,
    "fps": 30
  }
}
```

- `/dev/video10`은 반드시 `Video Output` capability가 있는 `v4l2loopback` 장치여야 합니다.
- 장치 상태 확인: `v4l2-ctl -D -d /dev/video10`
