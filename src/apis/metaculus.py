import httpx
from typing import Optional
from datetime import datetime

from src.models import Market

META_API = "https://api.metaculus.com/api2"
HEADERS = {"User-Agent": "ArbitrageResearchTool/1.0"}


async def fetch_markets(limit: int = 200) -> list[Market]:
    """Fetch open binary forecast questions from Metaculus (play-money)."""
    markets: list[Market] = []
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        url = f"{META_API}/questions/"
        params: dict = {
            "format": "json",
            "type": "forecast",
            "status": "open",
            "limit": min(100, limit),
        }
        while len(markets) < limit and url:
            try:
                if params:
                    resp = await client.get(url, params=params)
                else:
                    resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                break

            for q in data.get("results", []):
                mkt = _parse_question(q)
                if mkt:
                    markets.append(mkt)

            url = data.get("next") or ""
            params = {}  # Next URL already contains encoded params

            if len(data.get("results", [])) < 10:
                break

    return markets[:limit]


def _parse_question(q: dict) -> Optional[Market]:
    try:
        if q.get("possibilities", {}).get("type") != "binary":
            return None
        if q.get("resolution") not in (None, ""):
            return None  # Already resolved

        cp = q.get("community_prediction") or {}
        full = cp.get("full") or {}
        yes_price = float(full.get("q2") or full.get("median") or 0.5)
        yes_price = max(0.01, min(0.99, yes_price))

        close_time: Optional[datetime] = None
        for field in ("resolution_date", "close_time", "scheduled_close_time"):
            raw = q.get(field)
            if raw:
                try:
                    clean = str(raw).replace("Z", "+00:00")
                    close_time = datetime.fromisoformat(clean)
                    break
                except (ValueError, AttributeError):
                    pass

        qid = q.get("id", "")
        return Market(
            id=str(qid),
            title=str(q.get("title", "Unknown")),
            yes_price=yes_price,
            no_price=1.0 - yes_price,
            volume=float(q.get("activity") or q.get("prediction_count") or 0),
            liquidity=float(q.get("forecaster_count") or 0),
            close_time=close_time,
            category=str((q.get("categories") or [""])[0]),
            platform="metaculus",
            url=str(q.get("page_url") or f"https://www.metaculus.com/questions/{qid}/"),
        )
    except (ValueError, TypeError, KeyError):
        return None
