"""Tests for the LeaveManager MCP server.

Run them with:  pytest -q

Each test gets a fresh data file in a temporary folder, so the tests never
touch the real leave_data.json.
"""
from datetime import date, timedelta
import importlib
import json

import pytest


@pytest.fixture
def server(tmp_path, monkeypatch):
    """A freshly loaded server whose data file lives in a temp folder"""
    monkeypatch.setenv("LEAVE_DATA_FILE", str(tmp_path / "leave_data.json"))
    import main
    return importlib.reload(main)


def future_date(days_ahead: int = 30) -> str:
    return (date.today() + timedelta(days=days_ahead)).isoformat()


# --- get_leave_balance ---

def test_balance_for_known_employee(server):
    result = server.get_leave_balance("E001")
    assert result.balance == 18
    assert result.days_taken == 2


def test_balance_for_unknown_employee_raises(server):
    with pytest.raises(ValueError, match="not found"):
        server.get_leave_balance("NOPE")


# --- apply_leave ---

def test_apply_leave_deducts_balance(server):
    result = server.apply_leave("E002", [future_date(10), future_date(11)])
    assert result.days_used == 2
    assert result.remaining_balance == 18


def test_apply_leave_rejects_empty_list(server):
    with pytest.raises(ValueError, match="at least one date"):
        server.apply_leave("E002", [])


def test_apply_leave_rejects_invalid_date(server):
    with pytest.raises(ValueError, match="Invalid date"):
        server.apply_leave("E002", ["hello"])


def test_apply_leave_rejects_past_date(server):
    with pytest.raises(ValueError, match="past date"):
        server.apply_leave("E002", ["2020-01-01"])


def test_apply_leave_rejects_duplicates_in_one_request(server):
    repeated = future_date(12)
    with pytest.raises(ValueError, match="Duplicate dates"):
        server.apply_leave("E002", [repeated, repeated])


def test_apply_leave_rejects_date_already_booked(server):
    booked = future_date(13)
    server.apply_leave("E002", [booked])
    with pytest.raises(ValueError, match="already applied"):
        server.apply_leave("E002", [booked])


def test_apply_leave_rejects_more_days_than_balance(server):
    too_many = [future_date(d) for d in range(1, 25)]
    with pytest.raises(ValueError, match="Insufficient leave balance"):
        server.apply_leave("E002", too_many)


def test_apply_leave_saves_to_disk(server):
    server.apply_leave("E002", [future_date(14)])
    saved = json.loads(server.DATA_FILE.read_text())
    assert saved["E002"]["balance"] == 19


def test_balance_is_unchanged_when_apply_fails(server):
    before = server.get_leave_balance("E002").balance
    with pytest.raises(ValueError):
        server.apply_leave("E002", ["2020-01-01"])
    assert server.get_leave_balance("E002").balance == before


# --- cancel_leave ---

def test_cancel_leave_refunds_days(server):
    booked = future_date(15)
    server.apply_leave("E002", [booked])
    result = server.cancel_leave("E002", [booked])
    assert result.days_refunded == 1
    assert result.remaining_balance == 20
    assert server.get_leave_history("E002").dates == []


def test_cancel_leave_rejects_unbooked_date(server):
    with pytest.raises(ValueError, match="No leave booked"):
        server.cancel_leave("E002", [future_date(16)])


# --- add_employee ---

def test_add_employee(server):
    result = server.add_employee("E999", balance=5)
    assert result.balance == 5
    assert server.get_leave_balance("E999").balance == 5


def test_add_employee_rejects_existing_id(server):
    with pytest.raises(ValueError, match="already exists"):
        server.add_employee("E001")


def test_add_employee_rejects_empty_id(server):
    with pytest.raises(ValueError, match="cannot be empty"):
        server.add_employee("   ")


def test_add_employee_rejects_negative_balance(server):
    with pytest.raises(ValueError, match="negative"):
        server.add_employee("E998", balance=-1)


# --- check_availability ---

def test_check_availability_flags_each_problem(server):
    booked = future_date(17)
    server.apply_leave("E002", [booked])
    report = server.check_availability(
        "E002", [booked, "2020-01-01", "nope", future_date(18)]
    )
    assert [d.available for d in report.dates] == [False, False, False, True]
    assert report.all_available is False


def test_check_availability_all_free(server):
    report = server.check_availability("E002", [future_date(19), future_date(20)])
    assert report.all_available is True


def test_check_availability_does_not_change_balance(server):
    before = server.get_leave_balance("E002").balance
    server.check_availability("E002", [future_date(21)])
    assert server.get_leave_balance("E002").balance == before


# --- resources ---

def test_balance_resource_returns_json(server):
    data = json.loads(server.balance_resource("E001"))
    assert data["balance"] == 18
    assert data["dates"] == ["2024-12-25", "2025-01-01"]


def test_employees_resource_lists_everyone(server):
    roster = json.loads(server.employees_resource())
    assert [e["employee_id"] for e in roster] == ["E001", "E002"]


# --- data file ---

def test_data_survives_a_restart(server):
    booked = future_date(22)
    server.apply_leave("E002", [booked])
    reloaded = importlib.reload(server)
    assert reloaded.get_leave_balance("E002").balance == 19
    assert reloaded.get_leave_history("E002").dates == [booked]
