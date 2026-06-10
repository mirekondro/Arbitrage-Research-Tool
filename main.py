#!/usr/bin/env python3
"""
On-Chain Arbitrage Research Tool — dev entry point.

For production use, install via pip / pipx / brew and run ``arb-tool``.
This file exists so you can still run ``python main.py`` from a git checkout.
"""
from arb_tool.cli import main

if __name__ == "__main__":
    main()
