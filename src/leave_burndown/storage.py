"""JSON-file persistence for settings and leave entries."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_SETTINGS = {
    "year_start": "2026-09-01",
    "base_days": 25.0,  # placeholder: set your real allowance in the app
    "extra_days": 5.0,  # bought leave
    "carried_days": 0.0,
    "tolerance_pct": 10.0,  # how far from the even pace still counts as "on pace"
    "skip_bank_holidays": True,
}

EXAMPLE_ENTRIES = [
    {
        "id": "example",
        "label": "Bike packing adventure (example)",
        "start": "2026-10-29",
        "end": "2026-11-03",
        "status": "tentative",
    }
]


def load(path: Path) -> dict:
    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = {"entries": [dict(e) for e in EXAMPLE_ENTRIES]}
    data["settings"] = {**DEFAULT_SETTINGS, **data.get("settings", {})}
    data.setdefault("entries", [])
    data.setdefault("flexed_holidays", [])  # ISO dates of flexed bank holidays
    return data


def save(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)
