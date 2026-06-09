from __future__ import annotations

import asyncio
import time
import webbrowser
from datetime import datetime
from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, DataTable, Input, Label, Static, Switch

from src.models import ArbitrageOpportunity, Market
from src.core.arbitrage import scan_opportunities, REAL_MONEY_PLATFORMS

# ── Platform config ────────────────────────────────────────────────────────────

PLATFORM_CFG: dict[str, dict] = {
    "polymarket": {"short": "POLY", "color": "#a371f7",  "real": True},
    "kalshi":     {"short": "KALS", "color": "#3fb950",  "real": True},
    "manifold":   {"short": "MANI", "color": "#f78166",  "real": False},
    "predictit":  {"short": "PI",   "color": "#ffa657",  "real": True},
    "metaculus":  {"short": "MCTL", "color": "#00b4d8",  "real": False},
}

# How many sports rows to show in the "All" view before collapsing to a summary.
# Set to 0 to disable capping (Sports tab always shows all).
_MAX_SPORTS_IN_ALL = 5

AUTO_REFRESH_SEC = 60

# ── Category detection ─────────────────────────────────────────────────────────

_CATEGORY_KEYWORDS: dict[str, set[str]] = {
    # NOTE: order matters — first matching category wins.
    "cat-sports": {
        "nba", "nfl", "nhl", "mlb", "soccer", "football", "basketball",
        "baseball", "hockey", "tennis", "golf", "championship", "league",
        "cup", "playoff", "super bowl", "world series", "season",
        "knicks", "lakers", "warriors", "celtics", "bulls", "heat",
        "yankees", "mets", "dodgers", "cubs", "astros",
        "patriots", "chiefs", "eagles", "cowboys", "49ers",
        "wimbledon", "ufc", "boxing", "wrestling", "olympic",
        "tour de france", "formula 1", "f1", "grand prix",
    },
    # World/Geopolitics checked BEFORE US politics so geo topics land here
    "cat-world": {
        "greenland", "nato", "ukraine", "russia", "china", "taiwan",
        "border", "immigration", "deportation", "ceasefire", "cease fire",
        "nuclear", "treaty", "european union", "denmark",
        "israel", "iran", "middle east", "gaza", "g7", "g20",
        "sovereignty", "annexation", "invasion", "occupation",
        "prime minister", "chancellor", "trudeau", "macron", "scholz",
        "modi", "xi jinping", "kim jong", "zelensky", "putin",
        "un security", "un resolution", "iran nuclear", "north korea",
        "south korea", "japan", "india", "pakistan", "saudi",
        "africa", "latin america", "venezuela", "brazil", "turkey",
    },
    "cat-politics": {
        "president", "trump", "biden", "harris", "election", "vote", "senator",
        "congress", "democrat", "republican", "white house",
        "supreme court", "legislation", "bill signed", "governor",
        "pardon", "impeach", "cabinet", "executive order",
        "doge ", "vivek", "rfk", "desantis", "newsom", "gop",
        "midterm", "primary", "electoral", "filibuster",
    },
    "cat-crypto": {
        "bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol",
        "doge", "dogecoin", "blockchain", "token", "defi", "nft",
        "xrp", "ripple", "cardano", "ada", "polkadot", "binance", "coinbase",
        "100k", "200k", "50k",  # BTC price targets
        "stablecoin", "web3", "layer 2", "base chain", "sui", "aptos",
    },
    "cat-finance": {
        # Macro / central bank
        "gdp", "recession", "federal reserve", "fed", "fomc", "interest rate",
        "rate hike", "rate cut", "rate decision", "basis point",
        # Inflation
        "inflation", "cpi", "pce", "consumer price",
        # Labour / growth
        "unemployment", "nonfarm", "jobs report", "payroll",
        "economy", "economic growth", "economic contraction",
        # Markets
        "stock market", "s&p", "sp500", "nasdaq", "dow jones", "earnings",
        "ipo", "treasury", "yield curve", "bond yield",
        # Fiscal
        "debt ceiling", "budget deficit", "government shutdown",
        "tariff", "trade deficit", "sanctions",
        # Housing
        "mortgage rate", "housing market", "home price",
        # Companies
        "openai", "anthropic", "apple", "microsoft", "meta ", "google",
        "amazon", "nvidia", "tesla", "spacex", "stripe", "palantir",
    },
    "cat-science": {
        # AI / tech
        "artificial intelligence", " ai ", "machine learning", "llm",
        "gpt", "claude", "gemini", "agi", "superintelligence",
        "autopilot", "self-driving", "autonomous", "robot",
        # Climate / energy
        "climate", "carbon", "co2", "global warming", "renewable",
        "solar", "wind power", "nuclear energy", "fusion",
        "paris agreement", "cop ", "emissions",
        # Science / medicine
        "vaccine", "pandemic", "cancer", "alzheimer", "gene editing",
        "crispr", "longevity", "space", "mars", "moon", "nasa",
        "spacex launch", "asteroid", "exoplanet",
    },
}

# (display_label, button_id) pairs — order matters for UI layout
CATEGORIES = [
    ("All",           "cat-all"),
    ("⚽ Sports",     "cat-sports"),
    ("🏛 Politics",   "cat-politics"),
    ("🌍 World",      "cat-world"),
    ("💰 Crypto",     "cat-crypto"),
    ("📈 Finance",    "cat-finance"),
    ("🔬 Science",    "cat-science"),
]

# Reverse map: button_id → display label (without count)
_CAT_TO_LABEL: dict[str, str] = {cid: lbl for lbl, cid in CATEGORIES}


def _detect_category(title: str) -> str:
    """Return the category key that best matches the market title."""
    t = title.lower()
    for cat_key, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return cat_key
    return "cat-other"


# ── Tier / badge helpers ───────────────────────────────────────────────────────

def _tier(profit_pct: float) -> tuple[str, str]:
    """Return (badge_markup, row_color) for a profit percentage."""
    if profit_pct > 50:
        return "[bold yellow]●●●[/]", "#ffd700"
    if profit_pct > 10:
        return "[bold green]●● [/]", "#3fb950"
    if profit_pct > 2:
        return "[cyan]●  [/]", "#58a6ff"
    return "[dim]·  [/]", "#8b949e"


def _platform_badge(name: str) -> str:
    cfg = PLATFORM_CFG.get(name, {})
    color = cfg.get("color", "white")
    short = cfg.get("short", name[:4].upper())
    return f"[bold on {color}] {short} [/]"


def _liq_str(opp: ArbitrageOpportunity) -> str:
    total_liq = (opp.market_a.liquidity or 0) + (opp.market_b.liquidity or 0)
    if total_liq >= 1_000_000:
        return f"${total_liq/1_000_000:.1f}M"
    if total_liq >= 1_000:
        return f"${total_liq/1_000:.0f}K"
    return f"${total_liq:.0f}"


def _close_str(opp: ArbitrageOpportunity) -> str:
    """Return Rich markup for time-to-close with urgency coloring."""
    ct: Optional[datetime] = None
    for mkt in (opp.market_a, opp.market_b):
        if mkt.close_time:
            ct = mkt.close_time
            break
    if ct is None:
        return "[dim]─[/]"
    ct_naive = ct.replace(tzinfo=None) if ct.tzinfo else ct
    secs = (ct_naive - datetime.now()).total_seconds()
    if secs <= 0:
        return "[dim]exp[/]"
    days = int(secs / 86400)
    hours = int((secs % 86400) / 3600)
    if secs < 3600:
        mins = max(1, int(secs / 60))
        return f"[bold red]{mins}m[/]"
    if days == 0:
        return f"[bold red]{hours}h[/]"
    if days <= 3:
        return f"[bold red]{days}d[/]"
    if days <= 14:
        return f"[yellow]{days}d[/]"
    if days <= 90:
        return f"[dim]{days}d[/]"
    return f"[dim]{ct_naive.strftime('%b %d')}[/]"


def _profit_bar(pct: float, cap: float = 30.0) -> str:
    """Return a 5-block bar proportional to profit%."""
    filled = min(5, round(pct / cap * 5))
    return "█" * filled + "░" * (5 - filled)


def _is_real_money(opp: ArbitrageOpportunity) -> bool:
    return (opp.buy_yes_on in REAL_MONEY_PLATFORMS
            and opp.buy_no_on in REAL_MONEY_PLATFORMS)


def _opp_key(opp: ArbitrageOpportunity) -> str:
    """Stable string key for an opportunity (used for convergence tracking)."""
    return f"{opp.buy_yes_on}+{opp.buy_no_on}:{opp.matched_title[:60]}"


# ── Custom messages ────────────────────────────────────────────────────────────

class EdgeRequest(Message):
    """Posted when user wants to view edge window for the selected row."""
    def __init__(self, keyword: str) -> None:
        super().__init__()
        self.keyword = keyword


# ── Widgets ───────────────────────────────────────────────────────────────────

class PlatformBar(Horizontal):
    DEFAULT_CSS = """
    PlatformBar {
        height: 3;
        background: #0d1117;
        border-bottom: solid #21262d;
        padding: 0 1;
        align: left middle;
    }
    PlatformBar Label { width: auto; padding: 0 1; color: #8b949e; }
    PlatformBar Switch { width: 6; margin: 0 1; }
    .plat-label { color: #c9d1d9 !important; width: auto !important; }
    """

    def compose(self) -> ComposeResult:
        for pid, cfg in PLATFORM_CFG.items():
            color = cfg["color"]
            short = cfg["short"]
            # Give each label an ID so we can update the count after fetching
            yield Label(f"[bold {color}]{short}[/]", classes="plat-label", id=f"lbl-{pid}")
            yield Switch(value=True, id=f"sw-{pid}", animate=False)
        yield Label("  │  ", classes="plat-label")
        yield Label("Auto-refresh:", classes="plat-label")
        yield Switch(value=True, id="sw-auto", animate=False)
        yield Label("", id="countdown-lbl", classes="plat-label")


class CategoryBar(Horizontal):
    """Quick-filter bar: All / ⚽ Sports / 🏛 Politics / 💰 Crypto / 📈 Finance."""
    DEFAULT_CSS = """
    CategoryBar {
        height: 3;
        background: #161b22;
        border-bottom: solid #21262d;
        padding: 0 1;
        align: left middle;
    }
    CategoryBar Label { width: auto; padding: 0 1; color: #8b949e; }
    CategoryBar Button {
        height: 2;
        width: 18;
        margin: 0 0 0 1;
        background: #21262d;
        color: #8b949e;
        border: none;
    }
    CategoryBar Button.active-cat {
        background: #1f6feb;
        color: #ffffff;
    }
    CategoryBar Button:hover { background: #30363d; }
    CategoryBar Button.active-cat:hover { background: #388bfd; }
    """

    def compose(self) -> ComposeResult:
        yield Label("Topic:", classes="plat-label")
        for label, cat_id in CATEGORIES:
            classes = "active-cat" if cat_id == "cat-all" else ""
            # Start with placeholder "(─)" so the button is sized for count suffix
            if " " in label:
                emoji, name_rest = label.split(" ", 1)
                initial_lbl = f"{emoji} {name_rest} (─)"
            else:
                initial_lbl = f"{label} (─)"
            yield Button(initial_lbl, id=cat_id, classes=classes)


class ControlBar(Horizontal):
    DEFAULT_CSS = """
    ControlBar {
        height: 3;
        background: #0d1117;
        padding: 0 1;
        align: left middle;
        border-bottom: solid #21262d;
    }
    ControlBar Label { width: auto; padding: 0 1; color: #8b949e; }
    #filter-input { width: 22; }
    #min-profit   { width: 6;  }
    #min-vol      { width: 8;  }
    #sim-thresh   { width: 5;  }
    #sort-lbl     { color: #8b949e !important; }
    #refresh-btn  { width: 12; margin: 0 1; }
    #export-btn   { width: 11; margin: 0 1; }
    .real-label   { color: #3fb950 !important; }
    """

    def compose(self) -> ComposeResult:
        yield Label("Filter:")
        yield Input(placeholder="keyword…", id="filter-input")
        yield Label("  Min%:")
        yield Input(value="0.5", id="min-profit")
        yield Label("  Vol$:")
        yield Input(value="0", id="min-vol")
        yield Label("  Sim%:")
        yield Input(value="70", id="sim-thresh")
        yield Label("  Real$:", classes="real-label")
        yield Switch(value=False, id="sw-realonly", animate=False)
        yield Label("  Sort: [bold cyan]Profit%[/]  [dim]s[/]", id="sort-lbl")
        yield Button("⟳ Refresh", id="refresh-btn", variant="primary")
        yield Button("↓ CSV", id="export-btn")


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: #161b22;
        color: #c9d1d9;
        padding: 0 1;
        border-bottom: solid #30363d;
    }
    """


class DetailPanel(Static):
    DEFAULT_CSS = """
    DetailPanel {
        height: 10;
        background: #0d1117;
        border-top: solid #21262d;
        padding: 0 1;
        display: none;
    }
    DetailPanel.visible { display: block; }
    """


# ── Main tab ──────────────────────────────────────────────────────────────────

class ArbTab(Vertical):
    DEFAULT_CSS = """
    ArbTab { height: 1fr; }
    #arb-table { height: 1fr; }
    """

    opportunities:    reactive[list] = reactive([], layout=True)
    _filtered_opps:  list  = []
    _all_markets:    dict  = {}
    _next_refresh:   float = 0.0
    _auto_on:        bool  = True
    _real_only:      bool  = False
    _enabled_pforms: set   = set(PLATFORM_CFG.keys())
    _prev_real_keys: set   = set()   # track previously-seen real-money arb pairs
    _prev_profit_map: dict = {}      # profit_pct from the PREVIOUS scan (convergence Δ)
    _prev_opp_keys:  set   = set()   # all opp keys from previous scan (for NEW badge)
    _new_opp_keys:   set   = set()   # keys that are NEW this scan (shown in table)
    _is_first_scan:  bool  = True    # suppress NEW badges on the very first load
    _hidden_sports_count: int = 0    # sports rows hidden in All view by cap
    _sort_mode:      str   = "profit"  # "profit" | "liq" | "close"
    _category:       str   = "cat-all"  # active category tab

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield PlatformBar()
        yield CategoryBar()
        yield ControlBar()
        yield StatusBar("Starting up…", id="arb-status")
        yield DataTable(id="arb-table", zebra_stripes=True, cursor_type="row")
        yield DetailPanel(id="detail-panel")

    def on_mount(self) -> None:
        table = self.query_one("#arb-table", DataTable)
        table.add_columns(
            "Tier", "#", "Event",
            "YES on", "YES $",
            "NO on",  "NO $",
            "Profit%", "Δ", "Liq", "Match%", "Closes",
        )
        # Sync state from Switch widgets after the whole widget tree is mounted.
        # Textual may fire Switch.Changed events during compose with intermediate
        # values; reading the final widget value here is the authoritative source.
        try:
            self._real_only = self.query_one("#sw-realonly", Switch).value
        except Exception:
            self._real_only = True
        self.set_interval(1, self._tick)
        self.fetch_markets()

    # ── Events ────────────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "refresh-btn":
            self.fetch_markets()
        elif btn_id == "export-btn":
            self._export_csv()
        elif btn_id in {cid for _, cid in CATEGORIES}:
            self._set_category(btn_id)

    def _set_category(self, cat_id: str) -> None:
        """Switch active category and update button highlighting."""
        self._category = cat_id
        for _, cid in CATEGORIES:
            try:
                btn = self.query_one(f"#{cid}", Button)
                if cid == cat_id:
                    btn.add_class("active-cat")
                else:
                    btn.remove_class("active-cat")
            except Exception:
                pass
        self._apply_filter()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        sid = event.switch.id or ""
        if sid == "sw-auto":
            self._auto_on = event.value
            if event.value:
                self._schedule_next_refresh()
        elif sid == "sw-realonly":
            self._real_only = event.value
            self._apply_filter()
        elif sid.startswith("sw-"):
            pid = sid[3:]
            if event.value:
                self._enabled_pforms.add(pid)
            else:
                self._enabled_pforms.discard(pid)
            self._rescan()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-input":
            self._apply_filter()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = event.cursor_row
        if 0 <= idx < len(self._filtered_opps):
            opp = self._filtered_opps[idx]
            panel = self.query_one("#detail-panel", DetailPanel)
            panel.update(self._format_detail(opp))
            panel.add_class("visible")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update detail panel on arrow-key navigation."""
        idx = event.cursor_row
        if 0 <= idx < len(self._filtered_opps):
            opp = self._filtered_opps[idx]
            panel = self.query_one("#detail-panel", DetailPanel)
            panel.update(self._format_detail(opp))
            panel.add_class("visible")

    def on_key(self, event) -> None:
        key = event.key
        if key == "e":
            self._open_edge()
        elif key == "o":
            self._open_urls()
        elif key == "x":
            self._export_csv()
        elif key == "n":
            self._open_news()
        elif key == "s":
            self._cycle_sort()

    # ── Reactive watchers ─────────────────────────────────────────────────────

    def watch_opportunities(self, opps: list) -> None:
        self._apply_filter()

    # ── Timer ─────────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        if not self._auto_on or self._next_refresh == 0:
            self.query_one("#countdown-lbl", Label).update("")
            return
        remaining = max(0, int(self._next_refresh - time.time()))
        if remaining <= 10:
            self.query_one("#countdown-lbl", Label).update(
                f"  [bold red]⟳ {remaining}s[/]"
            )
        else:
            self.query_one("#countdown-lbl", Label).update(
                f"  [dim]⟳ {remaining}s[/]"
            )
        if remaining == 0:
            self.fetch_markets()

    def _schedule_next_refresh(self) -> None:
        self._next_refresh = time.time() + AUTO_REFRESH_SEC

    # ── Sort ──────────────────────────────────────────────────────────────────

    _SORT_CYCLE = ["profit", "liq", "close"]
    _SORT_LABELS = {"profit": "Profit%", "liq": "Liquidity", "close": "Close Date"}

    def _cycle_sort(self) -> None:
        idx = self._SORT_CYCLE.index(self._sort_mode)
        self._sort_mode = self._SORT_CYCLE[(idx + 1) % len(self._SORT_CYCLE)]
        lbl = self._SORT_LABELS[self._sort_mode]
        try:
            self.query_one("#sort-lbl", Label).update(
                f"  Sort: [bold cyan]{lbl}[/]  [dim]s[/]"
            )
        except Exception:
            pass
        self._apply_filter()

    # ── Data fetch ────────────────────────────────────────────────────────────

    @work(exclusive=True, thread=False)
    async def fetch_markets(self) -> None:
        from src.apis import polymarket, kalshi, manifold, predictit, metaculus

        t0 = time.time()

        # Show ⟳ spinner on every platform label immediately
        for pid, cfg in PLATFORM_CFG.items():
            try:
                self.query_one(f"#lbl-{pid}", Label).update(
                    f"[bold {cfg['color']}]{cfg['short']}[/] [dim]⟳[/]"
                )
            except Exception:
                pass

        self._set_status(
            "  ".join(
                f"[bold {cfg['color']}]{cfg['short']}[/] [dim]⟳[/]"
                for cfg in PLATFORM_CFG.values()
            ) + "  [dim]fetching…[/]"
        )

        async def _fetch_one(name: str, coro) -> tuple[str, list]:
            cfg = PLATFORM_CFG[name]
            color, short = cfg["color"], cfg["short"]
            try:
                result = await coro
                n = len(result)
                label = (
                    f"[bold {color}]{short}[/] [dim]{n} ✓[/]"
                    if n > 0
                    else f"[bold {color}]{short}[/] [dim]─[/]"
                )
                try:
                    self.query_one(f"#lbl-{name}", Label).update(label)
                except Exception:
                    pass
                return name, result
            except Exception:
                try:
                    self.query_one(f"#lbl-{name}", Label).update(
                        f"[bold {color}]{short}[/] [red]ERR[/]"
                    )
                except Exception:
                    pass
                return name, []

        try:
            pairs = await asyncio.gather(
                _fetch_one("polymarket", polymarket.fetch_markets(400)),
                _fetch_one("kalshi",     kalshi.fetch_markets(400)),
                _fetch_one("manifold",   manifold.fetch_markets(200)),
                _fetch_one("predictit",  predictit.fetch_markets(200)),
                _fetch_one("metaculus",  metaculus.fetch_markets(200)),
            )

            counts = []
            self._all_markets = {}
            for name, result in pairs:
                self._all_markets[name] = result
                cfg = PLATFORM_CFG[name]
                n = len(result)
                if n > 0:
                    counts.append(f"[bold]{n}[/] {cfg['short']}")
                # zero-result platforms (ERR or empty) silently skipped from count line

            elapsed = time.time() - t0
            self._rescan(status_prefix=f"[dim]{elapsed:.1f}s[/]  {'  '.join(counts)}  →  ")
            self._schedule_next_refresh()

        except Exception as exc:
            self._set_status(f"[red]Error: {exc}[/]")

    def _rescan(self, status_prefix: str = "") -> None:
        """Re-run opportunity scan with current enabled platforms."""
        enabled = {p: m for p, m in self._all_markets.items()
                   if p in self._enabled_pforms}
        if not enabled:
            self.opportunities = []
            self._set_status("No platforms enabled.")
            return

        try:
            sim_thresh = float(self.query_one("#sim-thresh", Input).value or "72")
        except Exception:
            sim_thresh = 72.0
        try:
            min_profit = float(self.query_one("#min-profit", Input).value or "0.5")
        except Exception:
            min_profit = 0.5
        try:
            min_vol = float(self.query_one("#min-vol", Input).value or "0")
        except Exception:
            min_vol = 0.0

        opps = scan_opportunities(enabled, threshold=sim_thresh)
        opps = [o for o in opps if o.profit_pct >= min_profit]
        if min_vol > 0:
            opps = [o for o in opps
                    if (o.market_a.volume + o.market_b.volume) >= min_vol]

        # Archive current profits as "previous" before replacing opportunities
        # This gives the convergence Δ column something to compare against
        old_map: dict[str, float] = {}
        for opp in self.opportunities:
            old_map[_opp_key(opp)] = opp.profit_pct
        self._prev_profit_map = old_map

        # Track which opportunities are genuinely NEW this scan
        cur_keys = {_opp_key(o) for o in opps}
        if self._is_first_scan:
            self._new_opp_keys = set()
            self._is_first_scan = False
        else:
            self._new_opp_keys = cur_keys - self._prev_opp_keys
        self._prev_opp_keys = cur_keys

        # Update status BEFORE setting reactive (so it shows during the render)
        now = datetime.now().strftime("%H:%M:%S")
        real_opps = [o for o in opps if _is_real_money(o)]
        real = len(real_opps)
        play = len(opps) - real
        real_alert = (
            f"  [bold green on #1a4d2e] ★ {real} REAL MONEY ARB [/]"
            if real > 0 else ""
        )
        sort_lbl = self._SORT_LABELS.get(self._sort_mode, "Profit%")
        real_filter_note = (
            f"  [bold green]Real$✓[/] [dim]{real} real / {play} play hidden[/]"
            if self._real_only else
            f"  [dim]{real} real · {play} play[/]"
        )
        self._set_status(
            f"{status_prefix}"
            f"[bold white]{len(opps)}[/] total"
            f"{real_filter_note}"
            f"{real_alert}"
            f"  [dim]│  {now}  │  s={sort_lbl}  e=edge  o=urls  n=news  x=csv[/]"
        )

        # Toast for NEW real-money opportunities
        cur_real_keys = {
            f"{o.buy_yes_on}+{o.buy_no_on}:{o.matched_title[:40]}"
            for o in real_opps
        }
        new_keys = cur_real_keys - self._prev_real_keys
        if new_keys and self._prev_real_keys:  # skip first load
            for key in list(new_keys)[:3]:
                title = key.split(":", 1)[-1]
                platforms = key.split(":", 1)[0]
                self.app.notify(
                    f"[{platforms}] {title}",
                    title="★ Real Arb Found",
                    severity="warning",
                    timeout=10,
                )
        self._prev_real_keys = cur_real_keys

        # Set reactive so downstream reactive watchers stay consistent,
        # then call _apply_filter directly — the worker context means the
        # watcher may be scheduled for a later event-loop tick, too late.
        self.opportunities = opps
        self._apply_filter()

    # ── Filter ────────────────────────────────────────────────────────────────

    def _apply_filter(self) -> None:
        try:
            kw = self.query_one("#filter-input", Input).value.strip().lower()
        except Exception:
            kw = ""

        # Use the backing field as the single source of truth.
        # The backing field is set in on_mount (from the Switch widget after full
        # DOM mount) and in on_switch_changed (when the user toggles). It is
        # intentionally NEVER written here to avoid worker-context query races.
        real_only = self._real_only

        opps = list(self.opportunities)

        if real_only:
            opps = [o for o in opps if _is_real_money(o)]

        if kw:
            opps = [
                o for o in opps
                if kw in o.matched_title.lower()
                or kw in o.buy_yes_on
                or kw in o.buy_no_on
            ]

        # Category counts are computed here — BEFORE the category filter — so
        # each button shows how many opportunities exist in that category given
        # the current Real$ + keyword filters (but not yet the category selection).
        # This means the counts accurately reflect what clicking each category
        # button would show, rather than confusingly counting hidden play-money rows.
        self._update_category_counts(opps)

        # Category filter (cat-all = no filter)
        if self._category != "cat-all":
            opps = [o for o in opps if _detect_category(o.matched_title) == self._category]

        # Sort by selected mode
        if self._sort_mode == "liq":
            opps.sort(
                key=lambda o: (o.market_a.liquidity or 0) + (o.market_b.liquidity or 0),
                reverse=True,
            )
        elif self._sort_mode == "close":
            def _close_key(o: ArbitrageOpportunity) -> datetime:
                ct = o.market_a.close_time or o.market_b.close_time
                if ct is None:
                    return datetime.max
                return ct.replace(tzinfo=None) if ct.tzinfo else ct
            opps.sort(key=_close_key)

        # In the "All" view, cap sports rows so they don't bury everything else.
        # Real-money rows are never capped regardless of category.
        self._hidden_sports_count = 0
        if self._category == "cat-all" and _MAX_SPORTS_IN_ALL > 0:
            is_sport = lambda o: _detect_category(o.matched_title) == "cat-sports"
            sports  = [o for o in opps if is_sport(o) and not _is_real_money(o)]
            others  = [o for o in opps if not (is_sport(o) and not _is_real_money(o))]
            if len(sports) > _MAX_SPORTS_IN_ALL:
                self._hidden_sports_count = len(sports) - _MAX_SPORTS_IN_ALL
                opps = others + sports[:_MAX_SPORTS_IN_ALL]
            # Re-sort after merge (others already sorted, sports subset preserves order)

        self._filtered_opps = opps
        self._populate_table(self._filtered_opps)

    def _update_category_counts(self, all_opps: list) -> None:
        """Refresh category button labels to show per-category opportunity counts."""
        cat_counts: dict[str, int] = {"cat-all": len(all_opps)}
        for opp in all_opps:
            cat = _detect_category(opp.matched_title)
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        for raw_label, cat_id in CATEGORIES:
            n = cat_counts.get(cat_id, 0)
            # Build new label text (emoji preserved, count appended)
            if " " in raw_label:
                emoji, name_rest = raw_label.split(" ", 1)
                new_lbl = f"{emoji} {name_rest} ({n})"
            else:
                new_lbl = f"{raw_label} ({n})"
            try:
                self.query_one(f"#{cat_id}", Button).label = new_lbl
            except Exception:
                pass

    # ── Table rendering ───────────────────────────────────────────────────────

    def _delta_arrow(self, opp: ArbitrageOpportunity) -> str:
        """Return Rich markup for the convergence Δ column."""
        prev = self._prev_profit_map.get(_opp_key(opp))
        if prev is None:
            return "[dim]─[/]"   # new opportunity, no previous data
        diff = opp.profit_pct - prev
        if diff > 0.05:
            return "[bold green]↑[/]"
        if diff < -0.05:
            return "[bold red]↓[/]"
        return "[dim]─[/]"

    def _populate_table(self, opps: list) -> None:
        table = self.query_one("#arb-table", DataTable)
        table.clear()

        if not opps:
            total = len(self.opportunities)
            if total == 0:
                hint = "[dim italic]Fetching markets… please wait[/]"
            elif self._category != "cat-all":
                # Show how many play-money opps exist in this category (hidden by Real$)
                in_cat = [o for o in self.opportunities
                          if _detect_category(o.matched_title) == self._category]
                play_in_cat  = [o for o in in_cat if not _is_real_money(o)]
                real_in_cat  = [o for o in in_cat if _is_real_money(o)]
                cat_lbl = _CAT_TO_LABEL.get(self._category, "").split()[-1] if _CAT_TO_LABEL.get(self._category) else "category"
                if self._real_only and play_in_cat and not real_in_cat:
                    hint = (
                        f"[dim italic]{len(play_in_cat)} {cat_lbl} opportunities are play-money "
                        f"— turn off [bold]Real$[/] [dim italic]to see them[/]"
                    )
                elif not in_cat:
                    hint = f"[dim italic]No {cat_lbl} opportunities found — try refreshing or checking back later[/]"
                else:
                    hint = "[dim italic]No opportunities match current filters — try adjusting Min%, Sim%, or keyword[/]"
            else:
                play_count = sum(1 for o in self.opportunities if not _is_real_money(o))
                real_count = total - play_count
                if self._real_only and play_count > 0 and real_count == 0:
                    hint = (
                        f"[dim italic]Real$ ON — all {play_count} opportunities are play-money. "
                        f"Turn off Real$ to see them.[/]"
                    )
                else:
                    hint = (
                        "[dim italic]No opportunities match current filters — "
                        "try lowering Min%, Sim%, or clearing the keyword filter[/]"
                    )
            table.add_row("", "", hint, "", "", "", "", "", "", "", "", "")
            return

        for i, opp in enumerate(opps, 1):
            real = _is_real_money(opp)
            is_new = _opp_key(opp) in self._new_opp_keys
            title = opp.matched_title
            if len(title) > 44:
                title = title[:43] + "…"

            # Title prefix: star for real-money, ✦ badge for genuinely NEW
            if real and is_new:
                title_cell = f"[bold green]★[/] [bold magenta]NEW[/] {title}"
            elif real:
                title_cell = f"[bold green]★[/] {title}"
            elif is_new:
                title_cell = f"[bold magenta]✦[/] {title}"
            else:
                title_cell = title

            badge, _ = _tier(opp.profit_pct)
            bar = _profit_bar(opp.profit_pct)
            # Flag Manifold-leg opportunities with huge spreads as "mispricing noise"
            mani_leg = "manifold" in (opp.buy_yes_on, opp.buy_no_on)
            if mani_leg and opp.profit_pct > 50 and not real:
                profit_markup = f"[dim]+{opp.profit_pct:.0f}%[/] [dim]{bar}[bold yellow]M↯[/][/]"
            elif real:
                profit_markup = f"[bold green]+{opp.profit_pct:.1f}%[/] [dim]{bar}[/]"
            else:
                profit_markup = f"[dim]+{opp.profit_pct:.1f}%[/] [dim]{bar}(p)[/]"

            table.add_row(
                badge,
                str(i),
                title_cell,
                _platform_badge(opp.buy_yes_on),
                f"{opp.yes_price:.3f}",
                _platform_badge(opp.buy_no_on),
                f"{opp.no_price:.3f}",
                profit_markup,
                self._delta_arrow(opp),
                _liq_str(opp),
                (f"[yellow]{opp.similarity:.0f}%⚠[/]" if opp.similarity < 80 else f"{opp.similarity:.0f}%"),
                _close_str(opp),
            )

        # Sports overflow footer (only shown in All view when cap was hit)
        if self._hidden_sports_count > 0:
            table.add_row(
                "[dim]…[/]", "",
                f"[dim italic]+ {self._hidden_sports_count} more ⚽ Sports — "
                f"click the Sports tab to see all[/]",
                "", "", "", "", "", "", "", "", "",
            )

    # ── Actions ───────────────────────────────────────────────────────────────

    def _open_edge(self) -> None:
        idx = self.query_one("#arb-table", DataTable).cursor_row
        if 0 <= idx < len(self._filtered_opps):
            opp = self._filtered_opps[idx]
            keyword = opp.matched_title.split()[0] if opp.matched_title else ""
            self.post_message(EdgeRequest(keyword))

    def _open_urls(self) -> None:
        idx = self.query_one("#arb-table", DataTable).cursor_row
        if 0 <= idx < len(self._filtered_opps):
            opp = self._filtered_opps[idx]
            for url in [opp.market_a.url, opp.market_b.url]:
                if url:
                    try:
                        webbrowser.open(url)
                    except Exception:
                        pass

    def _open_news(self) -> None:
        idx = self.query_one("#arb-table", DataTable).cursor_row
        if 0 <= idx < len(self._filtered_opps):
            opp = self._filtered_opps[idx]
            import urllib.parse
            query = urllib.parse.quote(opp.matched_title[:80])
            webbrowser.open(f"https://duckduckgo.com/?q={query}&ia=news")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _export_csv(self) -> None:
        import csv
        import os
        from datetime import datetime as dt
        if not self._filtered_opps:
            self._set_status("[yellow]Nothing to export.[/]")
            return
        path = os.path.expanduser(
            f"~/arb_export_{dt.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "title", "buy_yes_on", "yes_price", "buy_no_on", "no_price",
                "profit_pct", "similarity", "real_money", "category",
                "url_a", "url_b",
            ])
            for o in self._filtered_opps:
                w.writerow([
                    o.matched_title, o.buy_yes_on, f"{o.yes_price:.4f}",
                    o.buy_no_on, f"{o.no_price:.4f}", f"{o.profit_pct:.2f}",
                    f"{o.similarity:.0f}", _is_real_money(o),
                    _detect_category(o.matched_title).replace("cat-", ""),
                    o.market_a.url, o.market_b.url,
                ])
        self._set_status(f"[green]Exported {len(self._filtered_opps)} rows → {path}[/]")

    def _set_status(self, msg: str) -> None:
        try:
            self.query_one("#arb-status", StatusBar).update(msg)
        except Exception:
            pass

    def _format_detail(self, opp: ArbitrageOpportunity) -> str:
        a, b = opp.market_a, opp.market_b
        spread_pct = abs(a.yes_price - b.yes_price) * 100
        real_tag = "[bold green]REAL MONEY[/]" if _is_real_money(opp) else "[dim]PLAY MONEY[/]"

        # Category label for detail view
        cat_key = _detect_category(opp.matched_title)
        cat_label = _CAT_TO_LABEL.get(cat_key, "")

        # Convergence note
        prev = self._prev_profit_map.get(_opp_key(opp))
        if prev is not None and abs(opp.profit_pct - prev) >= 0.05:
            diff = opp.profit_pct - prev
            delta_note = (
                f"  [bold green]↑ +{diff:.2f}%[/] vs prev"
                if diff > 0
                else f"  [bold red]↓ {diff:.2f}%[/] vs prev"
            )
        else:
            delta_note = ""

        cat_part = f"  [dim]{cat_label}[/]" if cat_label else ""
        close_part = f"  Closes: {_close_str(opp)}" if (a.close_time or b.close_time) else ""

        # Bet sizing: split stake proportionally so both legs pay out equally
        total_raw = opp.yes_price + opp.no_price  # pre-fee combined cost
        bet_lines = []
        if total_raw > 0 and total_raw < 1.0:
            for stake in (100, 1_000, 10_000):
                yes_leg = stake * opp.yes_price / total_raw
                no_leg  = stake * opp.no_price  / total_raw
                profit  = stake * opp.profit_pct / 100
                bet_lines.append(
                    f"  💰 ${stake:,} → "
                    f"YES ${yes_leg:,.0f} on [bold]{opp.buy_yes_on}[/]  "
                    f"+ NO ${no_leg:,.0f} on [bold]{opp.buy_no_on}[/]  "
                    f"→ [bold green]+${profit:,.2f}[/] guaranteed"
                )
        # Max deployable (limited by smaller liquidity leg)
        liq_yes = a.liquidity if a.platform == opp.buy_yes_on else b.liquidity
        liq_no  = b.liquidity if b.platform == opp.buy_no_on  else a.liquidity
        min_liq = min(liq_yes or 0, liq_no or 0)
        if min_liq > 0:
            limiting_plat = opp.buy_yes_on if (liq_yes or 0) <= (liq_no or 0) else opp.buy_no_on
            max_profit = min_liq * opp.profit_pct / 100
            bet_lines.append(
                f"  📊 Max deployable: [bold]${min_liq:,.0f}[/] "
                f"→ [bold green]+${max_profit:,.0f}[/] "
                f"[dim](limited by {limiting_plat} liq)[/]"
            )

        bet_section = "\n".join(bet_lines) if bet_lines else ""

        # Warn when title similarity is borderline (may be a false-positive match)
        match_warn = ""
        if opp.similarity < 80:
            match_warn = "  [yellow]⚠ low match — verify titles below[/]"

        # Manifold often prices at 50% while real-money platforms price correctly.
        # A huge "profit" involving Manifold is almost always Manifold mispricing, not real arb.
        mani_note = ""
        if "manifold" in (opp.buy_yes_on, opp.buy_no_on) and opp.profit_pct > 50 and not _is_real_money(opp):
            mani_note = "\n  [dim yellow]⚡ Manifold default-prior mismatch — research signal only, not real-money arb[/]"

        # Show actual individual market titles so users can spot mis-matched pairs
        a_title_note = (
            f'[dim]  “{a.title[:70]}”[/]'
            if a.title.lower() != opp.matched_title.lower() else ""
        )
        b_title_note = (
            f'[dim]  “{b.title[:70]}”[/]'
            if b.title.lower() != opp.matched_title.lower() else ""
        )

        return (
            f"[bold]{opp.matched_title[:90]}[/]  {real_tag}{cat_part}{close_part}\n"
            f"  {_platform_badge(a.platform)}  YES={a.yes_price:.4f}  NO={a.no_price:.4f}"
            f"  Vol=${a.volume:,.0f}  Liq=${a.liquidity:,.0f}  [dim]{a.url[:45]}[/]"
            + (f"\n{a_title_note}" if a_title_note else "") + "\n"
            + f"  {_platform_badge(b.platform)}  YES={b.yes_price:.4f}  NO={b.no_price:.4f}"
            f"  Vol=${b.volume:,.0f}  Liq=${b.liquidity:,.0f}  [dim]{b.url[:45]}[/]"
            + (f"\n{b_title_note}" if b_title_note else "") + "\n"
            + f"  Spread: [yellow]{spread_pct:.1f}%[/]  │  "
            f"BUY YES on [bold]{opp.buy_yes_on}[/] @ {opp.yes_price:.4f}  "
            f"+  BUY NO on [bold]{opp.buy_no_on}[/] @ {opp.no_price:.4f}  "
            f"→  [bold green]+{opp.profit_pct:.2f}%[/]  (match={opp.similarity:.0f}%){match_warn}{delta_note}\n"
            + (f"{bet_section}\n" if bet_section else "")
            + mani_note
            + f"\n  [dim]e=Edge  o=URLs  n=News  x=CSV  s=Sort  ↑↓=Navigate[/]"
        )
