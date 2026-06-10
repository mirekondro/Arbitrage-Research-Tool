from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static

from src.models import Market, PricePoint


def _ascii_chart(
    series: dict[str, list[tuple[datetime, float]]],
    width: int = 110,
    height: int = 22,
) -> str:
    try:
        import plotext as plt
        plt.clf()
        plt.plotsize(width, height)
        plt.theme("dark")
        plt.ylim(0, 1)
        plt.ylabel("YES Probability")
        plt.title("Price History & Spread")

        palette = ["blue+", "green+", "orange+", "magenta+"]
        all_times: list[float] = []

        for idx, (label, points) in enumerate(series.items()):
            if not points or label == "_spread":
                continue
            xs = [p[0].timestamp() for p in points]
            ys = [p[1] for p in points]
            all_times.extend(xs)
            if len(xs) > width * 2:
                step = max(1, len(xs) // (width * 2))
                xs, ys = xs[::step], ys[::step]
            plt.plot(xs, ys, label=label, color=palette[idx % len(palette)])

        # Spread overlay (abs difference)
        if "_spread" in series:
            sp = series["_spread"]
            sxs = [p[0].timestamp() for p in sp]
            sys_ = [p[1] for p in sp]
            if len(sxs) > width * 2:
                step = max(1, len(sxs) // (width * 2))
                sxs, sys_ = sxs[::step], sys_[::step]
            plt.plot(sxs, sys_, label="spread", color="red")

        if all_times:
            plt.xlabel("Time →")
        return plt.build()
    except Exception as exc:
        return f"[Chart unavailable: {exc}]"


def _compute_spread(
    series: dict[str, list[tuple[datetime, float]]]
) -> list[tuple[datetime, float]]:
    """Interpolate two series onto a shared timeline and return abs difference."""
    names = [k for k in series if k != "_spread"]
    if len(names) < 2:
        return []

    pts_a = series[names[0]]
    pts_b = series[names[1]]
    if not pts_a or not pts_b:
        return []

    start = max(pts_a[0][0], pts_b[0][0])
    end   = min(pts_a[-1][0], pts_b[-1][0])
    if start >= end:
        return []

    def interp(pts: list, ts: datetime) -> float:
        for i, (t, p) in enumerate(pts):
            if t >= ts:
                if i == 0:
                    return p
                t0, p0 = pts[i-1]
                frac = (ts - t0).total_seconds() / max((t - t0).total_seconds(), 1)
                return p0 + frac * (p - p0)
        return pts[-1][1]

    total_sec = (end - start).total_seconds()
    n = min(200, max(40, int(total_sec / 3600)))
    result = []
    for i in range(n):
        ts = start + timedelta(seconds=i * total_sec / n)
        result.append((ts, abs(interp(pts_a, ts) - interp(pts_b, ts))))
    return result


def _edge_stats(series: dict) -> str:
    names = [k for k in series if k != "_spread"]
    if len(names) < 2:
        return "Load two platforms to see edge stats."

    spread = series.get("_spread") or _compute_spread({k: series[k] for k in names[:2]})
    if not spread:
        return "No overlapping time window."

    max_sp = max(spread, key=lambda x: x[1])
    avg_sp = sum(s for _, s in spread) / len(spread)

    edge_thresh = 0.02
    spans: list[float] = []
    span_start: Optional[datetime] = None
    for ts, sp in spread:
        if sp >= edge_thresh:
            if span_start is None:
                span_start = ts
        else:
            if span_start is not None:
                spans.append((ts - span_start).total_seconds() / 3600)
                span_start = None
    if span_start is not None:
        spans.append((spread[-1][0] - span_start).total_seconds() / 3600)

    avg_h = sum(spans) / len(spans) if spans else 0
    max_h = max(spans) if spans else 0

    lines = [
        f"  Platforms:   [bold]{names[0]}[/]  vs  [bold]{names[1]}[/]",
        f"  Peak spread: [bold yellow]{max_sp[1]*100:.1f}%[/]  @ {max_sp[0].strftime('%b %d %H:%M')}",
        f"  Avg spread:  {avg_sp*100:.1f}%",
        f"  Edge windows (>{edge_thresh*100:.0f}% spread): [bold]{len(spans)}[/]"
        f"  │  Avg duration: {avg_h:.1f}h  │  Longest: {max_h:.1f}h",
    ]
    if not spans:
        lines.append("  [dim]No significant edge windows in this period.[/]")
    return "\n".join(lines)


class EdgeTab(Vertical):
    DEFAULT_CSS = """
    EdgeTab { height: 1fr; }

    #edge-controls {
        height: 3;
        background: #161b22;
        border-bottom: solid #21262d;
        padding: 0 1;
        align: left middle;
    }
    #edge-controls Label { width: auto; padding: 0 1; color: #8b949e; }
    #market-search { width: 38; }
    #days-input    { width: 6; }
    #edge-run-btn  { width: 12; margin: 0 1; }

    #edge-status {
        height: 1;
        background: #0d1117;
        color: #8b949e;
        padding: 0 1;
        border-bottom: solid #21262d;
    }

    #edge-chart {
        height: 1fr;
        padding: 1;
        overflow: auto;
        background: #0d1117;
    }

    #edge-stats {
        height: 7;
        background: #161b22;
        border-top: solid #30363d;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="edge-controls"):
            yield Label("Market keyword:")
            yield Input(placeholder="e.g. Trump election", id="market-search")
            yield Label("Days:")
            yield Input(value="14", id="days-input")
            yield Button("⟳ Load", id="edge-run-btn", variant="primary")
        yield Static("Enter a keyword and click Load — or press E on an arb row.", id="edge-status")
        yield Static("", id="edge-chart", markup=False)
        yield Static("", id="edge-stats")

    # Called programmatically from ArbTab via the app
    def set_keyword(self, keyword: str) -> None:
        try:
            inp = self.query_one("#market-search", Input)
            inp.value = keyword
            days_str = self.query_one("#days-input", Input).value
            days = int(days_str) if days_str.isdigit() else 14
            self.load_edge(keyword, days)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "edge-run-btn":
            keyword = self.query_one("#market-search", Input).value.strip()
            try:
                days = int(self.query_one("#days-input", Input).value or "14")
            except ValueError:
                days = 14
            self.load_edge(keyword, days)

    @work(exclusive=True, thread=False)
    async def load_edge(self, keyword: str, days: int) -> None:
        from src.apis import polymarket, manifold

        status = self.query_one("#edge-status", Static)
        chart  = self.query_one("#edge-chart",  Static)
        stats  = self.query_one("#edge-stats",  Static)

        status.update(f"Searching for '{keyword}' on Polymarket & Manifold…")
        chart.update("")
        stats.update("")

        try:
            poly_mkts, mani_mkts = await asyncio.gather(
                polymarket.fetch_markets(300),
                manifold.fetch_markets(300),
            )

            kw = keyword.lower()
            poly_match = next((m for m in poly_mkts if kw in m.title.lower()), None)
            mani_match = next((m for m in mani_mkts if kw in m.title.lower()), None)

            if not poly_match and not mani_match:
                status.update(
                    f"[yellow]No markets found for '{keyword}'.[/] "
                    f"Try a shorter keyword (e.g. 'NBA', 'Trump', 'Bitcoin')."
                )
                return

            now_ts   = int(datetime.now().timestamp())
            start_ts = now_ts - min(days, 14) * 86_400

            series: dict[str, list[tuple[datetime, float]]] = {}

            if poly_match and poly_match.condition_id:
                status.update(f"Loading Polymarket history: {poly_match.title[:60]}…")
                pts = await polymarket.fetch_price_history(
                    poly_match.condition_id, start_ts, now_ts, interval="6h"
                )
                if pts:
                    series["polymarket"] = [(p.timestamp, p.price) for p in pts]

            if mani_match:
                status.update(f"Loading Manifold history: {mani_match.title[:60]}…")
                pts = await manifold.fetch_price_history(mani_match.id)
                cutoff = datetime.now() - timedelta(days=days)
                filtered = [(p.timestamp, p.price) for p in pts if p.timestamp >= cutoff]
                if filtered:
                    series["manifold"] = filtered

            if not series:
                status.update("[yellow]Price history unavailable — market may be too new.[/]")
                return

            # Compute spread line
            if len(series) >= 2:
                series["_spread"] = _compute_spread(series)

            # Header
            parts = []
            if poly_match:
                parts.append(f"POLY: {poly_match.title[:38]}")
            if mani_match:
                parts.append(f"MANI: {mani_match.title[:38]}")
            status.update(f"[dim]{days}d[/]  " + "  │  ".join(parts))

            # Chart
            try:
                from rich.text import Text
                raw = _ascii_chart(series)
                chart.update(Text.from_ansi(raw))
            except Exception:
                chart.update("[dim]Chart render failed — install plotext[/]")

            stats.update(_edge_stats(series))

        except Exception as exc:
            status.update(f"[red]Error: {exc}[/]")
