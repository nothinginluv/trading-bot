import pytest
from unittest.mock import AsyncMock
from storage.db import init_db
from storage.repository import PaperTradingRepository
from strategy.paper_engine import PaperEngine
from core.state import TradingState
from bot.handlers.portfolio import cmd_pnl
from core.risk_safeguards import RiskSafeguards

@pytest.mark.asyncio
async def test_performance_statistics_calculation(tmp_path):
    db_path = str(tmp_path / "test_perf.db")
    await init_db(db_path)
    paper_repo = PaperTradingRepository(db_path)
    engine = PaperEngine(paper_repo)
    await engine.initialize(5_000_000.0)

    # 1. When empty
    empty_stats = await paper_repo.get_performance_statistics()
    assert empty_stats["total_trades"] == 0
    assert empty_stats["win_rate_pct"] == 0.0
    assert empty_stats["profit_factor"] == 0.0

    # 2. Record simulated trades
    # Trade 1: Win (+200,000 VND)
    await paper_repo.record_trade("ord-b1", "HPG", "BUY", 100, 25000.0, 0.0, 0.0, 0.0)
    await paper_repo.record_trade("ord-s1", "HPG", "SELL", 100, 27000.0, 0.0, 0.0, 200000.0)

    # Trade 2: Loss (-100,000 VND)
    await paper_repo.record_trade("ord-b2", "TCB", "BUY", 100, 20000.0, 0.0, 0.0, 0.0)
    await paper_repo.record_trade("ord-s2", "TCB", "SELL", 100, 19000.0, 0.0, 0.0, -100000.0)

    # Trade 3: Break-even (0 VND)
    await paper_repo.record_trade("ord-b3", "SSI", "BUY", 100, 30000.0, 0.0, 0.0, 0.0)
    await paper_repo.record_trade("ord-s3", "SSI", "SELL", 100, 30000.0, 0.0, 0.0, 0.0)

    stats = await paper_repo.get_performance_statistics()
    assert stats["total_trades"] == 3
    assert stats["winning_trades"] == 1
    assert stats["losing_trades"] == 1
    assert stats["break_even_trades"] == 1
    assert stats["win_rate_pct"] == 33.33
    assert stats["total_realized_pnl"] == 100000.0
    assert stats["best_trade"] == 200000.0
    assert stats["worst_trade"] == -100000.0
    assert stats["profit_factor"] == 2.0

@pytest.mark.asyncio
async def test_cmd_pnl_telegram_handler(tmp_path):
    db_path = str(tmp_path / "test_cmd_pnl.db")
    await init_db(db_path)
    paper_repo = PaperTradingRepository(db_path)
    engine = PaperEngine(paper_repo)
    await engine.initialize(5_000_000.0)

    # Record 1 winning trade
    await paper_repo.record_trade("ord-b4", "FPT", "BUY", 100, 100000.0, 0.0, 0.0, 0.0)
    await paper_repo.record_trade("ord-s4", "FPT", "SELL", 100, 115000.0, 0.0, 0.0, 1500000.0)

    state = TradingState()
    state.nav_day_start = 5_000_000.0
    state.nav_week_start = 5_000_000.0
    safeguards = RiskSafeguards()

    mock_msg = AsyncMock()
    mock_msg.text = "/pnl"

    await cmd_pnl(
        message=mock_msg,
        state_obj=state,
        paper_engine=engine,
        paper_repo=paper_repo,
        safeguards=safeguards
    )

    mock_msg.answer.assert_called_once()
    reply_text = mock_msg.answer.call_args[0][0]

    assert "BÁO CÁO HIỆU SUẤT ĐẦU TƯ" in reply_text
    assert "Win Rate" in reply_text
    assert "100.0%" in reply_text
    assert "Lãi/Lỗ đã chốt" in reply_text
    assert "+1,500,000 đ" in reply_text
    assert "Phơi nhiễm danh mục" in reply_text
    assert "Trần: 85% NAV" in reply_text
    assert "Drawdown Ngày" in reply_text
