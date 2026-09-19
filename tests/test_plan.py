from datetime import date
from typing import TYPE_CHECKING

import pytest

from leave_burndown.plan import compute
from leave_burndown.storage import Entry, LeaveData, Settings

if TYPE_CHECKING:
    from collections.abc import Iterable

    from leave_burndown.storage import Status


def make_data(
    entries: Iterable[Entry] = (),
    flexed: Iterable[str] = (),
    *,
    skip_bank_holidays: bool = True,
) -> LeaveData:
    """Leave year 1 Sep 2026 - 31 Aug 2027 with a 30 day allowance (25 + 5 bought)."""
    return LeaveData(
        settings=Settings(skip_bank_holidays=skip_bank_holidays),
        entries=list(entries),
        flexed_holidays=[date.fromisoformat(d) for d in flexed],
    )


def entry(
    start: str,
    end: str,
    *,
    status: Status = "tentative",
    half_start: bool = False,
    half_end: bool = False,
) -> Entry:
    return Entry(
        label="x",
        start=date.fromisoformat(start),
        end=date.fromisoformat(end),
        status=status,
        half_start=half_start,
        half_end=half_end,
    )


def test_weekends_and_bank_holidays_dont_use_leave() -> None:
    # Thu 24 Dec - Tue 29 Dec 2026: Christmas Day and Boxing Day (substitute)
    # fall on Fri and Mon, leaving Thu and Tue.
    p = compute(make_data([entry("2026-12-24", "2026-12-29")]))
    assert p.entries[0].days_total == 2
    assert p.total == 30
    assert p.rem_all[-1] == 28


def test_bank_holidays_count_when_setting_is_off() -> None:
    p = compute(
        make_data([entry("2026-12-24", "2026-12-29")], skip_bank_holidays=False)
    )
    assert p.entries[0].days_total == 4  # Thu, Fri, Mon, Tue


# Wed 7 Oct - Sun 11 Oct 2026: Wed, Thu, Fri are working days.
def test_half_day_on_the_first_day() -> None:
    # Fly out Wednesday evening: half a day, then Thu and Fri; back on Sunday.
    p = compute(make_data([entry("2026-10-07", "2026-10-11", half_start=True)]))
    assert p.entries[0].days_total == 2.5
    assert p.used_all[p.idx(date(2026, 10, 7))] == 0.5  # shows on the chart's first day
    assert p.rem_all[-1] == 27.5


def test_half_days_on_both_ends() -> None:
    # Half a day out on Wednesday, back Monday morning: Wed(0.5) Thu Fri Mon(0.5).
    p = compute(
        make_data([entry("2026-10-07", "2026-10-12", half_start=True, half_end=True)])
    )
    assert p.entries[0].days_total == 3
    assert p.used_all[p.idx(date(2026, 10, 12))] == 0.5


def test_half_day_on_the_last_day_only() -> None:
    p = compute(make_data([entry("2026-10-07", "2026-10-12", half_end=True)]))
    assert p.entries[0].days_total == 3.5


@pytest.mark.parametrize(
    ("half_start", "half_end"), [(True, False), (False, True), (True, True)]
)
def test_a_single_half_day_costs_half_however_it_is_flagged(
    half_start: bool, half_end: bool
) -> None:
    one_day = entry(
        "2026-10-06", "2026-10-06", half_start=half_start, half_end=half_end
    )
    assert compute(make_data([one_day])).entries[0].days_total == 0.5


def test_half_day_on_a_non_working_end_changes_nothing() -> None:
    # Fri 9 - Sun 11 Oct: the Sunday isn't a working day, so there's nothing to halve.
    p = compute(make_data([entry("2026-10-09", "2026-10-11", half_end=True)]))
    assert p.entries[0].days_total == 1
    saturday = compute(make_data([entry("2026-10-10", "2026-10-10", half_start=True)]))
    assert saturday.entries[0].days_total == 0


def test_booked_and_tentative_are_tracked_separately() -> None:
    p = compute(
        make_data(
            [
                entry("2026-10-05", "2026-10-09", status="booked"),
                entry("2026-11-02", "2026-11-03", status="tentative"),
            ]
        )
    )
    assert p.rem_booked[-1] == 25
    assert p.rem_all[-1] == 23
    assert p.rem_all[p.idx(date(2026, 10, 10))] == 25  # after the first week only


def test_flexing_a_bank_holiday_adds_a_day_and_makes_it_use_leave() -> None:
    # Thu 25 Mar - Tue 30 Mar 2027 spans Good Friday and Easter Monday.
    trip = [entry("2027-03-25", "2027-03-30")]
    before = compute(make_data(trip))
    after = compute(make_data(trip, flexed=["2027-03-26"]))

    assert before.entries[0].days_total == 2
    assert after.entries[0].days_total == 3
    assert after.entries[0].flexed_names == ["Good Friday"]
    assert after.total == before.total + 1
    assert after.flexed == {date(2027, 3, 26)}


def test_fixed_holidays_cant_be_flexed_and_flexing_needs_bank_holidays_to_be_free() -> (
    None
):
    xmas = make_data([entry("2026-12-25", "2026-12-25")], flexed=["2026-12-25"])
    assert compute(xmas).flexed == frozenset()
    assert compute(xmas).entries[0].days_total == 0

    off = make_data(flexed=["2027-03-26"], skip_bank_holidays=False)
    assert compute(off).flexed == frozenset()
    assert compute(off).total == 30


def test_entry_outside_the_leave_year_is_flagged_and_not_counted() -> None:
    p = compute(
        make_data([entry("2027-08-30", "2027-09-03")])
    )  # 30 Aug is a bank holiday
    e = p.entries[0]
    assert e.days_total == 4  # Tue 31 Aug - Fri 3 Sep... Mon is the bank holiday
    assert e.days_in_year == 1  # only 31 Aug falls in the year
    assert e.outside
    assert p.rem_all[-1] == 29
