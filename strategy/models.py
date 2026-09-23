from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class StrategyName(str, Enum):
    BREAKOUT = "BREAKOUT"
    PULLBACK = "PULLBACK"
    MANUAL = "MANUAL"

class Signal(BaseModel):
    symbol: str
    signal_type: SignalType
    strategy: StrategyName
    price: float
    confidence: float = 1.0
    reason: str
    timestamp: datetime = Field(default_factory=datetime.now)

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class OrderType(str, Enum):
    MP = "MP"  # Market Price
    LO = "LO"  # Limit Order

class PaperOrder(BaseModel):
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    order_type: OrderType = OrderType.MP
    status: OrderStatus = OrderStatus.FILLED
    fee: float = 0.0
    tax: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    matched_at: Optional[datetime] = None

class SettlementTranche(BaseModel):
    id: Optional[int] = None
    symbol: str
    quantity: int
    buy_date: str    # YYYY-MM-DD
    settle_date: str # YYYY-MM-DD (T+2)
    is_settled: bool = False
    created_at: datetime = Field(default_factory=datetime.now)

class PaperPosition(BaseModel):
    symbol: str
    total_quantity: int = 0
    available_quantity: int = 0
    avg_buy_price: float = 0.0
    highest_price: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.now)

class PaperAccount(BaseModel):
    initial_balance: float = 5_000_000.0
    cash_balance: float = 5_000_000.0
    stock_value: float = 0.0
    nav: float = 5_000_000.0
    total_realized_pnl: float = 0.0
    auto_trade_enabled: bool = True
    updated_at: datetime = Field(default_factory=datetime.now)
