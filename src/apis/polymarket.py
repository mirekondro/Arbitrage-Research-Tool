import json
import httpx
from typing import Optional
from datetime import datetime

from src.models import Market, PricePoint, Trade

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API  = "https://clob.polymarket.com"
DATA_API  = "https://data-api.polymarket.com"

HEADERS = {"User-Agent": "ArbitrageResearchTool/1.0"}


async def fetch_markets(limit: int = 300) -> list[Market]:
    markets: list[Market] = []
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        offset = 0
        while len(markets) < limit:
            batch = min(100, limit - len(markets))
            try:
                resp = await client.get(
                    f"{GAMMA_API}/markets",
                    params={"limit": batch, "offset": offset,
                            "active": "true", "closed": "false"},
                )
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

            offset += len(data)
            if len(data) < batch:
                break

    return markets


def _parse_market(m: dict) -> Optional[Market]:
    try:
        # Prefer mid of bid/ask; fall back to lastTradePrice
        yes_price: float
        if m.get("bestBid") and m.get("bestAsk"):
            yes_price = (float(m["bestBid"]) + float(m["bestAsk"])) / 2
        elif m.get("lastTradePrice"):
            yes_price = float(m["lastTradePrice"])
        elif m.get("outcomePrices"):
            prices = json.loads(m["outcomePrices"])
            yes_price = float(prices[0])
        else:
            yes_price = 0.5

        yes_price = max(0.01, min(0.99, yes_price))

        close_time: Optional[datetime] = None
        for field in ("endDate", "endDateIso", "resolutionSource"):
            raw = m.get(field)
            if raw and isinstance(raw, str) and "T" in raw:
                try:
                    close_time = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    break
                except ValueError:
                    pass

        return Market(
            id=str(m.get("id", "")),
            title=m.get("question", m.get("title", "Unknown")),
            yes_price=yes_price,
            no_price=1.0 - yes_price,
            volume=float(m.get("volume24hr") or m.get("volume") or 0),
            liquidity=float(m.get("liquidity") or 0),
            close_time=close_time,
            category=str(m.get("category") or ""),
            platform="polymarket",
            url=f"https://polymarket.com/event/{m.get('slug', '')}",
            condition_id=m.get("conditionId"),
        )
    except (ValueError, TypeError, KeyError):
        return None


async def fetch_price_history(
    condition_id: str,
    start_ts: int,
    end_ts: int,
    interval: str = "6h",
) -> list[PricePoint]:
    """
    Fetch CLOB price history.  The endpoint requires the YES token id (a large
    decimal integer stored in clobTokenIds[0] on the Gamma market), not the
    conditionId.  Maximum allowed window is ~14 days; cap automatically.
    We accept condition_id here but resolve the token id internally.
    """
    points: list[PricePoint] = []

    # Resolve YES token id from Gamma API
    yes_token_id = await _resolve_yes_token(condition_id)
    if not yes_token_id:
        return points

    # Clamp to 14 days maximum (API rejects longer windows)
    max_window = 14 * 86_400
    if end_ts - start_ts > max_window:
        start_ts = end_ts - max_window

    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        try:
            resp = await client.get(
                f"{CLOB_API}/prices-history",
                params={"market": yes_token_id,
                        "startTs": start_ts,
                        "endTs": end_ts,
                        "interval": interval},
            )
            resp.raise_for_status()
            for pt in resp.json().get("history", []):
                try:
                    points.append(PricePoint(
                        timestamp=datetime.fromtimestamp(pt["t"]),
                        price=float(pt["p"]),
                        platform="polymarket",
                    ))
                except (KeyError, ValueError):
                    pass
        except Exception:
            pass
    return points


async def _resolve_yes_token(condition_id: str) -> str:
    """Look up the YES outcome token id for a given conditionId."""
    import json as _json
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        try:
            resp = await client.get(
                f"{GAMMA_API}/markets",
                params={"conditionId": condition_id, "limit": 1},
            )
            resp.raise_for_status()
            markets = resp.json()
            if not markets:
                return ""
            clob_ids_raw = markets[0].get("clobTokenIds", "[]")
            clob_ids = _json.loads(clob_ids_raw) if isinstance(clob_ids_raw, str) else clob_ids_raw
            return str(clob_ids[0]) if clob_ids else ""
        except Exception:
            return ""


async def fetch_wallet_activity(address: str, limit: int = 500) -> list[Trade]:
    trades: list[Trade] = []
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        for endpoint in [
            f"{DATA_API}/activity",
            f"{GAMMA_API}/activity",
        ]:
            try:
                resp = await client.get(
                    endpoint,
                    params={"user": address, "limit": limit},
                )
                resp.raise_for_status()
                raw = resp.json()
                items = raw if isinstance(raw, list) else raw.get("data", raw.get("activity", []))
                for item in items:
                    trade = _parse_trade(item)
                    if trade:
                        trades.append(trade)
                if trades:
                    break
            except Exception:
                continue
    return trades


def _parse_trade(item: dict) -> Optional[Trade]:
    try:
        ts_raw = item.get("timestamp") or item.get("createdAt") or item.get("date") or 0
        if isinstance(ts_raw, str):
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                ts = datetime.fromtimestamp(int(ts_raw))
        else:
            ts = datetime.fromtimestamp(int(ts_raw))

        # Side detection
        side = (item.get("side") or item.get("type") or item.get("outcome") or "YES").upper()
        if side in ("BUY", "LONG"):
            side = "YES"
        elif side in ("SELL", "SHORT"):
            side = "NO"

        size = float(
            item.get("usdcSize") or item.get("investmentAmount") or item.get("amount") or 0
        )
        price = float(item.get("price") or item.get("avgPrice") or 0.5)
        pnl_raw = item.get("profit") or item.get("pnl") or item.get("profitLoss")
        pnl = float(pnl_raw) if pnl_raw is not None else None

        market = item.get("market") or {}
        market_id = str(
            item.get("marketId") or item.get("market_id") or market.get("id") or ""
        )
        market_title = str(
            item.get("title") or item.get("question") or market.get("question") or "Unknown"
        )

        return Trade(
            id=str(item.get("id") or item.get("transactionHash") or ""),
            market_id=market_id,
            market_title=market_title,
            side=side,
            price=price,
            size=size,
            timestamp=ts,
            outcome=item.get("outcome"),
            pnl=pnl,
        )
    except (ValueError, TypeError, KeyError):
        return None
