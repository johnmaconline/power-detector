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
    assert probe.active_device_name == 'main_power_sentinel'
    assert probe.active_device_id == 'c45bbe6ad7d9'
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
    assert probe.active_device_name == 'alternate_sentinel'
    assert probe.active_device_id == '4022d8965492'
    assert 'alternate_sentinel' in second_result.reason
