import time
from typing import Optional, List
from dnse.models import AccountInfo, AccountBalance, PositionItem

class TradingState:
    def __init__(self):
        self.account: Optional[AccountInfo] = None
        self.balance: Optional[AccountBalance] = None
        self.positions: List[PositionItem] = []
        self.last_sync_time: float = 0.0
        self.is_connected: bool = False
        self.latency_ms: float = 0.0
        self.mode: str = "READ_ONLY"

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
