#!/usr/bin/env python3
##########################################################################################
#
# Script name: find_shelly.py
#
# Description: Scan IP targets and identify devices, including Shelly hosts,
#              with hostname, MAC, ports, and Shelly metadata.
#
# Author: John Macdonald
#
##########################################################################################

import argparse
import concurrent.futures
import ipaddress
import json
import platform
import re
import socket
import subprocess
import time
from typing import Dict, List, Optional, Tuple

import requests


def _ping_host(ip: str, timeout_seconds: float) -> Tuple[bool, int]:
    '''Ping a host once and return reachability with latency milliseconds.'''
    system = platform.system().lower()

    if system == 'windows':
        timeout_ms = max(100, int(timeout_seconds * 1000))
        cmd = ['ping', '-n', '1', '-w', str(timeout_ms), ip]
    elif system == 'darwin':
        cmd = ['ping', '-c', '1', '-t', '1', ip]
    else:
        cmd = ['ping', '-c', '1', '-W', str(max(1, int(timeout_seconds))), ip]

    started = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=max(1.0, timeout_seconds + 0.5),
            check=False,
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        return result.returncode == 0, latency_ms
    except (subprocess.TimeoutExpired, OSError):
        latency_ms = int((time.monotonic() - started) * 1000)
        return False, latency_ms


def _resolve_hostname(ip: str) -> str:
    '''Resolve reverse DNS hostname if available.'''
    try:
        host, _, _ = socket.gethostbyaddr(ip)
        return host
    except (socket.herror, socket.gaierror, OSError):
        return '-'


def _lookup_mac(ip: str) -> str:
    '''Read MAC from local ARP cache when available.'''
    try:
        output = subprocess.check_output(
            ['arp', '-an', ip],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return '-'

    pattern = re.compile(r'([0-9a-f]{2}[:-]){5}[0-9a-f]{2}', re.IGNORECASE)
    match = pattern.search(output)
    if not match:
        return '-'
    return match.group(0).lower().replace('-', ':')


def _check_ports(ip: str, ports: List[int], timeout_seconds: float) -> List[int]:
    '''Return list of open TCP ports from the requested probe set.'''
    open_ports: List[int] = []
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_seconds)
        try:
            status = sock.connect_ex((ip, port))
            if status == 0:
                open_ports.append(port)
        except OSError:
            pass
        finally:
            sock.close()
    return open_ports


def _probe_shelly(ip: str, timeout_seconds: float) -> Optional[Dict[str, str]]:
    '''Try common Shelly endpoints and return metadata when matched.'''
    endpoints = [
        '/rpc/Shelly.GetDeviceInfo',
        '/rpc/Shelly.GetStatus',
        '/shelly',
        '/status',
    ]

    for endpoint in endpoints:
        url = f'http://{ip}{endpoint}'
        try:
            response = requests.get(url, timeout=timeout_seconds)
            if response.status_code != 200:
                continue
        except requests.RequestException:
            continue

        text = response.text.strip()
        parsed = None
        try:
            parsed = response.json()
        except json.JSONDecodeError:
            parsed = None

        blob = (json.dumps(parsed) if parsed is not None else text).lower()
        if 'shelly' not in blob and 'gen' not in blob and endpoint != '/status':
            continue

        details = {
            'endpoint': endpoint,
            'model': '-',
            'generation': '-',
            'name': '-',
            'device_id': '-',
            'firmware': '-',
        }

        if isinstance(parsed, dict):
            details['model'] = str(
                parsed.get('model')
                or parsed.get('type')
                or parsed.get('device', {}).get('type')
                or '-'
            )
            details['generation'] = str(
                parsed.get('gen')
                or parsed.get('generation')
                or parsed.get('device', {}).get('gen')
                or '-'
            )
            details['name'] = str(
                parsed.get('name')
                or parsed.get('device', {}).get('name')
                or '-'
            )
            details['device_id'] = str(
                parsed.get('id')
                or parsed.get('mac')
                or parsed.get('device', {}).get('id')
                or '-'
            )
            details['firmware'] = str(
                parsed.get('fw_id')
                or parsed.get('fw')
                or parsed.get('app')
                or '-'
            )
        else:
            details['model'] = 'shelly-unknown'

        return details

    return None


def _parse_ports(value: str) -> List[int]:
    '''Parse comma-separated TCP port list.'''
    ports: List[int] = []
    for token in value.split(','):
        token = token.strip()
        if not token:
            continue
        port = int(token)
        if port < 1 or port > 65535:
            raise ValueError(f'Invalid port: {token}')
        ports.append(port)

    if len(ports) == 0:
        raise ValueError('At least one TCP port is required in --ports.')
    return ports


def _targets_from_spec(spec: str) -> List[str]:
    '''Expand one target spec to host IPs.

    Supported formats:
    - CIDR: 192.168.1.0/24
    - Range: 192.168.1.10-192.168.2.200
    - Single IP: 192.168.1.50
    '''
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


def _build_target_list(raw_targets: List[str], max_hosts: int) -> List[str]:
    '''Expand all target specs and enforce host-count safety limit.'''
    if len(raw_targets) == 0:
        raise ValueError('Provide at least one --target (CIDR, range, or IP).')

    expanded = []
    seen = set()

    for target in raw_targets:
        for ip in _targets_from_spec(target):
            if ip in seen:
                continue
            seen.add(ip)
            expanded.append(ip)
            if len(expanded) > max_hosts:
                raise ValueError(
                    f'Target size exceeded --max-hosts ({max_hosts}). '
                    f'Increase --max-hosts to continue.')

    return expanded


def _probe_host(ip: str, ping_timeout: float, http_timeout: float, ports: List[int]) -> Optional[Dict[str, str]]:
    '''Probe one host for identity and return record if any signal is found.'''
    ping_ok, ping_ms = _ping_host(ip, ping_timeout)
    open_ports = _check_ports(ip, ports, ping_timeout)
    shelly_info = _probe_shelly(ip, http_timeout)

    reachable = ping_ok or len(open_ports) > 0 or shelly_info is not None
    if not reachable:
        return None

    hostname = _resolve_hostname(ip)
    mac = _lookup_mac(ip)

    device_type = 'shelly' if shelly_info else 'unknown'

    record = {
        'ip': ip,
        'hostname': hostname,
        'mac': mac,
        'ping_ms': str(ping_ms) if ping_ok else '-',
        'open_ports': ','.join(str(port) for port in open_ports) if open_ports else '-',
        'device_type': device_type,
        'shelly_endpoint': '-',
        'shelly_model': '-',
        'shelly_gen': '-',
        'shelly_name': '-',
        'shelly_id': '-',
        'shelly_fw': '-',
    }

    if shelly_info:
        record['shelly_endpoint'] = shelly_info['endpoint']
        record['shelly_model'] = shelly_info['model']
        record['shelly_gen'] = shelly_info['generation']
        record['shelly_name'] = shelly_info['name']
        record['shelly_id'] = shelly_info['device_id']
        record['shelly_fw'] = shelly_info['firmware']

    return record


def main():
    parser = argparse.ArgumentParser(
        description='Discover reachable devices and identify Shelly hosts.')
    parser.add_argument(
        '--target',
        action='append',
        default=[],
        help='Target spec: CIDR, range, or single IP. Repeatable.')
    parser.add_argument(
        '--subnet',
        action='append',
        default=[],
        help='Alias for --target when using CIDR blocks.')
    parser.add_argument(
        '--ping-timeout',
        type=float,
        default=1.0,
        help='Ping/connect timeout in seconds.')
    parser.add_argument(
        '--http-timeout',
        type=float,
        default=0.6,
        help='HTTP timeout for Shelly endpoint checks.')
    parser.add_argument(
        '--ports',
        default='22,80,443',
        help='Comma-separated TCP ports to check for reachability metadata.')
    parser.add_argument(
        '--workers',
        type=int,
        default=128,
        help='Concurrent worker count.')
    parser.add_argument(
        '--max-hosts',
        type=int,
        default=65536,
        help='Safety cap for expanded targets.')
    parser.add_argument(
        '--json',
        action='store_true',
        help='Emit full records as JSON instead of table output.')

    args = parser.parse_args()

    try:
        ports = _parse_ports(args.ports)
    except ValueError as exc:
        raise SystemExit(f'Invalid --ports: {exc}') from exc

    raw_targets = args.target + args.subnet

    try:
        hosts = _build_target_list(raw_targets, args.max_hosts)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(f'Scanning {len(hosts)} hosts...')
    records: List[Dict[str, str]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(_probe_host, ip, args.ping_timeout, args.http_timeout, ports)
            for ip in hosts
        ]
        for future in concurrent.futures.as_completed(futures):
            record = future.result()
            if record is not None:
                records.append(record)

    if len(records) == 0:
        print('No reachable devices found in provided targets.')
        return

    records = sorted(records, key=lambda item: tuple(int(part) for part in item['ip'].split('.')))

    if args.json:
        print(json.dumps(records, indent=2))
        return

    print('')
    print('Discovered devices:')
    print('IP Address        Hostname                          MAC Address           Ping  Ports      Type')
    print('---------------  --------------------------------  ------------------  ----  ---------  -------')

    shelly_records = []

    for item in records:
        print(
            f"{item['ip']:<15}  "
            f"{item['hostname']:<32}  "
            f"{item['mac']:<18}  "
            f"{item['ping_ms']:<4}  "
            f"{item['open_ports']:<9}  "
            f"{item['device_type']}"
        )
        if item['device_type'] == 'shelly':
            shelly_records.append(item)

    print('')
    print(f'Total reachable devices: {len(records)}')
    print(f'Shelly devices detected: {len(shelly_records)}')

    if len(shelly_records) > 0:
        print('')
        print('Shelly details:')
        print('IP Address        Hostname                          Model                Gen  Name                 Device ID            Endpoint                    FW')
        print('---------------  --------------------------------  -------------------  ---  -------------------  -------------------  -------------------------  ----------------')
        for item in shelly_records:
            print(
                f"{item['ip']:<15}  "
                f"{item['hostname']:<32}  "
                f"{item['shelly_model'][:19]:<19}  "
                f"{item['shelly_gen'][:3]:<3}  "
                f"{item['shelly_name'][:19]:<19}  "
                f"{item['shelly_id'][:19]:<19}  "
                f"{item['shelly_endpoint'][:25]:<25}  "
                f"{item['shelly_fw'][:16]}"
            )


if __name__ == '__main__':
    main()
