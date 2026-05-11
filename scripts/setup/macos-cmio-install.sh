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
mkdir -p "$XCODE_PROJECT_DIR"

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

if [[ ! -f "$XCODE_PROJECT_FILE" ]]; then
  cat >"$XCODE_PROJECT_FILE" <<'EOF'
// !$*UTF8*$!
{
  archiveVersion = 1;
  classes = {};
  objectVersion = 56;
  objects = {};
  rootObject = 000000000000000000000000;
}
EOF
  log "Created CMIO Phase 0 placeholder project file:"
  log "  - $XCODE_PROJECT_FILE"
fi

date -u +"%Y-%m-%dT%H:%M:%SZ" >"$RUNTIME_READY_FILE"
log "CMIO project detected: $XCODE_PROJECT_FILE"
log "Marked runtime as ready: $RUNTIME_READY_FILE"
log "NOTE: this is Phase 0 scaffold only; streaming runtime is still pending implementation."
