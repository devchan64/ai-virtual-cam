#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[ai-virtual-cam] %s\n' "$*"
}

fail() {
  printf '[ai-virtual-cam] ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ "$(uname -s)" != "Darwin" ]]; then
  fail "mac-camera-install is only supported on macOS."
fi

log "CMIO virtual camera runtime installer is not implemented yet."
log "This project direction is OBS-free macOS virtual camera."
log "Roadmap: docs/macos-camera-extension-roadmap.md"
log "Next implementation: Xcode Camera Extension host project bootstrap + signing flow."

