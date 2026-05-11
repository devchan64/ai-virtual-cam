#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_PATH="${1:-$HOME/.avc/setting.json}"
CMIO_DIR="$ROOT_DIR/macos/cmio"
STATUS_FILE="$CMIO_DIR/.phase0_bootstrapped"
RUNTIME_READY_FILE="$CMIO_DIR/.runtime_ready"
XCODE_PROJECT_FILE="$CMIO_DIR/AVCVirtualCam.xcodeproj/project.pbxproj"
HOST_APP_SWIFT="$CMIO_DIR/host/App.swift"
HOST_INFO_PLIST="$CMIO_DIR/host/Info.plist"
EXT_PROVIDER_SWIFT="$CMIO_DIR/extension/CameraExtensionProvider.swift"
EXT_INFO_PLIST="$CMIO_DIR/extension/Info.plist"
ok=1

log() {
  printf '[ai-virtual-cam] %s\n' "$*"
}

check_cmd() {
  if command -v "$1" >/dev/null 2>&1; then
    log "OK: command available -> $1"
  else
    log "MISSING: command not found -> $1"
    ok=0
  fi
}

if [[ "$(uname -s)" != "Darwin" ]]; then
  log "ERROR: CMIO status check is only supported on macOS."
  exit 1
fi

log "CMIO runtime status (WIP)"
check_cmd xcodebuild
check_cmd xcrun
check_cmd python3

if [[ -d "$CMIO_DIR" ]]; then
  log "OK: CMIO workspace exists -> $CMIO_DIR"
else
  log "WARN: CMIO workspace missing -> $CMIO_DIR"
  log "      run ./bin/avc setup"
  ok=0
fi

if [[ -f "$STATUS_FILE" ]]; then
  log "OK: Phase 0 bootstrap marker exists"
else
  log "WARN: Phase 0 bootstrap marker missing"
  ok=0
fi

if [[ -f "$XCODE_PROJECT_FILE" ]]; then
  log "OK: CMIO Xcode project exists"
  if grep -q "000000000000000000000000" "$XCODE_PROJECT_FILE"; then
    log "INFO: placeholder Xcode project detected (Phase 0 scaffold)."
  fi
else
  log "WARN: CMIO Xcode project missing -> $XCODE_PROJECT_FILE"
  ok=0
fi

if [[ -f "$RUNTIME_READY_FILE" ]]; then
  log "OK: runtime ready marker exists"
else
  log "WARN: runtime ready marker missing (install not complete)"
  ok=0
fi

for f in "$HOST_APP_SWIFT" "$HOST_INFO_PLIST" "$EXT_PROVIDER_SWIFT" "$EXT_INFO_PLIST"; do
  if [[ -f "$f" ]]; then
    log "OK: scaffold file exists -> $f"
  else
    log "WARN: scaffold file missing -> $f"
    ok=0
  fi
done

if [[ -f "$CONFIG_PATH" ]]; then
  backend="$(python3 - <<PY
import json
from pathlib import Path
p=Path("$CONFIG_PATH").expanduser()
try:
    raw=json.loads(p.read_text(encoding="utf-8"))
    print((raw.get("outputCamera") or {}).get("backend","<missing>"))
except Exception:
    print("<invalid>")
PY
)"
  if [[ "$backend" == "cmio" ]]; then
    log "OK: config backend is cmio ($CONFIG_PATH)"
  else
    log "WARN: config backend is '$backend' (expected 'cmio') at $CONFIG_PATH"
    ok=0
  fi
else
  log "WARN: config not found at $CONFIG_PATH"
  ok=0
fi

log "INFO: CMIO runtime must be fully ready for ./bin/avc setup success."
log "INFO: see roadmap -> $ROOT_DIR/docs/macos-camera-extension-roadmap.md"

if [[ "$ok" -eq 1 ]]; then
  exit 0
fi
exit 1
