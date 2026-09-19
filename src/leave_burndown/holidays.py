"""England & Wales bank holidays. Edit or extend as needed."""

from datetime import date

# Sep 2026 - Aug 2028.
BANK_HOLIDAYS = frozenset(
    date.fromisoformat(s)
    for s in (
        "2026-12-25",
        "2026-12-28",
        "2027-01-01",
        "2027-03-26",
        "2027-03-29",
        "2027-05-03",
        "2027-05-31",
        "2027-08-30",
        "2027-12-27",
        "2027-12-28",
        "2028-01-03",
        "2028-04-14",
        "2028-04-17",
        "2028-05-01",
        "2028-05-29",
        "2028-08-28",
    )
)
