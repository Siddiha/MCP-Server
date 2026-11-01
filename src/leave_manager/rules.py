"""Date checks shared by the leave rules."""
from datetime import date


def parse_date(leave_date: str) -> date:
    """Turn a YYYY-MM-DD string into a date, or raise a readable error"""
    try:
        return date.fromisoformat(leave_date)
    except ValueError:
        raise ValueError(f"Invalid date '{leave_date}'. Use the format YYYY-MM-DD.")


def validate_dates(leave_dates: list[str], today: date | None = None) -> None:
    """Raise if any date is unusable. Returns nothing when all are fine.

    `today` is a parameter so tests can pin it instead of depending on the
    clock.
    """
    today = date.today() if today is None else today

    if not leave_dates:
        raise ValueError("Give at least one date.")

    for leave_date in leave_dates:
        if parse_date(leave_date) < today:
            raise ValueError(f"Cannot apply leave for a past date: {leave_date}.")

    if len(set(leave_dates)) != len(leave_dates):
        raise ValueError("Duplicate dates in your request. List each date once.")
