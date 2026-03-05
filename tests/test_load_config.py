import textwrap

import pytest

from detector.config import ConfigError, load_config


def test_load_config_success(tmp_path):
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(
        textwrap.dedent(
            '''
            sentinel:
              host: 192.168.1.50
            notification:
              smtp:
                host: smtp.example.com
                username: demo@example.com
                from_address: demo@example.com
              recipients:
                - phone: '5551234567'
                  carrier_code: verizon
            '''
        ).strip()
    )

    config = load_config(str(config_path))
    assert config['poll_interval_seconds'] == 10
    assert config['power_loss_threshold_seconds'] == 60


def test_load_config_missing_required_raises(tmp_path):
    config_path = tmp_path / 'config.yaml'
    config_path.write_text('sentinel:\n  host: ""\n')

    with pytest.raises(ConfigError):
        load_config(str(config_path))
