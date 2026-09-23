import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat, User
from bot.handlers.paper import cmd_paper, cmd_signals, cmd_autotrade_paper, cmd_buy_paper
from strategy.paper_engine import PaperEngine
from storage.db import init_db
from storage.repository import PaperTradingRepository
from core.state import TradingState

@pytest.mark.asyncio
async def test_cmd_paper_dashboard(tmp_path):
    test_db = str(tmp_path / "test_bot_handlers.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo)
    await engine.initialize(5000000.0)
    state = TradingState()
    
    msg = MagicMock(spec=Message)
    msg.from_user = User(id=7385637982, is_bot=False, first_name="Admin")
    msg.chat = Chat(id=7385637982, type="private")
    msg.text = "/paper"
    msg.answer = AsyncMock()
    
    await cmd_paper(msg, engine, repo, state)
    msg.answer.assert_called_once()
    output_text = msg.answer.call_args[0][0]
    assert "TÀI KHOẢN GIẢ LẬP" in output_text
    assert "5,000,000" in output_text

@pytest.mark.asyncio
async def test_cmd_autotrade_toggle(tmp_path):
    test_db = str(tmp_path / "test_bot_handlers2.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo)
    await engine.initialize(5000000.0)
    
    msg = MagicMock(spec=Message)
    msg.text = "/autotrade_paper off"
    msg.answer = AsyncMock()
    
    await cmd_autotrade_paper(msg, repo)
    msg.answer.assert_called_once()
    assert "TẮT" in msg.answer.call_args[0][0]
    
    acc = await repo.get_or_create_account()
    assert acc.auto_trade_enabled is False

@pytest.mark.asyncio
async def test_cmd_buy_paper_odd_lot(tmp_path):
    test_db = str(tmp_path / "test_bot_handlers3.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo)
    await engine.initialize(5000000.0)
    state = TradingState()
    
    msg = MagicMock(spec=Message)
    msg.text = "/buy_paper FPT 15 130000"
    msg.answer = AsyncMock()
    
    await cmd_buy_paper(msg, engine, state)
    msg.answer.assert_called_once()
    assert "KHỚP LỆNH MUA" in msg.answer.call_args[0][0]
    assert "15" in msg.answer.call_args[0][0]
