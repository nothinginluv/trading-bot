import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message
from bot.handlers.market import cmd_quote, cmd_indicators, cmd_scan, cmd_vn30
from core.state import TradingState
from indicators.models import TechnicalSummary

def make_test_summary(symbol="FPT", price=66.6):
    return TechnicalSummary(
        symbol=symbol, price=price, change=1.2, change_pct=1.8, open=65.5, high=67.0, low=65.2,
        volume=4500000, vol_sma20=3200000, vol_ratio=1.4, ema9=65.8, ema21=64.5, ema50=62.0,
        rsi14=62.5, macd=0.8, macd_signal=0.5, macd_hist=0.3, bb_upper=68.0, bb_middle=64.5,
        bb_lower=61.0, atr14=1.2, trend="UPTREND", rsi_status="NEUTRAL", macd_status="BULLISH",
        composite_signal="MUA MẠNH"
    )

@pytest.mark.asyncio
async def test_quote_command():
    state = TradingState()
    state.set_market_data({}, {"FPT": make_test_summary("FPT")})
    
    msg = MagicMock(spec=Message)
    msg.text = "/quote FPT"
    msg.answer = AsyncMock()
    
    await cmd_quote(msg, state)
    assert msg.answer.called
    reply_text = msg.answer.call_args[0][0]
    assert "FPT" in reply_text
    assert "66.6" in reply_text

@pytest.mark.asyncio
async def test_indicators_command():
    state = TradingState()
    state.set_market_data({}, {"FPT": make_test_summary("FPT")})

    msg = MagicMock(spec=Message)
    msg.text = "/indicators FPT"
    msg.answer = AsyncMock()

    await cmd_indicators(msg, state)
    assert msg.answer.called
    reply_text = msg.answer.call_args[0][0]
    assert "FPT" in reply_text
    assert "RSI" in reply_text
    assert "MACD" in reply_text

@pytest.mark.asyncio
async def test_scan_command():
    state = TradingState()
    state.set_market_data({}, {"FPT": make_test_summary("FPT")})
    
    msg = MagicMock(spec=Message)
    msg.text = "/scan"
    msg.answer = AsyncMock()
    
    await cmd_scan(msg, state)
    assert msg.answer.called
    reply_text = msg.answer.call_args[0][0]
    assert "KẾT QUẢ QUÉT" in reply_text

@pytest.mark.asyncio
async def test_vn30_command():
    state = TradingState()
    state.set_market_data({}, {"FPT": make_test_summary("FPT", price=66.6)})

    msg = MagicMock(spec=Message)
    msg.text = "/vn30"
    msg.answer = AsyncMock()

    await cmd_vn30(msg, state)
    assert msg.answer.called
    reply_text = msg.answer.call_args[0][0]
    assert "BẢNG GIÁ VN30" in reply_text
