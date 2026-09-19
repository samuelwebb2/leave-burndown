"""Server-rendered SVG chart of leave remaining against an even pace.

The chart is drawn twice, in a wide and a compact layout, and CSS shows whichever
fits the screen. Scaling one drawing down to phone width would shrink the text to
nothing, so the compact layout is taller, with fewer ticks and month labels.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from markupsafe import Markup, escape

from .formatting import fmt_date
from .holidays import BANK_HOLIDAYS
from .plan import Plan, christmas_k, month_starts

if TYPE_CHECKING:
    from datetime import date

APOSTROPHE = "\N{RIGHT SINGLE QUOTATION MARK}"  # typographic, for 'yy years


@dataclass(frozen=True)
class Layout:
    name: str
    W: int
    H: int
    L: int  # margins
    R: int
    T: int
    B: int
    max_ticks: int  # most y-axis gridlines
    month_every: int  # label every nth month
    font: int  # axis font size in viewBox units, to estimate label widths


WIDE = Layout("wide", 840, 400, 44, 26, 26, 44, max_ticks=8, month_every=1, font=12)
COMPACT = Layout(
    "compact", 360, 400, 30, 14, 24, 32, max_ticks=5, month_every=2, font=11
)


def tick_step(top: float, max_ticks: int) -> int:
    for s in (1, 2, 5, 10, 20, 25, 50, 100):
        if top / s <= max_ticks:
            return s
    return 100


def _text(value: float | str) -> str:
    """An attribute value: floats print to one decimal place, as SVG wants."""
    return f"{value:.1f}" if isinstance(value, float) else str(escape(value))


def el(tag: str, content: str | None = None, /, **attrs: float | str) -> str:
    """An SVG element. A trailing `_` is dropped from names (`class_`) and any other
    `_` becomes `-` (`text_anchor`)."""
    shown = "".join(
        f' {name.rstrip("_").replace("_", "-")}="{_text(value)}"'
        for name, value in attrs.items()
    )
    return f"<{tag}{shown}/>" if content is None else f"<{tag}{shown}>{content}</{tag}>"


def _render(p: Plan, lay: Layout, today: date) -> str:
    W, H, L, R, T, B = lay.W, lay.H, lay.L, lay.R, lay.T, lay.B
    pw, ph = W - L - R, H - T - B
    step = tick_step(p.total, lay.max_ticks)
    ymax = max(step, math.ceil(p.total / step) * step)
    lo = min(p.rem_all)
    ymin = (
        0 if lo >= 0 else -math.ceil(-lo / step) * step
    )  # room below zero if over-planned

    def X(k: float) -> float:
        return L + pw * k / p.n

    def Y(v: float) -> float:
        return T + ph * (1 - (v - ymin) / (ymax - ymin))

    def pt(k: float, v: float) -> str:
        return f"{X(k):.1f},{Y(v):.1f}"

    def vline(x: float, class_: str) -> str:
        return el("line", class_=class_, x1=x, x2=x, y1=T, y2=T + ph)

    hatch = f"hatch-{lay.name}"  # unique per drawing: both live in the same page
    stripe = el("line", class_="hatch-line", x1=0, y1=0, x2=0, y2=6)
    out: list[str] = [
        el(
            "defs",
            el(
                "pattern",
                stripe,
                id=hatch,
                width=6,
                height=6,
                patternUnits="userSpaceOnUse",
                patternTransform="rotate(45)",
            ),
        )
    ]

    def label(x: float, y: float, text: str, *, strong: bool = False) -> str:
        """Text at x, flipped to the left of x if it would run off the right edge."""
        flip = x + 5 + len(text) * lay.font * 0.6 > W - R
        attrs: dict[str, float | str] = {
            "class_": "axis strong" if strong else "axis",
            "x": x - 5 if flip else x + 5,
            "y": float(y),
        }
        if flip:
            attrs["text_anchor"] = "end"
        return el("text", text, **attrs)

    # horizontal grid + y labels
    for v in range(int(ymin), int(ymax) + 1, step):
        zero = v == 0 and ymin < 0
        out.append(
            el(
                "line",
                class_="grid zero" if zero else "grid",
                x1=L,
                x2=W - R,
                y1=Y(v),
                y2=Y(v),
            )
        )
        out.append(
            el("text", str(v), class_="axis", x=L - 6, y=Y(v) + 4, text_anchor="end")
        )

    # month lines + labels
    for i, ms in enumerate(month_starts(p)):
        k = p.idx(ms)
        out.append(vline(X(k), "grid faint"))
        if i % lay.month_every:
            continue
        text = (
            f"{ms:%b} {APOSTROPHE}{ms:%y}"
            if lay.month_every == 1 and (ms == p.start or ms.month == 1)
            else f"{ms:%b}"
        )
        out.append(el("text", text, class_="axis", x=X(k) + 4, y=H - B // 2 + 4))

    # tolerance band around the even pace
    if p.tol_days > 0 and p.total > 0:
        tol = p.tol_days
        breaks = sorted(
            {
                0.0,
                float(p.n),
                *(
                    min(max(b, 0.0), float(p.n))
                    for b in (p.n * tol / p.total, p.n * (1 - tol / p.total))
                ),
            }
        )
        upper = [(k, min(p.total, p.ideal(k) + tol)) for k in breaks]
        lower = [(k, max(0.0, p.ideal(k) - tol)) for k in reversed(breaks)]
        band = " ".join(pt(k, v) for k, v in upper + lower)
        out.append(el("polygon", class_="band", points=band))

    # leave blocks
    for e in p.entries:
        i0, i1 = max(p.idx(e.start_d), 0), min(p.idx(e.end_d), p.n - 1)
        if i1 < i0:
            continue
        x, w = X(i0), X(i1 + 1) - X(i0)
        booked = e.status == "booked"
        dates = f"{fmt_date(e.start_d)} to {fmt_date(e.end_d)}"
        title = f"{escape(e.label)}: {dates}, {e.days_total:g} days ({e.status})"
        out.append(
            el(
                "rect",
                el("title", title),
                class_="blk-booked" if booked else "blk-tent",
                x=x,
                y=T,
                width=max(w, 2.0),
                height=ph,
                fill="currentColor" if booked else f"url(#{hatch})",
            )
        )

    # flexed bank holidays: working days, so they must not be mistaken for days off
    for d in sorted(p.flexed):
        x = X(p.idx(d))
        title = f"{escape(BANK_HOLIDAYS[d].name)}: {fmt_date(d)} (flexed, working day)"
        out.append(
            el(
                "rect",
                el("title", title),
                class_="blk-flex",
                x=x,
                y=T,
                width=max(X(p.idx(d) + 1) - x, 3.0),
                height=ph,
            )
        )

    # even pace
    out.append(el("line", class_="ideal", x1=X(0), y1=Y(p.total), x2=X(p.n), y2=Y(0)))

    def polyline(rem: list[float], used: list[float]) -> str:
        ks = {0, p.n}
        for i, u in enumerate(used):
            if u > 0:
                ks.update((i, i + 1))
        return " ".join(pt(k, rem[k]) for k in sorted(ks))

    if any(e.status == "tentative" for e in p.entries):
        booked_only = polyline(p.rem_booked, p.used_booked)
        out.append(el("polyline", class_="plan booked-only", points=booked_only))
    out.append(el("polyline", class_="plan", points=polyline(p.rem_all, p.used_all)))

    # markers
    kx = christmas_k(p)
    if kx is not None:
        out.append(vline(X(kx), "marker"))
        out.append(label(X(kx), T + 12, "Christmas", strong=True))
        out.append(
            el("circle", class_="dot ideal-dot", cx=X(kx), cy=Y(p.ideal(kx)), r=4)
        )
        out.append(el("circle", class_="dot", cx=X(kx), cy=Y(p.rem_all[kx]), r=4.5))
    if p.start <= today <= p.end:
        kt = p.idx(today)
        out.append(vline(X(kt), "marker today"))
        # Drop the label a line if it would sit on top of the Christmas one.
        near_xmas = kx is not None and abs(X(kt) - X(kx)) < 9 * lay.font
        out.append(label(X(kt), T + (26 if near_xmas else 12), "Today", strong=True))

    end_v = p.rem_all[-1]
    out.append(el("circle", class_="dot", cx=X(p.n), cy=Y(end_v), r=4.5))
    end_label = f"{end_v:g} unplanned" if end_v >= 0 else f"{-end_v:g} over allowance"
    out.append(
        el(
            "text",
            end_label,
            class_="axis strong",
            x=X(p.n) - 9,
            y=Y(end_v) - 9,
            text_anchor="end",
        )
    )

    return el(
        "svg",
        "".join(out),
        class_=f"chart chart-{lay.name}",
        viewBox=f"0 0 {W} {H}",
        role="img",
        aria_label="Leave remaining across the year against an even pace",
    )


def build_chart(p: Plan, today: date) -> Markup:
    """Both layouts of the chart. `today` places the Today marker."""
    return Markup(_render(p, WIDE, today) + _render(p, COMPACT, today))
