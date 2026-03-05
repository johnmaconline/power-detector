##########################################################################################
#
# Script name: probes.py
#
# Description: Probe implementations for power sentinel and WAN checks.
#
# Author: John Macdonald
#
##########################################################################################

import socket
import time
from typing import List, Tuple

import requests

from detector.models import ProbeResult


class ShellyHttpProbe:
    '''Probe Shelly status endpoints to infer device availability.'''

    def __init__(self, host: str, timeout_seconds: int = 2):
        self.host = host
        self.timeout_seconds = timeout_seconds
        self.urls = [
            f'http://{host}/rpc/Shelly.GetStatus',
            f'http://{host}/status',
        ]

    def check(self) -> ProbeResult:
        '''Perform one HTTP check against known Shelly status endpoints.'''
        started = time.monotonic()
        last_error = 'unreachable'

        for url in self.urls:
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
