#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET=""
REMOTE_DIR="/opt/power-detector"
CONFIG_LOCAL="$ROOT_DIR/config.yaml"
DEVICES_LOCAL="$ROOT_DIR/devices.json"
ENV_LOCAL="$ROOT_DIR/.env"
COPY_ENV=1

usage() {
  echo "Usage: $0 --target USER@HOST [--remote-dir PATH] [--config-local PATH] [--devices-local PATH] [--env-local PATH] [--skip-env]" >&2
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
    --config-local)
      CONFIG_LOCAL="$2"
      shift 2
      ;;
    --devices-local)
      DEVICES_LOCAL="$2"
      shift 2
      ;;
    --env-local)
      ENV_LOCAL="$2"
      shift 2
      ;;
    --skip-env)
      COPY_ENV=0
      shift
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

if [[ ! -f "$CONFIG_LOCAL" ]]; then
  echo "Local config file not found: $CONFIG_LOCAL" >&2
  exit 1
fi

if [[ ! -f "$DEVICES_LOCAL" ]]; then
  echo "Local device registry file not found: $DEVICES_LOCAL" >&2
  exit 1
fi

scp "$CONFIG_LOCAL" "$TARGET:$REMOTE_DIR/config.yaml"
scp "$DEVICES_LOCAL" "$TARGET:$REMOTE_DIR/devices.json"

if [[ "$COPY_ENV" -eq 1 ]]; then
  if [[ ! -f "$ENV_LOCAL" ]]; then
    echo "Local env file not found: $ENV_LOCAL" >&2
    exit 1
  fi
  scp "$ENV_LOCAL" "$TARGET:$REMOTE_DIR/.env"
  ssh "$TARGET" "chmod 600 '$REMOTE_DIR/.env'"
fi
