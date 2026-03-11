# Raspberry Pi Deployment Procedure

This procedure assumes:

- The Raspberry Pi is reachable over SSH at `stormwatch.local`.
- You are running commands from your Mac in the local repo checkout.
- The production install path on the Pi is `/opt/power-detector`.
- You will use hostname and DHCP reservation rather than a hardcoded static IP.

## First-Time Pi Setup

1. Bootstrap the Pi and copy the repo contents:

```bash
./scripts/remote_pi_bootstrap.sh --target <pi_user>@stormwatch.local
```

2. Edit the local production config in this repo:

```bash
cp -n config.example.yaml config.yaml
```

Set at least these values in `config.yaml`:

- `sentinel.devices_file`
- `discovery.targets`
- `notification.transport`
- notification transport-specific settings such as `notification.ntfy.topic`

3. If your notification transport needs secrets, edit the local `.env`:

```bash
cp -n .env.example .env
```

4. Push `config.yaml`, `devices.json`, and optionally `.env` to the Pi:

```bash
./scripts/remote_pi_push_config.sh --target <pi_user>@stormwatch.local
```

5. Run the Pi smoke test:

```bash
./scripts/remote_pi_smoke_test.sh --target <pi_user>@stormwatch.local --send-test-notify
```

What this does:

- Runs `--oneshot --dry-run-notify` to validate probe/config startup.
- Runs `--test-notify` to verify the real notification path.

6. Install and start the `systemd` service:

```bash
./scripts/remote_pi_install_service.sh --target <pi_user>@stormwatch.local
```

7. Verify service health:

```bash
ssh <pi_user>@stormwatch.local
sudo systemctl status power-detector
journalctl -u power-detector -f
```

## Update Deployment

When you change code:

```bash
./scripts/remote_pi_bootstrap.sh --target <pi_user>@stormwatch.local
./scripts/remote_pi_smoke_test.sh --target <pi_user>@stormwatch.local
./scripts/remote_pi_install_service.sh --target <pi_user>@stormwatch.local
```

When you change only config or secrets:

```bash
./scripts/remote_pi_push_config.sh --target <pi_user>@stormwatch.local
./scripts/remote_pi_smoke_test.sh --target <pi_user>@stormwatch.local --send-test-notify
./scripts/remote_pi_install_service.sh --target <pi_user>@stormwatch.local
```

When you change only `devices.json`:

```bash
./scripts/remote_pi_push_devices.sh --target <pi_user>@stormwatch.local
```

Notes:
- No service restart is required for a pure `devices.json` change.
- The detector reloads the device registry on the next monitor loop.

## Physical Validation

After the service is running:

1. Confirm you receive the startup monitoring notification.
2. Unplug the Shelly sentinel from power.
3. Wait at least `60` seconds for the configured power-loss threshold.
4. Confirm the outage notification arrives.
5. Restore power to the Shelly sentinel.
6. Confirm the recovery notification arrives after the restore stability window.
