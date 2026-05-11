# macOS CMIO Workspace

이 디렉터리는 OBS 비의존 가상카메라 구현(CoreMediaIO Camera Extension) 작업 공간입니다.

- `host/`: Camera Extension Host 앱(Xcode target) 소스 위치
- `extension/`: CMIO Camera Extension 소스 위치
- `.phase0_bootstrapped`: Phase 0 부트스트랩 완료 마커

공식 실행 진입:
- `./bin/avc mac-camera-install`
- `./bin/avc mac-camera-status`
