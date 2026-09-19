"""The leave maths: turn settings and entries into a day-by-day plan."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .holidays import BANK_HOLIDAYS


def year_end(start: date) -> date:
    try:
        nxt = start.replace(year=start.year + 1)
    except ValueError:  # 29 Feb
        nxt = start.replace(year=start.year + 1, day=28)
    return nxt - timedelta(days=1)


def daterange(a: date, b: date):
    for i in range((b - a).days + 1):
        yield a + timedelta(days=i)


def working_days(a: date, b: date, skip_bh: bool) -> list[date]:
    return [
        d
        for d in daterange(a, b)
        if d.weekday() < 5 and not (skip_bh and d in BANK_HOLIDAYS)
    ]


@dataclass
class Plan:
    start: date
    end: date
    n: int  # days in the leave year
    total: float
    tol_days: float
    entries: list[dict]  # each entry plus computed fields
    used_all: list[float]  # leave used on each day (booked + tentative)
    used_booked: list[float]
    rem_all: list[float]  # remaining at the start of day k (length n + 1)
    rem_booked: list[float]

    def ideal(self, k: float) -> float:
        return self.total * (1 - k / self.n)

    def idx(self, d: date) -> int:
        return (d - self.start).days


def compute(data: dict) -> Plan:
    s = data["settings"]
    start = date.fromisoformat(s["year_start"])
    end = year_end(start)
    n = (end - start).days + 1
    total = s["base_days"] + s["extra_days"] + s["carried_days"]
    skip = s["skip_bank_holidays"]

    used_all, used_booked = [0.0] * n, [0.0] * n
    entries = []
    for raw in data["entries"]:
        e = dict(raw)
        e["start_d"], e["end_d"] = (
            date.fromisoformat(e["start"]),
            date.fromisoformat(e["end"]),
        )
        wd = working_days(e["start_d"], e["end_d"], skip)
        e["days_total"] = (
            float(e["days"]) if e.get("days") is not None else float(len(wd))
        )
        per_day = e["days_total"] / len(wd) if wd else 0.0
        contribution: dict[int, float] = {}
        for d in wd:
            contribution[(d - start).days] = per_day
        if not wd and e["days_total"] > 0:
            contribution[(e["start_d"] - start).days] = e["days_total"]
        in_year = 0.0
        for i, amount in contribution.items():
            if 0 <= i < n:
                used_all[i] += amount
                if e["status"] == "booked":
                    used_booked[i] += amount
                in_year += amount
        e["days_in_year"] = in_year
        e["outside"] = abs(in_year - e["days_total"]) > 1e-9
        entries.append(e)
    entries.sort(key=lambda e: (e["start_d"], e["end_d"]))

    def cumulative(used: list[float]) -> list[float]:
        rem = [total]
        for u in used:
            rem.append(rem[-1] - u)
        return rem

    return Plan(
        start=start,
        end=end,
        n=n,
        total=total,
        tol_days=total * s["tolerance_pct"] / 100,
        entries=entries,
        used_all=used_all,
        used_booked=used_booked,
        rem_all=cumulative(used_all),
        rem_booked=cumulative(used_booked),
    )


def month_starts(p: Plan) -> list[date]:
    out, d = [], p.start
    while d <= p.end:
        out.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def checkpoints(p: Plan) -> list[dict]:
    """Month-end rows comparing the plan with the even pace."""
    rows = []
    starts = month_starts(p)
    for i, ms in enumerate(starts):
        last_day = (starts[i + 1] - timedelta(days=1)) if i + 1 < len(starts) else p.end
        k = p.idx(last_day) + 1
        planned, ideal = p.rem_all[k], p.ideal(k)
        gap = planned - ideal
        state = (
            "fast"
            if gap < -p.tol_days - 1e-9
            else "slow"
            if gap > p.tol_days + 1e-9
            else "ok"
        )
        rows.append(
            {
                "date": last_day,
                "planned": planned,
                "ideal": ideal,
                "gap": gap,
                "state": state,
            }
        )
    return rows


def christmas_k(p: Plan) -> int | None:
    for y in (p.start.year, p.start.year + 1):
        d = date(y, 12, 25)
        if p.start <= d <= p.end:
            return p.idx(d)
    return None
