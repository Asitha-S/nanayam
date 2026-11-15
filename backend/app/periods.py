"""Query-parameter periods: start_date / end_date each default to today (the backend clock)."""
from datetime import date

from . import clock, errors


def resolve(start_date: date | None, end_date: date | None) -> tuple[date, date]:
    end = end_date or clock.today()
    start = start_date or end
    if end < start:
        raise errors.validation_error("end_date is before start_date", field="end_date")
    return start, end
