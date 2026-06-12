#!/usr/bin/env bash

set -euo pipefail

INPUT_DEVICE=0
DRY_RUN=0
OS_KIND=""
LINUX_DISTRO_ID=""
INVOKING_USER="${SUDO_USER:-${USER:-}}"
INVOKING_GROUP=""
TENSORRT_ENGINE_URL="${AVC_TENSORRT_ENGINE_URL:-}"
TENSORRT_ENGINE_SHA256="${AVC_TENSORRT_ENGINE_SHA256:-}"
TENSORRT_ENGINE_FORCE="${AVC_TENSORRT_ENGINE_FORCE:-0}"
TENSORRT_ENGINE_PATH="${AVC_TENSORRT_ENGINE_PATH:-}"
INSTALL_WHISPER_CUDA="${AVC_INSTALL_WHISPER_CUDA:-1}"

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

Environment:
  AVC_TENSORRT_ENGINE_URL      Download serialized TensorRT engine during setup
  AVC_TENSORRT_ENGINE_PATH     Engine output path (default: ~/.avc/models/person-segmentation.engine)
  AVC_TENSORRT_ENGINE_SHA256   Optional sha256 checksum for downloaded engine
  AVC_TENSORRT_ENGINE_FORCE    Set 1 to re-download when output path already exists
  AVC_INSTALL_WHISPER_CUDA     Linux only: install CUDA runtime libs for faster-whisper (default: 1)
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
  exec sudo env \
    AVC_TENSORRT_ENGINE_URL="$TENSORRT_ENGINE_URL" \
    AVC_TENSORRT_ENGINE_PATH="$TENSORRT_ENGINE_PATH" \
    AVC_TENSORRT_ENGINE_SHA256="$TENSORRT_ENGINE_SHA256" \
    AVC_TENSORRT_ENGINE_FORCE="$TENSORRT_ENGINE_FORCE" \
    AVC_INSTALL_WHISPER_CUDA="$INSTALL_WHISPER_CUDA" \
    bash "$0" "$@"
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

install_whisper_cuda_runtime_packages() {
  if [[ "$OS_KIND" != "linux" ]]; then
    log "Whisper CUDA runtime package install skipped (non-Linux host)"
    return 0
  fi
  if [[ "$INSTALL_WHISPER_CUDA" != "1" ]]; then
    log "Whisper CUDA runtime package install skipped (AVC_INSTALL_WHISPER_CUDA=$INSTALL_WHISPER_CUDA)"
    return 0
  fi

  local venv_py
  venv_py="$(pwd)/.venv/bin/python3"
  if [[ ! -x "$venv_py" ]]; then
    fail ".venv python not found after runtime sync: $venv_py"
  fi

  log "Installing Whisper CUDA runtime libraries for faster-whisper (cuBLAS/cuDNN via pip)"
  run_as_invoking_user "$venv_py" -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
}

verify_whisper_runtime_contract() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "Dry-run mode: skipping Whisper runtime checks"
    return 0
  fi

  local venv_py
  venv_py="$(pwd)/.venv/bin/python3"
  if [[ ! -x "$venv_py" ]]; then
    fail ".venv python not found for Whisper runtime check: $venv_py"
  fi

  if ! run_as_invoking_user "$venv_py" -c "import faster_whisper" >/dev/null 2>&1; then
    fail "faster-whisper is not importable in .venv. Run ./bin/avc setup again."
  fi
  if ! run_as_invoking_user "$venv_py" -c "import transformers, sentencepiece, torch" >/dev/null 2>&1; then
    fail "Whisper translation dependencies are not importable in .venv. Run ./bin/avc setup again to install transformers, sentencepiece, and torch."
  fi

  if [[ "$OS_KIND" == "linux" ]]; then
    if ! command -v parec >/dev/null 2>&1 && ! command -v parecord >/dev/null 2>&1; then
      fail "parec/parecord is not available. Whisper input meter requires pulseaudio-utils."
    fi
    if [[ "$INSTALL_WHISPER_CUDA" == "1" ]]; then
      if ! run_as_invoking_user "$venv_py" -c "import nvidia.cublas.lib, nvidia.cudnn.lib" >/dev/null 2>&1; then
        fail "NVIDIA cuBLAS/cuDNN Python packages are not importable. Retry ./bin/avc setup or set AVC_INSTALL_WHISPER_CUDA=0 for CPU-only testing."
      fi
      log "Whisper CUDA Python packages verified (nvidia-cublas-cu12, nvidia-cudnn-cu12)"
    fi
    if command -v nvidia-smi >/dev/null 2>&1; then
      log "NVIDIA GPU detected: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1)"
    else
      warn "nvidia-smi not found. faster-whisper CUDA may fail unless NVIDIA driver/runtime is installed."
    fi
  fi
}

invoking_home_dir() {
  if [[ "$OS_KIND" == "linux" && -n "$INVOKING_USER" ]]; then
    getent passwd "$INVOKING_USER" | cut -d: -f6
    return 0
  fi
  printf '%s\n' "${HOME:-}"
}

resolve_tensorrt_engine_path() {
  if [[ -n "$TENSORRT_ENGINE_PATH" ]]; then
    printf '%s\n' "$TENSORRT_ENGINE_PATH"
    return 0
  fi
  local home_dir
  home_dir="$(invoking_home_dir)"
  if [[ -z "$home_dir" ]]; then
    fail "Cannot determine home directory for TensorRT engine path. Set AVC_TENSORRT_ENGINE_PATH."
  fi
  printf '%s\n' "$home_dir/.avc/models/person-segmentation.engine"
}

download_tensorrt_engine() {
  if [[ -z "$TENSORRT_ENGINE_URL" ]]; then
    log "TensorRT engine download skipped (AVC_TENSORRT_ENGINE_URL is not set)"
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    fail "curl is required to download TensorRT engine."
  fi
  local output_path output_dir tmp_path
  output_path="$(resolve_tensorrt_engine_path)"
  output_dir="$(dirname "$output_path")"
  tmp_path="$output_path.tmp"

  if [[ -f "$output_path" && "$TENSORRT_ENGINE_FORCE" != "1" ]]; then
    log "TensorRT engine already exists: $output_path"
    return 0
  fi

  log "Downloading TensorRT engine to $output_path"
  run_as_invoking_user mkdir -p "$output_dir"
  run_as_invoking_user curl -fL --retry 3 --connect-timeout 10 -o "$tmp_path" "$TENSORRT_ENGINE_URL"
  if [[ -n "$TENSORRT_ENGINE_SHA256" ]]; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      printf '[dry-run] %s\n' "verify sha256 $TENSORRT_ENGINE_SHA256 $tmp_path"
    else
      printf '%s  %s\n' "$TENSORRT_ENGINE_SHA256" "$tmp_path" | sha256sum -c - >/dev/null
    fi
  fi
  run_as_invoking_user mv "$tmp_path" "$output_path"
  log "TensorRT engine ready: $output_path"
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
  install_whisper_cuda_runtime_packages
  download_tensorrt_engine
  verify_host_contract
  verify_whisper_runtime_contract
  log "Host dependency setup completed"
  if [[ "$OS_KIND" == "linux" ]]; then
    log "Linux Docker host deps installed: docker, docker compose, xauth, xhost"
    log "If current user cannot run docker, add user to docker group and re-login: sudo usermod -aG docker <user>"
  fi
  log "Setup does not create virtual devices. Use config GUI for virtual camera/speaker create/remove."
}

main "$@"
