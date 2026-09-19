"""Server-rendered SVG chart of leave remaining against an even pace.

The chart is drawn twice, in a wide and a compact layout, and CSS shows whichever
fits the screen. Scaling one drawing down to phone width would shrink the text to
nothing, so the compact layout is taller, with fewer ticks and month labels.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from markupsafe import Markup, escape

from .formatting import fmt_date
from .holidays import BANK_HOLIDAYS
from .plan import Plan, christmas_k, month_starts


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
COMPACT = Layout("compact", 360, 400, 30, 14, 24, 32, max_ticks=5, month_every=2, font=11)


def tick_step(top: float, max_ticks: int) -> int:
    for s in (1, 2, 5, 10, 20, 25, 50, 100):
        if top / s <= max_ticks:
            return s
    return 100


def _render(p: Plan, lay: Layout) -> str:
    W, H, L, R, T, B = lay.W, lay.H, lay.L, lay.R, lay.T, lay.B
    pw, ph = W - L - R, H - T - B
    step = tick_step(p.total, lay.max_ticks)
    ymax = max(step, math.ceil(p.total / step) * step)
    lo = min(p.rem_all)
    ymin = (
        0 if lo >= 0 else -math.ceil(-lo / step) * step
    )  # room below zero if over-planned
    X = lambda k: L + pw * k / p.n
    Y = lambda v: T + ph * (1 - (v - ymin) / (ymax - ymin))
    pt = lambda k, v: f"{X(k):.1f},{Y(v):.1f}"
    hatch = f"hatch-{lay.name}"  # unique per drawing: both live in the same page
    out: list[str] = []

    out.append(
        f'<defs><pattern id="{hatch}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<line class="hatch-line" x1="0" y1="0" x2="0" y2="6"/></pattern></defs>'
    )

    def label(x: float, y: float, text: str, strong: bool = False) -> str:
        """Text at x, flipped to the left of x if it would run off the right edge."""
        width = len(text) * lay.font * 0.6
        flip = x + 5 + width > W - R
        return (
            f'<text class="axis{" strong" if strong else ""}" x="{x - 5 if flip else x + 5:.1f}" y="{y:.1f}"'
            f'{' text-anchor="end"' if flip else ""}>{text}</text>'
        )

    # horizontal grid + y labels
    for v in range(int(ymin), int(ymax) + 1, step):
        out.append(
            f'<line class="grid{" zero" if v == 0 and ymin < 0 else ""}" x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
        )
        out.append(
            f'<text class="axis" x="{L - 6}" y="{Y(v) + 4:.1f}" text-anchor="end">{v}</text>'
        )

    # month lines + labels
    for i, ms in enumerate(month_starts(p)):
        k = p.idx(ms)
        out.append(
            f'<line class="grid faint" x1="{X(k):.1f}" x2="{X(k):.1f}" y1="{T}" y2="{T + ph}"/>'
        )
        if i % lay.month_every:
            continue
        text = (
            f"{ms:%b} ’{ms:%y}"
            if lay.month_every == 1 and (ms == p.start or ms.month == 1)
            else f"{ms:%b}"
        )
        out.append(f'<text class="axis" x="{X(k) + 4:.1f}" y="{H - B // 2 + 4}">{text}</text>')

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
        out.append(
            f'<polygon class="band" points="{" ".join(pt(k, v) for k, v in upper + lower)}"/>'
        )

    # leave blocks
    for e in p.entries:
        i0, i1 = max(p.idx(e["start_d"]), 0), min(p.idx(e["end_d"]), p.n - 1)
        if i1 < i0:
            continue
        x, w = X(i0), X(i1 + 1) - X(i0)
        cls = "blk-booked" if e["status"] == "booked" else "blk-tent"
        fill = (
            '<rect class="%s" x="%.1f" y="%d" width="%.1f" height="%d" fill="%s"><title>%s</title></rect>'
            % (
                cls,
                x,
                T,
                max(w, 2),
                ph,
                f"url(#{hatch})" if cls == "blk-tent" else "currentColor",
                f"{escape(e['label'])}: {fmt_date(e['start_d'])} to {fmt_date(e['end_d'])}, {e['days_total']:g} days ({e['status']})",
            )
        )
        out.append(fill)

    # flexed bank holidays: working days, so they must not be mistaken for days off
    for d in sorted(p.flexed):
        x = X(p.idx(d))
        out.append(
            f'<rect class="blk-flex" x="{x:.1f}" y="{T}" width="{max(X(p.idx(d) + 1) - x, 3):.1f}" height="{ph}">'
            f"<title>{escape(BANK_HOLIDAYS[d].name)}: {fmt_date(d)} (flexed, working day)</title></rect>"
        )

    # even pace
    out.append(
        f'<line class="ideal" x1="{X(0):.1f}" y1="{Y(p.total):.1f}" x2="{X(p.n):.1f}" y2="{Y(0):.1f}"/>'
    )

    def polyline(rem: list[float], used: list[float]) -> str:
        ks = {0, p.n}
        for i, u in enumerate(used):
            if u > 0:
                ks.update((i, i + 1))
        return " ".join(pt(k, rem[k]) for k in sorted(ks))

    has_tent = any(e["status"] == "tentative" for e in p.entries)
    if has_tent:
        out.append(
            f'<polyline class="plan booked-only" points="{polyline(p.rem_booked, p.used_booked)}"/>'
        )
    out.append(f'<polyline class="plan" points="{polyline(p.rem_all, p.used_all)}"/>')

    # markers
    kx = christmas_k(p)
    if kx is not None:
        out.append(
            f'<line class="marker" x1="{X(kx):.1f}" x2="{X(kx):.1f}" y1="{T}" y2="{T + ph}"/>'
        )
        out.append(label(X(kx), T + 12, "Christmas", strong=True))
        out.append(
            f'<circle class="dot ideal-dot" cx="{X(kx):.1f}" cy="{Y(p.ideal(kx)):.1f}" r="4"/>'
        )
        out.append(
            f'<circle class="dot" cx="{X(kx):.1f}" cy="{Y(p.rem_all[kx]):.1f}" r="4.5"/>'
        )
    today = date.today()
    if p.start <= today <= p.end:
        kt = p.idx(today)
        out.append(
            f'<line class="marker today" x1="{X(kt):.1f}" x2="{X(kt):.1f}" y1="{T}" y2="{T + ph}"/>'
        )
        # Drop the label a line if it would sit on top of the Christmas one.
        near_xmas = kx is not None and abs(X(kt) - X(kx)) < 9 * lay.font
        out.append(label(X(kt), T + (26 if near_xmas else 12), "Today", strong=True))

    end_v = p.rem_all[-1]
    out.append(f'<circle class="dot" cx="{X(p.n):.1f}" cy="{Y(end_v):.1f}" r="4.5"/>')
    end_label = f"{end_v:g} unplanned" if end_v >= 0 else f"{-end_v:g} over allowance"
    out.append(
        f'<text class="axis strong" x="{X(p.n) - 9:.1f}" y="{Y(end_v) - 9:.1f}" text-anchor="end">{end_label}</text>'
    )

    return (
        f'<svg class="chart chart-{lay.name}" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="Leave remaining across the year against an even pace">'
        + "".join(out)
        + "</svg>"
    )


def build_chart(p: Plan) -> Markup:
    return Markup(_render(p, WIDE) + _render(p, COMPACT))
