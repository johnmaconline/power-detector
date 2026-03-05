import copy

import pytest

from detector.config import (
    BUILTIN_CARRIER_GATEWAYS,
    ConfigError,
    DEFAULT_CONFIG,
    resolve_recipient_address,
)


def _base_cfg():
    config = copy.deepcopy(DEFAULT_CONFIG)
    config['sentinel']['host'] = '192.168.1.50'
    config['notification']['smtp']['host'] = 'smtp.example.com'
    config['notification']['smtp']['username'] = 'demo@example.com'
    config['notification']['smtp']['from_address'] = 'demo@example.com'
    config['notification']['recipients'] = [
        {
            'phone': '555-123-4567',
            'carrier_code': 'verizon',
        }
    ]
    return config


def test_builtin_carriers_present():
    for key in ('verizon', 'att', 'tmobile', 'uscellular'):
        assert key in BUILTIN_CARRIER_GATEWAYS


def test_resolve_recipient_builtin_carrier():
    addr = resolve_recipient_address({'phone': '(555) 123-4567', 'carrier_code': 'verizon'})
    assert addr == '5551234567@vtext.com'


def test_resolve_recipient_custom_domain():
    addr = resolve_recipient_address(
        {
            'phone': '+1 (555) 123-4567',
            'carrier_code': 'invalid',
            'custom_gateway_domain': 'sms.example.com',
        }
    )
    assert addr == '5551234567@sms.example.com'


def test_resolve_recipient_unknown_carrier_raises():
    with pytest.raises(ConfigError):
        resolve_recipient_address({'phone': '5551234567', 'carrier_code': 'unknown'})
