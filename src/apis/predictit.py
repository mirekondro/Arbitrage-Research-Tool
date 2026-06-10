import json
import os
import time
import httpx
from datetime import datetime
from typing import Optional

from src.models import Market

PREDICTIT_API = "https://www.predictit.org/api/marketdata/all/"
HEADERS = {"User-Agent": "ArbitrageResearchTool/1.0"}
CACHE_TTL  = 300   # 5 min in-process cache
DISK_CACHE = os.path.expanduser("~/.cache/arb_predictit.json")
DISK_TTL   = 3600  # 1 hour disk cache

_cache: list[Market] = []
_cache_ts: float = 0.0


def _load_disk_cache() -> list[dict]:
    try:
        if not os.path.exists(DISK_CACHE):
            return []
        age = time.time() - os.path.getmtime(DISK_CACHE)
        if age > DISK_TTL:
            return []
        with open(DISK_CACHE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_disk_cache(data: list[dict]) -> None:
    try:
        os.makedirs(os.path.dirname(DISK_CACHE), exist_ok=True)
        with open(DISK_CACHE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


async def fetch_markets(limit: int = 200) -> list[Market]:
    """Fetch binary (single-contract) markets from PredictIt — real money, US-regulated."""
    global _cache, _cache_ts
    now = time.time()
    if _cache and now - _cache_ts < CACHE_TTL:
        return _cache[:limit]

    markets: list[Market] = []
    raw_data: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(PREDICTIT_API)
            if resp.status_code == 429:
                # Try disk cache first, then in-process stale
                disk = _load_disk_cache()
                if disk:
                    raw_data = disk
                elif _cache:
                    return _cache[:limit]
                else:
                    return []
            else:
                resp.raise_for_status()
                data = resp.json()
                raw_data = data.get("markets", [])
                _save_disk_cache(raw_data)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            disk = _load_disk_cache()
            if disk:
                raw_data = disk
            elif _cache:
                return _cache[:limit]
            else:
                return []
        else:
            raise

    for mkt in raw_data:
        contracts = mkt.get("contracts", [])
        # Only true YES/NO binary markets (single contract)
        if len(contracts) != 1:
            continue
        c = contracts[0]
        if c.get("status") != "Open":
            continue
        parsed = _parse(mkt, c)
        if parsed:
            markets.append(parsed)
        if len(markets) >= limit:
            break

    _cache = markets
    _cache_ts = now
    return _cache[:limit]


def _parse(mkt: dict, contract: dict) -> Optional[Market]:
    try:
        # bestBuyYesCost = price to buy YES (ask side)
        yes_price = float(contract.get("bestBuyYesCost") or 0)
        no_price  = float(contract.get("bestBuyNoCost")  or 0)

        if yes_price <= 0 or no_price <= 0:
            return None
        if yes_price >= 1 or no_price >= 1:
            return None

        close_time: Optional[datetime] = None
        date_end = contract.get("dateEnd", "NA")
        if date_end and date_end != "NA":
            try:
                close_time = datetime.fromisoformat(str(date_end).replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        # PredictIt's 10% profit fee is baked into the fee model in arbitrage.py
        return Market(
            id=str(mkt.get("id", "")),
            title=str(mkt.get("name", "Unknown")),
            yes_price=yes_price,
            no_price=no_price,
            volume=0.0,  # Not exposed in the public API
            liquidity=0.0,
            close_time=close_time,
            category="politics",
            platform="predictit",
            url=str(mkt.get("url", f"https://www.predictit.org/markets/detail/{mkt.get('id', '')}")),
            condition_id=str(contract.get("id", "")),
        )
    except (ValueError, TypeError, KeyError):
        return None
