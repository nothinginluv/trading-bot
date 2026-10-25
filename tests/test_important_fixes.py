import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from core.market_hours import MarketHours
from strategy.paper_engine import get_next_business_day, PaperEngine
from core.state import TradingState
from dnse.models import AccountInfo, SubAccount
from bot.notifier import TelegramNotifier
from market.client import VN_TZ
from storage.db import init_db
from storage.repository import PaperTradingRepository


def test_safe_sub_account_id():
    state = TradingState()
    # 1. When state.account is None
    assert state.get_sub_account_id() == "0001880229"

    # 2. When state.account exists but accounts list is empty
    state.account = AccountInfo(name="Test", custodyCode="064C123", investorId="123", accounts=[])
    assert state.get_sub_account_id() == "0001880229"

    # 3. When custom fallback is passed
    assert state.get_sub_account_id(fallback="CUSTOM999") == "CUSTOM999"

    # 4. When sub-account exists
    state.account.accounts = [SubAccount(id="SUB001", dealAccount=True)]
    assert state.get_sub_account_id() == "SUB001"


def test_vietnam_holidays_and_market_hours():
    # 1. 2026-04-30 is Liberation Day holiday
    dt_holiday = datetime(2026, 4, 30, 10, 0)
    assert MarketHours.is_holiday(dt_holiday) is True
    assert MarketHours.get_session(dt_holiday) == "CLOSED"
    assert MarketHours.is_trading_time(dt_holiday) is False

    # 2. Business day calculation skipping holidays and weekend
    # 2026-04-29 is Wednesday. 30/4 & 1/5 are holidays, 2/5-3/5 are Sat-Sun -> Next business day must be Monday 2026-05-04!
    wednesday = datetime(2026, 4, 29)
    next_b_day = get_next_business_day(wednesday)
    assert next_b_day.strftime("%Y-%m-%d") == "2026-05-04"


def test_candle_timezone_vn():
    # Verify VN_TZ offset is UTC+7 (+25200 seconds)
    offset = VN_TZ.utcoffset(None)
    assert offset == timedelta(hours=7)

    # 17:00:00 UTC (which is 00:00:00 next day in VN)
    t = 1767200400  # 2026-01-01 00:00:00 VN time / 2025-12-31 17:00:00 UTC
    dt_vn = datetime.fromtimestamp(t, VN_TZ)
    assert dt_vn.strftime("%Y-%m-%d") == "2026-01-01"


@pytest.mark.asyncio
async def test_telegram_notifier_fallback_plain_text():
    mock_bot = AsyncMock()
    # First call with Markdown raises exception, second call without parse_mode succeeds
    mock_bot.send_message.side_effect = [Exception("can't parse entities"), None]

    notifier = TelegramNotifier(bot=mock_bot, chat_id=123456789)
    await notifier.send_alert("CẢNH BÁO", "Thông báo có ký tự đặc biệt: `MACD_HIST` và **[TEST]**")

    # Verify both calls were attempted
    assert mock_bot.send_message.call_count == 2
    # Verify fallback call does not use Markdown parse_mode
    fallback_call_args = mock_bot.send_message.call_args_list[1]
    assert "parse_mode" not in fallback_call_args.kwargs or fallback_call_args.kwargs.get("parse_mode") is None


@pytest.mark.asyncio
async def test_paper_engine_atomic_transaction(tmp_path):
    test_db = str(tmp_path / "test_atomic.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo)
    await engine.initialize(5000000.0)

    # Execute a buy order inside an atomic transaction
    order = await engine.execute_buy("HPG", 100, 25000.0)
    assert order.status.value == "FILLED"

    account = await repo.get_or_create_account()
    pos = await repo.get_position("HPG")
    assert pos is not None
    assert pos.total_quantity == 100
    assert account.cash_balance < 5000000.0


def test_rsi_flat_prices():
    import numpy as np
    from indicators.calculator import calculate_rsi
    # Flat series: price does not move across all periods
    flat_prices = np.full(30, 25000.0)
    rsi = calculate_rsi(flat_prices, period=14)
    # Must be neutral 50.0, NOT 100.0
    assert rsi[-1] == 50.0


def test_calculate_hose_collar():
    from core.risk_safeguards import calculate_hose_collar, RiskSafeguards
    # 1. Price < 10k: tick is 10
    floor, ceil = calculate_hose_collar(8500.0)
    assert floor == 7910.0  # 8500 * 0.93 = 7905 -> ceil to 7910
    assert ceil == 9090.0   # 8500 * 1.07 = 9095 -> floor to 9090

    # 2. 10k <= Price < 50k: tick is 50
    floor, ceil = calculate_hose_collar(26000.0)
    assert floor == 24200.0 # 26000 * 0.93 = 24180 -> ceil to 24200
    assert ceil == 27800.0  # 26000 * 1.07 = 27820 -> floor to 27800

    # 3. Price >= 50k: tick is 100
    floor, ceil = calculate_hose_collar(120000.0)
    assert floor == 111600.0 # 120000 * 0.93 = 111600 -> ceil to 111600
    assert ceil == 128400.0  # 120000 * 1.07 = 128400 -> floor to 128400

    # Validate with RiskSafeguards
    safeguards = RiskSafeguards()
    valid, _ = safeguards.validate_order("HPG", "NB", 100, 27800.0, 26000.0)
    assert valid is True
    valid_breach, msg = safeguards.validate_order("HPG", "NB", 100, 28000.0, 26000.0)
    assert valid_breach is False
    assert "vi phạm biên độ" in msg
