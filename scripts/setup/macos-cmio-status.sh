#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_PATH="${1:-$HOME/.avc/setting.json}"
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
  log "ERROR: mac-camera-status is only supported on macOS."
  exit 1
fi

log "CMIO runtime status (WIP)"
check_cmd xcodebuild
check_cmd xcrun
check_cmd python3

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

log "INFO: installer/runtime are pending implementation."
log "INFO: see roadmap -> $ROOT_DIR/docs/macos-camera-extension-roadmap.md"

if [[ "$ok" -eq 1 ]]; then
  exit 0
fi
exit 1

