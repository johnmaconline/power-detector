#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$ROOT_DIR"
CONFIG_PATH="$ROOT_DIR/config.yaml"
ENV_FILE="$ROOT_DIR/.env"
SERVICE_USER="$(id -un)"
SERVICE_GROUP="$(id -gn)"
SERVICE_NAME="power-detector"

usage() {
  echo "Usage: $0 [--repo-dir PATH] [--config PATH] [--env-file PATH] [--service-user USER] [--service-group GROUP]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-dir)
      REPO_DIR="$2"
      shift 2
      ;;
    --config)
      CONFIG_PATH="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --service-user)
      SERVICE_USER="$2"
      shift 2
      ;;
    --service-group)
      SERVICE_GROUP="$2"
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

if [[ ! -x "$REPO_DIR/.venv/bin/python" ]]; then
  echo "Missing virtual environment at $REPO_DIR/.venv. Run scripts/pi_bootstrap.sh first." >&2
  exit 1
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Config file not found: $CONFIG_PATH" >&2
  exit 1
fi

SERVICE_FILE="$(mktemp)"
trap 'rm -f "$SERVICE_FILE"' EXIT

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Power Detector Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$REPO_DIR
EnvironmentFile=-$ENV_FILE
ExecStart=$REPO_DIR/.venv/bin/python $REPO_DIR/power_detector.py --config $CONFIG_PATH
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "$SERVICE_FILE" "/etc/systemd/system/$SERVICE_NAME.service"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl --no-pager --full status "$SERVICE_NAME"
