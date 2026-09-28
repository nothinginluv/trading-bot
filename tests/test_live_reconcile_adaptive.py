import pytest
import time
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta
from storage.db import init_db
from storage.repository import PaperTradingRepository
from strategy.paper_engine import PaperEngine
from strategy.auto_trader import AutoTrader
from strategy.live_trader import LiveTrader
from core.risk_safeguards import RiskSafeguards, TradingMode
from core.state import TradingState
from news.models import CorporateEvent, EventType
from dnse.models import PositionItem
from bot.handlers.portfolio import cmd_reconcile

@pytest.mark.asyncio
async def test_adaptive_interval_normal_vs_event_day(tmp_path):
    db_file = str(tmp_path / "test_reconcile_interval.db")
    await init_db(db_file)
    repo = PaperTradingRepository(db_file)
    await repo.upsert_position("FPT", total_qty=1000, available_qty=1000, avg_price=120000.0, highest_price=120000.0)

    mock_client = AsyncMock()
    mock_client.get_positions.return_value = [
        PositionItem(symbol="FPT", accountNo="088C123456", openQuantity=1000, tradeQuantity=1000, costPrice=120000.0)
    ]
    safeguards = RiskSafeguards(mode=TradingMode.LIVE_AUTO)
    live_trader = LiveTrader(client=mock_client, safeguards=safeguards, account_no="088C123456")

    # 1. First run: last_reconcile_time = 0.0 -> runs
    await live_trader.reconcile_positions(repo, has_active_events=False)
    assert mock_client.get_positions.call_count == 1
    first_time = live_trader.last_reconcile_time
    assert first_time > 0

    # 2. Immediate second run on normal day: interval is 3600s -> skipped
    await live_trader.reconcile_positions(repo, has_active_events=False)
    assert mock_client.get_positions.call_count == 1  # not called again

    # 3. Simulate 1900s passed (more than 30m=1800s, but less than 60m=3600s)
    live_trader.last_reconcile_time = time.time() - 1900.0

    # If has_active_events=False (normal day), 1900s < 3600s -> still skipped
    await live_trader.reconcile_positions(repo, has_active_events=False)
    assert mock_client.get_positions.call_count == 1

    # If has_active_events=True (event day), 1900s >= 1800s -> executes!
    await live_trader.reconcile_positions(repo, has_active_events=True)
    assert mock_client.get_positions.call_count == 2

    # 4. force=True bypasses any interval
    await live_trader.reconcile_positions(repo, force=True)
    assert mock_client.get_positions.call_count == 3


@pytest.mark.asyncio
async def test_paper_mode_reconciliation_read_only(tmp_path):
    db_file = str(tmp_path / "test_paper_reconcile.db")
    await init_db(db_file)
    repo = PaperTradingRepository(db_file)
    # Local position: 1000 shares @ 120,000đ
    await repo.upsert_position("SSI", total_qty=1000, available_qty=1000, avg_price=35000.0, highest_price=35000.0)

    # DNSE has different quantity
    mock_client = AsyncMock()
    mock_client.get_positions.return_value = [
        PositionItem(symbol="SSI", accountNo="088C123456", openQuantity=2000, tradeQuantity=2000, costPrice=30000.0)
    ]
    # PAPER mode
    safeguards = RiskSafeguards(mode=TradingMode.PAPER)
    live_trader = LiveTrader(client=mock_client, safeguards=safeguards, account_no="088C123456")

    # In PAPER mode, background non-forced reconciliation does nothing
    alerts = await live_trader.reconcile_positions(repo, force=False)
    assert alerts == []
    assert mock_client.get_positions.call_count == 0

    # In PAPER mode with force=True (manual command): reports discrepancy but does NOT overwrite paper repo!
    await live_trader.reconcile_positions(repo, force=True)
    assert mock_client.get_positions.call_count == 1
    assert len(live_trader.last_reconcile_report) == 1
    item = live_trader.last_reconcile_report[0]
    assert item["symbol"] == "SSI"
    assert item["discrepancy"] is True
    assert item["synchronized"] is False  # Must NOT synchronize in PAPER mode!

    # Verify paper repo was preserved
    pos = await repo.get_position("SSI")
    assert pos.total_quantity == 1000
    assert pos.avg_buy_price == 35000.0


@pytest.mark.asyncio
async def test_autotrader_detects_event_window(tmp_path):
    db_file = str(tmp_path / "test_autotrader_event_win.db")
    await init_db(db_file)
    repo = PaperTradingRepository(db_file)
    engine = PaperEngine(repo)
    state = TradingState()

    await repo.upsert_position("HPG", total_qty=500, available_qty=500, avg_price=28000.0, highest_price=28000.0)

    # Event tomorrow (Ex-Date +1 day window)
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    state.set_corporate_events([
        CorporateEvent(
            id="ev_hpg",
            symbol="HPG",
            ex_date=tomorrow_str,
            event_type=EventType.DIVIDEND_CASH,
            content="Trả cổ tức tiền mặt"
        )
    ])

    mock_live_trader = MagicMock()
    mock_live_trader.safeguards = None
    mock_live_trader.auto_cancel_stale_orders = AsyncMock(return_value=[])
    mock_live_trader.reconcile_positions = AsyncMock(return_value=[])

    autotrader = AutoTrader(engine=engine, state=state, live_trader=mock_live_trader)
    await autotrader.process_cycle()

    # Verify reconcile_positions was called with has_active_events=True
    mock_live_trader.reconcile_positions.assert_called_once()
    _, kwargs = mock_live_trader.reconcile_positions.call_args
    assert kwargs.get("has_active_events") is True


@pytest.mark.asyncio
async def test_cmd_reconcile_telegram_handler(tmp_path):
    db_file = str(tmp_path / "test_cmd_reconcile.db")
    await init_db(db_file)
    repo = PaperTradingRepository(db_file)
    await repo.upsert_position("TCB", total_qty=1000, available_qty=1000, avg_price=24000.0, highest_price=24000.0)

    mock_client = AsyncMock()
    mock_client.get_positions.return_value = [
        PositionItem(symbol="TCB", accountNo="088C123456", openQuantity=1000, tradeQuantity=1000, costPrice=24000.0)
    ]
    safeguards = RiskSafeguards(mode=TradingMode.LIVE_CONFIRM)
    live_trader = LiveTrader(client=mock_client, safeguards=safeguards, account_no="088C123456")

    mock_message = AsyncMock()
    mock_message.text = "/reconcile"

    await cmd_reconcile(
        message=mock_message,
        state_obj=TradingState(),
        client=mock_client,
        paper_repo=repo,
        live_trader=live_trader,
        safeguards=safeguards
    )

    # Check messages sent to Telegram
    assert mock_message.answer.call_count == 2
    progress_msg = mock_message.answer.call_args_list[0][0][0]
    assert "Đang đối chiếu" in progress_msg

    final_report = mock_message.answer.call_args_list[1][0][0]
    assert "BÁO CÁO ĐỐI CHIẾU VỊ THẾ" in final_report
    assert "TCB" in final_report
    assert "Khớp hoàn toàn 100%" in final_report
