import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat, User, CallbackQuery
from core.risk_safeguards import RiskSafeguards, TradingMode
from dnse.mock_client import MockDNSEClient
from strategy.live_trader import LiveTrader
from core.state import TradingState
from bot.handlers.live import (
    cmd_mode,
    cmd_kill_switch,
    cmd_resume,
    cmd_buy_live,
    cmd_orders_live,
    cb_confirm_live
)

@pytest.mark.asyncio
async def test_cmd_mode_and_kill_switch():
    safeguards = RiskSafeguards()
    client = MockDNSEClient()
    state_obj = TradingState()

    msg = MagicMock(spec=Message)
    msg.from_user = User(id=7385637982, is_bot=False, first_name="Admin")
    msg.chat = Chat(id=7385637982, type="private")
    msg.answer = AsyncMock()

    # 1. Check mode command without args
    msg.text = "/mode"
    await cmd_mode(msg, safeguards)
    assert "CHẾ ĐỘ GIAO DỊCH" in msg.answer.call_args[0][0]

    # 2. Switch mode to live_confirm
    msg.text = "/mode live_confirm"
    await cmd_mode(msg, safeguards)
    assert safeguards.mode == TradingMode.LIVE_CONFIRM

    # 3. Kill Switch command
    await cmd_kill_switch(msg, safeguards, client, state_obj)
    assert safeguards.kill_switch_active is True
    assert "CẦU DAO KHẨN CẤP" in msg.answer.call_args[0][0]

    # 4. Resume command
    await cmd_resume(msg, safeguards)
    assert safeguards.kill_switch_active is False
    assert "ĐÃ KHÔI PHỤC" in msg.answer.call_args[0][0]

    await client.close()

@pytest.mark.asyncio
async def test_cmd_buy_live_and_confirm():
    safeguards = RiskSafeguards()
    safeguards.set_mode(TradingMode.LIVE_CONFIRM)
    client = MockDNSEClient()
    state_obj = TradingState()
    notifier = AsyncMock()
    live_trader = LiveTrader(client=client, safeguards=safeguards, account_no="0001880229", notify_func=notifier)

    msg = MagicMock(spec=Message)
    msg.from_user = User(id=7385637982, is_bot=False, first_name="Admin")
    msg.chat = Chat(id=7385637982, type="private")
    msg.answer = AsyncMock()

    # Place buy live order -> triggers PENDING_CONFIRMATION in LIVE_CONFIRM mode
    msg.text = "/buy_live HPG 100 26000"
    await cmd_buy_live(msg, live_trader, state_obj)
    assert len(live_trader.pending_confirmations) == 1
    confirm_id = list(live_trader.pending_confirmations.keys())[0]

    # Simulate CallbackQuery for confirmation
    query = MagicMock(spec=CallbackQuery)
    query.from_user = User(id=7385637982, is_bot=False, first_name="Admin")
    query.data = f"confirm_live:{confirm_id}"
    query.message = msg
    query.answer = AsyncMock()

    await cb_confirm_live(query, live_trader)
    assert len(live_trader.pending_confirmations) == 0

    # Orders book check
    msg.text = "/orders_live"
    await cmd_orders_live(msg, client, state_obj)
    assert msg.answer.called

    await client.close()
