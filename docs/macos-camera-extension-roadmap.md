# macOS Camera Extension Roadmap (OBS 제거)

## 목표
- macOS에서 `pyvirtualcam + OBS Virtual Camera` 의존성을 제거한다.
- Google Meet/Zoom/Teams에서 바로 선택 가능한 가상 카메라를 자체 제공한다.
- 기존 파이썬 파이프라인(`segmentation/composer`) 결과 프레임을 새 가상 카메라 백엔드로 송출한다.

## 범위
- 포함:
  - CoreMediaIO Camera Extension 기반 가상 카메라 구현
  - 파이썬 파이프라인과 macOS 확장 간 프레임 브리지
  - `./bin/avc setup`, `./bin/avc serve`, `./bin/avc doctor`의 macOS 경로 통합
- 제외(초기):
  - 오디오 가상 디바이스
  - 다중 가상 카메라 인스턴스
  - App Store 배포 자동화

## 아키텍처 제안
1. `AVC Virtual Camera Host` (macOS 앱/데몬)
- CoreMediaIO Camera Extension을 포함/설치/활성화하는 host 바이너리.
- launchd로 사용자 세션에서 실행 가능하게 구성.

2. `AVC Camera Extension` (System Extension)
- macOS 카메라 디바이스로 노출.
- Host에서 전달받은 프레임을 CMSampleBuffer로 변환하여 스트림 제공.

3. `Frame Bridge`
- 파이썬(`./bin/avc serve`)과 Host 사이 프레임 IPC.
- 1차안: Unix Domain Socket + shared memory ring buffer.
- 목표 지연: 720p30 기준 end-to-end 120ms 이하.

## 단계별 계획
### Phase 0: 기술검증 (3~5일)
- Xcode 샘플 기반 Camera Extension 최소 동작 확인.
- Meet/Zoom에서 장치 노출 및 선택 가능 여부 확인.
- 성공 기준:
  - 테스트 패턴(컬러바) 송출이 화상회의 앱에 표시됨.

### Phase 1: 런타임 골격 (1주)
- Host/Extension 프로젝트 생성 및 서명/권한 플로우 정리.
- `./bin/avc setup` 내부 단계로 CMIO 설치/상태 검증 통합.
- 성공 기준:
  - 개발자 맥에서 1회 설치 후 재부팅 없이 디바이스 사용 가능.

### Phase 2: 프레임 브리지 (1~1.5주)
- 파이썬 파이프라인 출력을 Bridge로 송신.
- Host가 프레임 수신 후 Extension으로 공급.
- 성공 기준:
  - `./bin/avc serve` 실행 시 실시간 카메라 프레임 송출.
  - 프레임 드롭률 < 5% (720p30, 5분).

### Phase 3: 품질/안정화 (1주)
- 연결 끊김 복구, 백프레셔, 프레임 스킵 정책.
- 앱 재시작/절전/권한 변경 시 복원 시나리오 테스트.
- 성공 기준:
  - 30분 연속 통화에서 크래시 0회.

### Phase 4: 제품화 (3~5일)
- 설치/진단 자동화 (`setup`, `doctor`) 업데이트.
- README/온보딩 문서 전면 교체(OBS 관련 기본 경로 제거).
- 성공 기준:
  - 신규 맥에서 문서만으로 설치부터 Meet 사용까지 15분 이내.

## 리스크 및 대응
1. 코드서명/시스템 확장 승인 UX 복잡성
- 대응: 설치 스크립트에서 단계별 안내 + 상태 점검 커맨드 제공.

2. IPC 성능 병목
- 대응: shared memory 기반 설계, 720p30 우선, 1080p는 옵션화.

3. macOS 버전/칩셋 차이
- 대응: Apple Silicon 우선 지원, Intel은 베타 지원으로 분리.

## 설정 모델 변경안
- `outputCamera.backend`에 `cmio` 추가.
- 예시:
```json
{
  "outputCamera": {
    "backend": "cmio",
    "devicePath": "ai-virtual-cam",
    "width": 1280,
    "height": 720,
    "fps": 30
  }
}
```

## 운영 정책
- macOS 기본 backend:
  - `cmio` 단일 경로 유지
  - `opencv`는 로컬 파일 출력 테스트 용도로만 유지

## 완료 정의 (DoD)
- OBS 미설치 환경에서 `./bin/avc serve`만으로 가상 카메라가 Meet에 노출.
- `./bin/avc doctor`가 설치/권한/실행 상태를 모두 PASS로 리포트.
- README Quickstart가 macOS에서 추가 도구 설치 없이 재현 가능.
