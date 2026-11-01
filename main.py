from mcp.server.fastmcp import FastMCP
from datetime import date
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

# Tool: Check Leave Balance
@mcp.tool()
def get_leave_balance(employee_id: str) -> str:
    """Check how many leave days are left for the employee"""
    data = employee_leaves.get(employee_id)
    if data:
        return f"{employee_id} has {data['balance']} leave days remaining."
    return "Employee ID not found."

# Tool: Apply for Leave with specific dates
@mcp.tool()
def apply_leave(employee_id: str, leave_dates: List[str]) -> str:
    """
    Apply leave for specific dates (e.g., ["2026-11-17", "2026-12-01"])
    """
    if employee_id not in employee_leaves:
        return "Employee ID not found."

    if not leave_dates:
        return "Please give at least one date."

    # Each date must be a real date in YYYY-MM-DD format and not in the past
    for leave_date in leave_dates:
        try:
            parsed = date.fromisoformat(leave_date)
        except ValueError:
            return f"Invalid date '{leave_date}'. Use the format YYYY-MM-DD."
        if parsed < date.today():
            return f"Cannot apply leave for a past date: {leave_date}."

    # The same date can't be listed twice in one request
    if len(set(leave_dates)) != len(leave_dates):
        return "Duplicate dates in your request. Each date can only be listed once."

    # The same date can't be booked twice across requests
    history = employee_leaves[employee_id]["history"]
    already_taken = [d for d in leave_dates if d in history]
    if already_taken:
        return f"Leave already applied for: {', '.join(already_taken)}."

    requested_days = len(leave_dates)
    available_balance = employee_leaves[employee_id]["balance"]

    if available_balance < requested_days:
        return f"Insufficient leave balance. You requested {requested_days} day(s) but have only {available_balance}."

    # Deduct balance and add to history
    employee_leaves[employee_id]["balance"] -= requested_days
    history.extend(leave_dates)
    save_leaves()
    log.info("%s applied for %d day(s)", employee_id, requested_days)

    return f"Leave applied for {requested_days} day(s). Remaining balance: {employee_leaves[employee_id]['balance']}."


# Tool: Leave history
@mcp.tool()
def get_leave_history(employee_id: str) -> str:
    """Get leave history for the employee"""
    data = employee_leaves.get(employee_id)
    if data:
        history = ', '.join(data['history']) if data['history'] else "No leaves taken."
        return f"Leave history for {employee_id}: {history}"
    return "Employee ID not found."

# Resource: Greeting
@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}! How can I assist you with leave management today?"

if __name__ == "__main__":
    mcp.run()
