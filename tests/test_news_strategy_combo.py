import pytest
from unittest.mock import AsyncMock
from core.state import TradingState
from strategy.auto_trader import AutoTrader
from strategy.models import Signal, SignalType, StrategyName, PaperPosition
from indicators.models import TechnicalSummary
from market.models import Candle, OHLCVSeries
from news.models import NewsArticle

from indicators.calculator import compute_technical_summary

def make_breakout_data(symbol: str = "HPG"):
    candles = []
    base_price = 25000.0
    for i in range(50):
        c = base_price + i * 200.0
        candles.append(Candle(
            timestamp=1700000000 + i * 86400,
            date_str=f"2026-01-{(i%30)+1:02d}",
            open=c - 100, high=c + 100, low=c - 100, close=c,
            volume=1000000 if i < 49 else 2500000
        ))
    series = OHLCVSeries(symbol=symbol, resolution="1D", candles=candles)
    summary = compute_technical_summary(series)
    return series, summary

@pytest.mark.asyncio
async def test_auto_trader_vetoes_buy_when_symbol_has_negative_news(tmp_path):
    db_file = str(tmp_path / "test_news_veto.db")
    from storage.db import init_db
    from storage.repository import PaperTradingRepository
    from strategy.paper_engine import PaperEngine

    await init_db(db_file)
    repo = PaperTradingRepository(db_file)
    engine = PaperEngine(repo)
    await engine.initialize(5_000_000.0)

    state = TradingState()
    state.market_regime = "BULLISH"
    series, summary = make_breakout_data("HPG")
    state.vn30_summaries["HPG"] = summary
    state.vn30_candles["HPG"] = series

    # Set negative news for HPG
    bad_article = NewsArticle(
        id="bad_hpg_1",
        title="Thanh tra phát hiện sai phạm nghiêm trọng tại tập đoàn HPG, thua lỗ nặng nề",
        link="https://cafef.vn/bad_hpg.chn",
        source="CafeF",
        related_symbols=["HPG"],
        sentiment_score=-0.7,
        sentiment_label="NEGATIVE"
    )
    state.set_news([bad_article])

    mock_notify = AsyncMock()
    trader = AutoTrader(engine=engine, state=state, notify_func=mock_notify)

    alerts = await trader.process_cycle()

    # Buy order should be VETOED by bad news!
    positions = await repo.get_positions()
    assert len(positions) == 0
    assert any("TỪ CHỐI MUA DO TIN XẤU" in a for a in alerts)

@pytest.mark.asyncio
async def test_auto_trader_crisis_emergency_exit_2b(tmp_path):
    # Option 2B: Severe negative news triggers immediate exit of open position
    db_file = str(tmp_path / "test_crisis_exit.db")
    from storage.db import init_db
    from storage.repository import PaperTradingRepository
    from strategy.paper_engine import PaperEngine

    await init_db(db_file)
    repo = PaperTradingRepository(db_file)
    engine = PaperEngine(repo)
    await engine.initialize(5_000_000.0)

    # Open position for VNM (100 shares settled)
    await repo.upsert_position("VNM", 100, 100, 70_000.0, 70_000.0)

    state = TradingState()
    state.market_regime = "BULLISH"
    _, vnm_summary = make_breakout_data("VNM")
    state.vn30_summaries["VNM"] = vnm_summary

    # Breaking Severe Crisis News arrives for VNM
    crisis_article = NewsArticle(
        id="crisis_vnm_1",
        title="Lãnh đạo chủ chốt VNM bất ngờ bị khởi tố bắt tạm giam, đình chỉ giao dịch cổ phiếu",
        link="https://vietstock.vn/crisis_vnm.htm",
        source="Vietstock",
        related_symbols=["VNM"],
        sentiment_score=-0.9,
        sentiment_label="NEGATIVE",
        is_severe_negative=True
    )
    state.set_news([crisis_article])

    mock_notify = AsyncMock()
    trader = AutoTrader(engine=engine, state=state, notify_func=mock_notify)

    alerts = await trader.process_cycle()

    # Position must be immediately EXITED (sold) due to crisis (Option 2B)
    pos = await repo.get_position("VNM")
    assert pos is None or pos.total_quantity == 0
    assert any("KHẨN CẤP" in a and "VNM" in a for a in alerts)
