from pydantic import BaseModel, Field
from typing import Optional, List

class SubAccount(BaseModel):
    id: str
    dealAccount: bool = True
    derivativeAccount: bool = False

class AccountInfo(BaseModel):
    name: str
    custodyCode: str
    investorId: str
    accounts: List[SubAccount] = []

class StockBalance(BaseModel):
    totalCash: float = 0.0
    availableCash: float = 0.0
    withdrawableCash: float = 0.0
    depositInterest: float = 0.0
    totalDebt: float = 0.0
    secureAmount: float = 0.0
    orderSecured: float = 0.0

class AccountBalance(BaseModel):
    stock: StockBalance
    raw: dict = Field(default_factory=dict)

class PositionItem(BaseModel):
    id: Optional[int] = None
    symbol: str
    accountNo: str
    status: str = "OPEN"
    side: str = "NB"
    tradeQuantity: int = 0
    openQuantity: int = 0
    costPrice: float = 0.0
    marketPrice: float = 0.0
    unrealizedPnl: float = 0.0
    pnlPercent: float = 0.0

class PositionsResponse(BaseModel):
    positions: List[PositionItem] = []
