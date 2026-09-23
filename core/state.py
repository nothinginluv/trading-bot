import time
from typing import Optional, List, Dict, Tuple
from dnse.models import AccountInfo, AccountBalance, PositionItem
from market.models import OHLCVSeries
from indicators.models import TechnicalSummary

class TradingState:
    def __init__(self):
        self.account: Optional[AccountInfo] = None
        self.balance: Optional[AccountBalance] = None
        self.positions: List[PositionItem] = []
        self.last_sync_time: float = 0.0
        self.is_connected: bool = False
        self.latency_ms: float = 0.0
        self.mode: str = "READ_ONLY"

        # Market data additions
        self.vn30_candles: Dict[str, OHLCVSeries] = {}
        self.vn30_summaries: Dict[str, TechnicalSummary] = {}
        self.last_market_sync_time: float = 0.0

    def set_account(self, account: AccountInfo):
        self.account = account
        self.is_connected = True
        self.last_sync_time = time.time()

    def set_balance(self, balance: AccountBalance):
        self.balance = balance
        self.last_sync_time = time.time()

    def set_positions(self, positions: List[PositionItem]):
        self.positions = positions
        self.last_sync_time = time.time()

    def is_cache_valid(self, ttl_seconds: float = 15.0) -> bool:
        return (time.time() - self.last_sync_time) < ttl_seconds and self.balance is not None

    def set_market_data(self, candles: Dict[str, OHLCVSeries], summaries: Dict[str, TechnicalSummary]):
        self.vn30_candles = candles
        self.vn30_summaries = summaries
        self.last_market_sync_time = time.time()

    def update_candles(self, symbol: str, series: OHLCVSeries):
        self.vn30_candles[symbol.upper()] = series

    def update_summary(self, symbol: str, summary: TechnicalSummary):
        self.vn30_summaries[symbol.upper()] = summary

    def get_summary(self, symbol: str) -> Optional[TechnicalSummary]:
        return self.vn30_summaries.get(symbol.upper())

    def get_top_movers(self, limit: int = 5) -> Tuple[List[TechnicalSummary], List[TechnicalSummary]]:
        all_items = list(self.vn30_summaries.values())
        gainers = sorted(all_items, key=lambda x: x.change_pct, reverse=True)[:limit]
        losers = sorted(all_items, key=lambda x: x.change_pct)[:limit]
        return gainers, losers
