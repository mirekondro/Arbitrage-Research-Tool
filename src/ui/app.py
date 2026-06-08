from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane

from src.ui.arb_tab      import ArbTab
from src.ui.edge_tab     import EdgeTab
from src.ui.backtest_tab import BacktestTab


class ArbitrageApp(App):
    TITLE = "On-Chain Arbitrage Research Tool"
    SUB_TITLE = "Polymarket · Kalshi · Manifold"
    CSS = """
    Screen {
        background: #0d1117;
    }
    Header {
        background: #161b22;
        color: #58a6ff;
    }
    TabbedContent {
        height: 1fr;
    }
    TabPane {
        padding: 0;
    }
    DataTable > .datatable--header {
        background: #21262d;
        color: #c9d1d9;
    }
    DataTable > .datatable--even-row {
        background: #0d1117;
    }
    DataTable > .datatable--odd-row {
        background: #161b22;
    }
    DataTable > .datatable--cursor {
        background: #1f6feb;
        color: white;
    }
    Input {
        background: #21262d;
        border: solid #30363d;
        color: #c9d1d9;
    }
    Input:focus {
        border: solid #58a6ff;
    }
    Button.primary {
        background: #1f6feb;
        color: white;
        border: none;
    }
    Button.primary:hover {
        background: #388bfd;
    }
    """
    BINDINGS = [
        Binding("q",   "quit",           "Quit",        show=True),
        Binding("r",   "refresh_arb",    "Refresh Arb", show=True),
        Binding("1",   "show_tab('arb')",      "Arbitrage",  show=False),
        Binding("2",   "show_tab('edge')",     "Edge Window",show=False),
        Binding("3",   "show_tab('backtest')", "Backtest",   show=False),
        Binding("ctrl+r", "refresh_arb", "Refresh",     show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="arb"):
            with TabPane("⚡ Arbitrage Scanner", id="arb"):
                yield ArbTab()
            with TabPane("📈 Edge Window", id="edge"):
                yield EdgeTab()
            with TabPane("🔁 Wallet Backtest", id="backtest"):
                yield BacktestTab()
        yield Footer()

    def action_refresh_arb(self) -> None:
        try:
            self.query_one(ArbTab).fetch_markets()
        except Exception:
            pass

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id
