"""Kraken public ticker API — best bid/ask for tracked pairs.

Kraken uses non-standard pair names (e.g. XXBTZUSD for BTC/USD).
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

# Kraken internal pair name → canonical ticker
KRAKEN_PAIRS: dict[str, str] = {
    "XXBTZUSD": "BTC",
    "XETHZUSD": "ETH",
    "SOLUSD":   "SOL",
    "XXRPZUSD": "XRP",
    "XDGUSD":   "DOGE",
    "ADAUSD":   "ADA",
    "AVAXUSD":  "AVAX",
    "LINKUSD":  "LINK",
    "XLTCZUSD": "LTC",
    "DOTUSD":   "DOT",
    "UNIUSD":   "UNI",
    "ATOMUSD":  "ATOM",
    "MATICUSD": "MATIC",
}

_BASE    = "https://api.kraken.com"
_TIMEOUT = 10.0


async def fetch_prices() -> dict[str, dict]:
    """Return {ticker: {bid, ask, exchange}} for all tracked pairs, or {} on error."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_BASE}/0/public/Ticker",
                params={"pair": ",".join(KRAKEN_PAIRS.keys())},
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("error"):
            log.debug("Kraken API error: %s", data["error"])
            return {}

        result: dict[str, dict] = {}
        for kraken_pair, info in data.get("result", {}).items():
            # Kraken may return slightly aliased pair names — try direct then fuzzy
            ticker = KRAKEN_PAIRS.get(kraken_pair)
            if ticker is None:
                for kp, t in KRAKEN_PAIRS.items():
                    if kp in kraken_pair or kraken_pair in kp:
                        ticker = t
                        break
            if ticker is None:
                continue
            try:
                # "a" = [ask_price, whole_lot_vol, lot_vol]
                # "b" = [bid_price, whole_lot_vol, lot_vol]
                result[ticker] = {
                    "bid":      float(info["b"][0]),
                    "ask":      float(info["a"][0]),
                    "exchange": "Kraken",
                }
            except (KeyError, ValueError, IndexError):
                pass
        return result
    except Exception as exc:
        log.debug("Kraken fetch error: %s", exc)
        return {}
