# Power Detector

Standalone Python service that detects home power loss from a non-UPS IoT sentinel and sends SMS alerts through SMTP email-to-SMS gateways.

## Features

- Power loss alert after configurable continuous failure duration (default `60s`)
- Power restore alert after configurable stability window (default `10s`)
- Separate WAN loss/restore alerts (defaults `90s`/`20s`)
- Deduplication cooldown and optional periodic outage reminders
- Phone + carrier recipient mapping with built-in US carrier domains and custom override
- macOS mock testing path and Raspberry Pi production deployment path

## Files

- `power_detector.py`: CLI entrypoint and service loop
- `detector/`: core modules (`config`, `models`, `probes`, `state_machine`, `notifier`)
- `config.example.yaml`: full user-configurable settings template
- `deploy/systemd/power-detector.service`: Linux service unit
- `scripts/run_macos_mock.sh`: local mock-mode run helper
- `docs/clarifying-questions.md`: ongoing discovery/decision log
- `docs/session-transcript.md`: full user/assistant session transcript for historical traceability

## Quick Start (macOS local)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# edit config.yaml values for your environment
python power_detector.py --config config.yaml --mock-sentinel --mock-wan --dry-run-notify
```

## Real LAN Test (macOS)

1. Set `sentinel.host` to your Shelly IP.
2. Keep `--dry-run-notify` for no-SMTP testing or set SMTP env var for real sends.

```bash
export POWER_DETECTOR_SMTP_PASSWORD='your_password'
python power_detector.py --config config.yaml --oneshot
python power_detector.py --config config.yaml --test-notify
```

## Raspberry Pi Deployment

1. Install Raspberry Pi OS Lite and enable SSH.
2. Configure DHCP reservation + hostname.
3. Clone repo to target path (for example `/opt/power-detector`).
4. Create venv and install requirements.
5. Create `config.yaml` from `config.example.yaml`.
6. Set `POWER_DETECTOR_SMTP_PASSWORD` in service environment.
7. Install and enable systemd unit.

```bash
sudo cp deploy/systemd/power-detector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable power-detector
sudo systemctl start power-detector
sudo systemctl status power-detector
```

## Config Defaults

- `poll_interval_seconds: 10`
- `power_loss_threshold_seconds: 60`
- `power_restore_stability_seconds: 10`
- `wan_loss_threshold_seconds: 90`
- `wan_restore_stability_seconds: 20`
- `event_cooldown_seconds: 180`
- `outage_cadence_mode: single_recovery`
- `outage_reminder_interval_seconds: 1800`

## Tests

```bash
source .venv/bin/activate
pytest -q
```
