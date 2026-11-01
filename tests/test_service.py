"""Tests for the leave rules (no MCP involved)."""
import json

import pytest

from conftest import future_date


# --- reading ---

def test_balance_for_known_employee(service):
    result = service.get_balance("E001")
    assert result.balance == 18
    assert result.days_taken == 2


def test_balance_for_unknown_employee_raises(service):
    with pytest.raises(ValueError, match="not found"):
        service.get_balance("NOPE")


def test_employee_record(service):
    record = service.employee_record("E001")
    assert record["balance"] == 18
    assert record["dates"] == ["2024-12-25", "2025-01-01"]


def test_roster_lists_everyone(service):
    assert [e["employee_id"] for e in service.roster()] == ["E001", "E002"]


# --- apply_leave ---

def test_apply_leave_deducts_balance(service):
    result = service.apply_leave("E002", [future_date(10), future_date(11)])
    assert result.days_used == 2
    assert result.remaining_balance == 18


def test_apply_leave_rejects_empty_list(service):
    with pytest.raises(ValueError, match="at least one date"):
        service.apply_leave("E002", [])


def test_apply_leave_rejects_invalid_date(service):
    with pytest.raises(ValueError, match="Invalid date"):
        service.apply_leave("E002", ["hello"])


def test_apply_leave_rejects_past_date(service):
    with pytest.raises(ValueError, match="past date"):
        service.apply_leave("E002", ["2020-01-01"])


def test_apply_leave_rejects_duplicates_in_one_request(service):
    repeated = future_date(12)
    with pytest.raises(ValueError, match="Duplicate dates"):
        service.apply_leave("E002", [repeated, repeated])


def test_apply_leave_rejects_date_already_booked(service):
    booked = future_date(13)
    service.apply_leave("E002", [booked])
    with pytest.raises(ValueError, match="already applied"):
        service.apply_leave("E002", [booked])


def test_apply_leave_rejects_more_days_than_balance(service):
    too_many = [future_date(d) for d in range(1, 25)]
    with pytest.raises(ValueError, match="Insufficient leave balance"):
        service.apply_leave("E002", too_many)


def test_balance_is_unchanged_when_apply_fails(service):
    before = service.get_balance("E002").balance
    with pytest.raises(ValueError):
        service.apply_leave("E002", ["2020-01-01"])
    assert service.get_balance("E002").balance == before


# --- cancel_leave ---

def test_cancel_leave_refunds_days(service):
    booked = future_date(15)
    service.apply_leave("E002", [booked])
    result = service.cancel_leave("E002", [booked])
    assert result.days_refunded == 1
    assert result.remaining_balance == 20
    assert service.get_history("E002").dates == []


def test_cancel_leave_rejects_unbooked_date(service):
    with pytest.raises(ValueError, match="No leave booked"):
        service.cancel_leave("E002", [future_date(16)])


# --- add_employee ---

def test_add_employee(service):
    result = service.add_employee("E999", balance=5)
    assert result.balance == 5
    assert service.get_balance("E999").balance == 5


def test_add_employee_uses_the_default_balance(service):
    assert service.add_employee("E998").balance == 20


def test_add_employee_rejects_existing_id(service):
    with pytest.raises(ValueError, match="already exists"):
        service.add_employee("E001")


def test_add_employee_rejects_empty_id(service):
    with pytest.raises(ValueError, match="cannot be empty"):
        service.add_employee("   ")


def test_add_employee_rejects_negative_balance(service):
    with pytest.raises(ValueError, match="negative"):
        service.add_employee("E997", balance=-1)


# --- check_availability ---

def test_check_availability_flags_each_problem(service):
    booked = future_date(17)
    service.apply_leave("E002", [booked])
    report = service.check_availability(
        "E002", [booked, "2020-01-01", "nope", future_date(18)]
    )
    assert [d.available for d in report.dates] == [False, False, False, True]
    assert report.all_available is False


def test_check_availability_all_free(service):
    report = service.check_availability("E002", [future_date(19), future_date(20)])
    assert report.all_available is True


def test_check_availability_does_not_change_balance(service):
    before = service.get_balance("E002").balance
    service.check_availability("E002", [future_date(21)])
    assert service.get_balance("E002").balance == before


# --- storage ---

def test_apply_leave_saves_to_disk(service, data_file):
    service.apply_leave("E002", [future_date(14)])
    assert json.loads(data_file.read_text())["E002"]["balance"] == 19


def test_data_survives_a_restart(service, data_file):
    from leave_manager.service import LeaveService
    from leave_manager.storage import LeaveStore

    booked = future_date(22)
    service.apply_leave("E002", [booked])

    restarted = LeaveService(LeaveStore(data_file))
    assert restarted.get_balance("E002").balance == 19
    assert restarted.get_history("E002").dates == [booked]


def test_the_store_creates_its_folder(tmp_path):
    from leave_manager.service import LeaveService
    from leave_manager.storage import LeaveStore

    nested = tmp_path / "does" / "not" / "exist" / "leave_data.json"
    LeaveService(LeaveStore(nested)).add_employee("E100")
    assert nested.exists()
