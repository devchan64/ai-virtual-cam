#!/usr/bin/env bash

set -euo pipefail

OUTPUT_DEVICE=10
INPUT_DEVICE=0
CARD_LABEL="ai-virtual-cam"
DRY_RUN=0
SKIP_DOCKER=0
SKIP_NVIDIA_TOOLKIT=0
SKIP_V4L2LOOPBACK=0

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
Usage: scripts/install-host-deps.sh [options]

Install host dependencies for ai-virtual-cam on Debian/Ubuntu systems.

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

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    fail "Run this script as root or via sudo."
  fi
}

require_apt() {
  if ! command -v apt-get >/dev/null 2>&1; then
    fail "This script currently supports Debian/Ubuntu systems with apt-get only."
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
  run curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  run chmod a+r /etc/apt/keyrings/docker.asc

  local suite
  suite="${UBUNTU_CODENAME:-${VERSION_CODENAME}}"

  if [[ "$DRY_RUN" -eq 0 ]]; then
    cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/${ID}
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

  setup_docker_repo
  run apt-get update
  apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  run systemctl enable --now docker
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

  if ! command -v docker >/dev/null 2>&1; then
    fail "docker is not available after installation."
  fi

  if [[ "$SKIP_NVIDIA_TOOLKIT" -eq 0 ]] && ! command -v nvidia-ctk >/dev/null 2>&1; then
    fail "nvidia-ctk is not available after installation."
  fi

  if [[ ! -e "/dev/video${INPUT_DEVICE}" ]]; then
    fail "Expected input camera /dev/video${INPUT_DEVICE} is missing."
  fi

  if [[ "$SKIP_V4L2LOOPBACK" -eq 0 ]] && [[ ! -e "/dev/video${OUTPUT_DEVICE}" ]]; then
    fail "Expected output virtual camera /dev/video${OUTPUT_DEVICE} is missing."
  fi
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
  require_root
  require_apt
  load_os_release
  install_base_packages
  install_docker
  install_nvidia_container_toolkit
  install_v4l2loopback
  verify_host_contract
  log "Host dependency setup completed"
}

main "$@"
