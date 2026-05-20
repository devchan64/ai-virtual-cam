#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "[avc-docker] ERROR: $*" >&2
  exit 2
}

if [[ -z "${AVC_INPUT_DEVICE:-}" ]]; then
  fail "AVC_INPUT_DEVICE is required."
fi

if [[ ! -e "${AVC_INPUT_DEVICE}" ]]; then
  fail "Configured input device is not mounted: ${AVC_INPUT_DEVICE}"
fi

if [[ "${1:-}" == "./bin/avc" && "${2:-}" == "serve" ]]; then
  if [[ -z "${AVC_OUTPUT_DEVICE:-}" ]]; then
    fail "AVC_OUTPUT_DEVICE is required for serve."
  fi
  if [[ ! -e "${AVC_OUTPUT_DEVICE}" ]]; then
    fail "Configured output device is not mounted: ${AVC_OUTPUT_DEVICE}"
  fi
fi

if [[ "${1:-}" == "./bin/avc" && "${2:-}" == "config" ]]; then
  [[ -n "${DISPLAY:-}" ]] || fail "DISPLAY is required for GUI config."
  [[ -S /tmp/.X11-unix/X0 || -d /tmp/.X11-unix ]] || fail "X11 socket mount is missing."
fi

mkdir -p "${HOME}/.avc"

exec "$@"
