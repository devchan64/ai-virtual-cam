#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$ROOT_DIR/scripts"

usage() {
  cat <<'EOF'
Usage:
  ./run-script.sh <script-name> [args...]

Examples:
  ./run-script.sh create-config.py --output config/settings.json
  ./run-script.sh install-host-deps.sh --help

Available scripts:
EOF
  find "$SCRIPTS_DIR" -maxdepth 1 -type f \( -name "*.py" -o -name "*.sh" \) -print \
    | sed "s|$SCRIPTS_DIR/|  - |" \
    | sort
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

script_name="$1"
shift || true

script_path="$SCRIPTS_DIR/$script_name"
if [[ ! -f "$script_path" ]]; then
  echo "Script not found: $script_name" >&2
  echo >&2
  usage >&2
  exit 1
fi

case "$script_path" in
  *.py) exec python3 "$script_path" "$@" ;;
  *.sh) exec bash "$script_path" "$@" ;;
  *)
    echo "Unsupported script type: $script_name" >&2
    exit 1
    ;;
esac
