"""England & Wales bank holidays. Edit or extend as needed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BankHoliday:
    date: date
    name: str
    # The firm keeps Christmas Day, Boxing Day and New Year's Day fixed for
    # everyone (including their substitute days); the rest may be flexed.
    flexible: bool


# Sep 2026 - Aug 2028.
_HOLIDAYS = (
    ("2026-12-25", "Christmas Day", False),
    ("2026-12-28", "Boxing Day (substitute)", False),
    ("2027-01-01", "New Year's Day", False),
    ("2027-03-26", "Good Friday", True),
    ("2027-03-29", "Easter Monday", True),
    ("2027-05-03", "Early May bank holiday", True),
    ("2027-05-31", "Spring bank holiday", True),
    ("2027-08-30", "Summer bank holiday", True),
    ("2027-12-27", "Christmas Day (substitute)", False),
    ("2027-12-28", "Boxing Day (substitute)", False),
    ("2028-01-03", "New Year's Day (substitute)", False),
    ("2028-04-14", "Good Friday", True),
    ("2028-04-17", "Easter Monday", True),
    ("2028-05-01", "Early May bank holiday", True),
    ("2028-05-29", "Spring bank holiday", True),
    ("2028-08-28", "Summer bank holiday", True),
)

BANK_HOLIDAYS: dict[date, BankHoliday] = {
    d: BankHoliday(d, name, flexible)
    for s, name, flexible in _HOLIDAYS
    for d in (date.fromisoformat(s),)
}
