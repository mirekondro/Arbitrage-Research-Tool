import httpx
from typing import Optional
from datetime import datetime

from src.models import Market

KALSHI_API = "https://trading-api.kalshi.com/trade-api/v2"
HEADERS = {
    "User-Agent": "ArbitrageResearchTool/1.0",
    "Accept": "application/json",
}


async def fetch_markets(limit: int = 300) -> list[Market]:
    markets: list[Market] = []
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        cursor: Optional[str] = None
        while len(markets) < limit:
            params: dict = {"limit": min(200, limit - len(markets)), "status": "open"}
            if cursor:
                params["cursor"] = cursor
            try:
                resp = await client.get(f"{KALSHI_API}/markets", params=params)
                resp.raise_for_status()
                body = resp.json()
            except Exception:
                break

            raw = body.get("markets", [])
            for m in raw:
                mkt = _parse_market(m)
                if mkt:
                    markets.append(mkt)

            cursor = body.get("cursor")
            if not cursor or len(raw) < params["limit"]:
                break

    return markets


def _parse_market(m: dict) -> Optional[Market]:
    try:
        # Kalshi prices are 0–100 (cents) on v2
        yes_bid = float(m.get("yes_bid") or 50)
        yes_ask = float(m.get("yes_ask") or 50)
        # Normalise: if they look like 0-1 already, skip dividing
        if yes_ask > 1:
            yes_bid /= 100
            yes_ask /= 100
        yes_price = (yes_bid + yes_ask) / 2
        yes_price = max(0.01, min(0.99, yes_price))

        close_time: Optional[datetime] = None
        raw_time = m.get("close_time") or m.get("expiration_time")
        if raw_time:
            try:
                close_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        ticker = str(m.get("ticker", ""))
        return Market(
            id=ticker,
            title=str(m.get("title") or m.get("subtitle") or ticker),
            yes_price=yes_price,
            no_price=1.0 - yes_price,
            volume=float(m.get("volume") or 0),
            liquidity=float(m.get("open_interest") or 0),
            close_time=close_time,
            category=str(m.get("category") or ""),
            platform="kalshi",
            url=f"https://kalshi.com/markets/{ticker}",
        )
    except (ValueError, TypeError, KeyError):
        return None
