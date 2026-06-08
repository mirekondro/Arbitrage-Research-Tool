from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, DataTable, Input, Label, Select, Static

from src.models import Market, PricePoint


def _ascii_chart(
    series: dict[str, list[tuple[datetime, float]]],
    width: int = 80,
    height: int = 18,
) -> str:
    """Render a basic ASCII line chart; returns ANSI string."""
    try:
        import plotext as plt
        plt.clf()
        plt.plotsize(width, height)
        plt.theme("dark")
        plt.ylim(0, 1)
        plt.ylabel("YES Price")

        colors = ["blue", "green", "magenta", "yellow"]
        for idx, (label, points) in enumerate(series.items()):
            if not points:
                continue
            xs = [p[0].timestamp() for p in points]
            ys = [p[1] for p in points]
            # Downsample if too many points
            if len(xs) > width * 2:
                step = len(xs) // (width * 2)
                xs = xs[::step]
                ys = ys[::step]
            plt.plot(xs, ys, label=label, color=colors[idx % len(colors)])

        plt.xlabel("Time")
        plt.date_form("H:M", from_form="timestamp")
        return plt.build()
    except Exception as exc:
        return f"[Chart unavailable: {exc}]"


def _edge_stats(
    series: dict[str, list[tuple[datetime, float]]],
) -> str:
    """Compute edge window statistics between the first two series."""
    names = list(series.keys())
    if len(names) < 2:
        return "Need at least two platforms to compute edge stats."

    points_a = series[names[0]]
    points_b = series[names[1]]
    if not points_a or not points_b:
        return "Insufficient price history data."

    # Align by common time range
    start = max(points_a[0][0], points_b[0][0])
    end   = min(points_a[-1][0], points_b[-1][0])

    def interp(pts: list[tuple[datetime, float]], ts: datetime) -> float:
        for i, (t, p) in enumerate(pts):
            if t >= ts:
                if i == 0:
                    return p
                t0, p0 = pts[i - 1]
                t1, p1 = t, p
                frac = (ts - t0).total_seconds() / max((t1 - t0).total_seconds(), 1)
                return p0 + frac * (p1 - p0)
        return pts[-1][1]

    if start >= end:
        return "No overlapping time range between the two platforms."

    # Sample spread at regular intervals
    total_seconds = (end - start).total_seconds()
    n_samples = min(500, max(50, int(total_seconds / 3600)))
    dt = total_seconds / n_samples

    spreads: list[tuple[datetime, float]] = []
    for i in range(n_samples):
        ts = start + timedelta(seconds=i * dt)
        pa = interp(points_a, ts)
        pb = interp(points_b, ts)
        spreads.append((ts, abs(pa - pb)))

    if not spreads:
        return "No spread data."

    max_spread_item = max(spreads, key=lambda x: x[1])
    avg_spread = sum(s for _, s in spreads) / len(spreads)

    # Edge window = contiguous span where spread > 2%
    edge_threshold = 0.02
    edge_spans: list[float] = []
    span_start: Optional[datetime] = None
    for ts, sp in spreads:
        if sp >= edge_threshold:
            if span_start is None:
                span_start = ts
        else:
            if span_start is not None:
                edge_spans.append((ts - span_start).total_seconds() / 3600)
                span_start = None
    if span_start is not None:
        edge_spans.append((spreads[-1][0] - span_start).total_seconds() / 3600)

    avg_edge_h = sum(edge_spans) / len(edge_spans) if edge_spans else 0
    max_edge_h = max(edge_spans) if edge_spans else 0

    return (
        f"Platforms: [bold]{names[0]}[/] vs [bold]{names[1]}[/]\n"
        f"Time range: {start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%Y-%m-%d %H:%M')}\n"
        f"Max spread:  [bold yellow]{max_spread_item[1]*100:.1f}%[/]  at {max_spread_item[0].strftime('%Y-%m-%d %H:%M')}\n"
        f"Avg spread:  {avg_spread*100:.1f}%\n"
        f"Edge windows (>{edge_threshold*100:.0f}% spread): {len(edge_spans)}"
        f"  |  Avg duration: {avg_edge_h:.1f}h  |  Max: {max_edge_h:.1f}h"
    )


class EdgeTab(Vertical):
    DEFAULT_CSS = """
    EdgeTab { height: 1fr; }
    #edge-controls {
        height: 3;
        background: $panel-darken-1;
        padding: 0 1;
        align: left middle;
    }
    #edge-controls Label { width: auto; padding: 0 1; }
    #market-search { width: 40; }
    #days-input { width: 6; }
    #edge-run-btn { width: 12; margin: 0 1; }
    #edge-status {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    #edge-chart {
        height: 1fr;
        padding: 1;
        overflow-y: auto;
        background: $surface;
    }
    #edge-stats {
        height: 8;
        background: $panel-darken-2;
        border-top: solid $accent;
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="edge-controls"):
            yield Label("Market title contains:")
            yield Input(placeholder="e.g. Trump 2024", id="market-search")
            yield Label("Days back:")
            yield Input(value="30", id="days-input")
            yield Button("⟳ Load", id="edge-run-btn", variant="primary")
        yield Static("Enter a market keyword and click Load.", id="edge-status")
        yield Static("", id="edge-chart", markup=False)
        yield Static("", id="edge-stats")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "edge-run-btn":
            keyword = self.query_one("#market-search", Input).value.strip()
            try:
                days = int(self.query_one("#days-input", Input).value or "30")
            except ValueError:
                days = 30
            self.load_edge(keyword, days)

    @work(exclusive=True, thread=False)
    async def load_edge(self, keyword: str, days: int) -> None:
        from src.apis import polymarket, manifold

        status = self.query_one("#edge-status", Static)
        chart  = self.query_one("#edge-chart",  Static)
        stats  = self.query_one("#edge-stats",  Static)

        status.update(f"Fetching markets matching '{keyword}'…")
        chart.update("")
        stats.update("")

        try:
            poly_markets, mani_markets = await asyncio.gather(
                polymarket.fetch_markets(300),
                manifold.fetch_markets(300),
            )

            kw = keyword.lower()
            poly_match = next((m for m in poly_markets if kw in m.title.lower()), None)
            mani_match = next((m for m in mani_markets if kw in m.title.lower()), None)

            if not poly_match and not mani_match:
                status.update(f"No markets found matching '{keyword}'. Try a different keyword.")
                return

            now_ts    = int(datetime.now().timestamp())
            start_ts  = now_ts - days * 86_400

            series: dict[str, list[tuple[datetime, float]]] = {}

            if poly_match and poly_match.condition_id:
                status.update(f"Fetching Polymarket history for: {poly_match.title[:60]}…")
                pts = await polymarket.fetch_price_history(
                    poly_match.condition_id, start_ts, now_ts, interval="1h"
                )
                if pts:
                    series["polymarket"] = [(p.timestamp, p.price) for p in pts]

            if mani_match:
                status.update(f"Fetching Manifold history for: {mani_match.title[:60]}…")
                pts = await manifold.fetch_price_history(mani_match.id)
                cutoff = datetime.now() - timedelta(days=days)
                filtered = [(p.timestamp, p.price) for p in pts if p.timestamp >= cutoff]
                if filtered:
                    series["manifold"] = filtered

            if not series:
                status.update("Price history unavailable for the matched markets.")
                return

            labels = list(series.keys())
            status.update(
                f"Showing {days}d price history"
                f"{'  |  POLY: ' + poly_match.title[:40] if poly_match else ''}"
                f"{'  |  MANI: ' + mani_match.title[:40] if mani_match else ''}"
            )

            try:
                from rich.text import Text
                raw = _ascii_chart(series, width=100, height=20)
                chart.update(Text.from_ansi(raw))
            except Exception:
                chart.update("[Chart render failed — plotext may not be installed]")

            stats.update(_edge_stats(series))

        except Exception as exc:
            status.update(f"Error: {exc}")
