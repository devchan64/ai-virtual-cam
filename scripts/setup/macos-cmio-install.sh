#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CMIO_DIR="$ROOT_DIR/macos/cmio"
HOST_DIR="$CMIO_DIR/host"
EXT_DIR="$CMIO_DIR/extension"
STATUS_FILE="$CMIO_DIR/.phase0_bootstrapped"
RUNTIME_READY_FILE="$CMIO_DIR/.runtime_ready"
XCODE_PROJECT_FILE="$CMIO_DIR/AVCVirtualCam.xcodeproj/project.pbxproj"
XCODE_PROJECT_DIR="$(dirname "$XCODE_PROJECT_FILE")"
XCODEGEN_SPEC_FILE="$CMIO_DIR/project.yml"
HOST_APP_SWIFT="$HOST_DIR/App.swift"
HOST_INFO_PLIST="$HOST_DIR/Info.plist"
HOST_ENTITLEMENTS="$HOST_DIR/AVCVirtualCamHost.entitlements"
EXT_PROVIDER_SWIFT="$EXT_DIR/CameraExtensionProvider.swift"
EXT_INFO_PLIST="$EXT_DIR/Info.plist"
EXT_ENTITLEMENTS="$EXT_DIR/AVCVirtualCamExtension.entitlements"

log() {
  printf '[ai-virtual-cam] %s\n' "$*"
}

fail() {
  printf '[ai-virtual-cam] ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ "$(uname -s)" != "Darwin" ]]; then
  fail "CMIO setup step is only supported on macOS."
fi

log "Preparing CMIO Phase 0 workspace"
mkdir -p "$HOST_DIR" "$EXT_DIR"

if [[ ! -f "$CMIO_DIR/README.md" ]]; then
  cat >"$CMIO_DIR/README.md" <<'EOF'
# macOS CMIO Workspace

이 디렉터리는 OBS 비의존 가상카메라 구현(CoreMediaIO Camera Extension) 작업 공간입니다.

- `host/`: Camera Extension Host 앱(Xcode target) 소스 위치
- `extension/`: CMIO Camera Extension 소스 위치
- `.phase0_bootstrapped`: Phase 0 부트스트랩 완료 마커

공식 실행 진입:
- `./bin/avc setup`
EOF
fi

date -u +"%Y-%m-%dT%H:%M:%SZ" >"$STATUS_FILE"

if ! command -v xcodegen >/dev/null 2>&1; then
  fail "xcodegen is required to generate CMIO Xcode project. Re-run ./bin/avc setup after installing xcodegen."
fi

if ! xcodebuild -version >/dev/null 2>&1; then
  fail "CMIO 빌드 단계에는 전체 Xcode 앱이 필요합니다.
1) App Store에서 Xcode를 설치하세요.
2) Xcode를 1회 실행해 초기 설정/라이선스를 완료하세요.
3) 개발자 경로를 Xcode로 전환하세요:
   sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
4) 확인:
   xcodebuild -version"
fi

if [[ ! -f "$XCODEGEN_SPEC_FILE" ]]; then
  fail "CMIO XcodeGen spec missing: $XCODEGEN_SPEC_FILE"
fi

log "Generating Xcode project from spec"
# Clean broken/nested project artifacts from older setup runs.
if [[ -d "$XCODE_PROJECT_DIR" ]]; then
  rm -rf "$XCODE_PROJECT_DIR"
fi

xcodegen --spec "$XCODEGEN_SPEC_FILE" --project "$CMIO_DIR"

if [[ ! -f "$HOST_APP_SWIFT" ]]; then
  cat >"$HOST_APP_SWIFT" <<'EOF'
import Foundation

@main
struct AVCVirtualCamHost {
    static func main() {
        print("[cmio-host] placeholder host started")
        RunLoop.main.run()
    }
}
EOF
fi

if [[ ! -f "$HOST_INFO_PLIST" ]]; then
  cat >"$HOST_INFO_PLIST" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key>
  <string>com.aivirtualcam.host</string>
  <key>CFBundleName</key>
  <string>AVCVirtualCamHost</string>
</dict>
</plist>
EOF
fi

if [[ ! -f "$HOST_ENTITLEMENTS" ]]; then
  cat >"$HOST_ENTITLEMENTS" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
</dict>
</plist>
EOF
fi

if [[ ! -f "$EXT_PROVIDER_SWIFT" ]]; then
  cat >"$EXT_PROVIDER_SWIFT" <<'EOF'
import Foundation

public final class CameraExtensionProvider {
    public init() {}
}
EOF
fi

if [[ ! -f "$EXT_INFO_PLIST" ]]; then
  cat >"$EXT_INFO_PLIST" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key>
  <string>com.aivirtualcam.extension</string>
  <key>CFBundleName</key>
  <string>AVCVirtualCamExtension</string>
</dict>
</plist>
EOF
fi

if [[ ! -f "$EXT_ENTITLEMENTS" ]]; then
  cat >"$EXT_ENTITLEMENTS" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
</dict>
</plist>
EOF
fi

date -u +"%Y-%m-%dT%H:%M:%SZ" >"$RUNTIME_READY_FILE"
log "CMIO project detected: $XCODE_PROJECT_FILE"
log "Marked runtime as ready: $RUNTIME_READY_FILE"
log "Generated Host/Extension scaffold sources under: $CMIO_DIR"
log "NOTE: streaming runtime bridge is still pending implementation."
