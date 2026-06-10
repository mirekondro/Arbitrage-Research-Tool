"""Crypto Exchange Arbitrage tab — live price spreads across Binance / Coinbase / Kraken.

Shows pairs where the ask price on one exchange is lower than the bid price on
another (i.e. a theoretical buy-low/sell-high opportunity across venues).
Refreshes every 30 seconds by default.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import NamedTuple

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, DataTable, Label, Static, Switch

from src.apis.binance  import fetch_prices as binance_prices
from src.apis.coinbase import fetch_prices as coinbase_prices
from src.apis.kraken   import fetch_prices as kraken_prices

log = logging.getLogger(__name__)

_AUTO_REFRESH_SECS = 30
_MIN_SPREAD_PCT    = 0.03   # hide sub-noise spreads

# Visual identity per exchange
_EX_COLOR = {
    "Binance":  "#f0b90b",
    "Coinbase": "#4d9fff",
    "Kraken":   "#9b7fe8",
}
_EX_SHORT = {
    "Binance":  "BNC",
    "Coinbase": "CBX",
    "Kraken":   "KRK",
}

_CRYPTO_ICON = {
    "BTC": "₿", "ETH": "Ξ", "SOL": "◎", "XRP": "✕",
    "DOGE": "Ð", "ADA": "₳", "AVAX": "▲", "LINK": "⬡",
    "LTC": "Ł", "DOT": "●", "UNI": "◈", "ATOM": "⚛",
    "MATIC": "⬡", "BNB": "✦",
}


# ── Data types ────────────────────────────────────────────────────────────────

class ExPrice(NamedTuple):
    exchange: str
    bid: float
    ask: float


class SpreadOpp(NamedTuple):
    ticker:       str
    buy_exchange: str
    buy_price:    float   # ask on buy side
    sell_exchange: str
    sell_price:   float   # bid on sell side
    spread_pct:   float


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tier(pct: float) -> str:
    if pct > 1.0:
        return "[bold yellow]●●●[/]"
    if pct > 0.3:
        return "[bold green]●● [/]"
    if pct > 0.1:
        return "[cyan]●  [/]"
    return "[dim]·  [/]"


def _ex(name: str) -> str:
    c = _EX_COLOR.get(name, "#c9d1d9")
    s = _EX_SHORT.get(name, name[:3].upper())
    return f"[bold {c}]{s}[/]"


def _fmt_price(p: float) -> str:
    if p >= 1_000:
        return f"${p:,.2f}"
    if p >= 1:
        return f"${p:.4f}"
    return f"${p:.6f}"


# ── Sub-widgets ───────────────────────────────────────────────────────────────

class _StatusBar(Static):
    DEFAULT_CSS = """
    _StatusBar {
        height: 1;
        background: #161b22;
        color: #8b949e;
        padding: 0 1;
    }
    """


class _ControlBar(Widget):
    DEFAULT_CSS = """
    _ControlBar {
        height: 3;
        background: #161b22;
        border-bottom: solid #30363d;
    }
    _ControlBar Horizontal { height: 3; align: left middle; padding: 0 1; }
    _ControlBar Label      { margin: 0 1; color: #8b949e; }
    _ControlBar Switch     { margin: 0 1; }
    _ControlBar Button     { margin: 0 1; min-width: 14; height: 3; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label("[dim]Auto-refresh:[/]")
            yield Switch(value=True, id="cx-auto-refresh")
            yield Button("⟳ Refresh", id="cx-refresh-btn", classes="primary")
            yield Label("", id="cx-countdown")
            yield Label(
                "  [dim]r=refresh  o=open exchange[/]",
                id="cx-hints",
            )


# ── Main tab ──────────────────────────────────────────────────────────────────

class CryptoTab(Widget):
    """Tab 4 — live cross-exchange crypto price spreads."""

    DEFAULT_CSS = """
    CryptoTab          { height: 1fr; layout: vertical; }
    CryptoTab DataTable { height: 1fr; }
    """

    _auto: reactive[bool] = reactive(True)
    _secs: reactive[int]  = reactive(_AUTO_REFRESH_SECS)

    # ── Composition ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield _ControlBar()
        yield _StatusBar("", id="cx-status")
        yield DataTable(id="cx-table")

    def on_mount(self) -> None:
        tbl = self.query_one("#cx-table", DataTable)
        tbl.cursor_type = "row"
        tbl.add_columns(
            "Tier", "#", "Pair",
            "Buy on", "Buy $",
            "Sell on", "Sell $",
            "Spread %",
            "Note",
        )
        self._fetch()
        self._tick()

    # ── Events ────────────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cx-refresh-btn":
            self._secs = _AUTO_REFRESH_SECS
            self._fetch()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "cx-auto-refresh":
            self._auto = event.value

    def on_key(self, event) -> None:
        key = event.key
        if key in ("r", "ctrl+r"):
            self._secs = _AUTO_REFRESH_SECS
            self._fetch()
        elif key == "o":
            self._open_exchange()

    # ── Background workers ────────────────────────────────────────────────────

    @work(thread=False)
    async def _tick(self) -> None:
        """One-second countdown; triggers auto-refresh at zero."""
        while True:
            await asyncio.sleep(1)
            if not self._auto:
                self._secs = _AUTO_REFRESH_SECS
                continue
            self._secs -= 1
            self._update_countdown()
            if self._secs <= 0:
                self._secs = _AUTO_REFRESH_SECS
                self._fetch()

    @work(thread=False)
    async def _fetch(self) -> None:
        """Fetch prices from all three exchanges and rebuild the table."""
        self._set_status("[dim]Fetching exchange prices…[/]")

        binance_data, coinbase_data, kraken_data = await asyncio.gather(
            binance_prices(),
            coinbase_prices(),
            kraken_prices(),
        )

        # Merge into all_prices[ticker][exchange] = ExPrice
        all_prices: dict[str, dict[str, ExPrice]] = {}
        for ex_name, data in (
            ("Binance",  binance_data),
            ("Coinbase", coinbase_data),
            ("Kraken",   kraken_data),
        ):
            for ticker, p in data.items():
                all_prices.setdefault(ticker, {})[ex_name] = ExPrice(
                    exchange=ex_name, bid=p["bid"], ask=p["ask"]
                )

        # Find all pairwise spread opportunities
        opps: list[SpreadOpp] = []
        for ticker, exchanges in all_prices.items():
            if len(exchanges) < 2:
                continue
            ex_list = list(exchanges.items())
            for i, (buy_name, buy_ep) in enumerate(ex_list):
                for j, (sell_name, sell_ep) in enumerate(ex_list):
                    if i == j:
                        continue
                    buy_price  = buy_ep.ask
                    sell_price = sell_ep.bid
                    if buy_price <= 0:
                        continue
                    pct = (sell_price - buy_price) / buy_price * 100
                    if pct >= _MIN_SPREAD_PCT:
                        opps.append(SpreadOpp(
                            ticker=ticker,
                            buy_exchange=buy_name,
                            buy_price=buy_price,
                            sell_exchange=sell_name,
                            sell_price=sell_price,
                            spread_pct=pct,
                        ))

        # Sort by spread desc; keep best opportunity per ticker
        opps.sort(key=lambda o: o.spread_pct, reverse=True)
        seen: set[str] = set()
        best: list[SpreadOpp] = []
        for opp in opps:
            if opp.ticker not in seen:
                best.append(opp)
                seen.add(opp.ticker)

        self._rebuild_table(best, all_prices)
        self._set_status_bar(best, binance_data, coinbase_data, kraken_data)

    # ── Table ─────────────────────────────────────────────────────────────────

    def _rebuild_table(
        self,
        opps: list[SpreadOpp],
        all_prices: dict[str, dict[str, ExPrice]],
    ) -> None:
        tbl = self.query_one("#cx-table", DataTable)
        tbl.clear()

        if not opps:
            tbl.add_row(
                "[dim]·  [/]", "", "[dim]No spreads found[/]",
                "", "", "", "", "", "[dim]All prices aligned[/]",
            )
            return

        for i, opp in enumerate(opps, 1):
            icon  = _CRYPTO_ICON.get(opp.ticker, "")
            pair  = f"{icon} {opp.ticker}/USD"

            pct   = opp.spread_pct
            if pct > 1.0:
                spread_markup = f"[bold yellow]+{pct:.3f}%[/]"
            elif pct > 0.3:
                spread_markup = f"[bold green]+{pct:.3f}%[/]"
            elif pct > 0.1:
                spread_markup = f"[cyan]+{pct:.3f}%[/]"
            else:
                spread_markup = f"[dim]+{pct:.3f}%[/]"

            # Note: flag when only 2 exchanges have the ticker (less confidence)
            n_ex   = len(all_prices.get(opp.ticker, {}))
            note   = "[dim]2-ex[/]" if n_ex < 3 else ""

            tbl.add_row(
                _tier(pct),
                str(i),
                pair,
                _ex(opp.buy_exchange),
                _fmt_price(opp.buy_price),
                _ex(opp.sell_exchange),
                _fmt_price(opp.sell_price),
                spread_markup,
                note,
            )

    # ── Status helpers ────────────────────────────────────────────────────────

    def _set_status_bar(
        self,
        opps: list[SpreadOpp],
        binance_data: dict,
        coinbase_data: dict,
        kraken_data: dict,
    ) -> None:
        parts: list[str] = []
        for ex_name, data in (
            ("Binance",  binance_data),
            ("Coinbase", coinbase_data),
            ("Kraken",   kraken_data),
        ):
            c = _EX_COLOR.get(ex_name, "#c9d1d9")
            s = _EX_SHORT[ex_name]
            if data:
                parts.append(f"[{c}]{s} {len(data)}✓[/]")
            else:
                parts.append(f"[dim]{s} ─[/]")

        n_real = sum(1 for o in opps if o.spread_pct >= 0.1)
        status = "  ".join(parts)
        status += f"  │  {len(opps)} pairs"
        if n_real:
            status += f"  │  [green]{n_real} ≥0.1%[/]"
        status += f"  │  [dim]{datetime.now():%H:%M:%S}[/]"
        status += "  [dim italic](spreads are theoretical — account for fees & slippage)[/]"
        self._set_status(status)

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#cx-status", _StatusBar).update(text)
        except Exception:
            pass

    def _update_countdown(self) -> None:
        try:
            lbl = self.query_one("#cx-countdown", Label)
            c   = self._secs
            col = "red" if c <= 10 else "dim"
            lbl.update(f"[{col}]⟳ {c}s[/]")
        except Exception:
            pass

    # ── Actions ───────────────────────────────────────────────────────────────

    def _open_exchange(self) -> None:
        """Open the selected pair on its buy-side exchange in the browser."""
        import webbrowser
        tbl = self.query_one("#cx-table", DataTable)
        if tbl.cursor_row < 0:
            return
        # We stored opps in order; get by index
        # Simplest: just open the exchange homepage if row is valid
        urls = {
            "Binance":  "https://www.binance.com/en/trade/",
            "Coinbase": "https://www.coinbase.com/advanced-trade/",
            "Kraken":   "https://www.kraken.com/prices/",
        }
        # Re-derive from table (fragile but avoids storing state separately)
        try:
            row_data = tbl.get_row_at(tbl.cursor_row)
            # row_data[3] is buy-exchange markup — extract name from _EX_SHORT reverse
            short_rev = {v: k for k, v in _EX_SHORT.items()}
            raw = str(row_data[3])          # e.g. "[bold #f0b90b]BNC[/]"
            for short, name in short_rev.items():
                if short in raw:
                    url = urls.get(name, "https://coinmarketcap.com")
                    webbrowser.open(url)
                    return
        except Exception:
            pass
