"""Coinbase Exchange public ticker API — best bid/ask for tracked pairs.

Uses the Coinbase Advanced Trade public endpoint (no auth required).
"""
from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

# USD product IDs on Coinbase Exchange
COINBASE_PAIRS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD",
    "ADA-USD", "AVAX-USD", "LINK-USD", "LTC-USD", "DOT-USD",
    "UNI-USD", "ATOM-USD", "MATIC-USD",
]

_PAIR_TO_TICKER: dict[str, str] = {p: p.split("-")[0] for p in COINBASE_PAIRS}

_BASE    = "https://api.exchange.coinbase.com"
_TIMEOUT = 10.0


async def _fetch_one(
    client: httpx.AsyncClient, pair: str
) -> tuple[str, dict | None]:
    ticker = _PAIR_TO_TICKER[pair]
    try:
        resp = await client.get(f"{_BASE}/products/{pair}/ticker")
        if resp.status_code != 200:
            return ticker, None
        d = resp.json()
        return ticker, {
            "bid":      float(d["bid"]),
            "ask":      float(d["ask"]),
            "exchange": "Coinbase",
        }
    except Exception as exc:
        log.debug("Coinbase %s error: %s", pair, exc)
        return ticker, None


async def fetch_prices() -> dict[str, dict]:
    """Return {ticker: {bid, ask, exchange}} for all tracked pairs, partial on errors."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            results = await asyncio.gather(
                *[_fetch_one(client, pair) for pair in COINBASE_PAIRS]
            )
        return {t: d for t, d in results if d is not None}
    except Exception as exc:
        log.debug("Coinbase batch error: %s", exc)
        return {}
