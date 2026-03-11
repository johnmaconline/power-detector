#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="$ROOT_DIR/config.yaml"
SEND_TEST_NOTIFY=0
VERBOSE=0

usage() {
  echo "Usage: $0 [--config PATH] [--send-test-notify] [--verbose]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      CONFIG_PATH="$2"
      shift 2
      ;;
    --send-test-notify)
      SEND_TEST_NOTIFY=1
      shift
      ;;
    --verbose)
      VERBOSE=1
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

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "Virtual environment is missing. Run scripts/pi_bootstrap.sh first." >&2
  exit 1
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Config file not found: $CONFIG_PATH" >&2
  exit 1
fi

cd "$ROOT_DIR"

COMMON_ARGS=(--config "$CONFIG_PATH")
if [[ "$VERBOSE" -eq 1 ]]; then
  COMMON_ARGS+=(--verbose)
fi

"$ROOT_DIR/.venv/bin/python" power_detector.py "${COMMON_ARGS[@]}" --oneshot --dry-run-notify

if [[ "$SEND_TEST_NOTIFY" -eq 1 ]]; then
  "$ROOT_DIR/.venv/bin/python" power_detector.py "${COMMON_ARGS[@]}" --test-notify
fi
