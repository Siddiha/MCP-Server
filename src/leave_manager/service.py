"""The leave rules.

Plain Python with no MCP in sight, so it can be tested directly and reused
behind any interface. The service is handed a store, rather than reaching
for a global one, which is what lets tests give it a temporary file.
"""
from datetime import date
import logging

from .models import (
    AvailabilityReport,
    DateAvailability,
    Employee,
    LeaveApplication,
    LeaveBalance,
    LeaveCancellation,
    LeaveHistory,
)
from .rules import parse_date, validate_dates
from .storage import LeaveStore

log = logging.getLogger(__name__)

AVAILABLE = "Available."


class LeaveService:
    """Everything you can do with employee leave"""

    def __init__(self, store: LeaveStore, default_balance: int = 20):
        self.store = store
        self.default_balance = default_balance

    # --- reading ---

    def get_balance(self, employee_id: str) -> LeaveBalance:
        """How many leave days the employee has left"""
        record = self.store.get(employee_id)
        return LeaveBalance(
            employee_id=employee_id,
            balance=record["balance"],
            days_taken=len(record["history"]),
        )

    def get_history(self, employee_id: str) -> LeaveHistory:
        """Every date the employee has booked"""
        record = self.store.get(employee_id)
        return LeaveHistory(
            employee_id=employee_id,
            dates=sorted(record["history"]),
            days_taken=len(record["history"]),
        )

    def employee_record(self, employee_id: str) -> dict:
        """Balance and booked dates, as plain data for a resource"""
        record = self.store.get(employee_id)
        return {
            "employee_id": employee_id,
            "balance": record["balance"],
            "dates": sorted(record["history"]),
        }

    def roster(self) -> list[dict]:
        """Every employee with their current balance"""
        return [
            {"employee_id": employee_id, "balance": record["balance"]}
            for employee_id, record in sorted(self.store.employees().items())
        ]

    # --- changing ---

    def apply_leave(self, employee_id: str, leave_dates: list[str]) -> LeaveApplication:
        """Book leave for these dates and deduct them from the balance"""
        record = self.store.get(employee_id)
        validate_dates(leave_dates)

        history = record["history"]
        already_taken = [d for d in leave_dates if d in history]
        if already_taken:
            raise ValueError(f"Leave already applied for: {', '.join(already_taken)}.")

        requested_days = len(leave_dates)
        if record["balance"] < requested_days:
            raise ValueError(
                f"Insufficient leave balance. You requested {requested_days} day(s) "
                f"but have only {record['balance']}."
            )

        record["balance"] -= requested_days
        history.extend(leave_dates)
        self.store.save()
        log.info("%s applied for %d day(s)", employee_id, requested_days)

        return LeaveApplication(
            employee_id=employee_id,
            dates_applied=sorted(leave_dates),
            days_used=requested_days,
            remaining_balance=record["balance"],
        )

    def cancel_leave(self, employee_id: str, leave_dates: list[str]) -> LeaveCancellation:
        """Give back days the employee had booked"""
        record = self.store.get(employee_id)

        if not leave_dates:
            raise ValueError("Give at least one date.")
        if len(set(leave_dates)) != len(leave_dates):
            raise ValueError("Duplicate dates in your request. List each date once.")

        history = record["history"]
        not_booked = [d for d in leave_dates if d not in history]
        if not_booked:
            raise ValueError(f"No leave booked on: {', '.join(not_booked)}.")

        for leave_date in leave_dates:
            history.remove(leave_date)
        record["balance"] += len(leave_dates)
        self.store.save()
        log.info("%s cancelled %d day(s)", employee_id, len(leave_dates))

        return LeaveCancellation(
            employee_id=employee_id,
            dates_cancelled=sorted(leave_dates),
            days_refunded=len(leave_dates),
            remaining_balance=record["balance"],
        )

    def add_employee(self, employee_id: str, balance: int | None = None) -> Employee:
        """Add a new employee with a starting leave balance"""
        employee_id = employee_id.strip()
        balance = self.default_balance if balance is None else balance

        if not employee_id:
            raise ValueError("Employee ID cannot be empty.")
        if employee_id in self.store:
            raise ValueError(f"Employee '{employee_id}' already exists.")
        if balance < 0:
            raise ValueError("Starting balance cannot be negative.")

        self.store.create(employee_id, balance)
        self.store.save()
        log.info("Added employee %s with %d day(s)", employee_id, balance)

        return Employee(employee_id=employee_id, balance=balance, days_taken=0)

    # --- checking without changing ---

    def check_availability(
        self, employee_id: str, leave_dates: list[str]
    ) -> AvailabilityReport:
        """Say whether each date could be booked, and why not when it can't"""
        record = self.store.get(employee_id)
        if not leave_dates:
            raise ValueError("Give at least one date.")

        today = date.today()
        history = record["history"]
        seen: set[str] = set()
        results = []

        for leave_date in leave_dates:
            try:
                parsed = parse_date(leave_date)
            except ValueError:
                reason = "Not a valid date. Use the format YYYY-MM-DD."
            else:
                if parsed < today:
                    reason = "This date is in the past."
                elif leave_date in history:
                    reason = "Leave is already booked on this date."
                elif leave_date in seen:
                    reason = "This date is listed twice in the request."
                else:
                    reason = AVAILABLE
            seen.add(leave_date)
            results.append(
                DateAvailability(
                    leave_date=leave_date,
                    available=reason == AVAILABLE,
                    reason=reason,
                )
            )

        free_days = sum(1 for r in results if r.available)
        return AvailabilityReport(
            employee_id=employee_id,
            dates=results,
            all_available=free_days == len(results) and free_days <= record["balance"],
        )
