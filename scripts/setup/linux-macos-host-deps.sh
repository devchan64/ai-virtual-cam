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

cleanup_v4l2loopback_dkms_state() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] rm -rf /var/crash/v4l2loopback*.crash\n'
    printf '[dry-run] rm -rf /var/lib/dkms/v4l2loopback\n'
    printf '[dry-run] dpkg --purge v4l2loopback-dkms\n'
    printf '[dry-run] dkms remove v4l2loopback/0.12.7 --all\n'
    return 0
  fi

  rm -f /var/crash/v4l2loopback*.crash || true
  rm -rf /var/lib/dkms/v4l2loopback || true
  if dpkg -s v4l2loopback-dkms >/dev/null 2>&1; then
    run apt-get purge -y --auto-remove v4l2loopback-dkms
  fi
  if command -v dkms >/dev/null 2>&1; then
    dkms remove v4l2loopback/0.12.7 --all || true
  fi
}

install_base_packages() {
  log "Installing base packages"
  run apt-get update
  apt_install ca-certificates curl gnupg gnupg2 lsb-release software-properties-common python3 python3-venv python3-pip libportaudio2 portaudio19-dev ffmpeg
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

install_v4l2loopback_from_source() {
  log "Falling back to v4l2loopback source build"
  cleanup_v4l2loopback_dkms_state
  apt_install build-essential dkms linux-headers-"$(uname -r)" git make

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "[dry-run] clone/build/install v4l2loopback from GitHub"
    return 0
  fi

  local src_dir="/tmp/v4l2loopback-avc"
  run rm -rf "$src_dir"
  run git clone --depth 1 https://github.com/umlaeute/v4l2loopback.git "$src_dir"
  if grep -q "strlcpy" "$src_dir/v4l2loopback.c"; then
    run bash -c "cd '$src_dir' && sed -i 's/\\bstrlcpy\\b/strscpy/g' v4l2loopback.c"
  fi
  run bash -c "cd '$src_dir' && make"
  run bash -c "cd '$src_dir' && make install DKMS=1"
}

load_v4l2loopback_module() {
  if [[ "$DRY_RUN" -eq 0 ]] && lsmod | grep -q '^v4l2loopback'; then
    run modprobe -r v4l2loopback
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] modprobe v4l2loopback video_nr=%s card_label=%s exclusive_caps=1\n' "$OUTPUT_DEVICE" "$CARD_LABEL"
    return 0
  fi

  run modprobe v4l2loopback "video_nr=${OUTPUT_DEVICE}" "card_label=${CARD_LABEL}" exclusive_caps=1
}

install_v4l2loopback() {
  if [[ "$OS_KIND" == "macos" ]]; then
    log "Skipping v4l2loopback: not available on macOS."
    return 0
  fi
  if [[ "$SKIP_V4L2LOOPBACK" -eq 1 ]]; then
    log "Skipping v4l2loopback installation"
    return 0
  fi

  log "Installing and configuring v4l2loopback"
  cleanup_v4l2loopback_dkms_state
  if ! install_v4l2loopback_from_source; then
    fail "v4l2loopback installation failed via source build."
  fi

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

  if ! load_v4l2loopback_module; then
    cleanup_v4l2loopback_dkms_state
    log "Failed to load v4l2loopback module after install. Trying source rebuild."
    if ! install_v4l2loopback_from_source; then
      fail "v4l2loopback module rebuild failed."
    fi
    if ! load_v4l2loopback_module; then
      fail "v4l2loopback module load failed after fallback build."
    fi
  fi
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

    if [[ "$SKIP_V4L2LOOPBACK" -eq 0 ]] && [[ ! -e "/dev/video${OUTPUT_DEVICE}" ]]; then
      fail "Expected output virtual camera /dev/video${OUTPUT_DEVICE} is missing."
    fi
    return 0
  fi

  if ! brew list --cask obs >/dev/null 2>&1; then
    fail "OBS Studio is not installed. macOS path requires OBS."
  fi
}

install_macos_packages() {
  log "Installing base packages with Homebrew (macOS)"
  run brew install python@3.12 python-tk@3.12 ffmpeg opencv
  run brew install --cask obs
  log "macOS OBS 연동 확인: OBS Studio를 열어 'Start Virtual Camera'를 1회 실행 후 종료하세요."
}

install_python_runtime_packages() {
  local venv_path
  local py_bootstrap
  venv_path="$(pwd)/.venv"

  if [[ "$OS_KIND" == "macos" ]]; then
    py_bootstrap="/opt/homebrew/bin/python3.12"
  else
    py_bootstrap="python3"
  fi

  if [[ ! -x "$venv_path/bin/python3" ]]; then
    log "Creating shared venv: $venv_path"
    run "$py_bootstrap" -m venv "$venv_path"
  else
    log "Using existing venv: $venv_path"
  fi

  run "$venv_path/bin/python3" -m pip install --upgrade pip

  log "Installing Python runtime dependencies (video/audio base)"
  run "$venv_path/bin/python3" -m pip install "numpy<2" "opencv-python>=4.10.0.84,<4.13.0" mediapipe==0.10.14 pyvirtualcam==0.14.0 sounddevice

  log "Installing noise-cancel dependencies"
  # rnnoise Python wrapper is currently not published on default PyPI index in a stable package.
  log "WARN: rnnoise install is skipped (package availability issue). denoise backend remains placeholder."
  # deepfilternet is Linux-only in our current policy.
  if [[ "$OS_KIND" == "linux" ]]; then
    log "Installing deepfilternet without dependency churn"
    if ! run "$venv_path/bin/python3" -m pip install --no-deps deepfilternet; then
      log "WARN: deepfilternet install failed. denoise.backend=deepfilternet runtime may be unavailable."
    fi
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
  install_v4l2loopback
  install_python_runtime_packages
  verify_host_contract
  log "Host dependency setup completed"
}

main "$@"
