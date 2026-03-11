#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET=""
REMOTE_DIR="/opt/power-detector"
DEVICES_LOCAL="$ROOT_DIR/devices.json"

usage() {
  echo "Usage: $0 --target USER@HOST [--remote-dir PATH] [--devices-local PATH]" >&2
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
    --devices-local)
      DEVICES_LOCAL="$2"
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

if [[ ! -f "$DEVICES_LOCAL" ]]; then
  echo "Local device registry file not found: $DEVICES_LOCAL" >&2
  exit 1
fi

scp "$DEVICES_LOCAL" "$TARGET:$REMOTE_DIR/devices.json"
