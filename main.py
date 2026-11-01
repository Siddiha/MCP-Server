from mcp.server.fastmcp import FastMCP
from datetime import date
from pydantic import BaseModel, Field
from pathlib import Path
from typing import List
import json
import logging
import os
import sys

# Logs go to stderr. Never print to stdout: with the stdio transport,
# stdout carries the MCP protocol messages and stray output breaks the client.
logging.basicConfig(
    stream=sys.stderr,
    level=os.environ.get("LEAVE_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("LeaveManager")

# Where leave data is saved between server restarts.
# Set LEAVE_DATA_FILE to keep the data somewhere else (tests use this).
DATA_FILE = Path(
    os.environ.get("LEAVE_DATA_FILE", Path(__file__).parent / "leave_data.json")
)

# Sample data, used only when no saved file exists yet
DEFAULT_LEAVES = {
    "E001": {"balance": 18, "history": ["2024-12-25", "2025-01-01"]},
    "E002": {"balance": 20, "history": []}
}

def load_leaves() -> dict:
    """Read leave data from the file, or start from the sample data"""
    if DATA_FILE.exists():
        log.info("Loading leave data from %s", DATA_FILE)
        return json.loads(DATA_FILE.read_text())
    log.info("No data file at %s, starting from sample data", DATA_FILE)
    return json.loads(json.dumps(DEFAULT_LEAVES))

def save_leaves() -> None:
    """Write the current leave data to the file"""
    DATA_FILE.write_text(json.dumps(employee_leaves, indent=2))
    log.info("Saved leave data to %s", DATA_FILE)

employee_leaves = load_leaves()

# Create MCP server
mcp = FastMCP("LeaveManager")


# Tools return these models, so the client gets structured JSON it can use,
# not a sentence it has to read.
class LeaveBalance(BaseModel):
    """How much leave an employee has left"""
    employee_id: str
    balance: int = Field(description="Leave days still available")
    days_taken: int = Field(description="Leave days already booked")


class LeaveApplication(BaseModel):
    """The result of applying for leave"""
    employee_id: str
    dates_applied: list[str]
    days_used: int
    remaining_balance: int


class LeaveHistory(BaseModel):
    """Every leave date an employee has booked"""
    employee_id: str
    dates: list[str]
    days_taken: int


class LeaveCancellation(BaseModel):
    """The result of cancelling leave"""
    employee_id: str
    dates_cancelled: list[str]
    days_refunded: int
    remaining_balance: int


class Employee(BaseModel):
    """An employee record"""
    employee_id: str
    balance: int
    days_taken: int


class DateAvailability(BaseModel):
    """Whether one date can still be booked"""
    leave_date: str
    available: bool
    reason: str


class AvailabilityReport(BaseModel):
    """Which of the requested dates are free"""
    employee_id: str
    dates: list[DateAvailability]
    all_available: bool


def get_employee(employee_id: str) -> dict:
    """Look up an employee, or raise an error the client can see"""
    data = employee_leaves.get(employee_id)
    if data is None:
        raise ValueError(f"Employee '{employee_id}' not found.")
    return data


def check_dates(leave_dates: list[str]) -> None:
    """Raise an error if any date is unusable. Returns nothing when all are fine."""
    if not leave_dates:
        raise ValueError("Give at least one date.")

    for leave_date in leave_dates:
        try:
            parsed = date.fromisoformat(leave_date)
        except ValueError:
            raise ValueError(f"Invalid date '{leave_date}'. Use the format YYYY-MM-DD.")
        if parsed < date.today():
            raise ValueError(f"Cannot apply leave for a past date: {leave_date}.")

    if len(set(leave_dates)) != len(leave_dates):
        raise ValueError("Duplicate dates in your request. List each date once.")


# Tool: Check Leave Balance
@mcp.tool()
def get_leave_balance(employee_id: str) -> LeaveBalance:
    """Check how many leave days are left for the employee"""
    data = get_employee(employee_id)
    return LeaveBalance(
        employee_id=employee_id,
        balance=data["balance"],
        days_taken=len(data["history"]),
    )


# Tool: Apply for Leave with specific dates
@mcp.tool()
def apply_leave(employee_id: str, leave_dates: list[str]) -> LeaveApplication:
    """Apply leave for specific dates (e.g., ["2026-11-17", "2026-12-01"])"""
    data = get_employee(employee_id)
    check_dates(leave_dates)

    # The same date can't be booked twice across requests
    history = data["history"]
    already_taken = [d for d in leave_dates if d in history]
    if already_taken:
        raise ValueError(f"Leave already applied for: {', '.join(already_taken)}.")

    requested_days = len(leave_dates)
    if data["balance"] < requested_days:
        raise ValueError(
            f"Insufficient leave balance. You requested {requested_days} day(s) "
            f"but have only {data['balance']}."
        )

    # Deduct balance and add to history
    data["balance"] -= requested_days
    history.extend(leave_dates)
    save_leaves()
    log.info("%s applied for %d day(s)", employee_id, requested_days)

    return LeaveApplication(
        employee_id=employee_id,
        dates_applied=sorted(leave_dates),
        days_used=requested_days,
        remaining_balance=data["balance"],
    )


# Tool: Leave history
@mcp.tool()
def get_leave_history(employee_id: str) -> LeaveHistory:
    """Get leave history for the employee"""
    data = get_employee(employee_id)
    return LeaveHistory(
        employee_id=employee_id,
        dates=sorted(data["history"]),
        days_taken=len(data["history"]),
    )


# Tool: Cancel leave that was already applied for
@mcp.tool()
def cancel_leave(employee_id: str, leave_dates: list[str]) -> LeaveCancellation:
    """Cancel leave for dates the employee already booked, and refund the days"""
    data = get_employee(employee_id)

    if not leave_dates:
        raise ValueError("Give at least one date.")
    if len(set(leave_dates)) != len(leave_dates):
        raise ValueError("Duplicate dates in your request. List each date once.")

    history = data["history"]
    not_booked = [d for d in leave_dates if d not in history]
    if not_booked:
        raise ValueError(f"No leave booked on: {', '.join(not_booked)}.")

    for leave_date in leave_dates:
        history.remove(leave_date)
    data["balance"] += len(leave_dates)
    save_leaves()
    log.info("%s cancelled %d day(s)", employee_id, len(leave_dates))

    return LeaveCancellation(
        employee_id=employee_id,
        dates_cancelled=sorted(leave_dates),
        days_refunded=len(leave_dates),
        remaining_balance=data["balance"],
    )


# Tool: Add a new employee
@mcp.tool()
def add_employee(employee_id: str, balance: int = 20) -> Employee:
    """Add a new employee with a starting leave balance"""
    employee_id = employee_id.strip()
    if not employee_id:
        raise ValueError("Employee ID cannot be empty.")
    if employee_id in employee_leaves:
        raise ValueError(f"Employee '{employee_id}' already exists.")
    if balance < 0:
        raise ValueError("Starting balance cannot be negative.")

    employee_leaves[employee_id] = {"balance": balance, "history": []}
    save_leaves()
    log.info("Added employee %s with %d day(s)", employee_id, balance)

    return Employee(employee_id=employee_id, balance=balance, days_taken=0)


# Tool: Check dates before applying
@mcp.tool()
def check_availability(employee_id: str, leave_dates: list[str]) -> AvailabilityReport:
    """Check whether dates can be booked, without applying for them"""
    data = get_employee(employee_id)
    if not leave_dates:
        raise ValueError("Give at least one date.")

    history = data["history"]
    seen: set[str] = set()
    results = []
    for leave_date in leave_dates:
        try:
            parsed = date.fromisoformat(leave_date)
        except ValueError:
            reason = "Not a valid date. Use the format YYYY-MM-DD."
        else:
            if parsed < date.today():
                reason = "This date is in the past."
            elif leave_date in history:
                reason = "Leave is already booked on this date."
            elif leave_date in seen:
                reason = "This date is listed twice in the request."
            else:
                reason = "Available."
        seen.add(leave_date)
        results.append(
            DateAvailability(
                leave_date=leave_date,
                available=reason == "Available.",
                reason=reason,
            )
        )

    free_days = sum(1 for r in results if r.available)
    all_available = free_days == len(results) and free_days <= data["balance"]

    return AvailabilityReport(
        employee_id=employee_id,
        dates=results,
        all_available=all_available,
    )


# Resource: Greeting
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}! How can I assist you with leave management today?"


if __name__ == "__main__":
    mcp.run()
