import copy
import json
import logging

from detector.config import DEFAULT_CONFIG, load_config
from detector.models import ProbeResult
from detector.probes import DeviceIdShellyProbe


def _base_probe_config(tmp_path):
    config_path = tmp_path / 'config.yaml'
    devices_path = tmp_path / 'devices.json'
    devices_path.write_text(json.dumps({
        'devices': [
            {
                'deviceid': 'C45BBE6AD7D9',
                'name': 'main_power_sentinel',
                'monitoring': True,
            },
            {
                'deviceid': '4022D8965492',
                'name': 'alternate_sentinel',
                'monitoring': False,
            },
        ]
    }))
    config_path.write_text(
        '\n'.join([
            'sentinel:',
            '  host: ""',
            '  device_id: ""',
            '  devices_file: ./devices.json',
            'discovery:',
            '  targets:',
            '    - 192.168.1.0/24',
            'notification:',
            '  transport: ntfy_push',
            '  ntfy:',
            '    server_url: https://ntfy.sh',
            '    topic: demo-topic',
        ])
    )
    return load_config(str(config_path)), devices_path


def test_device_registry_probe_reloads_active_monitored_device(tmp_path, monkeypatch):
    config, devices_path = _base_probe_config(tmp_path)
    logger = logging.getLogger('test_device_registry_probe_reloads_active_monitored_device')
    logger.setLevel(logging.DEBUG)

    host_by_device = {
        'c45bbe6ad7d9': '192.168.1.10',
        '4022d8965492': '192.168.1.11',
    }

    def fake_discover(target_specs, device_id, http_timeout, workers, max_hosts):
        return host_by_device[device_id.lower()]

    def fake_check(self):
        return ProbeResult(True, f'HTTP 200 from http://{self.host}/status', 1, 0.0)

    monkeypatch.setattr('detector.probes.discover_shelly_host_by_device_id', fake_discover)
    monkeypatch.setattr('detector.probes.ShellyHttpProbe.check', fake_check)

    probe = DeviceIdShellyProbe(copy.deepcopy(config), logger)
    first_result = probe.check()
    assert probe.last_check_metadata['monitored_devices'] == 'main_power_sentinel'
    assert probe.last_check_metadata['up_device_count'] == '1'
    assert 'main_power_sentinel' in first_result.reason

    devices_path.write_text(json.dumps({
        'devices': [
            {
                'deviceid': 'C45BBE6AD7D9',
                'name': 'main_power_sentinel',
                'monitoring': False,
            },
            {
                'deviceid': '4022D8965492',
                'name': 'alternate_sentinel',
                'monitoring': True,
            },
        ]
    }))

    second_result = probe.check()
    assert probe.last_check_metadata['monitored_devices'] == 'alternate_sentinel'
    assert probe.last_check_metadata['up_device_count'] == '1'
    assert 'alternate_sentinel' in second_result.reason


def test_device_registry_probe_accepts_multiple_monitored_devices(tmp_path, monkeypatch):
    config, devices_path = _base_probe_config(tmp_path)
    logger = logging.getLogger('test_device_registry_probe_accepts_multiple_monitored_devices')
    logger.setLevel(logging.DEBUG)

    devices_path.write_text(json.dumps({
        'devices': [
            {
                'deviceid': 'C45BBE6AD7D9',
                'name': 'main_power_sentinel',
                'monitoring': True,
            },
            {
                'deviceid': '4022D8965492',
                'name': 'alternate_sentinel',
                'monitoring': True,
            },
        ]
    }))

    host_by_device = {
        'c45bbe6ad7d9': '192.168.1.10',
        '4022d8965492': '192.168.1.11',
    }

    def fake_discover(target_specs, device_id, http_timeout, workers, max_hosts):
        return host_by_device[device_id.lower()]

    def fake_check(self):
        if self.host == '192.168.1.10':
            return ProbeResult(True, f'HTTP 200 from http://{self.host}/status', 1, 0.0)
        return ProbeResult(False, f'HTTP timeout from http://{self.host}/status', 1, 0.0)

    monkeypatch.setattr('detector.probes.discover_shelly_host_by_device_id', fake_discover)
    monkeypatch.setattr('detector.probes.ShellyHttpProbe.check', fake_check)

    probe = DeviceIdShellyProbe(copy.deepcopy(config), logger)
    result = probe.check()
    assert not result.ok
    assert probe.last_check_metadata['monitored_device_count'] == '2'
    assert probe.last_check_metadata['up_device_count'] == '1'
    assert probe.last_check_metadata['down_device_count'] == '1'
    assert 'main_power_sentinel' in probe.last_check_metadata['up_devices']
    assert 'alternate_sentinel' in probe.last_check_metadata['down_devices']
    assert 'still_up=' in result.reason
