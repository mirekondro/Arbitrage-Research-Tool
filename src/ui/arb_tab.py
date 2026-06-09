from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    Select,
    Static,
)

from src.models import ArbitrageOpportunity, Market
from src.core.arbitrage import scan_opportunities

PLATFORM_COLORS = {
    "polymarket": "blue",
    "kalshi":     "green",
    "manifold":   "magenta",
}

PLATFORM_SHORT = {
    "polymarket": "POLY",
    "kalshi":     "KALS",
    "manifold":   "MANI",
}


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """


class ArbTab(Vertical):
    DEFAULT_CSS = """
    ArbTab {
        height: 1fr;
    }
    #controls {
        height: 3;
        background: $panel-darken-1;
        padding: 0 1;
        align: left middle;
    }
    #controls Label {
        width: auto;
        padding: 0 1;
    }
    #min-profit {
        width: 8;
    }
    #refresh-btn {
        width: 12;
        margin: 0 1;
    }
    #arb-table {
        height: 1fr;
    }
    #detail-panel {
        height: 8;
        background: $panel-darken-2;
        border-top: solid $accent;
        padding: 0 1;
        display: none;
    }
    #detail-panel.visible {
        display: block;
    }
    """

    opportunities: reactive[list[ArbitrageOpportunity]] = reactive([], layout=True)
    status_msg: reactive[str] = reactive("Press R or click Refresh to scan markets")
    loading: reactive[bool] = reactive(False)
    _all_markets: dict[str, list[Market]] = {}

    def compose(self) -> ComposeResult:
        yield StatusBar(id="arb-status")
        with Horizontal(id="controls"):
            yield Label("Min profit %:")
            yield Input(value="0.5", id="min-profit", placeholder="0.5")
            yield Button("⟳ Refresh", id="refresh-btn", variant="primary")
            yield Label("  Threshold similarity %:")
            yield Input(value="72", id="sim-thresh", placeholder="72")
        yield DataTable(id="arb-table", zebra_stripes=True, cursor_type="row")
        yield Static("", id="detail-panel")

    def on_mount(self) -> None:
        table = self.query_one("#arb-table", DataTable)
        table.add_columns(
            "#",
            "Event",
            "Buy YES on",
            "YES $",
            "Buy NO on",
            "NO $",
            "Cost",
            "Profit %",
            "Match %",
            "Closes",
        )
        self.fetch_markets()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh-btn":
            self.fetch_markets()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = event.cursor_row
        if idx < len(self.opportunities):
            opp = self.opportunities[idx]
            detail = self.query_one("#detail-panel", Static)
            detail.update(self._format_detail(opp))
            detail.add_class("visible")

    def watch_status_msg(self, msg: str) -> None:
        self.query_one("#arb-status", StatusBar).update(msg)

    def watch_opportunities(self, opps: list[ArbitrageOpportunity]) -> None:
        self._populate_table(opps)

    @work(exclusive=True, thread=False)
    async def fetch_markets(self) -> None:
        from src.apis import polymarket, kalshi, manifold

        self.status_msg = "Fetching markets from Polymarket, Kalshi, Manifold…"
        self.loading = True

        try:
            poly_task  = asyncio.create_task(polymarket.fetch_markets(200))
            kals_task  = asyncio.create_task(kalshi.fetch_markets(200))
            mani_task  = asyncio.create_task(manifold.fetch_markets(200))

            poly, kals, mani = await asyncio.gather(
                poly_task, kals_task, mani_task, return_exceptions=True
            )

            self._all_markets = {}
            counts = []
            for name, result in [("polymarket", poly), ("kalshi", kals), ("manifold", mani)]:
                if isinstance(result, list):
                    self._all_markets[name] = result
                    counts.append(f"{name}:{len(result)}")
                else:
                    self._all_markets[name] = []
                    counts.append(f"{name}:ERR")

            try:
                min_profit = float(self.query_one("#min-profit", Input).value or "0.5")
            except Exception:
                min_profit = 0.5
            try:
                sim_thresh = float(self.query_one("#sim-thresh", Input).value or "72")
            except Exception:
                sim_thresh = 72.0

            opps = scan_opportunities(self._all_markets, threshold=sim_thresh)
            opps = [o for o in opps if o.profit_pct >= min_profit]
            self.opportunities = opps

            now = datetime.now().strftime("%H:%M:%S")
            self.status_msg = (
                f"[{now}]  Fetched: {' | '.join(counts)}"
                f"  •  Opportunities found: {len(opps)}"
                f"  •  R to refresh"
            )
        except Exception as exc:
            self.status_msg = f"Error: {exc}"
        finally:
            self.loading = False

    def _populate_table(self, opps: list[ArbitrageOpportunity]) -> None:
        table = self.query_one("#arb-table", DataTable)
        table.clear()
        for i, opp in enumerate(opps, 1):
            title = opp.matched_title[:48] + "…" if len(opp.matched_title) > 48 else opp.matched_title
            closes = ""
            for mkt in (opp.market_a, opp.market_b):
                if mkt.close_time:
                    closes = mkt.close_time.strftime("%b %d")
                    break

            profit_str = f"[bold green]+{opp.profit_pct:.1f}%[/]"
            cost_str   = f"${opp.total_cost:.3f}"

            table.add_row(
                str(i),
                title,
                f"[{PLATFORM_COLORS.get(opp.buy_yes_on,'white')}]{PLATFORM_SHORT.get(opp.buy_yes_on, opp.buy_yes_on)}[/]",
                f"{opp.yes_price:.3f}",
                f"[{PLATFORM_COLORS.get(opp.buy_no_on,'white')}]{PLATFORM_SHORT.get(opp.buy_no_on, opp.buy_no_on)}[/]",
                f"{opp.no_price:.3f}",
                cost_str,
                profit_str,
                f"{opp.similarity:.0f}%",
                closes,
            )

    def _format_detail(self, opp: ArbitrageOpportunity) -> str:
        a, b = opp.market_a, opp.market_b
        return (
            f"[bold]{opp.matched_title}[/]\n"
            f"  [{PLATFORM_COLORS.get(a.platform,'white')}]{a.platform.upper()}[/]  YES={a.yes_price:.4f}  NO={a.no_price:.4f}"
            f"  Vol=${a.volume:,.0f}  Liq=${a.liquidity:,.0f}\n"
            f"  [{PLATFORM_COLORS.get(b.platform,'white')}]{b.platform.upper()}[/]  YES={b.yes_price:.4f}  NO={b.no_price:.4f}"
            f"  Vol=${b.volume:,.0f}  Liq=${b.liquidity:,.0f}\n"
            f"  Strategy: BUY YES on [bold]{opp.buy_yes_on}[/] @ {opp.yes_price:.4f}"
            f"  +  BUY NO on [bold]{opp.buy_no_on}[/] @ {opp.no_price:.4f}"
            f"  →  Guaranteed edge: [bold green]+{opp.profit_pct:.2f}%[/]  (match={opp.similarity:.0f}%)\n"
            f"  URLs:  {a.url}  |  {b.url}"
        )
