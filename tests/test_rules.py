"""Tests for the date checks."""
from datetime import date

import pytest

from leave_manager.rules import parse_date, validate_dates

TODAY = date(2026, 11, 1)


def test_parse_date_accepts_iso_format():
    assert parse_date("2026-11-01") == TODAY


def test_parse_date_rejects_nonsense():
    with pytest.raises(ValueError, match="Invalid date 'hello'"):
        parse_date("hello")


def test_parse_date_rejects_a_day_that_does_not_exist():
    with pytest.raises(ValueError, match="Invalid date"):
        parse_date("2026-02-30")


def test_today_is_allowed():
    validate_dates(["2026-11-01"], today=TODAY)


def test_yesterday_is_not():
    with pytest.raises(ValueError, match="past date"):
        validate_dates(["2026-10-31"], today=TODAY)


def test_empty_list_is_rejected():
    with pytest.raises(ValueError, match="at least one date"):
        validate_dates([], today=TODAY)


def test_duplicates_are_rejected():
    with pytest.raises(ValueError, match="Duplicate dates"):
        validate_dates(["2026-12-01", "2026-12-01"], today=TODAY)
