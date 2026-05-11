#!/usr/bin/env bash

set -euo pipefail

OUTPUT_DEVICE=10
INPUT_DEVICE=0
CARD_LABEL="ai-virtual-cam"
DRY_RUN=0
SKIP_DOCKER=0
SKIP_NVIDIA_TOOLKIT=0
SKIP_V4L2LOOPBACK=0
OS_KIND=""
LINUX_DISTRO_ID=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() {
  printf '[ai-virtual-cam] %s\n' "$*"
}

fail() {
  printf '[ai-virtual-cam] ERROR: %s\n' "$*" >&2
  exit 1
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

Options:
  --output-device N        V4L2 loopback device number to create (default: 10)
  --input-device N         Expected USB camera device number (default: 0)
  --card-label LABEL       v4l2loopback card label (default: ai-virtual-cam)
  --skip-docker            Do not install Docker Engine
  --skip-nvidia-toolkit    Do not install NVIDIA Container Toolkit
  --skip-v4l2loopback      Do not install or configure v4l2loopback
  --dry-run                Print commands without executing them
  -h, --help               Show this help
EOF
}

require_privileges() {
  if [[ "$OS_KIND" == "linux" && "${EUID}" -ne 0 ]]; then
    fail "Run this script as root or via sudo on Linux."
  fi
  if [[ "$OS_KIND" == "macos" && "${EUID}" -eq 0 ]]; then
    fail "Do not run with sudo on macOS. Run as a normal user so Homebrew can work."
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
  apt_install ca-certificates curl gnupg gnupg2 lsb-release software-properties-common
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

  if [[ "$OS_KIND" == "macos" ]]; then
    if ! command -v brew >/dev/null 2>&1; then
      fail "Homebrew is required on macOS. Install it first: https://brew.sh"
    fi
    log "Installing Docker Desktop via Homebrew cask"
    run brew install --cask docker
  fi
}

brew_install() {
  if ! command -v brew >/dev/null 2>&1; then
    fail "Homebrew is required on macOS. Install it first: https://brew.sh"
  fi
  run brew install "$@"
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
    if [[ "$SKIP_NVIDIA_TOOLKIT" -eq 0 ]]; then
      log "Skipping NVIDIA Container Toolkit: not applicable on macOS."
    fi
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

install_v4l2loopback() {
  if [[ "$OS_KIND" == "macos" ]]; then
    if [[ "$SKIP_V4L2LOOPBACK" -eq 0 ]]; then
      log "Skipping v4l2loopback: not available on macOS."
    fi
    return 0
  fi

  if [[ "$SKIP_V4L2LOOPBACK" -eq 1 ]]; then
    log "Skipping v4l2loopback installation"
    return 0
  fi

  log "Installing and configuring v4l2loopback"
  apt_install v4l2loopback-dkms v4l2loopback-utils v4l-utils

  if [[ "$DRY_RUN" -eq 0 ]]; then
    cat >/etc/modules-load.d/ai-virtual-cam.conf <<EOF
v4l2loopback
EOF
    cat >/etc/modprobe.d/ai-virtual-cam-v4l2loopback.conf <<EOF
options v4l2loopback video_nr=${OUTPUT_DEVICE} card_label=${CARD_LABEL} exclusive_caps=1
EOF
  else
    printf '[dry-run] write /etc/modules-load.d/ai-virtual-cam.conf\n'
    printf '[dry-run] write /etc/modprobe.d/ai-virtual-cam-v4l2loopback.conf\n'
  fi

  if lsmod | grep -q '^v4l2loopback'; then
    run modprobe -r v4l2loopback
  fi

  run modprobe v4l2loopback "video_nr=${OUTPUT_DEVICE}" "card_label=${CARD_LABEL}" exclusive_caps=1
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

    if [[ ! -e "/dev/video${INPUT_DEVICE}" ]]; then
      fail "Expected input camera /dev/video${INPUT_DEVICE} is missing."
    fi

    if [[ "$SKIP_V4L2LOOPBACK" -eq 0 ]] && [[ ! -e "/dev/video${OUTPUT_DEVICE}" ]]; then
      fail "Expected output virtual camera /dev/video${OUTPUT_DEVICE} is missing."
    fi
    return 0
  fi

  if [[ "$OS_KIND" == "macos" ]]; then
    if ! command -v python3 >/dev/null 2>&1; then
      fail "python3 is not available after installation."
    fi
    if ! command -v ffmpeg >/dev/null 2>&1; then
      fail "ffmpeg is not available after installation."
    fi
    if [[ "$SKIP_DOCKER" -eq 0 ]] && ! command -v docker >/dev/null 2>&1; then
      log "docker CLI not found. Start Docker Desktop once to complete installation."
    fi
  fi
}

install_macos_packages() {
  log "Installing base packages with Homebrew (macOS)"
  brew_install python@3.12 python-tk@3.12 ffmpeg opencv xcodegen
  if [[ -x "/opt/homebrew/bin/python3.12" && "$DRY_RUN" -eq 0 ]]; then
    local venv_path
    local recreate_venv
    recreate_venv=0
    if [[ -x "$(pwd)/.venv/bin/python3" ]]; then
      venv_path="$(pwd)/.venv"
      if ! "$venv_path/bin/python3" -c "import tkinter" >/dev/null 2>&1; then
        recreate_venv=1
        log "Existing .venv lacks tkinter; recreating .venv with python3.12"
      else
        log "Using existing venv for GUI preview support: $venv_path"
      fi
    else
      venv_path="$(pwd)/.venv"
      recreate_venv=1
      log "Creating local venv for GUI preview support: $venv_path"
    fi
    if [[ "$recreate_venv" -eq 1 ]]; then
      run /opt/homebrew/bin/python3.12 -m venv --clear "$venv_path"
    fi
    if ! "$venv_path/bin/python3" -m pip --version >/dev/null 2>&1; then
      log "pip is missing in .venv; bootstrapping with ensurepip"
      run "$venv_path/bin/python3" -m ensurepip --upgrade
    fi
    run "$venv_path/bin/python3" -m pip install --upgrade pip
    run "$venv_path/bin/python3" -m pip install opencv-python numpy mediapipe==0.10.14
  elif [[ "$DRY_RUN" -eq 1 ]]; then
    log "Dry-run: would normalize/create .venv with python3.12 and install opencv-python,numpy,mediapipe==0.10.14"
  fi
  log "GUI runtime is unified to .venv."
}

install_macos_cmio_runtime() {
  if [[ "$OS_KIND" != "macos" ]]; then
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "Dry-run: would run internal CMIO install step"
    return 0
  fi
  log "Running macOS CMIO virtual camera installer"
  run bash "$SCRIPT_DIR/macos-cmio-install.sh"
}

verify_macos_cmio_runtime() {
  if [[ "$OS_KIND" != "macos" ]]; then
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "Dry-run: would run internal CMIO status step"
    return 0
  fi
  log "Verifying macOS CMIO runtime readiness"
  run bash "$SCRIPT_DIR/macos-cmio-status.sh"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --output-device)
        OUTPUT_DEVICE="$2"
        shift 2
        ;;
      --input-device)
        INPUT_DEVICE="$2"
        shift 2
        ;;
      --card-label)
        CARD_LABEL="$2"
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
      --skip-v4l2loopback)
        SKIP_V4L2LOOPBACK=1
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
    install_macos_packages
  fi
  install_docker
  install_nvidia_container_toolkit
  install_v4l2loopback
  install_macos_cmio_runtime
  verify_macos_cmio_runtime
  verify_host_contract
  log "Host dependency setup completed"
}

main "$@"
