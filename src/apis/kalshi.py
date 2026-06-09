import httpx
from typing import Optional
from datetime import datetime

from src.models import Market

# Kalshi migrated to this URL; the old trading-api.kalshi.com now redirects here
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
HEADERS = {
    "User-Agent": "ArbitrageResearchTool/1.0",
    "Accept": "application/json",
}


async def fetch_markets(limit: int = 300) -> list[Market]:
    """
    Kalshi exposes simple binary markets via /events?with_nested_markets=true.
    The /markets endpoint now primarily returns multivariate sports parlays.
    """
    markets: list[Market] = []
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        cursor: Optional[str] = None
        while len(markets) < limit:
            batch = min(200, limit - len(markets))
            params: dict = {
                "limit": batch,
                "status": "open",
                "with_nested_markets": "true",
            }
            if cursor:
                params["cursor"] = cursor
            try:
                resp = await client.get(f"{KALSHI_API}/events", params=params)
                resp.raise_for_status()
                body = resp.json()
            except Exception:
                break

            events = body.get("events", [])
            for ev in events:
                category = str(ev.get("category") or "")
                title = str(ev.get("title") or ev.get("event_ticker") or "")
                # The nested markets list — usually one per binary event
                for m in ev.get("markets", []):
                    mkt = _parse_market(m, title=title, category=category)
                    if mkt:
                        markets.append(mkt)

            cursor = body.get("cursor")
            if not cursor or len(events) < batch:
                break

    return markets


def _parse_market(m: dict, title: str = "", category: str = "") -> Optional[Market]:
    try:
        # New field names: yes_bid_dollars / yes_ask_dollars (already in 0-1 range)
        yes_bid = float(m.get("yes_bid_dollars") or m.get("yes_bid") or 0)
        yes_ask = float(m.get("yes_ask_dollars") or m.get("yes_ask") or 0)

        # Legacy normalisation: old API returned 0-100 cents
        if yes_ask > 1:
            yes_bid /= 100
            yes_ask /= 100

        if yes_bid == 0 and yes_ask == 0:
            return None

        yes_price = (yes_bid + yes_ask) / 2
        yes_price = max(0.01, min(0.99, yes_price))

        close_time: Optional[datetime] = None
        for field in ("close_time", "expiration_time", "expected_expiration_time"):
            raw_time = m.get(field)
            if raw_time:
                try:
                    close_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                    break
                except (ValueError, AttributeError):
                    pass

        ticker = str(m.get("ticker") or "")
        mkt_title = str(m.get("title") or m.get("subtitle") or title or ticker)
        vol = float(m.get("volume_fp") or m.get("volume_24h_fp") or m.get("volume") or 0)
        liq = float(m.get("open_interest_fp") or m.get("open_interest") or 0)

        return Market(
            id=ticker,
            title=mkt_title,
            yes_price=yes_price,
            no_price=1.0 - yes_price,
            volume=vol,
            liquidity=liq,
            close_time=close_time,
            category=category,
            platform="kalshi",
            url=f"https://kalshi.com/markets/{ticker}",
        )
    except (ValueError, TypeError, KeyError):
        return None
