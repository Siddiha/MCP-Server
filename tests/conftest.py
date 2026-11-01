"""Shared test fixtures.

Each test gets its own store on a temporary file, so nothing is shared
between tests and no test can touch real data.
"""
from datetime import date, timedelta

import anyio
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from leave_manager.server import create_server
from leave_manager.service import LeaveService
from leave_manager.storage import LeaveStore


@pytest.fixture
def data_file(tmp_path):
    """Where this test's leave data lives"""
    return tmp_path / "leave_data.json"


@pytest.fixture
def store(data_file):
    """A store holding the sample data, saved to a temporary file"""
    return LeaveStore(data_file)


@pytest.fixture
def service(store):
    """The leave rules, working on the temporary store"""
    return LeaveService(store)


@pytest.fixture
def server(service):
    """An MCP server wired to the temporary service"""
    return create_server(service)


@pytest.fixture
def call_server(server):
    """Run `body(client)` against a connected in-memory client session.

    Pass session arguments (logging_callback, sampling_callback) through as
    keyword arguments.
    """
    def run(body, **session_kwargs):
        async def go():
            async with create_connected_server_and_client_session(
                server._mcp_server, **session_kwargs
            ) as client:
                return await body(client)

        return anyio.run(go)

    return run


def future_date(days_ahead: int = 30) -> str:
    """A date far enough ahead to always be bookable"""
    return (date.today() + timedelta(days=days_ahead)).isoformat()
