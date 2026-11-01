"""Settings, read from the environment in one place."""
from dataclasses import dataclass
from pathlib import Path
import logging
import os
import sys

DEFAULT_DATA_FILE = Path.home() / ".leave_manager" / "leave_data.json"


@dataclass(frozen=True)
class Settings:
    """Everything the server can be configured with"""
    data_file: Path
    log_level: str
    default_balance: int


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build settings from environment variables"""
    env = os.environ if env is None else env
    return Settings(
        data_file=Path(env.get("LEAVE_DATA_FILE", DEFAULT_DATA_FILE)),
        log_level=env.get("LEAVE_LOG_LEVEL", "INFO"),
        default_balance=int(env.get("LEAVE_DEFAULT_BALANCE", "20")),
    )


def configure_logging(level: str) -> None:
    """Send logs to stderr.

    Never log to stdout: with the stdio transport, stdout carries the MCP
    protocol messages and stray output breaks the client.
    """
    logging.basicConfig(
        stream=sys.stderr,
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
