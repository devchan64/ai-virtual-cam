#!/usr/bin/env bash

set -euo pipefail

INPUT_DEVICE=0
DRY_RUN=0
OS_KIND=""
LINUX_DISTRO_ID=""
INVOKING_USER="${SUDO_USER:-${USER:-}}"
INVOKING_GROUP=""

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

run_as_invoking_user() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] %s\n' "$*"
    return 0
  fi

  if [[ "$OS_KIND" == "linux" && -n "${SUDO_USER:-}" && "$EUID" -eq 0 ]]; then
    sudo -u "$SUDO_USER" "$@"
    return 0
  fi

  "$@"
}

usage() {
  cat <<'EOF'
Usage: ./bin/avc setup [options]

Install host dependencies for ai-virtual-cam on Linux (Debian/Ubuntu) or macOS.
This command no longer creates virtual devices; it only prepares runtime dependencies.

Linux setup also installs Docker host dependencies for `./bin/avc docker`.

Options:
  --input-device N         Expected USB camera device number (default: 0)
  --dry-run                Print commands without executing them
  -h, --help               Show this help
EOF
}

require_privileges() {
  if [[ "$OS_KIND" == "macos" && "${EUID}" -eq 0 ]]; then
    fail "Do not run with sudo on macOS. Run as normal user."
  fi
}

elevate_linux_with_sudo() {
  if [[ "$OS_KIND" != "linux" || "${EUID}" -eq 0 ]]; then
    return 0
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    warn "Linux setup dry-run is running without sudo; privileged commands will be printed only."
    return 0
  fi

  if ! command -v sudo >/dev/null 2>&1; then
    fail "Linux setup requires root privileges, but sudo is not available. Retry as root or install sudo."
  fi

  log "Linux setup requires administrator privileges; requesting sudo authentication."
  exec sudo bash "$0" "$@"
}

detect_os() {
  case "$(uname -s)" in
    Linux) OS_KIND="linux" ;;
    Darwin) OS_KIND="macos" ;;
    *) fail "Unsupported OS: $(uname -s). Expected Linux or macOS." ;;
  esac
}

detect_invoking_user() {
  if [[ -z "$INVOKING_USER" ]]; then
    fail "Cannot determine invoking user."
  fi

  if [[ "$OS_KIND" == "linux" ]]; then
    INVOKING_GROUP="$(id -gn "$INVOKING_USER")"
  else
    INVOKING_GROUP="$(id -gn)"
  fi
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

package_available() {
  apt-cache show "$1" >/dev/null 2>&1
}

has_docker_engine() {
  command -v docker >/dev/null 2>&1
}

has_docker_compose_v2() {
  docker compose version >/dev/null 2>&1
}

install_linux_docker_packages() {
  log "Installing Linux Docker host packages"

  if has_docker_engine; then
    log "Existing Docker engine detected: $(docker --version)"
  else
    apt_install docker.io
  fi

  if has_docker_compose_v2; then
    log "Existing Docker Compose v2 detected"
  elif package_available docker-compose-plugin; then
    apt_install docker-compose-plugin
  elif package_available docker-compose-v2; then
    apt_install docker-compose-v2
  else
    fail "No supported Docker Compose v2 package found. Install docker-compose-plugin or docker-compose-v2."
  fi
}

install_base_packages() {
  log "Installing base packages"
  run apt-get update
  apt_install ca-certificates curl gnupg gnupg2 lsb-release software-properties-common python3 python3-venv python3-pip python3-tk libportaudio2 portaudio19-dev ffmpeg pulseaudio-utils \
    gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
    xauth x11-xserver-utils
  install_linux_docker_packages
}

verify_linux_docker_contract() {
  if ! command -v docker >/dev/null 2>&1; then
    fail "docker is not available after installation."
  fi

  if ! docker compose version >/dev/null 2>&1; then
    fail "docker compose v2 is not available after installation."
  fi

  if ! command -v xhost >/dev/null 2>&1; then
    fail "xhost is not available after installation. Docker config GUI requires X11 access control."
  fi

  if ! command -v xauth >/dev/null 2>&1; then
    fail "xauth is not available after installation. Docker config GUI requires Xauthority forwarding."
  fi
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

    verify_linux_docker_contract

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
  log "Syncing Python runtime dependencies from requirements.txt"
  run_as_invoking_user "$(pwd)/scripts/bin/avc-env" sync
}

repair_workspace_permissions() {
  if [[ "$OS_KIND" != "linux" || "$EUID" -ne 0 ]]; then
    return 0
  fi
  if [[ -z "$INVOKING_GROUP" ]]; then
    fail "Cannot determine invoking group for permission repair."
  fi

  if [[ -e "$(pwd)/.venv" ]]; then
    log "Repairing .venv ownership for $INVOKING_USER:$INVOKING_GROUP"
    run chown -R "$INVOKING_USER:$INVOKING_GROUP" "$(pwd)/.venv"
  fi
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
  elevate_linux_with_sudo "$@"
  detect_invoking_user
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
  repair_workspace_permissions
  install_python_runtime_packages
  verify_host_contract
  log "Host dependency setup completed"
  if [[ "$OS_KIND" == "linux" ]]; then
    log "Linux Docker host deps installed: docker, docker compose, xauth, xhost"
    log "If current user cannot run docker, add user to docker group and re-login: sudo usermod -aG docker <user>"
  fi
  log "Setup does not create virtual devices. Use config GUI for virtual camera/speaker create/remove."
}

main "$@"
