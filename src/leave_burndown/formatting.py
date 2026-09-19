from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date


def fmt_date(d: date, year: bool = False) -> str:
    return f"{d:%a} {d.day} {d:%b}" + (f" {d.year}" if year else "")
