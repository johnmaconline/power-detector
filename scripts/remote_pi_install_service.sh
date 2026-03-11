#!/usr/bin/env bash
set -euo pipefail

TARGET=""
REMOTE_DIR="/opt/power-detector"

usage() {
  echo "Usage: $0 --target USER@HOST [--remote-dir PATH]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET="$2"
      shift 2
      ;;
    --remote-dir)
      REMOTE_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  usage
  exit 1
fi

ssh -t "$TARGET" "bash '$REMOTE_DIR/scripts/pi_install_service.sh' --repo-dir '$REMOTE_DIR' --config '$REMOTE_DIR/config.yaml' --env-file '$REMOTE_DIR/.env'"
