"""
arb_tool.cli — console-script entry point for ``arb-tool``.

This module is what gets called when a user runs ``arb-tool`` after
installing via pip, pipx, or Homebrew.  It mirrors main.py so the repo
can still be run directly with ``python main.py``.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path


def _setup_logging() -> None:
    """Write debug logs to ~/.arb_tool/arb.log; keep the console clean."""
    log_dir = Path.home() / ".arb_tool"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "arb.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(fh)
    # Suppress console output — the TUI owns the terminal
    root.addHandler(logging.NullHandler())
    logging.getLogger("arb_tool").info("─── session start (%s) ───", _version())


def _version() -> str:
    try:
        from arb_tool import __version__
        return __version__
    except Exception:
        return "?"


def main() -> None:
    # Quick flags handled before the TUI starts
    args = sys.argv[1:]
    if "--version" in args or "-V" in args:
        print(f"arb-tool {_version()}")
        return
    if "--help" in args or "-h" in args:
        print(
            "Usage: arb-tool [--version]\n"
            "\n"
            "  Terminal UI for cross-platform prediction-market arbitrage.\n"
            "\n"
            "  Keybindings are shown in the ? help screen inside the app.\n"
            "  Logs:   ~/.arb_tool/arb.log\n"
            "  Config: ~/.arb_tool/config.toml  (created on first run)\n"
        )
        return

    _setup_logging()

    try:
        from src.ui.app import ArbitrageApp
    except ImportError as exc:
        print(f"Missing dependency: {exc}")
        print("Run:  pip install arb-tool   or   pipx install arb-tool")
        sys.exit(1)

    ArbitrageApp().run()


if __name__ == "__main__":
    main()
