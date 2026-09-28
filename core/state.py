import time
from typing import Optional, List, Dict, Tuple, Any
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

        # Market data additions (1D Daily)
        self.vn30_candles: Dict[str, OHLCVSeries] = {}
        self.vn30_summaries: Dict[str, TechnicalSummary] = {}
        self.last_market_sync_time: float = 0.0

        # Market data additions (15m Intraday)
        self.vn30_candles_15m: Dict[str, OHLCVSeries] = {}
        self.vn30_summaries_15m: Dict[str, TechnicalSummary] = {}
        self.last_market_sync_time_15m: float = 0.0

        # Benchmark Market Regime (VN-INDEX)
        self.vnindex_candles: Optional[OHLCVSeries] = None
        self.vnindex_summary: Optional[TechnicalSummary] = None
        self.vnindex_candles_15m: Optional[OHLCVSeries] = None
        self.vnindex_summary_15m: Optional[TechnicalSummary] = None
        self.market_regime: str = "BULLISH"

        # Circuit Breaker NAV tracking
        self.nav_day_start: Optional[float] = None
        self.nav_week_start: Optional[float] = None
        self.last_nav_reset_day: str = ""
        self.last_nav_reset_week: int = -1

        # Market News & Sentiment (CafeF & Vietstock)
        self.latest_news: list = []
        self.symbol_sentiment: Dict[str, float] = {}
        self.severe_crisis_symbols: Dict[str, str] = {}
        self.last_news_sync_time: float = 0.0

        # Corporate Events & Official Disclosures
        self.corporate_events: list = []
        self.symbol_events: Dict[str, list] = {}
        self.last_events_sync_time: float = 0.0

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

    def set_market_data(self, candles: Dict[str, OHLCVSeries], summaries: Dict[str, TechnicalSummary], resolution: str = "1D"):
        res_clean = "15" if resolution in ("15", "15m", "15M") else "1D"
        if res_clean == "15":
            self.vn30_candles_15m = candles
            self.vn30_summaries_15m = summaries
            self.last_market_sync_time_15m = time.time()
        else:
            self.vn30_candles = candles
            self.vn30_summaries = summaries
            self.last_market_sync_time = time.time()

    def update_candles(self, symbol: str, series: OHLCVSeries, resolution: str = "1D"):
        res_clean = "15" if resolution in ("15", "15m", "15M") else "1D"
        if res_clean == "15":
            self.vn30_candles_15m[symbol.upper()] = series
        else:
            self.vn30_candles[symbol.upper()] = series

    def update_summary(self, symbol: str, summary: TechnicalSummary, resolution: str = "1D"):
        res_clean = "15" if resolution in ("15", "15m", "15M") else "1D"
        if res_clean == "15":
            self.vn30_summaries_15m[symbol.upper()] = summary
        else:
            self.vn30_summaries[symbol.upper()] = summary

    def get_summary(self, symbol: str, resolution: str = "1D") -> Optional[TechnicalSummary]:
        res_clean = "15" if resolution in ("15", "15m", "15M") else "1D"
        if res_clean == "15":
            return self.vn30_summaries_15m.get(symbol.upper())
        return self.vn30_summaries.get(symbol.upper())

    def get_candles(self, symbol: str, resolution: str = "1D") -> Optional[OHLCVSeries]:
        res_clean = "15" if resolution in ("15", "15m", "15M") else "1D"
        if res_clean == "15":
            return self.vn30_candles_15m.get(symbol.upper())
        return self.vn30_candles.get(symbol.upper())

    def update_nav_tracker(self, current_nav: float, date_str: str, week_number: int):
        if current_nav <= 0:
            return
        if self.last_nav_reset_day != date_str or self.nav_day_start is None:
            self.nav_day_start = current_nav
            self.last_nav_reset_day = date_str
        if self.last_nav_reset_week != week_number or self.nav_week_start is None:
            self.nav_week_start = current_nav
            self.last_nav_reset_week = week_number

    def get_top_movers(self, limit: int = 5) -> Tuple[List[TechnicalSummary], List[TechnicalSummary]]:
        all_items = list(self.vn30_summaries.values())
        gainers = sorted(all_items, key=lambda x: x.change_pct, reverse=True)[:limit]
        losers = sorted(all_items, key=lambda x: x.change_pct)[:limit]
        return gainers, losers

    def set_market_regime(self, summary: TechnicalSummary, series: Optional[OHLCVSeries] = None):
        from indicators.calculator import evaluate_market_regime
        self.vnindex_summary = summary
        if series:
            self.vnindex_candles = series
        self.market_regime = evaluate_market_regime(summary)

    def set_news(self, articles: list):
        self.latest_news = articles
        self.last_news_sync_time = time.time()
        
        # Calculate average sentiment and detect crises per symbol
        scores: Dict[str, list] = {}
        crises: Dict[str, str] = {}
        for art in articles:
            symbols = art.related_symbols if hasattr(art, "related_symbols") else []
            for s in symbols:
                sym = s.upper()
                if sym not in scores:
                    scores[sym] = []
                scores[sym].append(art.sentiment_score)
                if getattr(art, "is_severe_negative", False):
                    crises[sym] = art.title

        self.symbol_sentiment = {
            sym: round(sum(sc) / len(sc), 2)
            for sym, sc in scores.items() if sc
        }
        self.severe_crisis_symbols = crises

    def get_symbol_sentiment(self, symbol: str) -> float:
        return self.symbol_sentiment.get(symbol.upper(), 0.0)

    def is_symbol_in_crisis(self, symbol: str) -> Tuple[bool, str]:
        sym = symbol.upper()
        if sym in self.severe_crisis_symbols:
            return True, self.severe_crisis_symbols[sym]
        return False, ""

    def set_corporate_events(self, events: list):
        self.corporate_events = events
        self.symbol_events = {}
        for ev in events:
            sym = ev.symbol.upper()
            self.symbol_events.setdefault(sym, []).append(ev)
        self.last_events_sync_time = time.time()

    def get_symbol_events(self, symbol: str) -> list:
        return self.symbol_events.get(symbol.upper(), [])

    def is_ex_date(self, symbol: str, target_date_str: str) -> Optional[Any]:
        """
        Returns the CorporateEvent if target_date_str matches the ex_date (GDKHQ)
        for the given symbol.
        """
        for ev in self.symbol_events.get(symbol.upper(), []):
            if ev.ex_date and ev.ex_date == target_date_str:
                return ev
        return None


