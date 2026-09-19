"""JSON-file persistence for settings and leave entries."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Literal, NotRequired, TypedDict

if TYPE_CHECKING:
    from pathlib import Path

Status = Literal["booked", "tentative"]


class Settings(TypedDict):
    year_start: str  # ISO date
    base_days: float
    extra_days: float  # bought leave
    carried_days: float
    tolerance_pct: float  # how far from the even pace still counts as "on pace"
    skip_bank_holidays: bool


class EntryFields(TypedDict):
    """What the leave form supplies: everything about an entry except its id."""

    label: str
    start: str  # ISO date
    end: str  # ISO date
    status: Status
    half_start: bool
    half_end: bool


class Entry(TypedDict):
    """A stored leave entry. Older entries may lack the half-day flags."""

    id: str
    label: str
    start: str  # ISO date
    end: str  # ISO date
    status: Status
    half_start: NotRequired[bool]
    half_end: NotRequired[bool]


class LeaveData(TypedDict):
    settings: Settings
    entries: list[Entry]
    flexed_holidays: list[str]  # ISO dates of flexed bank holidays


DEFAULT_SETTINGS: Settings = {
    "year_start": "2026-09-01",
    "base_days": 25.0,  # placeholder: set your real allowance in the app
    "extra_days": 5.0,
    "carried_days": 0.0,
    "tolerance_pct": 10.0,
    "skip_bank_holidays": True,
}

EXAMPLE_ENTRIES: list[Entry] = [
    {
        "id": "example",
        "label": "Bikepacking adventure (example)",
        "start": "2026-10-29",
        "end": "2026-11-03",
        "status": "tentative",
    }
]


def load(path: Path) -> LeaveData:
    """Read the data file, filling in defaults. A missing file gives the example entry."""
    raw: dict[str, Any] = (
        json.loads(path.read_text())
        if path.exists()
        else {"entries": deepcopy(EXAMPLE_ENTRIES)}
    )
    return {
        "settings": {**DEFAULT_SETTINGS, **raw.get("settings", {})},
        "entries": raw.get("entries", []),
        "flexed_holidays": raw.get("flexed_holidays", []),
    }


def save(path: Path, data: LeaveData) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)
