import httpx
from typing import Optional
from datetime import datetime

from src.models import Market, PricePoint

MANIFOLD_API = "https://api.manifold.markets/v0"
HEADERS = {"User-Agent": "ArbitrageResearchTool/1.0"}


async def fetch_markets(limit: int = 300) -> list[Market]:
    markets: list[Market] = []
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        before_id: Optional[str] = None
        while len(markets) < limit:
            params: dict = {
                "limit": min(100, limit - len(markets)),
                "sort": "last-bet-time",  # valid values: created-time|updated-time|last-bet-time|last-comment-time
            }
            if before_id:
                params["before"] = before_id
            try:
                resp = await client.get(f"{MANIFOLD_API}/markets", params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                break

            if not data:
                break

            for m in data:
                mkt = _parse_market(m)
                if mkt:
                    markets.append(mkt)

            if len(data) < params["limit"]:
                break
            before_id = data[-1]["id"]

    return markets


def _parse_market(m: dict) -> Optional[Market]:
    try:
        if m.get("outcomeType") != "BINARY":
            return None
        if m.get("isResolved"):
            return None

        yes_price = float(m.get("probability") or 0.5)
        yes_price = max(0.01, min(0.99, yes_price))

        close_time: Optional[datetime] = None
        if m.get("closeTime"):
            try:
                close_time = datetime.fromtimestamp(int(m["closeTime"]) / 1000)
            except (ValueError, TypeError):
                pass

        tags = m.get("groupSlugs") or []
        category = tags[0] if tags else ""

        return Market(
            id=str(m.get("id", "")),
            title=str(m.get("question", "Unknown")),
            yes_price=yes_price,
            no_price=1.0 - yes_price,
            volume=float(m.get("volume") or 0),
            liquidity=float(m.get("totalLiquidity") or 0),
            close_time=close_time,
            category=category,
            platform="manifold",
            url=str(m.get("url", "")),
        )
    except (ValueError, TypeError, KeyError):
        return None


async def fetch_price_history(market_id: str, limit: int = 1000) -> list[PricePoint]:
    """Reconstruct price history from bet stream."""
    points: list[PricePoint] = []
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        try:
            resp = await client.get(
                f"{MANIFOLD_API}/bets",
                params={"contractId": market_id, "limit": limit, "order": "asc"},
            )
            resp.raise_for_status()
            for bet in resp.json():
                try:
                    ts = datetime.fromtimestamp(int(bet["createdTime"]) / 1000)
                    price = float(bet.get("probAfter") or bet.get("probBefore") or 0.5)
                    points.append(PricePoint(
                        timestamp=ts,
                        price=price,
                        platform="manifold",
                    ))
                except (KeyError, ValueError):
                    pass
        except Exception:
            pass
    return points
