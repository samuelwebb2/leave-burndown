"""Flask app: routes and form handling."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from uuid import uuid4

from flask import Flask, abort, flash, redirect, render_template, request, url_for

from . import storage
from .chart import build_chart
from .formatting import fmt_date
from .holidays import BANK_HOLIDAYS
from .plan import Plan, checkpoints, christmas_k, compute


def parse_entry_form(form) -> tuple[dict | None, str | None]:
    """Validate the leave form. Returns (fields, None) or (None, error message)."""
    try:
        start = date.fromisoformat(form.get("start", ""))
        end = date.fromisoformat(form.get("end", ""))
    except ValueError:
        return None, "Enter both a first and a last day."
    days_raw = (form.get("days") or "").strip()
    try:
        days = float(days_raw) if days_raw else None
    except ValueError:
        days = -1.0
    if end < start:
        return None, "The last day can't be before the first day."
    if (end - start).days > 366:
        return None, "That range is longer than a year."
    if days is not None and days <= 0:
        return None, "Days must be a number above 0, or left blank."
    return {
        "label": (form.get("label") or "Leave").strip()[:80],
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "status": "booked" if form.get("status") == "booked" else "tentative",
    }, None


def summarise(p: Plan) -> dict:
    """Headline figures and warnings for the top of the page."""
    booked = sum(p.used_booked)
    planned = sum(p.used_all)
    unplanned = p.total - planned

    warnings = []
    if unplanned < -1e-9:
        warnings.append(
            f"You have planned {-unplanned:g} more days than your allowance."
        )
    kx = christmas_k(p)
    xmas = None
    if kx is not None:
        used = p.total - p.rem_all[kx]
        ideal_used = p.total - p.ideal(kx)
        fast = p.rem_all[kx] < p.ideal(kx) - p.tol_days - 1e-9
        xmas = {"used": used, "ideal_used": ideal_used, "fast": fast}
        if fast:
            warnings.append(
                f"By Christmas you would have used {used:g} of {p.total:g} days "
                f"({used / p.total:.0%}); an even pace would be about {ideal_used:.1f}."
            )
    return {
        "booked": booked,
        "tentative": planned - booked,
        "unplanned": unplanned,
        "xmas": xmas,
        "warnings": warnings,
    }


def create_app(data_file: str | os.PathLike | None = None) -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(16)
    path = Path(data_file or os.environ.get("LEAVE_DATA") or "leave_data.json")

    @app.get("/")
    def index():
        data = storage.load(path)
        p = compute(data)
        s = data["settings"]
        editing = next(
            (e for e in data["entries"] if e["id"] == request.args.get("edit")), None
        )
        return render_template(
            "index.html",
            p=p,
            s=s,
            chart=build_chart(p),
            rows=checkpoints(p),
            editing=editing,
            fd=fmt_date,
            open_settings=request.args.get("settings") == "1",
            js_config={
                "bankHolidays": sorted(d.isoformat() for d in p.non_working),
            },
            **summarise(p),
        )

    @app.post("/settings")
    def settings():
        data = storage.load(path)
        s = dict(data["settings"])
        try:
            s["year_start"] = date.fromisoformat(request.form["year_start"]).isoformat()
            for k in ("base_days", "extra_days", "carried_days"):
                v = float(request.form.get(k) or 0)
                if v < 0:
                    raise ValueError
                s[k] = v
            tol = float(request.form.get("tolerance_pct") or 0)
            if not 0 <= tol <= 50:
                raise ValueError
            s["tolerance_pct"] = tol
        except (KeyError, ValueError):
            flash(
                "Those settings weren't valid. Use a real date, days of 0 or more, and a tolerance of 0-50%."
            )
            return redirect(url_for("index", settings=1))
        s["skip_bank_holidays"] = request.form.get("skip_bank_holidays") == "on"
        data["settings"] = s
        storage.save(path, data)
        flash("Settings saved.", "info")
        return redirect(url_for("index"))

    @app.post("/add")
    def add():
        fields, error = parse_entry_form(request.form)
        if error:
            flash(error)
        else:
            data = storage.load(path)
            data["entries"].append({"id": uuid4().hex[:8], **fields})
            storage.save(path, data)
        return redirect(url_for("index"))

    @app.post("/edit/<eid>")
    def edit(eid):
        fields, error = parse_entry_form(request.form)
        if error:
            flash(error)
            return redirect(url_for("index", edit=eid))
        data = storage.load(path)
        for e in data["entries"]:
            if e["id"] == eid:
                e.update(fields)
                storage.save(path, data)
                break
        else:
            flash("That leave entry no longer exists.")
        return redirect(url_for("index"))

    @app.post("/flex/<iso>")
    def flex(iso):
        data = storage.load(path)
        try:
            holiday = BANK_HOLIDAYS[date.fromisoformat(iso)]
        except (ValueError, KeyError):
            abort(404)
        if not holiday.flexible:
            flash(f"{holiday.name} is a fixed bank holiday and can't be flexed.")
        elif not data["settings"]["skip_bank_holidays"]:
            flash("Bank holidays are set to use leave, so there is nothing to flex.")
        else:
            flexed = set(data["flexed_holidays"])
            flexed ^= {holiday.date.isoformat()}  # toggle
            data["flexed_holidays"] = sorted(flexed)
            storage.save(path, data)
        return redirect(url_for("index") + "#bank-holidays")

    @app.post("/toggle/<eid>")
    def toggle(eid):
        data = storage.load(path)
        for e in data["entries"]:
            if e["id"] == eid:
                e["status"] = "tentative" if e["status"] == "booked" else "booked"
        storage.save(path, data)
        return redirect(url_for("index"))

    @app.post("/delete/<eid>")
    def delete(eid):
        data = storage.load(path)
        data["entries"] = [e for e in data["entries"] if e["id"] != eid]
        storage.save(path, data)
        return redirect(url_for("index"))

    return app
