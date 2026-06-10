"""Binance public book-ticker API — best bid/ask for tracked pairs.

No API key required. Binance.com may be geo-blocked for US users;
the fetch will silently return {} in that case.
"""
from __future__ import annotations

import json
import logging

import httpx

log = logging.getLogger(__name__)

# USDT-quoted pairs — highest liquidity on Binance
BINANCE_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT",
    "DOTUSDT", "UNIUSDT", "ATOMUSDT", "MATICUSDT",
]

_SYMBOL_TO_TICKER: dict[str, str] = {s: s.replace("USDT", "") for s in BINANCE_SYMBOLS}

_BASE    = "https://api.binance.com"
_TIMEOUT = 10.0


async def fetch_prices() -> dict[str, dict]:
    """Return {ticker: {bid, ask, exchange}} for all tracked pairs, or {} on error."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_BASE}/api/v3/ticker/bookTicker",
                params={"symbols": json.dumps(BINANCE_SYMBOLS)},
            )
            resp.raise_for_status()
            data = resp.json()

        result: dict[str, dict] = {}
        for item in data:
            ticker = _SYMBOL_TO_TICKER.get(item.get("symbol", ""))
            if ticker is None:
                continue
            try:
                result[ticker] = {
                    "bid":      float(item["bidPrice"]),
                    "ask":      float(item["askPrice"]),
                    "exchange": "Binance",
                }
            except (KeyError, ValueError):
                pass
        return result
    except Exception as exc:
        log.debug("Binance fetch error: %s", exc)
        return {}
