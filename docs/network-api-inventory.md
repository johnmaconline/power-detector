# Network API Inventory

Last updated: 2026-03-11

This inventory summarizes devices discovered on the local `192.168.1.0/24` LAN that expose usable APIs or other scriptable control surfaces.

Notes:
- IP addresses are DHCP-assigned and may change. Prefer hostnames or device identifiers where possible.
- `Confirmed` means a callable endpoint returned structured data during the scan.
- `Likely` means the device exposes an obvious programmable surface, but auth or additional path discovery is still needed.
- `Inferred` means vendor or device class was derived from page content, TLS certificate, or JS assets.

## Confirmed APIs

| IP | Hostname | Device | API Surface | Confidence | Notes |
| --- | --- | --- | --- | --- | --- |
| `192.168.1.3` | `-` | Shelly 1PM `98CDAC2F3D1B` | HTTP JSON | Confirmed | `/status`, `/shelly` |
| `192.168.1.9` | `-` | Shelly 1PM `BCFF4DFCEE58` | HTTP JSON | Confirmed | `/status`, `/shelly` |
| `192.168.1.14` | `-` | Shelly 1PM `A4CF12F3DB50` | HTTP JSON | Confirmed | `/status`, `/shelly` |
| `192.168.1.27` | `-` | Shelly 1PM `C45BBE6AD7D9` | HTTP JSON | Confirmed | `/status`, `/shelly` |
| `192.168.1.50` | `-` | Camera/NVR-style web viewer | HTTP CGI | Confirmed | `/cgi-bin/login.cgi` accepts JSON POST and returns pre-login info |
| `192.168.1.53` | `HP4CCF7C8D0F85.local` | HP DeskJet 2800 | HTTP XML / eSCL | Confirmed | `/eSCL/ScannerStatus` returns XML |
| `192.168.1.72`, `192.168.1.73` | `stormwatch.local` | Raspberry Pi `stormwatch` | SSH | Confirmed | Headless remote command/control |

## Likely Scriptable Devices

| IP | Device | Surface | Confidence | Notes |
| --- | --- | --- | --- | --- |
| `192.168.1.19` | NETGEAR Orbi | HTTP admin API behind auth | Likely | Root page returns `401 Unauthorized`, `WWW-Authenticate: Basic realm="NETGEAR Orbi"` |
| `192.168.1.20` | NETGEAR Orbi | HTTP admin API behind auth | Likely | Same fingerprint as `.19` |
| `192.168.1.25` | Linkplay / Arylic audio device | HTTP API | Likely | `httpapi.asp` responds with JSON status; web UI identified as Linkplay |
| `192.168.1.63` | Brother HL-2270DW | HTTP printer admin, IPP | Likely | Web UI confirmed; no clean status API confirmed in this pass |

## Details By Device

### Shelly 1PM devices

Confirmed devices:
- `192.168.1.3` -> `98CDAC2F3D1B`
- `192.168.1.9` -> `BCFF4DFCEE58`
- `192.168.1.14` -> `A4CF12F3DB50`
- `192.168.1.27` -> `C45BBE6AD7D9`

Useful endpoints:

```bash
curl http://192.168.1.27/status
curl http://192.168.1.27/shelly
```

Observed behavior:
- `/status` returned JSON device state
- `/shelly` returned model/device info JSON
- No auth required on the current LAN configuration

### `192.168.1.50`: camera/NVR-style web viewer

This device exposes a browser viewer titled `Web Viewer` and references a local playback plugin plus a remote installer URL:
- `https://ocx.jftechws.com/ocx/VideoPlayToolSetup.exe`

That strongly suggests an OEM camera/NVR web UI. The exact vendor name is not confirmed, but the CGI API surface is real.

Confirmed endpoint:

```bash
curl -H 'Content-Type: application/json' \
  -X POST \
  http://192.168.1.50/cgi-bin/login.cgi \
  --data '{"Name":"GetPreLoginInfo"}'
```

Observed response:

```json
{ "Ret":100, "TCPPort":34567, "Language":"SimpChinese" }
```

Other evidence:
- Port `554` is open, which is consistent with RTSP-capable camera/NVR gear.
- The web UI exposes sections labeled `Preview`, `Playback`, `Alarm`, and `Remote Setting`.

### `192.168.1.53`: HP DeskJet 2800

Confirmed endpoint:

```bash
curl http://192.168.1.53/eSCL/ScannerStatus
```

Observed behavior:
- Returned XML scanner status
- Several printer management endpoints redirect to HTTPS

This is a good candidate for read-only health/status automation.

### `192.168.1.19` and `192.168.1.20`: NETGEAR Orbi

Root response headers identified these as NETGEAR Orbi admin surfaces:

```text
WWW-Authenticate: Basic realm="NETGEAR Orbi"
```

Observed behavior:
- Root path returns `401 Unauthorized`
- Back-end headers show `uhttpd/1.0.0`
- These are scriptable only after authentication

These are likely your router / satellite management endpoints, but this scan did not enumerate authenticated JSON or RPC calls.

### `192.168.1.25`: Linkplay / Arylic audio device

This host serves a Vue-based `Web Management` UI. The TLS certificate subject identifies it as Linkplay:

```text
CN=www.linkplay.com
O=linkplay
```

The page also references `radio.arylic.com`, which fits Arylic/Linkplay audio gear.

Confirmed endpoints:

```bash
curl 'http://192.168.1.25/httpapi.asp?command=getStatusEx'
curl 'http://192.168.1.25/httpapi.asp?command=getPlayerStatus'
```

Observed behavior:
- `getStatusEx` returned JSON-like device metadata including:
  - `DeviceName: Basement SoundSystem`
  - `project: ARYLIC_A50N`
  - firmware/build details
  - MAC addresses
- `getPlayerStatus` returned player state including `status`, `Title`, `Artist`, and `vol`

Open ports observed:
- `53`, `80`, `443`, `8888`, `49152`

This is a strong automation candidate.

### `192.168.1.63`: Brother HL-2270DW

Confirmed:
- Web UI title: `Brother HL-2270DW series`
- Open ports: `23`, `53`, `80`, `631`

Likely useful surfaces:
- HTTP admin pages
- IPP on port `631`

This pass did not confirm a structured status endpoint, so treat it as likely scriptable but not yet integrated.

### `stormwatch.local`: Raspberry Pi

Confirmed access:

```bash
ssh johnmacdonald@stormwatch.local
```

This is the most flexible automation/control surface on the network because it can host arbitrary scripts, agents, and local integrations.

## Recommended Next Integrations

Highest-value devices to integrate next:
1. Linkplay / Arylic audio device on `192.168.1.25`
2. Camera/NVR device on `192.168.1.50`
3. HP printer health/status on `192.168.1.53`
4. Orbi router telemetry on `192.168.1.19` / `192.168.1.20` after authenticated endpoint discovery

## Suggested Next Steps

1. Build a small inventory scanner that stores these findings as structured JSON.
2. Add adapter modules for:
   - Shelly
   - Linkplay / Arylic
   - Camera/NVR CGI login + status
   - HP printer eSCL status
3. Add authenticated Orbi endpoint discovery only if router telemetry is worth the effort.
