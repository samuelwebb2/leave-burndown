"""Settings and leave entries as validated models, and their JSON-file persistence.

The file holds ISO dates ("2026-09-01"); loading turns them into real dates and
saving writes them back, so the file format is the same as it always was.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, ClassVar, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from pathlib import Path

Status = Literal["booked", "tentative"]


class Model(BaseModel):
    """Base for everything stored: assignments are validated too."""

    model_config: ClassVar[ConfigDict] = ConfigDict(validate_assignment=True)


class Settings(Model):
    year_start: date = date(2026, 9, 1)
    # The default is a placeholder: set the real allowance in the app.
    base_days: float = Field(default=25.0, ge=0)
    extra_days: float = Field(default=5.0, ge=0)  # bought leave
    carried_days: float = Field(default=0.0, ge=0)
    # How far from the even pace still counts as "on pace".
    tolerance_pct: float = Field(default=10.0, ge=0, le=50)
    skip_bank_holidays: bool = True


def new_id() -> str:
    return uuid4().hex[:8]


class Entry(Model):
    id: str = Field(default_factory=new_id)
    label: str
    start: date
    end: date
    status: Status
    half_start: bool = False
    half_end: bool = False


class LeaveData(Model):
    settings: Settings = Field(default_factory=Settings)
    entries: list[Entry] = Field(default_factory=list)
    flexed_holidays: list[date] = Field(default_factory=list)


def example_data() -> LeaveData:
    """What a brand-new install shows before anything is saved."""
    return LeaveData(
        entries=[
            Entry(
                id="example",
                label="Bikepacking adventure (example)",
                start=date(2026, 10, 29),
                end=date(2026, 11, 3),
                status="tentative",
            )
        ]
    )


def load(path: Path) -> LeaveData:
    """Read the data file, with defaults filled in (or the example if missing)."""
    if not path.exists():
        return example_data()
    return LeaveData.model_validate_json(path.read_text())


def save(path: Path, data: LeaveData) -> None:
    tmp = path.with_suffix(".tmp")
    _ = tmp.write_text(data.model_dump_json(indent=2))
    _ = tmp.replace(path)
