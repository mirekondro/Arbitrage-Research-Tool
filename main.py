#!/usr/bin/env python3
"""
On-Chain Arbitrage Research Tool
─────────────────────────────────
  Tab 1 – Arbitrage Scanner   : live cross-platform price discrepancies
  Tab 2 – Edge Window         : visualise how fast odds converge after news
  Tab 3 – Wallet Backtest     : simulate copying a Polymarket wallet

Keys
  q           quit
  r / Ctrl+R  refresh arbitrage scan
  1 / 2 / 3   jump to tab
  c           copy trade details to clipboard
  w           toggle watchlist for selected row
"""
import logging
import sys
from pathlib import Path


def _setup_logging() -> None:
    """Configure file-based logging to ~/.arb_tool/arb.log."""
    log_dir = Path.home() / ".arb_tool"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "arb.log"

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    # Keep the console quiet — TUI owns the terminal
    logging.getLogger().addHandler(logging.NullHandler())
    logging.getLogger("arb_tool").info("─── session start ───")


def main() -> None:
    _setup_logging()
    try:
        from src.ui.app import ArbitrageApp
    except ImportError as exc:
        print(f"Missing dependency: {exc}")
        print("Run:  pip install -r requirements.txt")
        sys.exit(1)

    app = ArbitrageApp()
    app.run()


if __name__ == "__main__":
    main()
