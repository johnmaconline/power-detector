#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "pi_bootstrap.sh must run on the Raspberry Pi (Linux)." >&2
  exit 1
fi

if ! command -v apt >/dev/null 2>&1; then
  echo "This script expects apt to be available on the Raspberry Pi." >&2
  exit 1
fi

sudo apt update
sudo apt install -y git python3 python3-venv

cd "$ROOT_DIR"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [[ ! -f config.yaml ]]; then
  cp config.example.yaml config.yaml
fi

if [[ -f .env.example && ! -f .env ]]; then
  cp .env.example .env
fi

echo "Bootstrap complete."
echo "Next:"
echo "1. Edit $ROOT_DIR/config.yaml for the Pi."
echo "2. Edit $ROOT_DIR/.env if your notification transport needs secrets."
echo "3. Run $ROOT_DIR/scripts/pi_smoke_test.sh."
