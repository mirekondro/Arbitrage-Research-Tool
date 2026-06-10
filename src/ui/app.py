from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

from src.ui.arb_tab      import ArbTab, EdgeRequest
from src.ui.edge_tab     import EdgeTab
from src.ui.backtest_tab import BacktestTab
from src.ui.crypto_tab   import CryptoTab


HELP_TEXT = """\
[bold cyan]ON-CHAIN ARBITRAGE RESEARCH TOOL — KEYBOARD REFERENCE[/]

[bold]── Navigation ──────────────────────────────────────────[/]
  [yellow]1[/]  /  [yellow]2[/]  /  [yellow]3[/]  /  [yellow]4[/]    Switch tabs  (Arb Scanner / Edge Window / Backtest / Crypto Arb)
  [yellow]↑ ↓[/]             Navigate rows in the table
  [yellow]/[/]               Focus the filter input

[bold]── Arbitrage Scanner ───────────────────────────────────[/]
  [yellow]r[/]  or  [yellow]Ctrl+R[/]   Refresh all markets now
  [yellow]s[/]               Cycle sort mode: Profit% → Liquidity → Close Date
  [yellow]e[/]               Open Edge Window for the selected row
  [yellow]o[/]               Open both market URLs in browser
  [yellow]n[/]               Search recent news for this topic
  [yellow]c[/]               Copy trade details to clipboard  (requires pyperclip)
  [yellow]w[/]               Toggle watchlist for selected row  (📌 badge; persists to disk)
  [yellow]x[/]               Export current results to CSV  (~/arb_export_*.csv)

[bold]── Platform toggles (top bar) ──────────────────────────[/]
  POLY / KALS / MANI / PI    Enable or disable each data source
  Labels update to show live market count after each fetch
  Auto-refresh               Toggle 60-second auto-refresh

[bold]── Category quick-filter (second bar) ─────────────────[/]
  All / ⚽ Sports / 🏛 Politics / 🌍 World / 💰 Crypto / 📈 Finance / 🔬 Science
  Click a category to filter the table; count shown per button
  Stacks with the keyword filter and Real$ toggle
  🌍 World = geopolitics (NATO, Greenland, Ukraine, Taiwan, Iran, etc.)
  🔬 Science = AI/ML, climate, space, medicine, technology

[bold]── Filters (third bar) ─────────────────────────────────[/]
  Min%     Minimum guaranteed profit % (default 0.5)
  Vol$     Minimum combined volume across both legs
  Sim%     Minimum title similarity for cross-platform matching
  Real$    Only show real-money opportunities  (POLY / KALS / PI)
  Sort     Current sort mode (press [yellow]s[/] to cycle)

[bold]── Table columns ─────────────────────────────────────────[/]
  Tier     Profit tier badge (●●●/●●/●/·)
  Δ        Convergence arrow: [bold green]↑[/] growing edge  [bold red]↓[/] shrinking  [dim]─[/] stable
  ★        Gold star prefix on rows where both legs are real money

[bold]── Profit tiers ─────────────────────────────────────────[/]
  [bold yellow]●●●[/]   Gold    > 50 % profit
  [bold green]●● [/]   Green   > 10 %
  [cyan]●  [/]   Cyan    >  2 %
  [dim]·  [/]   Dim     ≤  2 % (below noise threshold)

[bold]── Platforms ────────────────────────────────────────────[/]
  [bold #a371f7]POLY[/]   Polymarket   (real money, 2 % fee)
  [bold #3fb950]KALS[/]   Kalshi       (real money, 7 % fee)
  [bold #f78166]MANI[/]   Manifold     (play money, no fee)
  [bold #ffa657]PI  [/]   PredictIt    (real money, 10 % profit fee)
  [bold #00b4d8]MCTL[/]   Metaculus    (forecasting / play money)

[bold]── Crypto Exchange Arb (Tab 4) ──────────────────────────[/]
  Live price spread across Binance / Coinbase / Kraken
  [yellow]r[/]               Refresh exchange prices now
  [yellow]o[/]               Open buy-side exchange in browser
  Spreads ≥ 0.1 % flagged; ●●● tier = > 1 %
  [dim]⚠  Theoretical only — fees and slippage will reduce real profit[/]

[bold]── Other ────────────────────────────────────────────────[/]
  [yellow]?[/]               Show this help screen
  [yellow]q[/]               Quit

[bold]── Persistence ──────────────────────────────────────────[/]
  Watchlist / history stored in [dim]~/.arb_tool/[/]
  Logs written to             [dim]~/.arb_tool/arb.log[/]
  Edit [dim]config.toml[/] in the project root to tune thresholds

[dim]Press Escape or ? to close[/]
"""


class HelpScreen(ModalScreen):
    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen > Static {
        width: 72;
        height: auto;
        max-height: 90vh;
        background: #161b22;
        border: solid #30363d;
        padding: 1 2;
        overflow: auto;
        color: #c9d1d9;
    }
    """
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Close", show=False),
        Binding("question_mark", "app.pop_screen", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static(HELP_TEXT)


class ArbitrageApp(App):
    TITLE = "On-Chain Arbitrage Research Tool"
    SUB_TITLE = "Polymarket · Kalshi · Manifold · PredictIt · Binance · Coinbase · Kraken"

    CSS = """
    /* ── Global ─────────────────────────────────────────────────────────── */
    Screen { background: #0d1117; }

    Header {
        background: #161b22;
        color: #58a6ff;
        text-style: bold;
    }

    Footer {
        background: #161b22;
        color: #8b949e;
    }

    TabbedContent { height: 1fr; }
    TabPane       { padding: 0; }

    /* Tab bar */
    TabbedContent > ContentSwitcher { height: 1fr; }
    Tabs { background: #161b22; }
    Tabs Tab {
        background: #161b22;
        color: #8b949e;
        padding: 0 2;
    }
    Tabs Tab:hover  { color: #c9d1d9; }
    Tabs Tab.-active {
        color: #58a6ff;
        background: #0d1117;
        text-style: bold;
        border-bottom: solid #58a6ff;
    }

    /* ── DataTable ───────────────────────────────────────────────────────── */
    DataTable > .datatable--header {
        background: #161b22;
        color: #8b949e;
        text-style: bold;
    }
    DataTable > .datatable--even-row { background: #0d1117; color: #c9d1d9; }
    DataTable > .datatable--odd-row  { background: #0d1117; color: #c9d1d9; }
    DataTable > .datatable--cursor   { background: #1f6feb; color: #ffffff; }
    DataTable > .datatable--highlight { background: #21262d; }

    /* ── Inputs ──────────────────────────────────────────────────────────── */
    Input {
        background: #21262d;
        border: tall #30363d;
        color: #c9d1d9;
        height: 3;
    }
    Input:focus { border: tall #58a6ff; }

    /* ── Buttons ─────────────────────────────────────────────────────────── */
    Button { height: 3; }
    Button.primary          { background: #1f6feb; color: #ffffff; border: none; }
    Button.primary:hover    { background: #388bfd; }
    Button.primary:focus    { background: #388bfd; border: tall #58a6ff; }

    /* ── Switch ──────────────────────────────────────────────────────────── */
    Switch.-on  { background: #3fb950; }
    Switch.-off { background: #30363d; }

    /* ── Scrollbars ──────────────────────────────────────────────────────── */
    ScrollBar { background: #0d1117; }
    ScrollBar > ScrollBarThumb { background: #30363d; }
    """

    BINDINGS = [
        Binding("q",             "quit",              "Quit",        show=True),
        Binding("r",             "refresh_arb",       "Refresh",     show=True),
        Binding("e",             "edge_for_row",      "Edge",        show=True),
        Binding("n",             "open_news",         "News",        show=True),
        Binding("o",             "open_urls",         "URLs",        show=True),
        Binding("question_mark", "show_help",         "Help",        show=True),
        Binding("1",             "show_tab('arb')",   "Arb",         show=False),
        Binding("2",             "show_tab('edge')",  "Edge",        show=False),
        Binding("3",             "show_tab('back')",   "Backtest",    show=False),
        Binding("4",             "show_tab('crypto')", "Crypto",      show=False),
        Binding("ctrl+r",        "refresh_arb",       "Refresh",     show=False),
        Binding("slash",         "focus_filter",      "Filter",      show=False),
        Binding("x",             "export_csv",        "Export CSV",  show=False),
        Binding("s",             "cycle_sort",        "Sort",        show=False),
        Binding("c",             "copy_trade",        "Copy",        show=False),
        Binding("w",             "toggle_watch",      "Watch",       show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="arb"):
            with TabPane("⚡ Arbitrage Scanner", id="arb"):
                yield ArbTab()
            with TabPane("📈 Edge Window", id="edge"):
                yield EdgeTab()
            with TabPane("🔁 Wallet Backtest", id="back"):
                yield BacktestTab()
            with TabPane("₿ Crypto Exchange Arb", id="crypto"):
                yield CryptoTab()
        yield Footer()

    # ── Cross-tab message handler ─────────────────────────────────────────────

    def on_edge_request(self, msg: EdgeRequest) -> None:
        tc = self.query_one(TabbedContent)
        tc.active = "edge"
        self.call_after_refresh(
            lambda: self.query_one(EdgeTab).set_keyword(msg.keyword)
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_refresh_arb(self) -> None:
        try:
            self.query_one(ArbTab).fetch_markets()
        except Exception:
            pass

    def action_edge_for_row(self) -> None:
        try:
            self.query_one(ArbTab)._open_edge()
        except Exception:
            pass

    def action_open_urls(self) -> None:
        try:
            self.query_one(ArbTab)._open_urls()
        except Exception:
            pass

    def action_open_news(self) -> None:
        try:
            self.query_one(ArbTab)._open_news()
        except Exception:
            pass

    def action_export_csv(self) -> None:
        try:
            self.query_one(ArbTab)._export_csv()
        except Exception:
            pass

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_focus_filter(self) -> None:
        try:
            from textual.widgets import Input
            self.query_one("#filter-input", Input).focus()
        except Exception:
            pass

    def action_cycle_sort(self) -> None:
        try:
            self.query_one(ArbTab)._cycle_sort()
        except Exception:
            pass

    def action_copy_trade(self) -> None:
        try:
            self.query_one(ArbTab)._copy_trade()
        except Exception:
            pass

    def action_toggle_watch(self) -> None:
        try:
            self.query_one(ArbTab)._toggle_watch()
        except Exception:
            pass

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen())
