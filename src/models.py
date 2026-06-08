from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Market:
    id: str
    title: str
    yes_price: float  # 0.0 – 1.0
    no_price: float   # 0.0 – 1.0
    volume: float
    liquidity: float
    close_time: Optional[datetime]
    category: str
    platform: str     # "polymarket" | "kalshi" | "manifold"
    url: str
    condition_id: Optional[str] = None  # Polymarket CLOB condition id

    @property
    def mid_price(self) -> float:
        return (self.yes_price + (1.0 - self.no_price)) / 2.0


@dataclass
class ArbitrageOpportunity:
    market_a: Market
    market_b: Market
    matched_title: str
    similarity: float
    buy_yes_on: str   # platform name
    buy_no_on: str    # platform name
    yes_price: float  # cost to buy YES
    no_price: float   # cost to buy NO  (= 1 – other_yes)
    profit_pct: float # guaranteed profit % after fees
    total_cost: float # total capital deployed per $1 payout


@dataclass
class PricePoint:
    timestamp: datetime
    price: float
    platform: str


@dataclass
class Trade:
    id: str
    market_id: str
    market_title: str
    side: str            # "YES" | "NO"
    price: float         # fill price 0–1
    size: float          # USDC invested
    timestamp: datetime
    outcome: Optional[str] = None  # "WIN" | "LOSS" | None
    pnl: Optional[float] = None


@dataclass
class BacktestResult:
    address: str
    trades: list = field(default_factory=list)
    total_pnl: float = 0.0
    win_rate: float = 0.0
    roi_pct: float = 0.0
    total_invested: float = 0.0
    running_pnl: list = field(default_factory=list)
    running_dates: list = field(default_factory=list)
