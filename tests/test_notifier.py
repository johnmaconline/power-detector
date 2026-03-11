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


def test_notify_twilio_dry_run_success():
    logger = logging.getLogger('test_notify_twilio_dry_run_success')
    logger.setLevel(logging.DEBUG)

    config = _config_for_notifier()
    config['notification']['transport'] = 'twilio_sms'
    config['notification']['twilio']['account_sid'] = 'AC1234567890abcdef1234567890abcd'
    config['notification']['twilio']['auth_token_env_var'] = 'POWER_DETECTOR_TWILIO_AUTH_TOKEN'
    config['notification']['twilio']['from_number'] = '+15555550123'
    config['notification']['recipients'] = [
        {
            'phone': '5551234567',
        }
    ]
    notifier = Notifier(config, logger)

    event = AlertEvent(
        kind=EventKind.POWER_LOSS,
        started_at=0.0,
        duration_seconds=65,
        details='test',
    )

    assert notifier.notify(event, dry_run=True)


def test_notify_ntfy_dry_run_success():
    logger = logging.getLogger('test_notify_ntfy_dry_run_success')
    logger.setLevel(logging.DEBUG)

    config = _config_for_notifier()
    config['notification']['transport'] = 'ntfy_push'
    config['notification']['ntfy']['server_url'] = 'https://ntfy.sh'
    config['notification']['ntfy']['topic'] = 'demo-power-detector-topic'
    notifier = Notifier(config, logger)

    event = AlertEvent(
        kind=EventKind.POWER_LOSS,
        started_at=0.0,
        duration_seconds=65,
        details='test',
    )

    assert notifier.notify(event, dry_run=True)


def test_compose_message_includes_device_metadata():
    logger = logging.getLogger('test_compose_message_includes_device_metadata')
    logger.setLevel(logging.DEBUG)

    config = _config_for_notifier()
    notifier = Notifier(config, logger)

    event = AlertEvent(
        kind=EventKind.POWER_LOSS,
        started_at=0.0,
        duration_seconds=65,
        details='test',
        metadata={
            'device_name': 'main_power_sentinel',
            'device_id': 'C45BBE6AD7D9',
            'device_host': '192.168.1.27',
        },
    )

    message = notifier._compose_message(event, 'stormwatch')
    assert 'device=main_power_sentinel' in message
    assert 'device_id=C45BBE6AD7D9' in message
    assert 'device_host=192.168.1.27' in message
