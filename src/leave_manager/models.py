"""What the tools return.

Returning models instead of sentences means MCP can publish an output
schema, and the client gets JSON it can use directly.
"""
from pydantic import BaseModel, Field


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


class LeaveCancellation(BaseModel):
    """The result of cancelling leave"""
    employee_id: str
    dates_cancelled: list[str]
    days_refunded: int
    remaining_balance: int


class LeaveHistory(BaseModel):
    """Every leave date an employee has booked"""
    employee_id: str
    dates: list[str]
    days_taken: int


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
