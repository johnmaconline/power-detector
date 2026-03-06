##########################################################################################
#
# Script name: probes.py
#
# Description: Probe implementations for power sentinel and WAN checks.
#
# Author: John Macdonald
#
##########################################################################################

import concurrent.futures
import ipaddress
import re
import socket
import time
from typing import Dict, List, Optional, Tuple

import requests

from detector.models import ProbeResult


class ShellyHttpProbe:
    '''Probe Shelly status endpoints to infer device availability.'''

    def __init__(self, host: str, timeout_seconds: int = 2):
        self.host = host
        self.timeout_seconds = timeout_seconds

    def _urls(self) -> List[str]:
        return [
            f'http://{self.host}/rpc/Shelly.GetStatus',
            f'http://{self.host}/status',
        ]

    def check(self) -> ProbeResult:
        '''Perform one HTTP check against known Shelly status endpoints.'''
        started = time.monotonic()
        last_error = 'unreachable'

        for url in self._urls():
            try:
                response = requests.get(url, timeout=self.timeout_seconds)
                if response.status_code == 200:
                    latency_ms = int((time.monotonic() - started) * 1000)
                    return ProbeResult(True, f'HTTP 200 from {url}', latency_ms, time.monotonic())
                last_error = f'HTTP {response.status_code} from {url}'
            except requests.RequestException as exc:
                last_error = f'{url} failed: {exc}'

        latency_ms = int((time.monotonic() - started) * 1000)
        return ProbeResult(False, last_error, latency_ms, time.monotonic())


class DeviceIdShellyProbe:
    '''Probe Shelly by stable device ID, discovering current host as needed.''' 

    def __init__(self, config: Dict, logger):
        self.config = config
        self.log = logger
        self.sentinel_cfg = config.get('sentinel', {})
        self.discovery_cfg = config.get('discovery', {})
        self.device_id = _normalize_device_id(str(self.sentinel_cfg.get('device_id', '')))
        self.timeout_seconds = int(self.sentinel_cfg.get('timeout_seconds', 2))
        self.refresh_seconds = int(self.discovery_cfg.get('refresh_seconds', 300))

        # Prefer configured host initially if present.
        self.current_host = str(self.sentinel_cfg.get('host', '')).strip() or None
        self.last_discovery_at = 0.0

    def _discover(self, force: bool = False) -> bool:
        '''Discover host IP by sentinel device ID and update current host.'''
        now_ts = time.monotonic()
        if not force and self.current_host and (now_ts - self.last_discovery_at) < self.refresh_seconds:
            return True

        targets = self.discovery_cfg.get('targets', [])
        workers = int(self.discovery_cfg.get('workers', 128))
        http_timeout = float(self.discovery_cfg.get('http_timeout_seconds', 0.6))
        max_hosts = int(self.discovery_cfg.get('max_hosts', 65536))

        if not self.device_id:
            return bool(self.current_host)

        try:
            resolved_host = discover_shelly_host_by_device_id(
                target_specs=targets,
                device_id=self.device_id,
                http_timeout=http_timeout,
                workers=workers,
                max_hosts=max_hosts,
            )
        except ValueError as exc:
            self.log.error(f'Discovery configuration error: {exc}')
            self.last_discovery_at = now_ts
            return bool(self.current_host)

        self.last_discovery_at = now_ts

        if resolved_host:
            if self.current_host != resolved_host:
                self.log.info(
                    f'Resolved Shelly device_id={self.device_id} to host={resolved_host}.')
            self.current_host = resolved_host
            return True

        self.log.error(f'Could not resolve Shelly host for device_id={self.device_id}.')
        return bool(self.current_host)

    def check(self) -> ProbeResult:
        '''Probe with current host and re-discover if needed on failures.'''
        if not self.current_host:
            self._discover(force=True)

        if not self.current_host:
            return ProbeResult(False, f'No host resolved for device_id={self.device_id}', 0, time.monotonic())

        probe = ShellyHttpProbe(self.current_host, timeout_seconds=self.timeout_seconds)
        result = probe.check()
        if result.ok:
            return result

        # Probe failed; force discovery to handle DHCP changes and retry once.
        self._discover(force=True)
        if not self.current_host:
            return result

        retry_probe = ShellyHttpProbe(self.current_host, timeout_seconds=self.timeout_seconds)
        retry_result = retry_probe.check()
        if retry_result.ok:
            return retry_result

        return retry_result


class WanProbe:
    '''Probe external network using DNS socket checks and HTTP checks.'''

    def __init__(self, dns_targets: List[str], http_targets: List[str], timeout_seconds: int = 2):
        self.dns_targets = dns_targets
        self.http_targets = http_targets
        self.timeout_seconds = timeout_seconds

    def _check_dns(self) -> Tuple[bool, str]:
        for target in self.dns_targets:
            try:
                sock = socket.create_connection((target, 53), timeout=self.timeout_seconds)
                sock.close()
                return True, f'DNS TCP reachable at {target}:53'
            except OSError:
                continue
        return False, 'No DNS targets reachable'

    def _check_http(self) -> Tuple[bool, str]:
        for url in self.http_targets:
            try:
                response = requests.get(url, timeout=self.timeout_seconds)
                if response.status_code < 500:
                    return True, f'HTTP target reachable: {url} ({response.status_code})'
            except requests.RequestException:
                continue
        return False, 'No HTTP targets reachable'

    def check(self) -> ProbeResult:
        '''Perform one WAN probe cycle and return aggregated health result.'''
        started = time.monotonic()
        dns_ok, dns_reason = self._check_dns()
        http_ok, http_reason = self._check_http()

        ok = dns_ok or http_ok
        reason = f'dns={dns_reason}; http={http_reason}'
        latency_ms = int((time.monotonic() - started) * 1000)
        return ProbeResult(ok, reason, latency_ms, time.monotonic())


class MockSequenceProbe:
    '''Mock probe that replays deterministic ok/fail intervals for testing.'''

    def __init__(self, sequence: str):
        self.sequence = self._parse_sequence(sequence)
        self.started_at = time.monotonic()

    def _parse_sequence(self, sequence: str):
        parsed = []
        for segment in sequence.split(','):
            segment = segment.strip()
            if not segment:
                continue
            parts = segment.split(':')
            if len(parts) != 2:
                raise ValueError(f'Invalid mock segment: {segment}')
            state = parts[0].strip().lower()
            duration = int(parts[1].strip())
            if state not in ('ok', 'fail'):
                raise ValueError(f'Invalid mock state: {state}')
            if duration <= 0:
                raise ValueError(f'Invalid mock duration: {duration}')
            parsed.append((state, duration))

        if not parsed:
            parsed.append(('ok', 999999))

        return parsed

    def check(self) -> ProbeResult:
        '''Return current mocked probe status based on elapsed monotonic time.'''
        elapsed = int(time.monotonic() - self.started_at)
        sequence_total = sum(duration for _, duration in self.sequence)

        if sequence_total <= 0:
            sequence_total = 1

        position = elapsed % sequence_total
        cursor = 0
        state = 'ok'
        for seq_state, duration in self.sequence:
            if position < cursor + duration:
                state = seq_state
                break
            cursor += duration

        ok = state == 'ok'
        reason = f'mock sequence state={state}'
        return ProbeResult(ok, reason, 0, time.monotonic())


def _normalize_device_id(raw: str) -> str:
    '''Normalize Shelly device IDs for stable comparisons.'''
    return re.sub(r'[^a-zA-Z0-9]', '', raw or '').lower()


def _extract_shelly_device_id(payload: Dict) -> str:
    '''Extract probable device ID from known Shelly payload shapes.'''
    candidates = [
        payload.get('id'),
        payload.get('mac'),
        payload.get('device', {}).get('id') if isinstance(payload.get('device'), dict) else None,
        payload.get('sys', {}).get('mac') if isinstance(payload.get('sys'), dict) else None,
    ]

    for candidate in candidates:
        normalized = _normalize_device_id(str(candidate or ''))
        if normalized:
            return normalized

    return ''


def _probe_shelly_identity(ip: str, timeout_seconds: float) -> str:
    '''Probe Shelly identity endpoints and return normalized device ID.'''
    endpoints = [
        '/rpc/Shelly.GetDeviceInfo',
        '/shelly',
        '/status',
    ]

    for endpoint in endpoints:
        url = f'http://{ip}{endpoint}'
        try:
            response = requests.get(url, timeout=timeout_seconds)
            if response.status_code != 200:
                continue
            payload = response.json()
            if not isinstance(payload, dict):
                continue
            device_id = _extract_shelly_device_id(payload)
            if device_id:
                return device_id
        except (requests.RequestException, ValueError):
            continue

    return ''


def _targets_from_spec(spec: str) -> List[str]:
    '''Expand one target specification into IP hosts.'''
    spec = spec.strip()
    if not spec:
        return []

    if '-' in spec:
        start_raw, end_raw = spec.split('-', 1)
        start_ip = ipaddress.ip_address(start_raw.strip())
        end_ip = ipaddress.ip_address(end_raw.strip())
        if type(start_ip) is not type(end_ip):
            raise ValueError(f'IP range must be same family: {spec}')
        if int(end_ip) < int(start_ip):
            raise ValueError(f'IP range end must be >= start: {spec}')
        return [str(ipaddress.ip_address(i)) for i in range(int(start_ip), int(end_ip) + 1)]

    if '/' in spec:
        network = ipaddress.ip_network(spec, strict=False)
        return [str(ip) for ip in network.hosts()]

    return [str(ipaddress.ip_address(spec))]


def _build_targets(target_specs: List[str], max_hosts: int) -> List[str]:
    '''Expand target specs into unique hosts with limit checks.'''
    expanded: List[str] = []
    seen = set()

    for spec in target_specs:
        for host in _targets_from_spec(spec):
            if host in seen:
                continue
            seen.add(host)
            expanded.append(host)
            if len(expanded) > max_hosts:
                raise ValueError(
                    f'Target size exceeded max_hosts={max_hosts}. '
                    f'Reduce range or increase discovery.max_hosts.')

    return expanded


def discover_shelly_host_by_device_id(
    target_specs: List[str],
    device_id: str,
    http_timeout: float,
    workers: int,
    max_hosts: int,
) -> Optional[str]:
    '''Discover Shelly host for a known device ID across target specs.'''
    normalized_device_id = _normalize_device_id(device_id)
    if not normalized_device_id:
        return None

    if not isinstance(target_specs, list) or len(target_specs) == 0:
        return None

    hosts = _build_targets(target_specs, max_hosts)
    if len(hosts) == 0:
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(_probe_shelly_identity, host, http_timeout): host
            for host in hosts
        }

        for future in concurrent.futures.as_completed(future_map):
            host = future_map[future]
            try:
                candidate_id = future.result()
            except Exception:
                continue

            if candidate_id and candidate_id == normalized_device_id:
                for pending in future_map:
                    if not pending.done():
                        pending.cancel()
                return host

    return None
