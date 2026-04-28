#!/usr/bin/env bash

set -euo pipefail

INPUT_DEVICE="${INPUT_DEVICE:-/dev/video0}"
OUTPUT_DEVICE="${OUTPUT_DEVICE:-/dev/video10}"
REQUIRE_GPU="${REQUIRE_GPU:-1}"
REQUIRE_INPUT_DEVICE="${REQUIRE_INPUT_DEVICE:-0}"
REQUIRE_OUTPUT_DEVICE="${REQUIRE_OUTPUT_DEVICE:-0}"

log() {
  printf '[ai-virtual-cam] %s\n' "$*"
}

fail() {
  printf '[ai-virtual-cam] ERROR: %s\n' "$*" >&2
  exit 1
}

check_device() {
  local device_path="$1"
  local required="$2"

  if [[ "$required" -eq 1 && ! -e "$device_path" ]]; then
    fail "Required device is missing: $device_path"
  fi

  if [[ -e "$device_path" ]]; then
    log "Detected device: $device_path"
  else
    log "Device not mounted: $device_path"
  fi
}

check_gpu() {
  if [[ "$REQUIRE_GPU" -eq 0 ]]; then
    log "GPU check skipped"
    return 0
  fi

  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi >/dev/null 2>&1 || fail "nvidia-smi exists but GPU runtime is not available."
    log "NVIDIA runtime detected"
    return 0
  fi

  if [[ -e /dev/nvidiactl || -d /proc/driver/nvidia ]]; then
    log "NVIDIA device nodes detected"
    return 0
  fi

  fail "GPU runtime is not available. Run the container with NVIDIA Container Toolkit and --gpus all."
}

main() {
  check_gpu
  check_device "$INPUT_DEVICE" "$REQUIRE_INPUT_DEVICE"
  check_device "$OUTPUT_DEVICE" "$REQUIRE_OUTPUT_DEVICE"
  exec "$@"
}

main "$@"
