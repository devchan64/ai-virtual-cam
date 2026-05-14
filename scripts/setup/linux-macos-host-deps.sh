#!/usr/bin/env bash

set -euo pipefail

INPUT_DEVICE=0
DRY_RUN=0
OS_KIND=""
LINUX_DISTRO_ID=""

log() {
  printf '[ai-virtual-cam] %s\n' "$*"
}

fail() {
  printf '[ai-virtual-cam] ERROR: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf '[ai-virtual-cam] WARN: %s\n' "$*"
}

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] %s\n' "$*"
    return 0
  fi

  "$@"
}

usage() {
  cat <<'EOF'
Usage: ./bin/avc setup [options]

Install host dependencies for ai-virtual-cam on Linux (Debian/Ubuntu) or macOS.
This command no longer creates virtual devices; it only prepares runtime dependencies.

Options:
  --input-device N         Expected USB camera device number (default: 0)
  --dry-run                Print commands without executing them
  -h, --help               Show this help
EOF
}

require_privileges() {
  if [[ "$OS_KIND" == "linux" && "${EUID}" -ne 0 ]]; then
    fail "Run this script as root or via sudo on Linux."
  fi
  if [[ "$OS_KIND" == "macos" && "${EUID}" -eq 0 ]]; then
    fail "Do not run with sudo on macOS. Run as normal user."
  fi
}

detect_os() {
  case "$(uname -s)" in
    Linux) OS_KIND="linux" ;;
    Darwin) OS_KIND="macos" ;;
    *) fail "Unsupported OS: $(uname -s). Expected Linux or macOS." ;;
  esac
}

load_os_release() {
  if [[ ! -f /etc/os-release ]]; then
    fail "Cannot detect OS: /etc/os-release is missing."
  fi

  # shellcheck disable=SC1091
  source /etc/os-release

  if [[ "${ID:-}" != "ubuntu" && "${ID:-}" != "debian" ]]; then
    fail "Unsupported distribution: ${ID:-unknown}. Expected ubuntu or debian."
  fi
  LINUX_DISTRO_ID="${ID}"
}

apt_install() {
  run apt-get install -y "$@"
}

install_base_packages() {
  log "Installing base packages"
  run apt-get update
  apt_install ca-certificates curl gnupg gnupg2 lsb-release software-properties-common python3 python3-venv python3-pip libportaudio2 portaudio19-dev ffmpeg pulseaudio-utils \
    gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly
}

verify_host_contract() {
  log "Verifying host contract"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "Dry-run mode: skipping host contract checks"
    return 0
  fi

  if [[ "$OS_KIND" == "linux" ]]; then
    if ! command -v ffmpeg >/dev/null 2>&1; then
      fail "ffmpeg is not available after installation."
    fi

    if [[ ! -e "/dev/video${INPUT_DEVICE}" ]]; then
      fail "Expected input camera /dev/video${INPUT_DEVICE} is missing."
    fi
    return 0
  fi

  if ! brew list --cask obs >/dev/null 2>&1; then
    fail "OBS Studio is not installed. macOS path requires OBS."
  fi

  if ! brew list --cask blackhole-2ch >/dev/null 2>&1; then
    fail "BlackHole 2ch is not installed. macOS path requires virtual audio device."
  fi

}

install_macos_packages() {
  log "Installing base packages with Homebrew (macOS)"
  run brew install python@3.12 python-tk@3.12 ffmpeg opencv gstreamer
  run brew install --cask obs
  run brew install --cask blackhole-2ch
  log "macOS OBS 연동 확인: OBS Studio를 열어 'Start Virtual Camera'를 1회 실행 후 종료하세요."
  log "macOS 오디오 루프백 설치: BlackHole 2ch"
}

install_python_runtime_packages() {
  log "Syncing Python runtime dependencies from requirements.lock"
  run "$(pwd)/scripts/bin/avc-env" sync
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --input-device)
        INPUT_DEVICE="$2"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        fail "Unknown argument: $1"
        ;;
    esac
  done
}

main() {
  parse_args "$@"
  detect_os
  require_privileges
  if [[ "$OS_KIND" == "linux" ]]; then
    if ! command -v apt-get >/dev/null 2>&1; then
      fail "Linux host requires apt-get (Debian/Ubuntu)."
    fi
    load_os_release
    install_base_packages
  else
    if ! command -v brew >/dev/null 2>&1; then
      fail "Homebrew is required on macOS."
    fi
    install_macos_packages
  fi
  log "Setup now installs dependencies only; create virtual devices in config."
  install_python_runtime_packages
  verify_host_contract
  log "Host dependency setup completed"
  log "Setup does not create virtual devices. Use config GUI for virtual camera/speaker create/remove."
}

main "$@"
