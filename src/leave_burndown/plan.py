"""The leave maths: turn settings and entries into a day-by-day plan."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Literal

from .holidays import BANK_HOLIDAYS, BankHoliday

if TYPE_CHECKING:
    from collections.abc import Collection, Iterator

    from .storage import LeaveData, Status


def year_end(start: date) -> date:
    try:
        nxt = start.replace(year=start.year + 1)
    except ValueError:  # 29 Feb
        nxt = start.replace(year=start.year + 1, day=28)
    return nxt - timedelta(days=1)


def daterange(a: date, b: date) -> Iterator[date]:
    for i in range((b - a).days + 1):
        yield a + timedelta(days=i)


def flexed_dates(data: LeaveData) -> frozenset[date]:
    """Flexed bank holidays that are in force.

    Only the flexible ones count, and only while bank holidays are free days
    (flexing is meaningless if they already use leave).
    """
    if not data.settings.skip_bank_holidays:
        return frozenset[date]()
    return frozenset(
        d
        for d in data.flexed_holidays
        if d in BANK_HOLIDAYS and BANK_HOLIDAYS[d].flexible
    )


def working_days(a: date, b: date, non_working: Collection[date]) -> list[date]:
    """Weekdays in a..b that use leave, i.e. not in `non_working`."""
    return [d for d in daterange(a, b) if d.weekday() < 5 and d not in non_working]


@dataclass
class PlannedEntry:
    """A leave entry with what it costs worked out."""

    id: str
    label: str
    status: Status
    start: date
    end: date
    half_start: bool
    half_end: bool
    days_total: float  # leave days used, wherever they fall
    days_in_year: float  # ...of which fall inside this leave year
    outside: bool  # whether any of it falls outside this leave year
    flexed_names: list[str]  # flexed bank holidays it spans (it uses leave on them)


@dataclass
class Plan:
    start: date
    end: date
    n: int  # days in the leave year
    total: float
    tol_days: float
    entries: list[PlannedEntry]
    used_all: list[float]  # leave used on each day (booked + tentative)
    used_booked: list[float]
    rem_all: list[float]  # remaining at the start of day k (length n + 1)
    rem_booked: list[float]
    holidays: list[BankHoliday]  # bank holidays in this leave year
    flexed: frozenset[date]  # flexed bank holidays in this year: worked, not days off
    non_working: frozenset[date]  # bank holidays that do not use leave

    def ideal(self, k: float) -> float:
        return self.total * (1 - k / self.n)

    def idx(self, d: date) -> int:
        return (d - self.start).days


def compute(data: LeaveData) -> Plan:
    s = data.settings
    start = s.year_start
    end = year_end(start)
    n = (end - start).days + 1
    holidays = [h for d, h in sorted(BANK_HOLIDAYS.items()) if start <= d <= end]

    # Flexing only means something when bank holidays normally cost no leave.
    # A flexed holiday is a working day: it adds a day to the allowance, and
    # leave that spans it uses a day. `non_working` covers every known bank
    # holiday, not just this year's, so entries outside the year still count right.
    flexed_all = flexed_dates(data)
    non_working = frozenset(BANK_HOLIDAYS if s.skip_bank_holidays else ()) - flexed_all
    flexed = frozenset(h.date for h in holidays if h.date in flexed_all)
    total = s.base_days + s.extra_days + s.carried_days + len(flexed)

    used_all, used_booked = [0.0] * n, [0.0] * n
    entries: list[PlannedEntry] = []
    for e in data.entries:
        # Each working day costs 1, except a half day at either end of the leave,
        # which costs 0.5. (An end that isn't a working day has nothing to halve.)
        cost = dict.fromkeys(working_days(e.start, e.end, non_working), 1.0)
        for half, d in ((e.half_start, e.start), (e.half_end, e.end)):
            if half and d in cost:
                cost[d] = 0.5
        days_total = sum(cost.values())

        in_year = 0.0
        for d, amount in cost.items():
            i = (d - start).days
            if 0 <= i < n:
                used_all[i] += amount
                if e.status == "booked":
                    used_booked[i] += amount
                in_year += amount

        entries.append(
            PlannedEntry(
                id=e.id,
                label=e.label,
                status=e.status,
                start=e.start,
                end=e.end,
                half_start=e.half_start,
                half_end=e.half_end,
                days_total=days_total,
                days_in_year=in_year,
                outside=abs(in_year - days_total) > 1e-9,
                flexed_names=[
                    BANK_HOLIDAYS[d].name
                    for d in sorted(flexed_all)
                    if e.start <= d <= e.end
                ],
            )
        )
    entries.sort(key=lambda e: (e.start, e.end))

    def cumulative(used: list[float]) -> list[float]:
        rem: list[float] = [total]
        for u in used:
            rem.append(rem[-1] - u)
        return rem

    return Plan(
        start=start,
        end=end,
        n=n,
        total=total,
        tol_days=total * s.tolerance_pct / 100,
        entries=entries,
        used_all=used_all,
        used_booked=used_booked,
        rem_all=cumulative(used_all),
        rem_booked=cumulative(used_booked),
        holidays=holidays,
        flexed=flexed,
        non_working=non_working,
    )


def month_starts(p: Plan) -> list[date]:
    out: list[date] = []
    d = p.start
    while d <= p.end:
        out.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


@dataclass
class Checkpoint:
    """Where the plan stands against the even pace at the end of a month."""

    day: date
    planned: float  # leave remaining if the plan is followed
    ideal: float  # leave remaining on an even pace
    gap: float
    state: Literal["ok", "fast", "slow"]  # within tolerance / using too fast / too slow


def checkpoints(p: Plan) -> list[Checkpoint]:
    """Month-end rows comparing the plan with the even pace."""
    starts = month_starts(p)
    month_ends = [*(s - timedelta(days=1) for s in starts[1:]), p.end]
    rows: list[Checkpoint] = []
    for last_day in month_ends:
        k = p.idx(last_day) + 1
        planned, ideal = p.rem_all[k], p.ideal(k)
        gap = planned - ideal
        state: Literal["ok", "fast", "slow"] = (
            "fast"
            if gap < -p.tol_days - 1e-9
            else "slow"
            if gap > p.tol_days + 1e-9
            else "ok"
        )
        rows.append(Checkpoint(last_day, planned, ideal, gap, state))
    return rows


def christmas_k(p: Plan) -> int | None:
    for y in (p.start.year, p.start.year + 1):
        d = date(y, 12, 25)
        if p.start <= d <= p.end:
            return p.idx(d)
    return None
