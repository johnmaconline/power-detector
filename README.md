# Power Detector

Standalone Python service that detects home power loss from a non-UPS IoT sentinel and sends SMS alerts through SMTP email-to-SMS gateways.

## Features

- Startup SMS when monitoring begins and power is confirmed
- Power loss alert after configurable continuous failure duration (default `60s`)
- Power restore alert after configurable stability window (default `10s`)
- Separate WAN loss/restore alerts (defaults `90s`/`20s`)
- Deduplication cooldown and optional periodic outage reminders
- Phone + carrier recipient mapping with built-in US carrier domains and custom override
- Free `ntfy` push notification transport
- Twilio SMS transport support for reliable direct text delivery
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

Note:
- The app auto-loads secrets from `.env` (current working directory or config file directory).
- Existing shell env vars take precedence over `.env` values.

## Real LAN Test (macOS)

1. Prefer setting `sentinel.device_id` and `discovery.targets` so DHCP IP changes are handled automatically.
2. Optional fallback: set `sentinel.host` to a stable hostname (for example `shellyplug-sensor.local`).
3. Keep `--dry-run-notify` for no-SMTP testing or set SMTP env var for real sends.

```bash
export POWER_DETECTOR_SMTP_PASSWORD='your_password'
python power_detector.py --config config.yaml --oneshot
python power_detector.py --config config.yaml --test-notify
```

To send startup monitoring SMS on normal runs, ensure:
- `notification.enabled: true`
- `notification.startup_message_enabled: true`
- `monitoring_started` exists in `notification.events_enabled`

## Twilio SMS Setup (Recommended)

Carrier email-to-SMS is increasingly unreliable. Use Twilio for direct SMS:

1. In `config.yaml`:
```yaml
notification:
  transport: twilio_sms
  twilio:
    account_sid: ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    auth_token_env_var: POWER_DETECTOR_TWILIO_AUTH_TOKEN
    from_number: '+15555550123'
    messaging_service_sid: ''
```

2. In `.env`:
```bash
POWER_DETECTOR_TWILIO_AUTH_TOKEN='your_twilio_auth_token'
```

3. Set recipients (phone only is enough for Twilio mode):
```yaml
notification:
  recipients:
    - phone: '6108238852'
```

4. Test:
```bash
python power_detector.py --config config.yaml --test-notify
```

Notes:
- Use either `from_number` or `messaging_service_sid`.
- In Twilio mode, `carrier_code` is ignored.

## ntfy Push Setup (Free)

`ntfy` is the zero-cost push option. It sends app notifications to a topic that you subscribe to from your phone.

1. Install the `ntfy` app on your phone.
2. In `config.yaml`:
```yaml
notification:
  transport: ntfy_push
  ntfy:
    server_url: https://ntfy.sh
    topic: your-unique-power-detector-topic
    token_env_var: ''
    default_priority: default
    default_tags: [zap, house]
```
3. In the `ntfy` phone app, subscribe to the same topic.
4. Test:
```bash
python power_detector.py --config config.yaml --test-notify
```

Notes:
- Pick a topic name that is hard to guess.
- Public `ntfy.sh` works without secrets, but topic privacy depends on topic uniqueness.
- Self-hosting `ntfy` is possible later if you want stronger control.

## Discover Devices (LAN)

Use the discovery script to list reachable devices, hostnames, and Shelly matches:

```bash
source .venv/bin/activate
python scripts/find_shelly.py --target 192.168.1.0/24
```

This helps you capture either:
- `sentinel.device_id` for DHCP-resilient monitoring (recommended)
- or a stable hostname for `sentinel.host`

You can scan wider ranges:

```bash
# Multiple subnets
python scripts/find_shelly.py --target 192.168.1.0/24 --target 192.168.2.0/24

# Explicit IP range
python scripts/find_shelly.py --target 192.168.0.1-192.168.3.254

# Large CIDR with raised safety cap
python scripts/find_shelly.py --target 192.168.0.0/16 --max-hosts 70000
```

Discovery output includes:
- IP address
- Hostname (reverse DNS)
- MAC address (from ARP cache, when available)
- Ping latency
- Open TCP ports from configured probe list
- Device type (`shelly` or `unknown`)
- Shelly details (model, generation, name, device id, endpoint, firmware)

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
- `notification.startup_message_enabled: true`

Production note:
- Preferred: configure `sentinel.device_id` + `discovery.targets`.
- Fallback: use hostname in `sentinel.host` instead of raw IP.

## Tests

```bash
source .venv/bin/activate
pytest -q
```
