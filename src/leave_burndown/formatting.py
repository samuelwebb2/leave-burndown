from __future__ import annotations

from datetime import date


def fmt_date(d: date, year: bool = False) -> str:
    return f"{d:%a} {d.day} {d:%b}" + (f" {d.year}" if year else "")
