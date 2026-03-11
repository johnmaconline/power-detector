#!/usr/bin/env bash
set -euo pipefail

TARGET=""
REMOTE_DIR="/opt/power-detector"
SEND_TEST_NOTIFY=0
VERBOSE=0

usage() {
  echo "Usage: $0 --target USER@HOST [--remote-dir PATH] [--send-test-notify] [--verbose]" >&2
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

if [[ -z "$TARGET" ]]; then
  usage
  exit 1
fi

REMOTE_CMD="bash '$REMOTE_DIR/scripts/pi_smoke_test.sh'"
if [[ "$SEND_TEST_NOTIFY" -eq 1 ]]; then
  REMOTE_CMD+=" --send-test-notify"
fi
if [[ "$VERBOSE" -eq 1 ]]; then
  REMOTE_CMD+=" --verbose"
fi

ssh -t "$TARGET" "$REMOTE_CMD"
