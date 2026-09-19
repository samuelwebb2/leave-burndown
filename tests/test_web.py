from datetime import date
from typing import TYPE_CHECKING

import pytest

from leave_burndown import create_app
from leave_burndown.plan import compute
from leave_burndown.storage import LeaveData, load, save

if TYPE_CHECKING:
    from pathlib import Path

    from flask.testing import FlaskClient

    from leave_burndown.storage import Entry

GOOD_FRIDAY = "2027-03-26"


@pytest.fixture
def path(tmp_path: Path) -> Path:
    # An existing file, so the app doesn't seed its example entry.
    p = tmp_path / "leave.json"
    save(p, LeaveData())
    return p


@pytest.fixture
def client(path: Path) -> FlaskClient:
    return create_app(path).test_client()


def entries(path: Path) -> list[Entry]:
    return load(path).entries


def post(client: FlaskClient, url: str, **form: str) -> None:
    """Do something on the site; what happens is checked afterwards."""
    _ = client.post(url, data=form)


def submit(client: FlaskClient, url: str, **form: str) -> str:
    """Post a form and return the page it redirects to."""
    return client.post(url, data=form, follow_redirects=True).get_data(as_text=True)


def add(
    client: FlaskClient, start: str, end: str, label: str = "x", **extra: str
) -> None:
    post(client, "/add", label=label, start=start, end=end, **extra)


def page(client: FlaskClient, url: str = "/") -> str:
    return client.get(url).get_data(as_text=True)


def test_half_days_at_either_end_are_saved_and_cost_half(
    client: FlaskClient, path: Path
) -> None:
    add(client, "2026-10-07", "2026-10-12", half_start="on", half_end="on")
    saved = entries(path)[0]
    assert saved.half_start and saved.half_end
    assert compute(load(path)).entries[0].days_total == 3


def test_unticked_half_days_are_full_days(client: FlaskClient, path: Path) -> None:
    add(client, "2026-10-07", "2026-10-12")
    assert compute(load(path)).entries[0].days_total == 4


def test_editing_can_add_and_remove_half_days(client: FlaskClient, path: Path) -> None:
    add(client, "2026-10-07", "2026-10-12")
    eid = entries(path)[0].id
    form = {"label": "x", "start": "2026-10-07", "end": "2026-10-12"}

    post(client, f"/edit/{eid}", **form, half_start="on")
    assert compute(load(path)).entries[0].days_total == 3.5

    post(client, f"/edit/{eid}", **form)  # untick it again
    assert compute(load(path)).entries[0].days_total == 4
    assert entries(path)[0].id == eid  # still the same entry


def test_leave_covering_a_flexed_bank_holiday_is_rejected(
    client: FlaskClient, path: Path
) -> None:
    post(client, f"/flex/{GOOD_FRIDAY}")

    # The week ending on Good Friday.
    message = submit(client, "/add", label="x", start="2027-03-22", end="2027-03-26")
    assert "covers Good Friday" in message
    assert entries(path) == []

    add(client, "2027-03-22", "2027-03-25")  # the days either side are fine
    add(client, "2027-03-29", "2027-03-30")
    assert len(entries(path)) == 2


def test_editing_leave_to_cover_a_flexed_bank_holiday_is_rejected(
    client: FlaskClient, path: Path
) -> None:
    post(client, f"/flex/{GOOD_FRIDAY}")
    add(client, "2027-03-22", "2027-03-25")
    eid = entries(path)[0].id

    message = submit(
        client, f"/edit/{eid}", label="x", start="2027-03-22", end="2027-03-26"
    )
    assert "covers Good Friday" in message
    assert entries(path)[0].end == date(2027, 3, 25)


def test_cant_flex_a_bank_holiday_inside_existing_leave(
    client: FlaskClient, path: Path
) -> None:
    add(client, "2027-03-22", "2027-03-26", label="Lake District")

    message = submit(client, f"/flex/{GOOD_FRIDAY}")
    assert "Can&#39;t flex Good Friday" in message
    assert "Lake District" in message
    assert load(path).flexed_holidays == []


def test_flexing_can_be_undone_even_if_it_was_flexed_first(
    client: FlaskClient, path: Path
) -> None:
    post(client, f"/flex/{GOOD_FRIDAY}")
    assert compute(load(path)).flexed
    post(client, f"/flex/{GOOD_FRIDAY}")
    assert not compute(load(path)).flexed


def test_page_opens_on_the_chart_with_everything_else_collapsed(
    client: FlaskClient,
) -> None:
    html = page(client)
    for section in ("leave", "months", "bank-holidays", "settings"):
        assert f'<details class="sect" id="{section}" >' in html, section
    assert "used by Christmas" not in html  # the tile is gone


def test_open_parameter_expands_that_section_only(client: FlaskClient) -> None:
    html = page(client, "/?open=leave")
    assert '<details class="sect" id="leave" open>' in html
    assert '<details class="sect" id="settings" >' in html


def test_actions_reopen_the_section_they_came_from(
    client: FlaskClient, path: Path
) -> None:
    add(client, "2026-10-05", "2026-10-06")
    eid = entries(path)[0].id
    assert client.post(f"/toggle/{eid}").headers["Location"].endswith("?open=leave")
    assert client.post(f"/delete/{eid}").headers["Location"].endswith("?open=leave")
    assert "open=holidays" in client.post(f"/flex/{GOOD_FRIDAY}").headers["Location"]


def test_allowance_is_broken_down_into_its_parts(
    client: FlaskClient, path: Path
) -> None:
    data = load(path)
    data.settings.base_days = 26
    data.settings.extra_days = 5
    data.settings.carried_days = 3
    save(path, data)
    post(client, f"/flex/{GOOD_FRIDAY}")

    html = page(client)
    for part in (
        "<b>26</b> base",
        "<b>5</b> bought",
        "<b>3</b> carried over",
        "<b>1</b> flexed",
    ):
        assert part in html, part
    assert "<b>35</b><span>days this year" in html  # 26 + 5 + 3 + 1 flexed


def test_chart_has_a_wide_and_a_compact_layout_that_dont_share_ids(
    client: FlaskClient,
) -> None:
    add(client, "2026-10-05", "2026-10-06")  # tentative, so it uses the hatch pattern
    html = page(client)
    assert 'class="chart chart-wide"' in html and 'class="chart chart-compact"' in html
    assert 'id="hatch-wide"' in html and 'id="hatch-compact"' in html
    assert "url(#hatch-wide)" in html and "url(#hatch-compact)" in html


SETTINGS = {
    "year_start": "2027-09-01",
    "base_days": "26",
    "extra_days": "4",
    "carried_days": "2.5",
    "tolerance_pct": "15",
    "skip_bank_holidays": "on",
}


def test_settings_are_saved_as_real_values(client: FlaskClient, path: Path) -> None:
    post(client, "/settings", **SETTINGS)
    saved = load(path).settings
    assert saved.year_start == date(2027, 9, 1)
    assert (saved.base_days, saved.extra_days, saved.carried_days) == (26, 4, 2.5)
    assert saved.tolerance_pct == 15
    assert saved.skip_bank_holidays


def test_settings_checkbox_off_and_blank_numbers(
    client: FlaskClient, path: Path
) -> None:
    form = {**SETTINGS, "carried_days": "", "extra_days": ""}
    del form["skip_bank_holidays"]  # an unticked checkbox isn't sent at all
    post(client, "/settings", **form)
    saved = load(path).settings
    assert saved.carried_days == 0
    assert saved.extra_days == 0
    assert not saved.skip_bank_holidays


@pytest.mark.parametrize(
    "bad",
    [
        {"tolerance_pct": "60"},
        {"tolerance_pct": "-1"},
        {"base_days": "-3"},
        {"year_start": "not a date"},
        {"base_days": "lots"},
    ],
)
def test_invalid_settings_are_rejected_and_nothing_is_saved(
    client: FlaskClient, path: Path, bad: dict[str, str]
) -> None:
    before = load(path).settings
    message = submit(client, "/settings", **{**SETTINGS, **bad})
    assert "valid. Use a real date" in message
    assert load(path).settings == before


def test_dates_are_written_to_the_file_as_iso_strings(
    client: FlaskClient, path: Path
) -> None:
    add(client, "2026-10-05", "2026-10-06")
    post(client, f"/flex/{GOOD_FRIDAY}")
    text = path.read_text()
    assert '"start": "2026-10-05"' in text
    assert '"end": "2026-10-06"' in text
    assert f'"{GOOD_FRIDAY}"' in text


def test_an_older_data_file_still_loads(path: Path) -> None:
    """Earlier versions stored a `days` count and had no half-day flags."""
    _ = path.write_text(
        '{"entries": [{"id": "abc", "label": "Old", "start": "2026-10-05",'
        + ' "end": "2026-10-09", "days": null, "status": "booked"}]}'
    )
    data = load(path)
    old = data.entries[0]
    assert (old.start, old.end) == (date(2026, 10, 5), date(2026, 10, 9))
    assert not old.half_start
    assert not old.half_end
    assert data.settings.base_days == 25  # defaults fill the gaps
    assert compute(data).entries[0].days_total == 5
