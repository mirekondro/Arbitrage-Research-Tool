from __future__ import annotations

from datetime import datetime
from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, DataTable, Input, Label, Static

from src.models import BacktestResult, Trade


def _pnl_chart(result: BacktestResult, width: int = 90, height: int = 14) -> str:
    if not result.running_pnl:
        return "[No P&L data to chart]"
    try:
        import plotext as plt
        plt.clf()
        plt.plotsize(width, height)
        plt.theme("dark")

        xs = list(range(len(result.running_pnl)))
        ys = result.running_pnl

        # Color positive / negative regions
        pos_xs = [x for x, y in zip(xs, ys) if y >= 0]
        pos_ys = [y for y in ys if y >= 0] or None
        neg_xs = [x for x, y in zip(xs, ys) if y < 0]
        neg_ys = [y for y in ys if y < 0] or None

        plt.plot(xs, ys, label="Running P&L ($)", color="white")
        plt.hline(0, color="dark_gray")
        plt.xlabel("Trade #")
        plt.ylabel("Cumulative P&L ($)")
        plt.title("Copy-Trade P&L Curve")
        return plt.build()
    except Exception as exc:
        # Fallback: simple text sparkline
        mn, mx = min(result.running_pnl), max(result.running_pnl)
        rng = mx - mn or 1
        bars = "▁▂▃▄▅▆▇█"
        spark = "".join(
            bars[min(7, int((v - mn) / rng * 7))]
            for v in result.running_pnl[:: max(1, len(result.running_pnl) // 60)]
        )
        return f"P&L Sparkline:\n{spark}\nMin: ${mn:.2f}  Max: ${mx:.2f}"


class BacktestTab(Vertical):
    DEFAULT_CSS = """
    BacktestTab { height: 1fr; }
    #bt-controls {
        height: 3;
        background: $panel-darken-1;
        padding: 0 1;
        align: left middle;
    }
    #bt-controls Label { width: auto; padding: 0 1; }
    #wallet-input { width: 48; }
    #delay-input  { width: 6; }
    #days-bt      { width: 6; }
    #bt-run-btn   { width: 12; margin: 0 1; }
    #bt-status {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    #bt-summary {
        height: 5;
        background: $panel-darken-2;
        padding: 1 2;
        border-bottom: solid $accent;
    }
    #bt-chart {
        height: 16;
        background: $surface;
        padding: 1;
        overflow-y: auto;
        border-bottom: solid $primary;
    }
    #bt-table { height: 1fr; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="bt-controls"):
            yield Label("Wallet 0x:")
            yield Input(placeholder="0xabc…", id="wallet-input")
            yield Label("Delay (h):")
            yield Input(value="0", id="delay-input")
            yield Label("Days:")
            yield Input(value="90", id="days-bt")
            yield Button("▶ Run", id="bt-run-btn", variant="primary")
        yield Static("Enter a Polymarket wallet address and click Run.", id="bt-status")
        yield Static("", id="bt-summary")
        yield Static("", id="bt-chart", markup=False)
        yield DataTable(id="bt-table", zebra_stripes=True, cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#bt-table", DataTable)
        table.add_columns("#", "Market", "Side", "Price", "Size $", "Time", "Outcome", "P&L $")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "bt-run-btn":
            return
        address = self.query_one("#wallet-input", Input).value.strip()
        if not address:
            self.query_one("#bt-status", Static).update("[red]Please enter a wallet address.[/]")
            return
        try:
            delay = float(self.query_one("#delay-input", Input).value or "0")
        except ValueError:
            delay = 0.0
        try:
            days = int(self.query_one("#days-bt", Input).value or "90")
        except ValueError:
            days = 90
        self.run_backtest(address, delay, days)

    @work(exclusive=True, thread=False)
    async def run_backtest(self, address: str, delay_hours: float, days: int) -> None:
        from src.core.backtest import run_backtest

        status  = self.query_one("#bt-status",  Static)
        summary = self.query_one("#bt-summary", Static)
        chart   = self.query_one("#bt-chart",   Static)
        table   = self.query_one("#bt-table",   DataTable)

        status.update(f"Fetching trade history for {address[:12]}…")
        summary.update("")
        chart.update("")
        table.clear()

        try:
            result = await run_backtest(address, lookback_days=days, copy_delay_hours=delay_hours)

            if not result.trades:
                status.update(
                    "No trades found. Check the address or try a known active wallet."
                )
                return

            # Summary
            pnl_color = "green" if result.total_pnl >= 0 else "red"
            sign = "+" if result.total_pnl >= 0 else ""
            summary.update(
                f"[bold]Copy-Trade Backtest[/]   Wallet: [dim]{address[:20]}…[/]   "
                f"Delay: {delay_hours}h   Period: {days}d\n"
                f"  Trades:  [bold]{len(result.trades)}[/]   "
                f"Win rate:  [bold]{result.win_rate*100:.1f}%[/]   "
                f"Invested:  [bold]${result.total_invested:,.2f}[/]\n"
                f"  Total P&L:  [{pnl_color}][bold]{sign}${result.total_pnl:,.2f}[/][/]   "
                f"ROI:  [{pnl_color}][bold]{sign}{result.roi_pct:.1f}%[/][/]"
            )

            # P&L chart
            try:
                from rich.text import Text
                raw = _pnl_chart(result)
                chart.update(Text.from_ansi(raw))
            except Exception:
                chart.update("[Chart unavailable]")

            # Trade table
            for i, t in enumerate(result.trades, 1):
                pnl_str = ""
                if t.pnl is not None:
                    sign2 = "+" if t.pnl >= 0 else ""
                    col   = "green" if t.pnl >= 0 else "red"
                    pnl_str = f"[{col}]{sign2}{t.pnl:.2f}[/]"
                outcome_str = t.outcome or "pending"
                table.add_row(
                    str(i),
                    t.market_title[:45] + ("…" if len(t.market_title) > 45 else ""),
                    f"[bold]{'[green]' if t.side=='YES' else '[red]'}{t.side}[/]",
                    f"{t.price:.3f}",
                    f"${t.size:.2f}",
                    t.timestamp.strftime("%Y-%m-%d %H:%M"),
                    outcome_str,
                    pnl_str,
                )

            status.update(
                f"Loaded {len(result.trades)} trades  |  "
                f"P&L: {sign}${result.total_pnl:,.2f}  |  ROI: {sign}{result.roi_pct:.1f}%"
            )

        except Exception as exc:
            status.update(f"[red]Error: {exc}[/]")
