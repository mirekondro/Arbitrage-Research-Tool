"""
config.py — load user settings from config.toml at project root.

Uses Python 3.11+'s built-in tomllib; falls back to tomli for older versions.
Falls back silently to safe defaults when the file is missing or invalid.

Usage:
    from src.core.config import get as cfg_get
    min_pct = cfg_get("scan.min_profit_pct")     # 0.5
    sound   = cfg_get("alerts.sound_on_real_arb") # False
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("arb_tool.config")

# Locate config.toml relative to this file's package root
_CONFIG_FILE = Path(__file__).parents[2] / "config.toml"

# Safe defaults — mirrors the structure of config.toml
_DEFAULTS: dict[str, Any] = {
    "scan.min_profit_pct":          0.5,
    "scan.min_volume_usd":          0,
    "scan.similarity_threshold":    70.0,
    "scan.auto_refresh_seconds":    60,
    "scan.max_sports_in_all_view":  5,
    "display.real_money_only":      False,
    "display.default_sort":         "profit",
    "platforms.polymarket_limit":   400,
    "platforms.kalshi_limit":       400,
    "platforms.manifold_limit":     200,
    "platforms.predictit_limit":    200,
    "platforms.metaculus_limit":    200,
    "alerts.sound_on_real_arb":     False,
}

_cache: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache

    flat: dict[str, Any] = {}
    try:
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ImportError:
                log.debug("No TOML library available; using defaults (install tomli for Python < 3.11)")
                _cache = dict(_DEFAULTS)
                return _cache

        raw = tomllib.loads(_CONFIG_FILE.read_text())
        for section, entries in raw.items():
            if isinstance(entries, dict):
                for key, value in entries.items():
                    flat[f"{section}.{key}"] = value
            else:
                flat[section] = entries
        log.debug("Loaded config from %s", _CONFIG_FILE)
    except FileNotFoundError:
        log.debug("config.toml not found; using built-in defaults")
    except Exception as exc:
        log.warning("config.toml parse error (%s); using defaults", exc)

    _cache = {**_DEFAULTS, **flat}
    return _cache


def get(key: str, default: Any = None) -> Any:
    """Return a config value by dotted key, e.g. ``'scan.min_profit_pct'``."""
    cfg = _load()
    return cfg.get(key, _DEFAULTS.get(key, default))


def reload() -> None:
    """Force re-read of config.toml on next :func:`get` call."""
    global _cache
    _cache = None
