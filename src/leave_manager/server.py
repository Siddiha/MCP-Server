"""The MCP layer: tools, resources and a prompt.

`create_server` takes the service as an argument rather than building one,
so a test can pass a service backed by a temporary file and get a server
that is identical in every other way.

Tools take a `ctx: Context` argument. MCP fills it in and it never appears
in the tool's input schema. Context is how a tool talks back to the client
while it runs: log messages, progress updates, and sampling.
"""
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import SamplingMessage, TextContent
import json

from .models import (
    AvailabilityReport,
    Employee,
    LeaveApplication,
    LeaveBalance,
    LeaveCancellation,
    LeaveHistory,
)
from .service import LeaveService


def create_server(service: LeaveService) -> FastMCP:
    """Build an MCP server that works on the given service"""
    mcp = FastMCP("LeaveManager")

    # ------------------------------------------------------------ tools

    @mcp.tool()
    async def get_leave_balance(employee_id: str, ctx: Context) -> LeaveBalance:
        """Check how many leave days are left for the employee"""
        await ctx.debug(f"Looking up balance for {employee_id}")
        return service.get_balance(employee_id)

    @mcp.tool()
    async def apply_leave(
        employee_id: str, leave_dates: list[str], ctx: Context
    ) -> LeaveApplication:
        """Apply leave for specific dates (e.g., ["2026-11-17", "2026-12-01"])"""
        await ctx.info(f"Checking {len(leave_dates)} date(s) for {employee_id}")
        await ctx.report_progress(progress=0, total=2, message="Checking dates")

        result = service.apply_leave(employee_id, leave_dates)

        await ctx.report_progress(progress=2, total=2, message="Saved")
        await ctx.info(
            f"{result.days_used} day(s) applied. {result.remaining_balance} left."
        )
        return result

    @mcp.tool()
    async def cancel_leave(
        employee_id: str, leave_dates: list[str], ctx: Context
    ) -> LeaveCancellation:
        """Cancel leave for dates the employee already booked, and refund the days"""
        result = service.cancel_leave(employee_id, leave_dates)
        await ctx.info(f"Refunded {result.days_refunded} day(s) to {employee_id}.")
        return result

    @mcp.tool()
    async def get_leave_history(employee_id: str, ctx: Context) -> LeaveHistory:
        """Get leave history for the employee"""
        await ctx.debug(f"Reading history for {employee_id}")
        return service.get_history(employee_id)

    @mcp.tool()
    async def add_employee(
        employee_id: str, ctx: Context, balance: int | None = None
    ) -> Employee:
        """Add a new employee with a starting leave balance"""
        result = service.add_employee(employee_id, balance)
        await ctx.info(f"Added {result.employee_id} with {result.balance} day(s).")
        return result

    @mcp.tool()
    async def check_availability(
        employee_id: str, leave_dates: list[str], ctx: Context
    ) -> AvailabilityReport:
        """Check whether dates can be booked, without applying for them"""
        report = service.check_availability(employee_id, leave_dates)
        free = sum(1 for d in report.dates if d.available)
        await ctx.info(f"{free} of {len(report.dates)} date(s) are free.")
        return report

    @mcp.tool()
    async def draft_handover_note(employee_id: str, ctx: Context) -> str:
        """Draft a handover note for the employee's booked leave.

        This asks the *client's* model to write the note, which MCP calls
        sampling. The server never needs its own API key.
        """
        history = service.get_history(employee_id)
        if not history.dates:
            raise ValueError(f"{employee_id} has no booked leave to hand over.")

        await ctx.info(f"Asking your model to draft a note for {employee_id}.")
        question = (
            f"Write a short handover note (under 80 words) for employee "
            f"{employee_id}, who is on leave on these dates: "
            f"{', '.join(history.dates)}. Ask colleagues to route urgent work "
            f"to the team inbox. Plain text only."
        )

        try:
            answer = await ctx.session.create_message(
                messages=[
                    SamplingMessage(
                        role="user", content=TextContent(type="text", text=question)
                    )
                ],
                max_tokens=300,
            )
        except Exception as exc:  # the client may not support sampling at all
            raise ValueError(
                "This client cannot draft the note: it does not support sampling. "
                f"({exc})"
            )

        if isinstance(answer.content, TextContent):
            return answer.content.text
        raise ValueError("The client returned a non-text answer.")

    # -------------------------------------------------------- resources

    # A resource is for reading data. Use a tool when something changes.
    @mcp.resource("leave://{employee_id}/balance")
    def balance_resource(employee_id: str) -> str:
        """Leave balance and booked dates for one employee"""
        return json.dumps(service.employee_record(employee_id), indent=2)

    @mcp.resource("leave://employees")
    def employees_resource() -> str:
        """Every employee with their current balance"""
        return json.dumps(service.roster(), indent=2)

    @mcp.resource("greeting://{name}")
    def get_greeting(name: str) -> str:
        """Get a personalized greeting"""
        return f"Hello, {name}! How can I assist you with leave management today?"

    # ---------------------------------------------------------- prompts

    @mcp.prompt()
    def leave_request_email(
        employee_id: str, leave_dates: str, reason: str = "personal reasons"
    ) -> str:
        """Draft a short leave request email for these dates"""
        return (
            f"Write a short, polite leave request email.\n\n"
            f"Employee ID: {employee_id}\n"
            f"Dates requested: {leave_dates}\n"
            f"Reason: {reason}\n\n"
            f"Keep it under 120 words. Before writing, call check_availability "
            f"for these dates and mention in the email only the dates that are free."
        )

    return mcp
