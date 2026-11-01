"""Tests for the MCP layer: tools, resources, prompts and Context.

These talk to the server through a real in-memory MCP client session, so
they cover what direct function calls cannot: schemas, tool errors,
progress notifications, log messages sent to the client, and sampling.
"""
from datetime import date, timedelta
import importlib

import anyio
import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CreateMessageResult, TextContent


@pytest.fixture
def server(tmp_path, monkeypatch):
    """A freshly loaded server whose data file lives in a temp folder"""
    monkeypatch.setenv("LEAVE_DATA_FILE", str(tmp_path / "leave_data.json"))
    import leave_service
    import main
    importlib.reload(leave_service)
    return importlib.reload(main)


def with_client(server, body, **session_kwargs):
    """Run `body(client)` against a connected client session"""
    async def go():
        async with create_connected_server_and_client_session(
            server.mcp._mcp_server, **session_kwargs
        ) as client:
            return await body(client)

    return anyio.run(go)


def future_date(days_ahead: int = 30) -> str:
    return (date.today() + timedelta(days=days_ahead)).isoformat()


# --- tool declarations ---

def test_all_tools_are_registered(server):
    async def body(client):
        return {t.name for t in (await client.list_tools()).tools}

    assert with_client(server, body) == {
        "get_leave_balance",
        "apply_leave",
        "cancel_leave",
        "get_leave_history",
        "add_employee",
        "check_availability",
        "draft_handover_note",
    }


def test_ctx_is_not_part_of_the_input_schema(server):
    async def body(client):
        tools = {t.name: t for t in (await client.list_tools()).tools}
        return tools["apply_leave"].inputSchema["properties"]

    properties = with_client(server, body)
    assert "ctx" not in properties
    assert set(properties) == {"employee_id", "leave_dates"}


def test_tools_declare_an_output_schema(server):
    async def body(client):
        tools = {t.name: t for t in (await client.list_tools()).tools}
        return tools["get_leave_balance"].outputSchema

    assert with_client(server, body) is not None


# --- calling tools ---

def test_tool_returns_structured_content(server):
    async def body(client):
        return await client.call_tool("get_leave_balance", {"employee_id": "E001"})

    result = with_client(server, body)
    assert result.isError is False
    assert result.structuredContent == {
        "employee_id": "E001",
        "balance": 18,
        "days_taken": 2,
    }


def test_bad_input_comes_back_as_a_tool_error(server):
    async def body(client):
        return await client.call_tool("get_leave_balance", {"employee_id": "NOPE"})

    result = with_client(server, body)
    assert result.isError is True
    assert "not found" in result.content[0].text


# --- Context: progress and logging ---

def test_apply_leave_reports_progress(server):
    updates = []

    async def on_progress(progress, total, message):
        updates.append((progress, total, message))

    async def body(client):
        await client.call_tool(
            "apply_leave",
            {"employee_id": "E002", "leave_dates": [future_date(5)]},
            progress_callback=on_progress,
        )

    with_client(server, body)
    assert updates == [(0.0, 2.0, "Checking dates"), (2.0, 2.0, "Saved")]


def test_apply_leave_sends_log_messages_to_the_client(server):
    messages = []

    async def on_log(params):
        messages.append(params.data)

    async def body(client):
        await client.call_tool(
            "apply_leave",
            {"employee_id": "E002", "leave_dates": [future_date(6)]},
        )

    with_client(server, body, logging_callback=on_log)
    assert any("Checking 1 date" in str(m) for m in messages)
    assert any("1 day(s) applied" in str(m) for m in messages)


# --- Context: sampling ---

def fake_model(reply: str = "Please route urgent work to the team inbox."):
    """A stand-in for the client's model"""
    async def on_sampling(context, params):
        return CreateMessageResult(
            role="assistant",
            content=TextContent(type="text", text=reply),
            model="fake-test-model",
        )

    return on_sampling


def test_draft_handover_note_asks_the_client_model(server):
    async def body(client):
        await client.call_tool(
            "apply_leave", {"employee_id": "E002", "leave_dates": [future_date(7)]}
        )
        return await client.call_tool("draft_handover_note", {"employee_id": "E002"})

    result = with_client(server, body, sampling_callback=fake_model())
    assert result.isError is False
    assert "team inbox" in result.content[0].text


def test_draft_handover_note_needs_booked_leave(server):
    async def body(client):
        return await client.call_tool("draft_handover_note", {"employee_id": "E002"})

    result = with_client(server, body, sampling_callback=fake_model())
    assert result.isError is True
    assert "no booked leave" in result.content[0].text


def test_draft_handover_note_fails_politely_without_sampling(server):
    async def body(client):
        await client.call_tool(
            "apply_leave", {"employee_id": "E002", "leave_dates": [future_date(8)]}
        )
        return await client.call_tool("draft_handover_note", {"employee_id": "E002"})

    result = with_client(server, body)
    assert result.isError is True
    assert "does not support sampling" in result.content[0].text


# --- resources and prompts ---

def test_resources_are_listed(server):
    async def body(client):
        listed = [str(r.uri) for r in (await client.list_resources()).resources]
        templates = [
            t.uriTemplate for t in (await client.list_resource_templates()).resourceTemplates
        ]
        return listed, templates

    listed, templates = with_client(server, body)
    assert "leave://employees" in listed
    assert "leave://{employee_id}/balance" in templates


def test_reading_a_leave_resource(server):
    async def body(client):
        result = await client.read_resource("leave://E001/balance")
        return result.contents[0].text

    assert '"balance": 18' in with_client(server, body)


def test_prompt_renders_with_arguments(server):
    async def body(client):
        return await client.get_prompt(
            "leave_request_email",
            {"employee_id": "E001", "leave_dates": "2026-12-24"},
        )

    prompt = with_client(server, body)
    text = prompt.messages[0].content.text
    assert "E001" in text
    assert "2026-12-24" in text
