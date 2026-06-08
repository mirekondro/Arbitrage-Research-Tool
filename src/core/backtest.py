from datetime import datetime, timedelta
from typing import Optional

from src.models import Trade, BacktestResult


async def run_backtest(
    address: str,
    lookback_days: int = 90,
    copy_delay_hours: float = 0.0,
) -> BacktestResult:
    from src.apis.polymarket import fetch_wallet_activity

    raw_trades = await fetch_wallet_activity(address, limit=500)

    cutoff = datetime.now() - timedelta(days=lookback_days)
    trades = sorted(
        [t for t in raw_trades if t.timestamp >= cutoff],
        key=lambda t: t.timestamp,
    )

    if not trades:
        return BacktestResult(address=address)

    simulated: list[Trade] = []
    total_invested = 0.0
    cumulative_pnl = 0.0
    wins = losses = 0
    running_pnl: list[float] = []
    running_dates: list[datetime] = []

    for t in trades:
        exec_time = t.timestamp + timedelta(hours=copy_delay_hours)
        total_invested += t.size

        pnl = t.pnl
        if pnl is None and t.outcome:
            # Estimate P&L from outcome
            if t.outcome.upper() in ("WIN", "YES", "CORRECT"):
                pnl = t.size * (1.0 / t.price - 1.0) if t.price > 0 else 0.0
            else:
                pnl = -t.size

        if pnl is not None:
            cumulative_pnl += pnl
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1

        running_pnl.append(cumulative_pnl)
        running_dates.append(exec_time)

        simulated.append(Trade(
            id=f"copy_{t.id}",
            market_id=t.market_id,
            market_title=t.market_title,
            side=t.side,
            price=t.price,
            size=t.size,
            timestamp=exec_time,
            outcome=t.outcome,
            pnl=pnl,
        ))

    total_resolved = wins + losses
    return BacktestResult(
        address=address,
        trades=simulated,
        total_pnl=cumulative_pnl,
        win_rate=wins / total_resolved if total_resolved > 0 else 0.0,
        roi_pct=cumulative_pnl / total_invested * 100.0 if total_invested > 0 else 0.0,
        total_invested=total_invested,
        running_pnl=running_pnl,
        running_dates=running_dates,
    )
