import json

import pytest

from leave_burndown import create_app
from leave_burndown.plan import compute
from leave_burndown.storage import load

GOOD_FRIDAY = "2027-03-26"


@pytest.fixture
def path(tmp_path):
    # An existing file, so the app doesn't seed its example entry.
    p = tmp_path / "leave.json"
    p.write_text(json.dumps({"entries": []}))
    return p


@pytest.fixture
def client(path):
    return create_app(path).test_client()


def entries(path):
    return json.loads(path.read_text())["entries"]


def add(client, start, end, label="x", **extra):
    return client.post(
        "/add",
        data={"label": label, "start": start, "end": end, **extra},
        follow_redirects=True,
    )


def test_half_days_at_either_end_are_saved_and_cost_half(client, path):
    add(client, "2026-10-07", "2026-10-12", half_start="on", half_end="on")
    saved = entries(path)[0]
    assert saved["half_start"] is True and saved["half_end"] is True
    assert compute(load(path)).entries[0]["days_total"] == 3


def test_unticked_half_days_are_full_days(client, path):
    add(client, "2026-10-07", "2026-10-12")
    assert compute(load(path)).entries[0]["days_total"] == 4


def test_editing_can_add_and_remove_half_days(client, path):
    add(client, "2026-10-07", "2026-10-12")
    eid = entries(path)[0]["id"]
    form = {"label": "x", "start": "2026-10-07", "end": "2026-10-12"}

    client.post(f"/edit/{eid}", data={**form, "half_start": "on"})
    assert compute(load(path)).entries[0]["days_total"] == 3.5

    client.post(f"/edit/{eid}", data=form)  # untick it again
    assert compute(load(path)).entries[0]["days_total"] == 4


def test_leave_covering_a_flexed_bank_holiday_is_rejected(client, path):
    client.post(f"/flex/{GOOD_FRIDAY}")

    page = add(client, "2027-03-22", "2027-03-26")  # the week ending on Good Friday
    assert "covers Good Friday" in page.get_data(as_text=True)
    assert entries(path) == []

    add(client, "2027-03-22", "2027-03-25")  # the days either side are fine
    add(client, "2027-03-29", "2027-03-30")
    assert len(entries(path)) == 2


def test_editing_leave_to_cover_a_flexed_bank_holiday_is_rejected(client, path):
    client.post(f"/flex/{GOOD_FRIDAY}")
    add(client, "2027-03-22", "2027-03-25")
    eid = entries(path)[0]["id"]

    page = client.post(
        f"/edit/{eid}",
        data={"label": "x", "start": "2027-03-22", "end": "2027-03-26"},
        follow_redirects=True,
    )
    assert "covers Good Friday" in page.get_data(as_text=True)
    assert entries(path)[0]["end"] == "2027-03-25"


def test_cant_flex_a_bank_holiday_inside_existing_leave(client, path):
    add(client, "2027-03-22", "2027-03-26", label="Lake District")

    page = client.post(f"/flex/{GOOD_FRIDAY}", follow_redirects=True)
    assert "Can&#39;t flex Good Friday" in page.get_data(as_text=True)
    assert "Lake District" in page.get_data(as_text=True)
    assert load(path)["flexed_holidays"] == []


def test_flexing_can_be_undone_even_if_it_was_flexed_first(client, path):
    client.post(f"/flex/{GOOD_FRIDAY}")
    assert compute(load(path)).flexed
    client.post(f"/flex/{GOOD_FRIDAY}")
    assert not compute(load(path)).flexed


def page(client, url="/"):
    return client.get(url).get_data(as_text=True)


def test_page_opens_on_the_chart_with_everything_else_collapsed(client):
    html = page(client)
    for section in ("leave", "months", "bank-holidays", "settings"):
        assert f'<details class="sect" id="{section}" >' in html, section
    assert "used by Christmas" not in html  # the tile is gone


def test_open_parameter_expands_that_section_only(client):
    html = page(client, "/?open=leave")
    assert '<details class="sect" id="leave" open>' in html
    assert '<details class="sect" id="settings" >' in html


def test_actions_reopen_the_section_they_came_from(client, path):
    add(client, "2026-10-05", "2026-10-06")
    eid = entries(path)[0]["id"]
    assert client.post(f"/toggle/{eid}").headers["Location"].endswith("?open=leave")
    assert client.post(f"/delete/{eid}").headers["Location"].endswith("?open=leave")
    assert "open=holidays" in client.post(f"/flex/{GOOD_FRIDAY}").headers["Location"]


def test_allowance_is_broken_down_into_its_parts(client, path):
    data = json.loads(path.read_text())
    data["settings"] = {"base_days": 26, "extra_days": 5, "carried_days": 3}
    path.write_text(json.dumps(data))
    client.post(f"/flex/{GOOD_FRIDAY}")

    html = page(client)
    for part in (
        "<b>26</b> base",
        "<b>5</b> bought",
        "<b>3</b> carried over",
        "<b>1</b> flexed",
    ):
        assert part in html, part
    assert "<b>35</b><span>days this year" in html  # 26 + 5 + 3 + 1 flexed


def test_chart_has_a_wide_and_a_compact_layout_that_dont_share_ids(client, path):
    add(client, "2026-10-05", "2026-10-06")  # tentative, so it uses the hatch pattern
    html = page(client)
    assert 'class="chart chart-wide"' in html and 'class="chart chart-compact"' in html
    assert 'id="hatch-wide"' in html and 'id="hatch-compact"' in html
    assert "url(#hatch-wide)" in html and "url(#hatch-compact)" in html
