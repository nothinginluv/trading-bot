import pytest
from datetime import datetime
from unittest.mock import AsyncMock
from news.models import CorporateEvent, EventType
from news.event_adjuster import parse_event_adjustment, PositionAdjustmentInfo
from storage.db import init_db
from storage.repository import PaperTradingRepository
from strategy.paper_engine import PaperEngine
from strategy.auto_trader import AutoTrader
from core.state import TradingState

def test_parse_event_adjustment_stock_dividend():
    # 1. Percentage format
    ev1 = CorporateEvent(
        id="ev1",
        symbol="FPT",
        event_type=EventType.DIVIDEND_STOCK,
        content="Trả cổ tức bằng cổ phiếu tỷ lệ 15% và phát hành cổ phiếu thưởng"
    )
    adj1 = parse_event_adjustment(ev1)
    assert adj1 is not None
    assert adj1.adjustment_type == "STOCK_DIVIDEND"
    assert pytest.approx(adj1.ratio, 0.001) == 0.15
    assert pytest.approx(adj1.multiplier, 0.001) == 1.15

    # 2. 100:15 ratio format
    ev2 = CorporateEvent(
        id="ev2",
        symbol="MBB",
        event_type=EventType.DIVIDEND_STOCK,
        content="Trả cổ tức năm 2023 bằng cổ phiếu, tỷ lệ 100:15"
    )
    adj2 = parse_event_adjustment(ev2)
    assert adj2 is not None
    assert pytest.approx(adj2.ratio, 0.001) == 0.15
    assert pytest.approx(adj2.multiplier, 0.001) == 1.15

    # 3. 10:1 ratio format
    ev3 = CorporateEvent(
        id="ev3",
        symbol="ACB",
        event_type=EventType.DIVIDEND_STOCK,
        content="Trả cổ tức bằng cổ phiếu tỷ lệ 10:1"
    )
    adj3 = parse_event_adjustment(ev3)
    assert adj3 is not None
    assert pytest.approx(adj3.ratio, 0.001) == 0.10
    assert pytest.approx(adj3.multiplier, 0.001) == 1.10

def test_parse_event_adjustment_stock_split():
    ev = CorporateEvent(
        id="ev_split",
        symbol="HPG",
        event_type=EventType.OTHER,
        content="Thực hiện chia tách cổ phiếu tỷ lệ 2:1"
    )
    adj = parse_event_adjustment(ev)
    assert adj is not None
    assert adj.adjustment_type == "STOCK_SPLIT"
    assert pytest.approx(adj.multiplier, 0.001) == 2.0

def test_parse_event_adjustment_cash_dividend():
    # 1. Percentage of par value (10,000 VND)
    ev1 = CorporateEvent(
        id="ev_cash1",
        symbol="VNM",
        event_type=EventType.DIVIDEND_CASH,
        content="Trả cổ tức đợt 2/2025 bằng tiền mặt tỷ lệ 10%"
    )
    adj1 = parse_event_adjustment(ev1)
    assert adj1 is not None
    assert adj1.adjustment_type == "CASH_DIVIDEND"
    assert adj1.cash_per_share == 1000.0

    # 2. Explicit VND amount
    ev2 = CorporateEvent(
        id="ev_cash2",
        symbol="GAS",
        event_type=EventType.DIVIDEND_CASH,
        content="Trả cổ tức bằng tiền mặt 1.500 đồng/cp"
    )
    adj2 = parse_event_adjustment(ev2)
    assert adj2 is not None
    assert adj2.adjustment_type == "CASH_DIVIDEND"
    assert adj2.cash_per_share == 1500.0

def test_parse_event_adjustment_ignores_non_dividend():
    ev = CorporateEvent(
        id="ev_agm",
        symbol="VIC",
        event_type=EventType.AGM,
        content="Họp Đại hội đồng cổ đông thường niên năm 2026"
    )
    adj = parse_event_adjustment(ev)
    assert adj is None

@pytest.mark.asyncio
async def test_repository_position_adjustment_lifecycle(tmp_path):
    db_file = str(tmp_path / "test_repo_adj.db")
    await init_db(db_file)
    repo = PaperTradingRepository(db_file)

    # Initial state
    assert await repo.is_adjustment_applied("test_ev_01") is False

    # Insert position
    await repo.upsert_position("FPT", total_qty=1000, available_qty=1000, avg_price=120000.0, highest_price=125000.0)

    # Apply adjustment: 20% stock dividend
    await repo.apply_position_adjustment(
        symbol="FPT",
        new_total_qty=1200,
        new_available_qty=1000,
        new_avg_price=100000.0,
        new_highest_price=104200.0,
        cash_delta=0.0
    )
    await repo.record_position_adjustment(
        event_id="test_ev_01",
        symbol="FPT",
        adjustment_type="STOCK_DIVIDEND",
        ratio=0.20,
        cash_per_share=0.0,
        old_quantity=1000,
        new_quantity=1200,
        old_avg_price=120000.0,
        new_avg_price=100000.0,
        old_highest_price=125000.0,
        new_highest_price=104200.0,
        applied_date="2026-09-24"
    )

    assert await repo.is_adjustment_applied("test_ev_01") is True

    # Verify updated position
    pos = await repo.get_position("FPT")
    assert pos.total_quantity == 1200
    assert pos.available_quantity == 1000
    assert pos.avg_buy_price == 100000.0
    assert pos.highest_price == 104200.0

    # Verify audit log
    records = await repo.get_position_adjustments("FPT")
    assert len(records) == 1
    assert records[0]["event_id"] == "test_ev_01"
    assert records[0]["ratio"] == 0.20

@pytest.mark.asyncio
async def test_autotrader_prevents_false_stop_loss_on_ex_date(tmp_path):
    db_file = str(tmp_path / "test_autotrader_adj.db")
    await init_db(db_file)
    repo = PaperTradingRepository(db_file)
    engine = PaperEngine(repo)
    state = TradingState()

    # Admin notification collector
    notifications = []
    async def mock_notify(msg: str):
        notifications.append(msg)

    autotrader = AutoTrader(engine=engine, state=state, notify_func=mock_notify)

    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Setup open position in FPT: 1000 shares @ 120,000đ (highest 125,000đ)
    await repo.upsert_position("FPT", total_qty=1000, available_qty=1000, avg_price=120000.0, highest_price=125000.0)

    # 2. Setup Corporate Event: Stock dividend 20% on today (Ex-Date)
    ev = CorporateEvent(
        id="fpt_div_2026",
        symbol="FPT",
        ex_date=today_str,
        event_type=EventType.DIVIDEND_STOCK,
        content="Trả cổ tức bằng cổ phiếu tỷ lệ 20%"
    )
    state.set_corporate_events([ev])

    # 3. Simulate market price drop on Ex-Date:
    # 120,000 / 1.20 = 100,000 reference price. Market trades at 101,000đ (+1.0% above reference)
    # Without adjustment, 101,000 vs old 120,000 is -15.8% drop -> FALSE STOP LOSS!
    from indicators.models import TechnicalSummary
    summary = TechnicalSummary(
        symbol="FPT",
        price=101000.0,
        change=1000.0,
        change_pct=1.0,
        open=100000.0,
        high=102000.0,
        low=100000.0,
        volume=1000000,
        vol_sma20=800000.0,
        vol_ratio=1.25,
        ema9=100000.0,
        ema21=98000.0,
        ema50=95000.0,
        rsi14=55.0,
        macd=100.0,
        macd_signal=50.0,
        macd_hist=50.0,
        bb_upper=105000.0,
        bb_middle=100000.0,
        bb_lower=95000.0,
        atr14=2000.0,
        trend="UPTREND",
        rsi_status="NEUTRAL",
        macd_status="BULLISH",
        composite_signal="TRUNG LẬP"
    )
    state.update_summary("FPT", summary)

    # Run AutoTrader cycle
    alerts = await autotrader.process_cycle()

    # 4. Verify Technical Adjustment occurred
    assert any("[ĐIỀU CHỈNH KỸ THUẬT NGÀY GDKHQ] FPT" in a for a in alerts)
    assert any("FPT" in n and "ĐIỀU CHỈNH KỸ THUẬT" in n for n in notifications)

    # Verify updated position in repo
    updated_pos = await repo.get_position("FPT")
    assert updated_pos.total_quantity == 1200
    assert updated_pos.avg_buy_price == 100000.0
    assert updated_pos.highest_price == 104200.0

    # Verify NO STOP LOSS happened (position remains open, not sold)
    assert updated_pos.total_quantity > 0
    assert not any("Cắt lỗ tự động" in a for a in alerts)
    assert not any("BÁN TOÀN BỘ" in a for a in alerts)

    # 5. Verify Idempotency: Running another cycle today does not re-adjust
    alerts2 = await autotrader.process_cycle()
    assert not any("[ĐIỀU CHỈNH KỸ THUẬT NGÀY GDKHQ] FPT" in a for a in alerts2)
    pos_after = await repo.get_position("FPT")
    assert pos_after.total_quantity == 1200
    assert pos_after.avg_buy_price == 100000.0

@pytest.mark.asyncio
async def test_autotrader_cash_dividend_credits_cash_and_lowers_cost_basis(tmp_path):
    db_file = str(tmp_path / "test_cash_div.db")
    await init_db(db_file)
    repo = PaperTradingRepository(db_file)
    engine = PaperEngine(repo)
    state = TradingState()
    await repo.get_or_create_account(initial_capital=5_000_000.0)

    autotrader = AutoTrader(engine=engine, state=state)
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Position: 500 shares of VNM @ 70,000đ
    await repo.upsert_position("VNM", total_qty=500, available_qty=500, avg_price=70000.0, highest_price=72000.0)

    # Corporate Event: Cash dividend 2,000 VND/share on Ex-Date
    ev = CorporateEvent(
        id="vnm_cash_div",
        symbol="VNM",
        ex_date=today_str,
        event_type=EventType.DIVIDEND_CASH,
        content="Trả cổ tức bằng tiền mặt 2.000 đồng/cp"
    )
    state.set_corporate_events([ev])

    from indicators.models import TechnicalSummary
    state.update_summary("VNM", TechnicalSummary(
        symbol="VNM", price=68500.0, change=500.0, change_pct=0.7,
        open=68000.0, high=69000.0, low=68000.0, volume=500000, vol_sma20=400000.0,
        vol_ratio=1.2, ema9=68000.0, ema21=67000.0, ema50=66000.0, rsi14=50.0,
        macd=50.0, macd_signal=30.0, macd_hist=20.0, bb_upper=71000.0,
        bb_middle=68000.0, bb_lower=65000.0, atr14=1200.0, trend="UPTREND",
        rsi_status="NEUTRAL", macd_status="BULLISH", composite_signal="TRUNG LẬP"
    ))

    alerts = await autotrader.process_cycle()
    assert any("[ĐIỀU CHỈNH KỸ THUẬT NGÀY GDKHQ] VNM" in a for a in alerts)

    # Verify updated position: avg_price = 70,000 - 2,000 = 68,000đ
    pos = await repo.get_position("VNM")
    assert pos.total_quantity == 500
    assert pos.avg_buy_price == 68000.0
    assert pos.highest_price == 70000.0

    # Verify cash credited: 500 * 2,000 = 1,000,000đ -> total cash = 6,000,000đ
    acc = await repo.get_or_create_account()
    assert acc.cash_balance == 6_000_000.0

@pytest.mark.asyncio
async def test_autotrader_floors_fractional_shares_stock_dividend(tmp_path):
    db_file = str(tmp_path / "test_floor.db")
    await init_db(db_file)
    repo = PaperTradingRepository(db_file)
    engine = PaperEngine(repo)
    state = TradingState()

    notifications = []
    async def mock_notify(msg: str):
        notifications.append(msg)

    autotrader = AutoTrader(engine=engine, state=state, notify_func=mock_notify)
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 10 shares of FPT @ 120,000đ
    await repo.upsert_position("FPT", total_qty=10, available_qty=10, avg_price=120000.0, highest_price=120000.0)

    # 15% stock dividend -> 10 * 1.15 = 11.5 shares.
    # round(11.5) = 12 (phantom share!). floor(11.5) = 11 shares, fractional = 0.50 shares.
    ev = CorporateEvent(
        id="fpt_div_15pct",
        symbol="FPT",
        ex_date=today_str,
        event_type=EventType.DIVIDEND_STOCK,
        content="Trả cổ tức bằng cổ phiếu tỷ lệ 15%"
    )
    state.set_corporate_events([ev])

    from indicators.models import TechnicalSummary
    state.update_summary("FPT", TechnicalSummary(
        symbol="FPT", price=104500.0, change=150.0, change_pct=0.1,
        open=104300.0, high=105000.0, low=104000.0, volume=1000000, vol_sma20=800000.0,
        vol_ratio=1.2, ema9=104000.0, ema21=102000.0, ema50=100000.0, rsi14=55.0,
        macd=100.0, macd_signal=50.0, macd_hist=50.0, bb_upper=110000.0,
        bb_middle=104000.0, bb_lower=98000.0, atr14=2000.0, trend="UPTREND",
        rsi_status="NEUTRAL", macd_status="BULLISH", composite_signal="TRUNG LẬP"
    ))

    alerts = await autotrader.process_cycle()
    pos = await repo.get_position("FPT")

    # MUST be floored to 11, NOT 12!
    assert pos.total_quantity == 11
    # Check that alert mentions fractional 0.50 share
    assert any("0.50" in n and "chi trả bằng tiền mặt" in n for n in notifications)

@pytest.mark.asyncio
async def test_live_trader_reconciles_positions_with_dnse(tmp_path):
    from unittest.mock import AsyncMock
    from dnse.models import PositionItem
    from strategy.live_trader import LiveTrader
    from core.risk_safeguards import RiskSafeguards, TradingMode

    db_file = str(tmp_path / "test_reconcile.db")
    await init_db(db_file)
    repo = PaperTradingRepository(db_file)

    # Local position: 1000 shares @ 120,000đ
    await repo.upsert_position("FPT", total_qty=1000, available_qty=1000, avg_price=120000.0, highest_price=125000.0)

    # Mock DNSE client returning adjusted position from exchange
    mock_client = AsyncMock()
    mock_client.get_positions.return_value = [
        PositionItem(
            symbol="FPT",
            accountNo="088C123456",
            openQuantity=1150,
            tradeQuantity=1000,
            costPrice=104348.0,
            marketPrice=105000.0
        )
    ]

    safeguards = RiskSafeguards(mode=TradingMode.LIVE_CONFIRM)
    notifications = []
    async def mock_notify(msg: str):
        notifications.append(msg)

    live_trader = LiveTrader(
        client=mock_client,
        safeguards=safeguards,
        account_no="088C123456",
        notify_func=mock_notify
    )

    # Run reconciliation
    alerts = await live_trader.reconcile_positions(repo)

    # Verify reconciliation detected discrepancy and synchronized to DNSE
    assert len(alerts) == 1
    assert "ĐỐI CHIẾU VỊ THẾ SÀN DNSE" in alerts[0]
    assert "1,150" in alerts[0]
    assert "104,348" in alerts[0]

    # Check local repo was synchronized
    synced_pos = await repo.get_position("FPT")
    assert synced_pos.total_quantity == 1150
    assert synced_pos.available_quantity == 1000
    assert synced_pos.avg_buy_price == 104348.0


