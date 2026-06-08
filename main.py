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
"""
import sys

def main() -> None:
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
