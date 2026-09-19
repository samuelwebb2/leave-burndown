"""Flask app: routes and form handling."""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

from flask import Flask, abort, flash, redirect, render_template, request, url_for

from .chart import build_chart
from .formatting import fmt_date
from .holidays import BANK_HOLIDAYS
from .plan import checkpoints, christmas_k, compute, flexed_dates
from .storage import Entry, Settings, load, new_id, save

if TYPE_CHECKING:
    from collections.abc import Mapping

    from werkzeug.wrappers import Response

    from .plan import Plan


class InvalidLeaveError(ValueError):
    """The leave form was filled in wrongly; the message is shown to the user."""


def parse_entry_form(
    form: Mapping[str, str], flexed: frozenset[date], entry_id: str | None = None
) -> Entry:
    """Validate the leave form, raising InvalidLeaveError if it is wrong.

    `flexed` are the bank holidays being worked, which leave can't cover.
    """
    try:
        start = date.fromisoformat(form.get("start", ""))
        end = date.fromisoformat(form.get("end", ""))
    except ValueError:
        msg = "Enter both a first and a last day."
        raise InvalidLeaveError(msg) from None
    if end < start:
        msg = "The last day can't be before the first day."
        raise InvalidLeaveError(msg)
    if (end - start).days > 366:
        msg = "That range is longer than a year."
        raise InvalidLeaveError(msg)
    if clashes := [BANK_HOLIDAYS[d] for d in sorted(flexed) if start <= d <= end]:
        names = ", ".join(f"{h.name} ({fmt_date(h.date)})" for h in clashes)
        msg = (
            f"That leave covers {names}, which you've flexed, so you'd be working "
            + "that day. Unflex it first, or book the days either side."
        )
        raise InvalidLeaveError(msg)
    return Entry(
        id=entry_id or new_id(),
        label=(form.get("label") or "Leave").strip()[:80],
        start=start,
        end=end,
        status="booked" if form.get("status") == "booked" else "tentative",
        half_start=form.get("half_start") == "on",
        half_end=form.get("half_end") == "on",
    )


class Summary(TypedDict):
    booked: float
    tentative: float
    unplanned: float
    warnings: list[str]


def summarise(p: Plan) -> Summary:
    """Headline figures and warnings for the top of the page."""
    booked = sum(p.used_booked)
    planned = sum(p.used_all)
    unplanned = p.total - planned

    warnings: list[str] = []
    if unplanned < -1e-9:
        warnings.append(
            f"You have planned {-unplanned:g} more days than your allowance."
        )
    kx = christmas_k(p)
    if kx is not None and p.rem_all[kx] < p.ideal(kx) - p.tol_days - 1e-9:
        used, ideal_used = p.total - p.rem_all[kx], p.total - p.ideal(kx)
        warnings.append(
            f"By Christmas you would have used {used:g} of {p.total:g} days "
            + f"({used / p.total:.0%}); an even pace would be about {ideal_used:.1f}."
        )
    return {
        "booked": booked,
        "tentative": planned - booked,
        "unplanned": unplanned,
        "warnings": warnings,
    }


def create_app(data_file: str | os.PathLike[str] | None = None) -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(16)
    path = Path(data_file or os.environ.get("LEAVE_DATA") or "leave_data.json")

    @app.get("/")
    def index() -> str:
        data = load(path)
        p = compute(data)
        editing = next(
            (e for e in data.entries if e.id == request.args.get("edit")), None
        )
        return render_template(
            "index.html",
            p=p,
            s=data.settings,
            chart=build_chart(p, datetime.now().astimezone().date()),
            rows=checkpoints(p),
            editing=editing,
            fd=fmt_date,
            open_section=request.args.get("open"),
            js_config={
                "bankHolidays": sorted(d.isoformat() for d in p.non_working),
            },
            **summarise(p),
        )

    @app.post("/settings")
    def settings() -> Response:
        data = load(path)
        try:
            # A blank number means 0. The model checks the dates and the limits.
            data.settings = Settings.model_validate(
                {
                    "year_start": request.form["year_start"],
                    "base_days": request.form.get("base_days") or 0,
                    "extra_days": request.form.get("extra_days") or 0,
                    "carried_days": request.form.get("carried_days") or 0,
                    "tolerance_pct": request.form.get("tolerance_pct") or 0,
                    "skip_bank_holidays": (
                        request.form.get("skip_bank_holidays") == "on"
                    ),
                }
            )
        except KeyError, ValueError:  # a pydantic ValidationError is a ValueError
            flash(
                "Those settings weren't valid. Use a real date, days of 0 or more, "
                + "and a tolerance of 0-50%."
            )
            return redirect(url_for("index", open="settings"))
        save(path, data)
        flash("Settings saved.", "info")
        return redirect(url_for("index"))

    @app.post("/add")
    def add() -> Response:
        data = load(path)
        try:
            entry = parse_entry_form(request.form, flexed_dates(data))
        except InvalidLeaveError as error:
            flash(str(error))
        else:
            data.entries.append(entry)
            save(path, data)
        return redirect(url_for("index"))

    @app.post("/edit/<eid>")
    def edit(eid: str) -> Response:
        data = load(path)
        try:
            entry = parse_entry_form(request.form, flexed_dates(data), eid)
        except InvalidLeaveError as error:
            flash(str(error))
            return redirect(url_for("index", edit=eid, open="leave"))
        for i, e in enumerate(data.entries):
            if e.id == eid:
                data.entries[i] = entry
                save(path, data)
                break
        else:
            flash("That leave entry no longer exists.")
        return redirect(url_for("index", open="leave"))

    @app.post("/flex/<iso>")
    def flex(iso: str) -> Response:
        data = load(path)
        try:
            holiday = BANK_HOLIDAYS[date.fromisoformat(iso)]
        except ValueError, KeyError:
            abort(404)
        if not holiday.flexible:
            flash(f"{holiday.name} is a fixed bank holiday and can't be flexed.")
        elif not data.settings.skip_bank_holidays:
            flash("Bank holidays are set to use leave, so there is nothing to flex.")
        else:
            day = holiday.date
            flexed = set(data.flexed_holidays)
            inside = next((e for e in data.entries if e.start <= day <= e.end), None)
            if day not in flexed and inside:
                # Flexing means working it, so it can't be leave.
                flash(
                    f"Can't flex {holiday.name}: it falls inside your leave "
                    + f"“{inside.label}” ({fmt_date(inside.start)} to "
                    + f"{fmt_date(inside.end)}). Change or delete that leave first."
                )
            else:
                flexed ^= {day}  # toggle
                data.flexed_holidays = sorted(flexed)
                save(path, data)
        return redirect(url_for("index", open="holidays") + "#bank-holidays")

    @app.post("/toggle/<eid>")
    def toggle(eid: str) -> Response:
        data = load(path)
        for e in data.entries:
            if e.id == eid:
                e.status = "tentative" if e.status == "booked" else "booked"
        save(path, data)
        return redirect(url_for("index", open="leave"))

    @app.post("/delete/<eid>")
    def delete(eid: str) -> Response:
        data = load(path)
        data.entries = [e for e in data.entries if e.id != eid]
        save(path, data)
        return redirect(url_for("index", open="leave"))

    return app
