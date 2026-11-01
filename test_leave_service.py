"""Tests for the leave rules and storage (no MCP involved).

Run them with:  pytest -q

Each test gets a fresh data file in a temporary folder, so the tests never
touch the real leave_data.json.
"""
from datetime import date, timedelta
import importlib
import json

import pytest


@pytest.fixture
def svc(tmp_path, monkeypatch):
    """A freshly loaded service whose data file lives in a temp folder"""
    monkeypatch.setenv("LEAVE_DATA_FILE", str(tmp_path / "leave_data.json"))
    import leave_service
    return importlib.reload(leave_service)


def future_date(days_ahead: int = 30) -> str:
    return (date.today() + timedelta(days=days_ahead)).isoformat()


# --- get_leave_balance ---

def test_balance_for_known_employee(svc):
    result = svc.get_leave_balance("E001")
    assert result.balance == 18
    assert result.days_taken == 2


def test_balance_for_unknown_employee_raises(svc):
    with pytest.raises(ValueError, match="not found"):
        svc.get_leave_balance("NOPE")


# --- apply_leave ---

def test_apply_leave_deducts_balance(svc):
    result = svc.apply_leave("E002", [future_date(10), future_date(11)])
    assert result.days_used == 2
    assert result.remaining_balance == 18


def test_apply_leave_rejects_empty_list(svc):
    with pytest.raises(ValueError, match="at least one date"):
        svc.apply_leave("E002", [])


def test_apply_leave_rejects_invalid_date(svc):
    with pytest.raises(ValueError, match="Invalid date"):
        svc.apply_leave("E002", ["hello"])


def test_apply_leave_rejects_past_date(svc):
    with pytest.raises(ValueError, match="past date"):
        svc.apply_leave("E002", ["2020-01-01"])


def test_apply_leave_rejects_duplicates_in_one_request(svc):
    repeated = future_date(12)
    with pytest.raises(ValueError, match="Duplicate dates"):
        svc.apply_leave("E002", [repeated, repeated])


def test_apply_leave_rejects_date_already_booked(svc):
    booked = future_date(13)
    svc.apply_leave("E002", [booked])
    with pytest.raises(ValueError, match="already applied"):
        svc.apply_leave("E002", [booked])


def test_apply_leave_rejects_more_days_than_balance(svc):
    too_many = [future_date(d) for d in range(1, 25)]
    with pytest.raises(ValueError, match="Insufficient leave balance"):
        svc.apply_leave("E002", too_many)


def test_apply_leave_saves_to_disk(svc):
    svc.apply_leave("E002", [future_date(14)])
    saved = json.loads(svc.DATA_FILE.read_text())
    assert saved["E002"]["balance"] == 19


def test_balance_is_unchanged_when_apply_fails(svc):
    before = svc.get_leave_balance("E002").balance
    with pytest.raises(ValueError):
        svc.apply_leave("E002", ["2020-01-01"])
    assert svc.get_leave_balance("E002").balance == before


# --- cancel_leave ---

def test_cancel_leave_refunds_days(svc):
    booked = future_date(15)
    svc.apply_leave("E002", [booked])
    result = svc.cancel_leave("E002", [booked])
    assert result.days_refunded == 1
    assert result.remaining_balance == 20
    assert svc.get_leave_history("E002").dates == []


def test_cancel_leave_rejects_unbooked_date(svc):
    with pytest.raises(ValueError, match="No leave booked"):
        svc.cancel_leave("E002", [future_date(16)])


# --- add_employee ---

def test_add_employee(svc):
    result = svc.add_employee("E999", balance=5)
    assert result.balance == 5
    assert svc.get_leave_balance("E999").balance == 5


def test_add_employee_rejects_existing_id(svc):
    with pytest.raises(ValueError, match="already exists"):
        svc.add_employee("E001")


def test_add_employee_rejects_empty_id(svc):
    with pytest.raises(ValueError, match="cannot be empty"):
        svc.add_employee("   ")


def test_add_employee_rejects_negative_balance(svc):
    with pytest.raises(ValueError, match="negative"):
        svc.add_employee("E998", balance=-1)


# --- check_availability ---

def test_check_availability_flags_each_problem(svc):
    booked = future_date(17)
    svc.apply_leave("E002", [booked])
    report = svc.check_availability(
        "E002", [booked, "2020-01-01", "nope", future_date(18)]
    )
    assert [d.available for d in report.dates] == [False, False, False, True]
    assert report.all_available is False


def test_check_availability_all_free(svc):
    report = svc.check_availability("E002", [future_date(19), future_date(20)])
    assert report.all_available is True


def test_check_availability_does_not_change_balance(svc):
    before = svc.get_leave_balance("E002").balance
    svc.check_availability("E002", [future_date(21)])
    assert svc.get_leave_balance("E002").balance == before


# --- plain data accessors ---

def test_employee_record(svc):
    data = svc.employee_record("E001")
    assert data["balance"] == 18
    assert data["dates"] == ["2024-12-25", "2025-01-01"]


def test_roster_lists_everyone(svc):
    assert [e["employee_id"] for e in svc.roster()] == ["E001", "E002"]


# --- data file ---

def test_data_survives_a_restart(svc):
    booked = future_date(22)
    svc.apply_leave("E002", [booked])
    reloaded = importlib.reload(svc)
    assert reloaded.get_leave_balance("E002").balance == 19
    assert reloaded.get_leave_history("E002").dates == [booked]
