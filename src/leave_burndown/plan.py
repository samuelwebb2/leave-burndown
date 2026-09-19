"""The leave maths: turn settings and entries into a day-by-day plan."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, timedelta

from .holidays import BANK_HOLIDAYS, BankHoliday


def year_end(start: date) -> date:
    try:
        nxt = start.replace(year=start.year + 1)
    except ValueError:  # 29 Feb
        nxt = start.replace(year=start.year + 1, day=28)
    return nxt - timedelta(days=1)


def daterange(a: date, b: date):
    for i in range((b - a).days + 1):
        yield a + timedelta(days=i)


def working_days(a: date, b: date, non_working: Collection[date]) -> list[date]:
    """Weekdays in a..b that use leave, i.e. not in `non_working`."""
    return [d for d in daterange(a, b) if d.weekday() < 5 and d not in non_working]


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
    holidays: list[BankHoliday]  # bank holidays in this leave year
    flexed: frozenset[date]  # flexed bank holidays in this year: worked, not days off
    non_working: frozenset[date]  # bank holidays that do not use leave

    def ideal(self, k: float) -> float:
        return self.total * (1 - k / self.n)

    def idx(self, d: date) -> int:
        return (d - self.start).days


def compute(data: dict) -> Plan:
    s = data["settings"]
    start = date.fromisoformat(s["year_start"])
    end = year_end(start)
    n = (end - start).days + 1
    holidays = [h for d, h in sorted(BANK_HOLIDAYS.items()) if start <= d <= end]

    # Flexing only means something when bank holidays normally cost no leave.
    # A flexed holiday is a working day: it adds a day to the allowance, and
    # leave that spans it uses a day. `non_working` covers every known bank
    # holiday, not just this year's, so entries outside the year still count right.
    skip = s["skip_bank_holidays"]
    flexed_all = {
        d
        for d in map(date.fromisoformat, data.get("flexed_holidays", []))
        if skip and d in BANK_HOLIDAYS and BANK_HOLIDAYS[d].flexible
    }
    non_working = frozenset(BANK_HOLIDAYS if skip else ()) - flexed_all
    flexed = frozenset(h.date for h in holidays if h.date in flexed_all)
    total = s["base_days"] + s["extra_days"] + s["carried_days"] + len(flexed)

    used_all, used_booked = [0.0] * n, [0.0] * n
    entries = []
    for raw in data["entries"]:
        e = dict(raw)
        e["start_d"], e["end_d"] = (
            date.fromisoformat(e["start"]),
            date.fromisoformat(e["end"]),
        )
        # Each working day costs 1, except a half day at either end of the leave,
        # which costs 0.5. (An end that isn't a working day has nothing to halve.)
        cost = {d: 1.0 for d in working_days(e["start_d"], e["end_d"], non_working)}
        for flag, d in (("half_start", e["start_d"]), ("half_end", e["end_d"])):
            if e.get(flag) and d in cost:
                cost[d] = 0.5
        e["days_total"] = sum(cost.values())
        in_year = 0.0
        for d, amount in cost.items():
            i = (d - start).days
            if 0 <= i < n:
                used_all[i] += amount
                if e["status"] == "booked":
                    used_booked[i] += amount
                in_year += amount
        e["days_in_year"] = in_year
        e["outside"] = abs(in_year - e["days_total"]) > 1e-9
        e["flexed_names"] = [
            BANK_HOLIDAYS[d].name for d in sorted(flexed_all)
            if e["start_d"] <= d <= e["end_d"]
        ]
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
        holidays=holidays,
        flexed=flexed,
        non_working=non_working,
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
