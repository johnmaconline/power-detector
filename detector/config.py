##########################################################################################
#
# Script name: config.py
#
# Description: Configuration loading and validation for the power detector.
#
# Author: John Macdonald
#
##########################################################################################

import copy
import os
import re
from typing import Any, Dict, List

import yaml


DEFAULT_CONFIG: Dict[str, Any] = {
    'poll_interval_seconds': 10,
    'power_loss_threshold_seconds': 60,
    'power_restore_stability_seconds': 10,
    'wan_loss_threshold_seconds': 90,
    'wan_restore_stability_seconds': 20,
    'event_cooldown_seconds': 180,
    'outage_cadence_mode': 'single_recovery',
    'outage_reminder_interval_seconds': 1800,
    'sentinel': {
        'type': 'shelly_http',
        'host': '',
        'device_id': '',
        'timeout_seconds': 2,
    },
    'discovery': {
        'targets': [],
        'workers': 128,
        'http_timeout_seconds': 0.6,
        'max_hosts': 65536,
        'refresh_seconds': 300,
    },
    'wan_probe': {
        'dns_targets': [
            '1.1.1.1',
            '8.8.8.8',
        ],
        'http_targets': [
            'https://1.1.1.1/cdn-cgi/trace',
        ],
    },
    'notification': {
        'enabled': True,
        'startup_message_enabled': True,
        'transport': 'smtp_email_to_sms',
        'smtp': {
            'host': '',
            'port': 587,
            'use_starttls': True,
            'username': '',
            'password_env_var': 'POWER_DETECTOR_SMTP_PASSWORD',
            'from_address': '',
            'max_retries': 3,
            'retry_backoff_seconds': [2, 5, 10],
            'timeout_seconds': 10,
        },
        'recipients': [],
        'events_enabled': [
            'monitoring_started',
            'power_loss',
            'power_restore',
            'wan_loss',
            'wan_restore',
        ],
    },
    'logging': {
        'file_path': './power-detector.log',
        'max_mb': 10,
        'backup_count': 3,
    },
    'mock': {
        'sentinel_sequence': 'ok:120,fail:120,ok:120',
        'wan_sequence': 'ok:300,fail:180,ok:300',
    },
}


BUILTIN_CARRIER_GATEWAYS: Dict[str, str] = {
    'verizon': 'vtext.com',
    'att': 'txt.att.net',
    'tmobile': 'tmomail.net',
    'uscellular': 'email.uscc.net',
}

_CARRIER_CODE_ALIASES: Dict[str, str] = {
    'atandt': 'att',
    'att': 'att',
    'tmobile': 'tmobile',
    'uscellular': 'uscellular',
    'verizon': 'verizon',
}


class ConfigError(Exception):
    '''Raised when configuration is invalid or incomplete.'''
    pass


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    '''Recursively merge two dictionaries.'''
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _require_int(value: Any, key: str, minimum: int = 0) -> int:
    '''Validate integer configuration values.'''
    if not isinstance(value, int):
        raise ConfigError(f'Config key {key} must be an integer.')
    if value < minimum:
        raise ConfigError(f'Config key {key} must be >= {minimum}.')
    return value


def _require_float(value: Any, key: str, minimum: float = 0.0) -> float:
    '''Validate float configuration values.'''
    if not isinstance(value, (int, float)):
        raise ConfigError(f'Config key {key} must be a number.')
    numeric = float(value)
    if numeric < minimum:
        raise ConfigError(f'Config key {key} must be >= {minimum}.')
    return numeric


def _normalize_phone(phone_raw: str) -> str:
    '''Normalize a US phone number to 10 digits for gateway delivery.'''
    digits = re.sub(r'\D', '', str(phone_raw))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) != 10:
        raise ConfigError(f'Invalid phone number for recipient: {phone_raw}')
    return digits


def _normalize_carrier_code(carrier_raw: str) -> str:
    '''Normalize carrier input strings to a built-in canonical code.'''
    cleaned = re.sub(r'[^a-z0-9]', '', str(carrier_raw).strip().lower())
    return _CARRIER_CODE_ALIASES.get(cleaned, '')


def _validate_recipients(recipients: List[Dict[str, Any]]) -> None:
    '''Validate recipient mapping records for phone+carrier configuration.'''
    if not isinstance(recipients, list) or len(recipients) == 0:
        raise ConfigError('notification.recipients must contain at least one recipient.')

    for idx, recipient in enumerate(recipients):
        if not isinstance(recipient, dict):
            raise ConfigError(f'notification.recipients[{idx}] must be a mapping.')

        if 'phone' not in recipient:
            raise ConfigError(f'notification.recipients[{idx}].phone is required.')
        _normalize_phone(recipient['phone'])

        custom_domain = str(recipient.get('custom_gateway_domain', '')).strip()
        carrier_code = _normalize_carrier_code(recipient.get('carrier_code', ''))

        if custom_domain:
            continue

        if not carrier_code:
            raise ConfigError(
                f'notification.recipients[{idx}] requires carrier_code or custom_gateway_domain.')

        if carrier_code not in BUILTIN_CARRIER_GATEWAYS:
            raise ConfigError(
                f'Unknown carrier_code {recipient.get("carrier_code", "")} '
                f'at notification.recipients[{idx}].')


def _validate(config: Dict[str, Any]) -> Dict[str, Any]:
    '''Validate full merged configuration and return normalized config.'''
    _require_int(config['poll_interval_seconds'], 'poll_interval_seconds', 1)
    _require_int(config['power_loss_threshold_seconds'], 'power_loss_threshold_seconds', 60)
    _require_int(config['power_restore_stability_seconds'], 'power_restore_stability_seconds', 1)
    _require_int(config['wan_loss_threshold_seconds'], 'wan_loss_threshold_seconds', 1)
    _require_int(config['wan_restore_stability_seconds'], 'wan_restore_stability_seconds', 1)
    _require_int(config['event_cooldown_seconds'], 'event_cooldown_seconds', 0)
    _require_int(config['outage_reminder_interval_seconds'], 'outage_reminder_interval_seconds', 60)

    if config['outage_cadence_mode'] not in ('single_recovery', 'periodic'):
        raise ConfigError('outage_cadence_mode must be single_recovery or periodic.')

    sentinel = config.get('sentinel', {})
    if sentinel.get('type') != 'shelly_http':
        raise ConfigError('sentinel.type must be shelly_http for v1.')
    sentinel_host = str(sentinel.get('host', '')).strip()
    sentinel_device_id = str(sentinel.get('device_id', '')).strip()
    if not sentinel_host and not sentinel_device_id:
        raise ConfigError('sentinel.host or sentinel.device_id is required.')
    _require_int(sentinel.get('timeout_seconds', 0), 'sentinel.timeout_seconds', 1)

    discovery = config.get('discovery', {})
    _require_int(discovery.get('workers', 0), 'discovery.workers', 1)
    _require_float(discovery.get('http_timeout_seconds', 0), 'discovery.http_timeout_seconds', 0.1)
    _require_int(discovery.get('max_hosts', 0), 'discovery.max_hosts', 1)
    _require_int(discovery.get('refresh_seconds', 0), 'discovery.refresh_seconds', 1)

    targets = discovery.get('targets', [])
    if not isinstance(targets, list):
        raise ConfigError('discovery.targets must be a list.')
    if sentinel_device_id and not sentinel_host and len(targets) == 0:
        raise ConfigError(
            'discovery.targets is required when using sentinel.device_id without sentinel.host.')

    wan_probe = config.get('wan_probe', {})
    if not wan_probe.get('dns_targets') and not wan_probe.get('http_targets'):
        raise ConfigError('At least one WAN target is required (dns_targets or http_targets).')

    notification = config.get('notification', {})
    if notification.get('transport') != 'smtp_email_to_sms':
        raise ConfigError('notification.transport must be smtp_email_to_sms for v1.')

    _validate_recipients(notification.get('recipients', []))

    smtp_cfg = notification.get('smtp', {})
    for key in ('host', 'username', 'password_env_var', 'from_address'):
        if not str(smtp_cfg.get(key, '')).strip():
            raise ConfigError(f'notification.smtp.{key} is required.')

    _require_int(smtp_cfg.get('port', 0), 'notification.smtp.port', 1)
    _require_int(smtp_cfg.get('max_retries', 0), 'notification.smtp.max_retries', 1)
    _require_int(smtp_cfg.get('timeout_seconds', 0), 'notification.smtp.timeout_seconds', 1)

    retries = smtp_cfg.get('retry_backoff_seconds', [])
    if not isinstance(retries, list) or len(retries) == 0:
        raise ConfigError('notification.smtp.retry_backoff_seconds must be a non-empty list.')
    for index, backoff in enumerate(retries):
        _require_int(backoff, f'notification.smtp.retry_backoff_seconds[{index}]', 1)

    events_enabled = notification.get('events_enabled', [])
    valid_events = {
        'monitoring_started',
        'power_loss',
        'power_restore',
        'wan_loss',
        'wan_restore',
    }
    if not set(events_enabled).issubset(valid_events):
        raise ConfigError('notification.events_enabled contains invalid event kinds.')

    return config


def load_config(config_path: str) -> Dict[str, Any]:
    '''Load YAML config from disk, merge defaults, and validate.'''
    if not os.path.exists(config_path):
        raise ConfigError(f'Config file not found: {config_path}')

    with open(config_path, 'r', encoding='utf-8') as fh:
        loaded = yaml.safe_load(fh) or {}

    if not isinstance(loaded, dict):
        raise ConfigError('Config root must be a mapping/object.')

    merged = _deep_merge(DEFAULT_CONFIG, loaded)
    return _validate(merged)


def load_env_file(env_path: str, override: bool = False) -> int:
    '''Load KEY=VALUE pairs from a dotenv-style file into os.environ.

    Returns:
        Count of variables loaded into the environment.
    '''
    if not env_path or not os.path.exists(env_path):
        return 0

    loaded_count = 0
    with open(env_path, 'r', encoding='utf-8') as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue

            if line.startswith('export '):
                line = line[7:].strip()

            if '=' not in line:
                continue

            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()

            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
                continue

            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]

            if not override and key in os.environ:
                continue

            os.environ[key] = value
            loaded_count += 1

    return loaded_count


def resolve_recipient_address(recipient: Dict[str, Any]) -> str:
    '''Map a recipient record to an email-to-SMS gateway address.'''
    phone = _normalize_phone(recipient['phone'])
    custom_domain = str(recipient.get('custom_gateway_domain', '')).strip().lower()

    if custom_domain:
        return f'{phone}@{custom_domain}'

    carrier_code = _normalize_carrier_code(recipient.get('carrier_code', ''))
    domain = BUILTIN_CARRIER_GATEWAYS.get(carrier_code)
    if not domain:
        raise ConfigError(
            f'Unknown carrier_code {recipient.get("carrier_code", "")}; '
            f'provide custom_gateway_domain.')
    return f'{phone}@{domain}'
