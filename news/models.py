from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class NewsArticle(BaseModel):
    id: str
    title: str
    link: str
    source: str  # "CafeF" | "Vietstock"
    published_at: Optional[str] = None
    related_symbols: List[str] = Field(default_factory=list)
    sentiment_score: float = 0.0  # -1.0 (very negative) to +1.0 (very positive)
    sentiment_label: str = "NEUTRAL"  # "POSITIVE", "NEGATIVE", "NEUTRAL"
    is_severe_negative: bool = False  # True if contains severe crisis keywords (arrest, fraud, halt)
    summary: str = ""
    created_at: datetime = Field(default_factory=datetime.now)

class SymbolNewsSummary(BaseModel):
    symbol: str
    sentiment_score: float = 0.0
    sentiment_label: str = "NEUTRAL"
    has_severe_negative: bool = False
    articles_count: int = 0
    recent_articles: List[NewsArticle] = Field(default_factory=list)

from enum import Enum

class EventType(str, Enum):
    DIVIDEND_CASH = "DIVIDEND_CASH"          # Cổ tức tiền mặt
    DIVIDEND_STOCK = "DIVIDEND_STOCK"        # Cổ tức cổ phiếu / thưởng
    ISSUE_ADDITIONAL = "ISSUE_ADDITIONAL"    # Phát hành thêm / chào bán
    ESOP = "ESOP"                            # Phát hành ESOP
    AGM = "AGM"                              # Đại hội đồng cổ đông
    PERSONNEL = "PERSONNEL"                  # Thay đổi nhân sự cấp cao
    LISTING = "LISTING"                      # Niêm yết / Giao dịch bổ sung
    OTHER = "OTHER"

class CorporateEvent(BaseModel):
    id: str
    symbol: str
    ex_date: Optional[str] = None          # Ngày GDKHQ (YYYY-MM-DD)
    record_date: Optional[str] = None      # Ngày ĐKCC (YYYY-MM-DD)
    event_type: EventType = EventType.OTHER
    content: str
    source: str = "CafeF Official / CBTT"
    created_at: datetime = Field(default_factory=datetime.now)

