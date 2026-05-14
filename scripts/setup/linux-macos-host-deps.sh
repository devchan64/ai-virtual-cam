#!/usr/bin/env bash

set -euo pipefail

INPUT_DEVICE=0
DRY_RUN=0
SKIP_DOCKER=0
SKIP_NVIDIA_TOOLKIT=0
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
  --skip-docker            Do not install Docker Engine
  --skip-nvidia-toolkit    Do not install NVIDIA Container Toolkit
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

setup_docker_repo() {
  log "Configuring Docker apt repository"
  run install -m 0755 -d /etc/apt/keyrings
  run curl -fsSL "https://download.docker.com/linux/${LINUX_DISTRO_ID}/gpg" -o /etc/apt/keyrings/docker.asc
  run chmod a+r /etc/apt/keyrings/docker.asc

  local suite
  suite="${UBUNTU_CODENAME:-${VERSION_CODENAME}}"

  if [[ "$DRY_RUN" -eq 0 ]]; then
    cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/${LINUX_DISTRO_ID}
Suites: ${suite}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  else
    printf '[dry-run] write /etc/apt/sources.list.d/docker.sources\n'
  fi
}

install_docker() {
  if [[ "$SKIP_DOCKER" -eq 1 ]]; then
    log "Skipping Docker installation"
    return 0
  fi

  if command -v docker >/dev/null 2>&1; then
    log "Docker already installed"
    return 0
  fi

  if [[ "$OS_KIND" == "linux" ]]; then
    setup_docker_repo
    run apt-get update
    apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    run systemctl enable --now docker
    return 0
  fi

  run brew install --cask docker
}

setup_nvidia_container_toolkit_repo() {
  log "Configuring NVIDIA Container Toolkit repository"
  run install -m 0755 -d /usr/share/keyrings
  run curl -fsSL "https://nvidia.github.io/libnvidia-container/gpgkey" \
    -o /tmp/nvidia-container-toolkit.gpg
  run gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg /tmp/nvidia-container-toolkit.gpg
  run chmod a+r /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

  if [[ "$DRY_RUN" -eq 0 ]]; then
    curl -s -L "https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list" \
      | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
      | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
  else
    printf '[dry-run] write /etc/apt/sources.list.d/nvidia-container-toolkit.list from stable/deb\n'
  fi
}

install_nvidia_container_toolkit() {
  if [[ "$OS_KIND" == "macos" ]]; then
    log "Skipping NVIDIA Container Toolkit: not applicable on macOS."
    return 0
  fi
  if [[ "$SKIP_NVIDIA_TOOLKIT" -eq 1 ]]; then
    log "Skipping NVIDIA Container Toolkit installation"
    return 0
  fi

  if command -v nvidia-ctk >/dev/null 2>&1; then
    log "NVIDIA Container Toolkit already installed"
  else
    setup_nvidia_container_toolkit_repo
    run apt-get update
    apt_install nvidia-container-toolkit
  fi

  run nvidia-ctk runtime configure --runtime=docker
  run systemctl restart docker
}

verify_host_contract() {
  log "Verifying host contract"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "Dry-run mode: skipping host contract checks"
    return 0
  fi

  if ! command -v docker >/dev/null 2>&1; then
    fail "docker is not available after installation."
  fi

  if [[ "$OS_KIND" == "linux" ]]; then
    if [[ "$SKIP_NVIDIA_TOOLKIT" -eq 0 ]] && ! command -v nvidia-ctk >/dev/null 2>&1; then
      fail "nvidia-ctk is not available after installation."
    fi

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
      --skip-docker)
        SKIP_DOCKER=1
        shift
        ;;
      --skip-nvidia-toolkit)
        SKIP_NVIDIA_TOOLKIT=1
        shift
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
  install_docker
  install_nvidia_container_toolkit
  log "Setup now installs dependencies only; create virtual devices in config."
  install_python_runtime_packages
  verify_host_contract
  log "Host dependency setup completed"
  log "Setup does not create virtual devices. Use config GUI for virtual camera/speaker create/remove."
}

main "$@"
