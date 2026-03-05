import copy
import logging

from detector.config import DEFAULT_CONFIG
from detector.models import AlertEvent, EventKind
from detector.notifier import Notifier


def _config_for_notifier():
    config = copy.deepcopy(DEFAULT_CONFIG)
    config['sentinel']['host'] = '192.168.1.50'
    config['notification']['smtp']['host'] = 'smtp.example.com'
    config['notification']['smtp']['username'] = 'demo@example.com'
    config['notification']['smtp']['from_address'] = 'demo@example.com'
    config['notification']['recipients'] = [
        {
            'phone': '5551234567',
            'carrier_code': 'verizon',
        }
    ]
    return config


def test_notify_dry_run_success():
    logger = logging.getLogger('test_notify_dry_run_success')
    logger.setLevel(logging.DEBUG)

    config = _config_for_notifier()
    notifier = Notifier(config, logger)

    event = AlertEvent(
        kind=EventKind.POWER_LOSS,
        started_at=0.0,
        duration_seconds=65,
        details='test',
    )

    assert notifier.notify(event, dry_run=True)


def test_notify_event_disabled_is_noop_success():
    logger = logging.getLogger('test_notify_event_disabled_is_noop_success')
    logger.setLevel(logging.DEBUG)

    config = _config_for_notifier()
    config['notification']['events_enabled'] = ['wan_loss']
    notifier = Notifier(config, logger)

    event = AlertEvent(
        kind=EventKind.POWER_LOSS,
        started_at=0.0,
        duration_seconds=65,
        details='test',
    )

    assert notifier.notify(event, dry_run=True)
