from typing import Optional

from src.models import Market, ArbitrageOpportunity
from src.core.matcher import find_matches

# Conservative fee estimates (round-trip: maker + taker typical worst-case)
FEES: dict[str, float] = {
    "polymarket": 0.02,
    "kalshi":     0.07,
    "manifold":   0.00,  # play money
}

MIN_PROFIT_PCT = 0.5  # surface opportunities with >0.5% guaranteed edge


def _arb_profit(buy_yes_mkt: Market, buy_no_mkt: Market) -> Optional[float]:
    """
    Buy YES on buy_yes_mkt and NO on buy_no_mkt.
    Both legs pay out $1 on the correct outcome — guaranteed profit exists when
    total cost (including fees) < $1.

    Returns profit % or None if no arb.
    """
    cost_yes = buy_yes_mkt.yes_price
    cost_no  = buy_no_mkt.no_price   # = 1 – buy_no_mkt.yes_price

    fee_yes = cost_yes * FEES.get(buy_yes_mkt.platform, 0.02)
    fee_no  = cost_no  * FEES.get(buy_no_mkt.platform,  0.02)
    total   = cost_yes + cost_no + fee_yes + fee_no

    if total >= 1.0:
        return None
    return (1.0 - total) / total * 100.0


def check_pair(
    market_a: Market,
    market_b: Market,
    similarity: float,
) -> Optional[ArbitrageOpportunity]:
    for buy_yes_mkt, buy_no_mkt in [(market_a, market_b), (market_b, market_a)]:
        profit_pct = _arb_profit(buy_yes_mkt, buy_no_mkt)
        if profit_pct is None or profit_pct < MIN_PROFIT_PCT:
            continue

        cost_yes = buy_yes_mkt.yes_price
        cost_no  = buy_no_mkt.no_price
        total    = cost_yes + cost_no  # pre-fee for display

        title = market_a.title if len(market_a.title) <= len(market_b.title) else market_b.title

        return ArbitrageOpportunity(
            market_a=market_a,
            market_b=market_b,
            matched_title=title,
            similarity=similarity,
            buy_yes_on=buy_yes_mkt.platform,
            buy_no_on=buy_no_mkt.platform,
            yes_price=cost_yes,
            no_price=cost_no,
            profit_pct=profit_pct,
            total_cost=total,
        )
    return None


def scan_opportunities(
    all_markets: dict[str, list[Market]],
    threshold: float = 72.0,
) -> list[ArbitrageOpportunity]:
    """Cross all platform pairs and return sorted arbitrage opportunities."""
    opportunities: list[ArbitrageOpportunity] = []
    platforms = [p for p, mkts in all_markets.items() if mkts]

    for i in range(len(platforms)):
        for j in range(i + 1, len(platforms)):
            pa, pb = platforms[i], platforms[j]
            for mkt_a, mkt_b, sim in find_matches(all_markets[pa], all_markets[pb], threshold):
                opp = check_pair(mkt_a, mkt_b, sim)
                if opp:
                    opportunities.append(opp)

    opportunities.sort(key=lambda o: o.profit_pct, reverse=True)
    return opportunities
