"""Tests for settings loading."""
from pathlib import Path

from leave_manager.config import DEFAULT_DATA_FILE, load_settings


def test_defaults_when_nothing_is_set():
    settings = load_settings(env={})
    assert settings.data_file == DEFAULT_DATA_FILE
    assert settings.log_level == "INFO"
    assert settings.default_balance == 20


def test_environment_overrides_everything():
    settings = load_settings(
        env={
            "LEAVE_DATA_FILE": "/tmp/somewhere/leave.json",
            "LEAVE_LOG_LEVEL": "DEBUG",
            "LEAVE_DEFAULT_BALANCE": "30",
        }
    )
    assert settings.data_file == Path("/tmp/somewhere/leave.json")
    assert settings.log_level == "DEBUG"
    assert settings.default_balance == 30
