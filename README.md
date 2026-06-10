# Arbitrage Research Tool

A terminal UI for finding price discrepancies across prediction markets — real money and play money — in real time.

```
┌─ On-Chain Arbitrage Research Tool ─────────────────────────────────────────┐
│ POLY ⟳  KALS ✓  MANI ✓  PI ✓  MCTL ─  │  Auto-refresh: ● │  ⟳ 47s        │
│ Topic: [All(68)] [⚽ Sports(12)] [🏛 Politics(9)] [🌍 World(7)] [💰 Crypto(5)] │
│ Filter: ________  Min%: 0.5  Vol$: 0  Sim%: 70  Real$: ○  Sort: Profit% s  │
├──────────────────────────────────────────────────────────────────────────────│
│ Tier  #  Event                          YES on  YES$  NO on  NO$  Profit%   │
│ ●●●   1  Will Greenland become part…   [POLY]  0.12  [KALS] 0.82  +5.2%   │
│ ●●    2  Trump signs executive order…  [KALS]  0.33  [POLY] 0.61  +3.8%   │
│  ·    3  📌 Bitcoin above $200K by…    [MANI]  0.44  [POLY] 0.50  +1.2%   │
└──────────────────────────────────────────────────────────────────────────────┘
  [bold] BUY YES on polymarket @ 0.1200  +  BUY NO on kalshi @ 0.8200 → +5.24%
  💰 $100 → YES $13 on polymarket + NO $87 on kalshi → +$5.24 guaranteed
  📊 Max deployable: $3,200 → +$166 (limited by kalshi liq)
```

## Quick install

```bash
# Recommended — isolated environment, auto-updates
pipx install arb-tool

# Homebrew (macOS / Linux)
brew tap miroslavondrousek/arb-tool https://github.com/miroslavondrousek/Arbitrage-Research-Tool
brew install --HEAD arb-tool   # until a versioned release tag exists

# Plain pip (into current environment)
pip install arb-tool
```

Then just run:
```bash
arb-tool
```

> **Why pipx?**  pipx installs Python CLI tools in their own isolated virtualenv so they never conflict with other packages.  It's the recommended way to install command-line Python apps.

---

## What it does

Connects to five prediction market platforms simultaneously, finds markets covering the same event, and highlights when the combined cost of YES + NO is less than $1 — a risk-free arbitrage.

**Platforms monitored:**
| Badge | Platform | Type | Fee |
|-------|----------|------|-----|
| `POLY` | Polymarket | Real money | 2% |
| `KALS` | Kalshi | Real money | 7% |
| `PI` | PredictIt | Real money | 10% profit fee |
| `MANI` | Manifold | Play money | none |
| `MCTL` | Metaculus | Forecasting / play | none |

## Install in detail

### Option 1 — pipx (recommended for end users)

```bash
pipx install arb-tool
arb-tool
```

Upgrades: `pipx upgrade arb-tool`

### Option 2 — Homebrew (macOS / Linux)

```bash
# Add the custom tap (one-time)
brew tap miroslavondrousek/arb-tool \
    https://github.com/miroslavondrousek/Arbitrage-Research-Tool

# Install (HEAD = latest dev branch; drop --HEAD once v1.0.0 tag exists)
brew install --HEAD arb-tool
```

Upgrades: `brew reinstall --HEAD arb-tool`

A default config is installed to `$(brew --prefix)/etc/arb-tool/config.toml.default`. Copy it to `~/.arb_tool/config.toml` to customise.

### Option 3 — From source (developers)

```bash
git clone https://github.com/miroslavondrousek/Arbitrage-Research-Tool.git
cd Arbitrage-Research-Tool
pip install -e .        # installs in editable mode with all deps
arb-tool                # or: python main.py
```

### Option 4 — Plain pip

```bash
pip install arb-tool
arb-tool
```

**Requirements:** Python 3.10+. Python 3.11+ recommended (`tomllib` is built-in; older versions automatically use `tomli`).

## Key bindings

### Navigation
| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate table rows |
| `1` / `2` / `3` | Switch tabs (Arb / Edge / Backtest) |
| `/` | Focus the keyword filter |
| `?` | Show full keyboard reference |
| `q` | Quit |

### Arbitrage Scanner
| Key | Action |
|-----|--------|
| `r` / `Ctrl+R` | Force refresh all platforms |
| `s` | Cycle sort: Profit% → Liquidity → Close Date |
| `e` | Open Edge Window for selected market |
| `o` | Open both market URLs in browser |
| `n` | DuckDuckGo news search for this topic |
| `c` | **Copy trade to clipboard** (requires `pyperclip`) |
| `w` | **Toggle watchlist** for selected row (📌 badge, persisted) |
| `x` | Export current view to CSV (`~/arb_export_*.csv`) |

## Features

### Live arbitrage table (13 columns)

| Column | Meaning |
|--------|---------|
| `Tier` | Profit tier: ●●● gold >50% · ●● green >10% · ● cyan >2% · · dim ≤2% |
| `#` | Row number in current filtered view |
| `Event` | Matched market title (★ real money · ✦ new · 📌 watching) |
| `YES on` | Platform to buy YES on |
| `YES $` | YES price (cost per share) |
| `NO on` | Platform to buy NO on |
| `NO $` | NO price (cost per share) |
| `Profit%` | Guaranteed profit % with mini bar chart |
| `Δ` | Convergence arrow — ↑ growing edge · ↓ shrinking · ─ stable |
| `Liq` | Combined liquidity across both legs |
| `Match%` | Title similarity score (yellow ⚠ if below 80%) |
| `Closes` | Time to market close (red if <3 days) |
| `Age` | How long this opportunity has been visible (new · 5m · 3h · 2d) |

### Category quick-filter

Click any category button (or just browse All) to filter by topic:

| Category | Keywords matched |
|----------|-----------------|
| ⚽ Sports | NBA, NFL, Champions League, F1, UFC, Olympics … |
| 🏛 Politics | Trump, Congress, elections, executive orders … |
| 🌍 World | Ukraine, NATO, Taiwan, Greenland, G7, Zelensky … |
| 💰 Crypto | BTC, ETH, Solana, DeFi, stablecoins … |
| 📈 Finance | Fed rates, CPI, S&P 500, earnings, tariffs … |
| 🔬 Science | AI/AGI, climate, space, vaccines, CRISPR … |

The count in each button shows how many opportunities exist in that category given the current Real$ + keyword filters — so clicking never produces an empty screen.

### Detail panel (bottom of screen)

Select any row with `↑` / `↓` or click to open the detail panel:

- Both platform prices and liquidity side by side
- Actual raw market titles (spot mis-matched pairs)
- Bet-sizing calculator: $100 · $1,000 · $10,000 stake breakdowns
- Maximum deployable capital limited by the smaller liquidity leg
- Convergence Δ vs the previous scan
- Manifold mispricing warning when a Manifold leg has >50% "profit" (always a prior mismatch, not real arb)
- Watchlist status and first-seen age

### Watchlist (w key)

Press `w` on any row to bookmark it. Watched markets show a 📌 badge in the table and detail panel. The count appears in the status bar. Watchlist persists across sessions in `~/.arb_tool/watchlist.json`.

### Age tracking

Every opportunity is timestamped when first seen. The `Age` column shows:
- `new` — appeared this scan (magenta)
- `5m`, `3h` — minutes / hours (cyan / yellow)
- `2d` — days (dim)

History is pruned automatically after 7 days if the opportunity is no longer active. Stored in `~/.arb_tool/history.json`.

### Copy trade (c key)

Copies a structured trade memo to your clipboard:

```
ARB: Will Greenland become part of the US in 2025?
  BUY YES on polymarket @ 0.1200
  BUY NO  on kalshi @ 0.8200
  Expected profit: +5.24%
  YES URL: https://polymarket.com/...
  NO  URL: https://kalshi.com/...
```

Install `pyperclip` (already in `requirements.txt`) for cross-platform clipboard support.

### Auto-refresh

Enabled by default — fetches all platforms every 60 seconds. A countdown timer appears in the top bar. The last 10 seconds flash red. Toggle with the Auto-refresh switch.

### Real$ filter

The `Real$` toggle (top control bar) hides all play-money opportunities, leaving only Polymarket + Kalshi + PredictIt arb. Off by default so you can see all opportunities on first launch.

### Alerts

When a new real-money arb opportunity appears:
1. A desktop toast notification fires (title: "★ Real Arb Found")
2. A terminal bell rings if `alerts.sound_on_real_arb = true` in `config.toml`

## Configuration (`config.toml`)

Edit `config.toml` in the project root to tune behaviour without touching code:

```toml
[scan]
min_profit_pct = 0.5          # surface opportunities with > 0.5% profit
similarity_threshold = 70.0   # minimum title-match score
auto_refresh_seconds = 60
max_sports_in_all_view = 5    # cap sports rows in "All" view (0 = no cap)

[display]
real_money_only = false       # start with Real$ filter on/off
default_sort = "profit"       # "profit" | "liq" | "close"

[platforms]
polymarket_limit = 400        # markets to fetch per platform
kalshi_limit = 400

[alerts]
sound_on_real_arb = false     # ring terminal bell on new real-money arb
```

Changes take effect on the next app launch (or call `reload()` in code).

## Data storage

All persistent data lives in `~/.arb_tool/`:

| File | Contents |
|------|---------|
| `history.json` | First-seen timestamps for up to 3,000 opportunities |
| `watchlist.json` | Keys of watched opportunities |
| `arb.log` | Debug log (append-only, rotated manually) |

## Important caveats

- **Play-money arb is not real profit.** Manifold and Metaculus use fake currencies. The `M↯` badge flags Manifold default-prior mismatches that look like high-profit arb but are just their starting prior of 50%.
- **Fees are estimates.** Polymarket 2%, Kalshi ~7%, PredictIt 10% profit fee. Actual costs depend on your position size and order book depth.
- **Prices are snapshots.** By the time you place an order, prices may have moved. Always check the actual market before trading.
- **Match quality.** A yellow `⚠` in the `Match%` column means the title similarity is below 80% — two different events may have been matched. Always read both market titles in the detail panel before trading.

## Architecture

```
src/
  apis/
    polymarket.py    Polymarket CLOB API v2
    kalshi.py        Kalshi REST API v2
    manifold.py      Manifold REST API
    predictit.py     PredictIt public API
    metaculus.py     Metaculus API v2
  core/
    arbitrage.py     Profit calculation and opportunity scanning
    matcher.py       Fuzzy title matching (rapidfuzz Jaccard)
    history.py       Persistent age tracking and watchlist
    config.py        config.toml loader with safe defaults
    backtest.py      Wallet backtest logic
  models.py          Market and ArbitrageOpportunity dataclasses
  ui/
    app.py           Main Textual App + HelpScreen
    arb_tab.py       Arbitrage Scanner tab (main UI)
    edge_tab.py      Edge Window tab
    backtest_tab.py  Wallet Backtest tab
config.toml          User-editable settings
main.py              Entry point + logging setup
```

## Publishing to PyPI

```bash
# Install build tools (one-time)
pip install build twine

# Build sdist + wheel
python -m build

# Check the package before upload
twine check dist/*

# Upload to PyPI (needs ~/.pypirc or TWINE_PASSWORD env var)
twine upload dist/*
```

After uploading, `pipx install arb-tool` and `pip install arb-tool` will work globally.

### Updating the Homebrew formula after a release

1. Create a GitHub release with tag `v1.x.y`
2. Download the auto-generated tarball and get its hash:
   ```bash
   curl -L https://github.com/miroslavondrousek/Arbitrage-Research-Tool/archive/refs/tags/v1.x.y.tar.gz \
        -o arb-tool-1.x.y.tar.gz
   shasum -a 256 arb-tool-1.x.y.tar.gz
   ```
3. Edit `Formula/arb-tool.rb` — uncomment and update `url`, `sha256`, `version`
4. Commit and push — `brew upgrade arb-tool` will pick it up automatically

## License

MIT
