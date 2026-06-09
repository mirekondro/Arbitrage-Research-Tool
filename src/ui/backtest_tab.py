from __future__ import annotations

from datetime import datetime
from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Label, Static

from src.models import BacktestResult, Trade


def _max_drawdown(running_pnl: list[float]) -> float:
    """Maximum peak-to-trough drop in the running P&L curve."""
    if len(running_pnl) < 2:
        return 0.0
    peak = running_pnl[0]
    max_dd = 0.0
    for v in running_pnl:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _streak(trades: list[Trade]) -> tuple[int, int]:
    """Return (current_win_streak, current_loss_streak)."""
    win_streak = loss_streak = 0
    cur_wins = cur_losses = 0
    for t in trades:
        if t.pnl is None:
            continue
        if t.pnl > 0:
            cur_wins += 1
            cur_losses = 0
        elif t.pnl < 0:
            cur_losses += 1
            cur_wins = 0
        win_streak  = max(win_streak,  cur_wins)
        loss_streak = max(loss_streak, cur_losses)
    return win_streak, loss_streak


def _pnl_chart(result: BacktestResult, width: int = 100, height: int = 14) -> str:
    if not result.running_pnl:
        return "[No P&L data]"
    try:
        import plotext as plt
        plt.clf()
        plt.plotsize(width, height)
        plt.theme("dark")

        xs = list(range(len(result.running_pnl)))
        ys = result.running_pnl

        plt.plot(xs, ys, label="Cumulative P&L ($)", color="green+")
        plt.hline(0, color="white")
        plt.xlabel("Trade #")
        plt.ylabel("P&L ($)")
        plt.title("Copy-Trade Equity Curve")
        return plt.build()
    except Exception:
        mn, mx = min(result.running_pnl), max(result.running_pnl)
        rng = mx - mn or 1
        bars = "▁▂▃▄▅▆▇█"
        spark = "".join(
            bars[min(7, int((v - mn) / rng * 7))]
            for v in result.running_pnl[::max(1, len(result.running_pnl) // 70)]
        )
        return f"Equity sparkline (${mn:.0f} → ${mx:.0f}):\n{spark}"


class BacktestTab(Vertical):
    DEFAULT_CSS = """
    BacktestTab { height: 1fr; }

    #bt-controls {
        height: 3;
        background: #161b22;
        border-bottom: solid #21262d;
        padding: 0 1;
        align: left middle;
    }
    #bt-controls Label { width: auto; padding: 0 1; color: #8b949e; }
    #wallet-input { width: 46; }
    #delay-input  { width: 6; }
    #days-bt      { width: 6; }
    #bt-run-btn   { width: 10; margin: 0 1; }

    #bt-status {
        height: 1;
        background: #0d1117;
        color: #8b949e;
        padding: 0 1;
        border-bottom: solid #21262d;
    }

    #bt-summary {
        height: 6;
        background: #161b22;
        padding: 1 2;
        border-bottom: solid #30363d;
    }

    #bt-chart {
        height: 16;
        background: #0d1117;
        padding: 1;
        overflow: auto;
        border-bottom: solid #30363d;
    }

    #bt-table { height: 1fr; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="bt-controls"):
            yield Label("Wallet 0x:")
            yield Input(placeholder="0xabc123…", id="wallet-input")
            yield Label("  Copy delay (h):")
            yield Input(value="0", id="delay-input")
            yield Label("  Lookback (days):")
            yield Input(value="90", id="days-bt")
            yield Button("▶ Run", id="bt-run-btn", variant="primary")
        yield Static(
            "Enter a Polymarket wallet address and press [bold]Run[/] to simulate copying their trades.",
            id="bt-status",
        )
        yield Static("", id="bt-summary")
        yield Static("", id="bt-chart", markup=False)
        yield DataTable(id="bt-table", zebra_stripes=True, cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#bt-table", DataTable)
        table.add_columns(
            "#", "Market", "Side", "Fill $", "Size $",
            "Date", "Outcome", "P&L $",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "bt-run-btn":
            return
        address = self.query_one("#wallet-input", Input).value.strip()
        if not address:
            self.query_one("#bt-status", Static).update(
                "[red]Please enter a wallet address.[/]"
            )
            return
        try:
            delay = float(self.query_one("#delay-input", Input).value or "0")
        except ValueError:
            delay = 0.0
        try:
            days = int(self.query_one("#days-bt", Input).value or "90")
        except ValueError:
            days = 90
        self._run(address, delay, days)

    @work(exclusive=True, thread=False)
    async def _run(self, address: str, delay_hours: float, days: int) -> None:
        from src.core.backtest import run_backtest

        status  = self.query_one("#bt-status",  Static)
        summary = self.query_one("#bt-summary", Static)
        chart   = self.query_one("#bt-chart",   Static)
        table   = self.query_one("#bt-table",   DataTable)

        status.update(f"Fetching activity for [bold]{address[:16]}…[/]")
        summary.update("")
        chart.update("")
        table.clear()

        try:
            result = await run_backtest(
                address, lookback_days=days, copy_delay_hours=delay_hours
            )

            if not result.trades:
                status.update(
                    "[yellow]No trades found.[/] Double-check the address or try a more "
                    "active wallet. Polymarket wallets are 0x Polygon addresses."
                )
                return

            # ── Stats ────────────────────────────────────────────────────────
            max_dd = _max_drawdown(result.running_pnl)
            best_win_streak, worst_loss_streak = _streak(result.trades)
            resolved = [t for t in result.trades if t.pnl is not None]
            avg_pnl  = sum(t.pnl for t in resolved) / len(resolved) if resolved else 0

            pnl_col  = "green" if result.total_pnl >= 0 else "red"
            roi_col  = "green" if result.roi_pct   >= 0 else "red"
            sign     = "+" if result.total_pnl >= 0 else ""

            summary.update(
                f"  [bold white]Wallet:[/] [dim]{address[:26]}…[/]   "
                f"[bold white]Delay:[/] {delay_hours}h   "
                f"[bold white]Period:[/] {days}d\n"
                f"\n"
                f"  Trades: [bold]{len(result.trades)}[/] "
                f"  Win rate: [bold]{result.win_rate*100:.1f}%[/] "
                f"  Avg P&L/trade: [bold]${avg_pnl:.2f}[/] "
                f"  Invested: [bold]${result.total_invested:,.2f}[/]\n"
                f"\n"
                f"  Total P&L: [{pnl_col}][bold]{sign}${result.total_pnl:,.2f}[/][/]   "
                f"ROI: [{roi_col}][bold]{sign}{result.roi_pct:.1f}%[/][/]   "
                f"Max drawdown: [red]${max_dd:,.2f}[/]   "
                f"Best streak: [green]{best_win_streak}W[/]  [red]{worst_loss_streak}L[/]"
            )

            # ── Chart ────────────────────────────────────────────────────────
            try:
                from rich.text import Text
                chart.update(Text.from_ansi(_pnl_chart(result)))
            except Exception:
                chart.update("[dim]Chart unavailable[/]")

            # ── Trades table ─────────────────────────────────────────────────
            for i, t in enumerate(result.trades, 1):
                side_markup = (
                    f"[bold green]YES[/]" if t.side == "YES"
                    else f"[bold red]NO[/]"
                )
                pnl_str = ""
                if t.pnl is not None:
                    s = "+" if t.pnl >= 0 else ""
                    col = "green" if t.pnl >= 0 else "red"
                    pnl_str = f"[{col}]{s}{t.pnl:.2f}[/]"
                table.add_row(
                    str(i),
                    t.market_title[:46] + ("…" if len(t.market_title) > 46 else ""),
                    side_markup,
                    f"{t.price:.3f}",
                    f"${t.size:.2f}",
                    t.timestamp.strftime("%Y-%m-%d %H:%M"),
                    t.outcome or "[dim]pending[/]",
                    pnl_str,
                )

            status.update(
                f"[dim]{address[:20]}…[/]   "
                f"{len(result.trades)} trades   "
                f"P&L: [{pnl_col}]{sign}${result.total_pnl:,.2f}[/]   "
                f"ROI: [{roi_col}]{sign}{result.roi_pct:.1f}%[/]"
            )

        except Exception as exc:
            status.update(f"[red]Error: {exc}[/]")
