import os

from detector.config import load_env_file


def test_load_env_file_loads_quoted_values(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text(
        """
# comment
POWER_DETECTOR_SMTP_PASSWORD='abc-123'
export ANOTHER_SECRET="hello"
INVALID LINE
        """.strip(),
        encoding='utf-8',
    )

    monkeypatch.delenv('POWER_DETECTOR_SMTP_PASSWORD', raising=False)
    monkeypatch.delenv('ANOTHER_SECRET', raising=False)

    loaded_count = load_env_file(str(env_file))

    assert loaded_count == 2
    assert os.environ['POWER_DETECTOR_SMTP_PASSWORD'] == 'abc-123'
    assert os.environ['ANOTHER_SECRET'] == 'hello'


def test_load_env_file_does_not_override_existing_by_default(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text("POWER_DETECTOR_SMTP_PASSWORD='new-value'", encoding='utf-8')

    monkeypatch.setenv('POWER_DETECTOR_SMTP_PASSWORD', 'old-value')

    loaded_count = load_env_file(str(env_file), override=False)

    assert loaded_count == 0
    assert os.environ['POWER_DETECTOR_SMTP_PASSWORD'] == 'old-value'
