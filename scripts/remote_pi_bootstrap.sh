#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

ssh "$TARGET" "sudo mkdir -p '$REMOTE_DIR' && sudo chown -R \$(id -un):\$(id -gn) '$REMOTE_DIR'"

tar \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='.pytest_cache' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='power-detector.log' \
  --exclude='config.yaml' \
  --exclude='.env' \
  -C "$ROOT_DIR" \
  -czf - . | ssh "$TARGET" "tar -xzf - -C '$REMOTE_DIR'"

ssh "$TARGET" "bash '$REMOTE_DIR/scripts/pi_bootstrap.sh'"
