import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat, User
from config.constants import get_symbol_sector, VN30_SECTOR_MAP
from core.risk_safeguards import RiskSafeguards
from storage.db import init_db
from storage.repository import PaperTradingRepository
from strategy.paper_engine import PaperEngine
from strategy.auto_trader import AutoTrader
from core.state import TradingState
from market.models import Candle, OHLCVSeries
from indicators.calculator import compute_technical_summary
from bot.handlers.paper import cmd_buy_paper

def test_vn30_sector_mapping():
    assert get_symbol_sector("TCB") == "NGÂN HÀNG"
    assert get_symbol_sector("MBB") == "NGÂN HÀNG"
    assert get_symbol_sector("VCB") == "NGÂN HÀNG"
    assert get_symbol_sector("HPG") == "THÉP & VẬT LIỆU"
    assert get_symbol_sector("FPT") == "CÔNG NGHỆ"
    assert get_symbol_sector("MWG") == "BÁN LẺ"
    # Borderline and newly separated sectors
    assert get_symbol_sector("GAS") == "DẦU KHÍ & XĂNG DẦU"
    assert get_symbol_sector("PLX") == "DẦU KHÍ & XĂNG DẦU"
    assert get_symbol_sector("BSR") == "DẦU KHÍ & XĂNG DẦU"
    assert get_symbol_sector("POW") == "ĐIỆN & TIỆN ÍCH"
    assert get_symbol_sector("GVR") == "CAO SU & VẬT LIỆU"
    assert get_symbol_sector("UNKNOWN") == "KHÁC"

def test_risk_safeguards_sector_concentration():
    safeguards = RiskSafeguards(max_positions_per_sector=2)

    # 1. 0 positions held -> allow any
    ok, _ = safeguards.validate_sector_concentration("TCB", [])
    assert ok is True

    # 2. 1 bank held -> allow 2nd bank
    ok, _ = safeguards.validate_sector_concentration("TCB", ["MBB"])
    assert ok is True

    # 3. 2 banks held -> reject 3rd bank
    ok, reason = safeguards.validate_sector_concentration("CTG", ["MBB", "TCB"])
    assert ok is False
    assert "NGÂN HÀNG" in reason
    assert "Vượt quá giới hạn tối đa 2 mã" in reason

    # 4. 2 banks held -> allow non-bank (e.g. HPG, FPT)
    ok, _ = safeguards.validate_sector_concentration("HPG", ["MBB", "TCB"])
    assert ok is True
    ok, _ = safeguards.validate_sector_concentration("FPT", ["MBB", "TCB"])
    assert ok is True

@pytest.mark.asyncio
async def test_autotrader_skips_saturated_sector_and_selects_next_best(tmp_path):
    test_db = str(tmp_path / "test_sec_autotrader.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo, slippage_pct=0.0)
    await engine.initialize(initial_capital=5000000.0)
    
    # Pre-populate 2 banking positions in portfolio
    await repo.upsert_position("MBB", 100, 100, 20000.0, 20000.0)
    await repo.upsert_position("VCB", 50, 50, 80000.0, 80000.0)

    state = TradingState()
    safeguards = RiskSafeguards(max_concurrent_positions=4, max_positions_per_sector=2)

    notifications = []
    async def capture_notify(text: str):
        notifications.append(text)

    live_trader = MagicMock()
    live_trader.safeguards = safeguards
    live_trader.auto_cancel_stale_orders = AsyncMock(return_value=[])

    trader = AutoTrader(engine=engine, state=state, notify_func=capture_notify, live_trader=live_trader)

    # Setup candidate 1: TCB (Banking, confidence 0.90)
    def make_breakout_series(sym, base):
        candles = []
        for i in range(50):
            c = base + i * 100.0
            candles.append(Candle(
                timestamp=1700000000 + i * 86400,
                date_str=f"2026-01-{(i%30)+1:02d}",
                open=c - 50, high=c + 50, low=c - 50, close=c,
                volume=1000000 if i < 49 else 2500000
            ))
        series = OHLCVSeries(symbol=sym, resolution="1D", candles=candles)
        summary = compute_technical_summary(series)
        state.update_candles(sym, series)
        state.update_summary(sym, summary)

    # Provide summaries for held positions
    make_breakout_series("MBB", 20000.0)
    make_breakout_series("VCB", 80000.0)
    # Create breakout for TCB (Bank) and FPT (Tech)
    make_breakout_series("TCB", 25000.0)
    make_breakout_series("FPT", 120000.0)

    # AutoTrader process cycle
    alerts = await trader.process_cycle()

    # TCB should be rejected due to sector concentration (2 banks already held: MBB, VCB)
    assert any("TỪ CHỐI MUA DO TẬP TRUNG NGÀNH" in a and "TCB" in a for a in alerts)
    
    # AutoTrader should have picked FPT instead!
    pos_fpt = await repo.get_position("FPT")
    assert pos_fpt is not None
    assert pos_fpt.total_quantity > 0

    # TCB position should NOT be created
    pos_tcb = await repo.get_position("TCB")
    assert pos_tcb is None or pos_tcb.total_quantity == 0

@pytest.mark.asyncio
async def test_cmd_buy_paper_sector_limit_check(tmp_path):
    test_db = str(tmp_path / "test_cmd_sec.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo, slippage_pct=0.0)
    await engine.initialize(initial_capital=5000000.0)

    # Pre-populate 2 banks: MBB and TCB
    await repo.upsert_position("MBB", 100, 100, 20000.0, 20000.0)
    await repo.upsert_position("TCB", 100, 100, 25000.0, 25000.0)

    state = TradingState()
    safeguards = RiskSafeguards(max_positions_per_sector=2)

    msg = MagicMock(spec=Message)
    msg.text = "/buy_paper CTG 50 30000"
    msg.answer = AsyncMock()

    await cmd_buy_paper(msg, engine, state, paper_repo=repo, safeguards=safeguards)
    msg.answer.assert_called_once()
    assert "TỪ CHỐI BỞI QUẢN TRỊ RỦI RO NGÀNH" in msg.answer.call_args[0][0]
    assert "NGÂN HÀNG" in msg.answer.call_args[0][0]

    # Now buy non-bank HPG
    msg2 = MagicMock(spec=Message)
    msg2.text = "/buy_paper HPG 50 25000"
    msg2.answer = AsyncMock()

    await cmd_buy_paper(msg2, engine, state, paper_repo=repo, safeguards=safeguards)
    msg2.answer.assert_called_once()
    assert "KHỚP LỆNH MUA GIẢ LẬP THÀNH CÔNG" in msg2.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_sectors(tmp_path):
    from bot.handlers.market import cmd_sectors
    test_db = str(tmp_path / "test_cmd_sec_audit.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    await repo.upsert_position("MBB", 100, 100, 20000.0, 20000.0)
    await repo.upsert_position("TCB", 100, 100, 25000.0, 25000.0)

    safeguards = RiskSafeguards(max_positions_per_sector=2)

    msg = MagicMock(spec=Message)
    msg.text = "/sectors"
    msg.answer = AsyncMock()

    await cmd_sectors(msg, paper_repo=repo, safeguards=safeguards)
    msg.answer.assert_called_once()
    out = msg.answer.call_args[0][0]
    assert "BẢNG PHÂN LOẠI NGÀNH VN30" in out
    assert "DẦU KHÍ & XĂNG DẦU" in out
    assert "ĐIỆN & TIỆN ÍCH" in out
    assert "CAO SU & VẬT LIỆU" in out
    assert "ĐẦY 2/2" in out or "2/2" in out
