import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message
from bot.handlers.news import cmd_news
from core.state import TradingState
from news.models import NewsArticle

@pytest.mark.asyncio
async def test_cmd_news_general():
    state = TradingState()
    art1 = NewsArticle(
        id="art1",
        title="FPT ký hợp đồng AI bán dẫn quy mô lớn với đối tác Mỹ",
        link="https://cafef.vn/art1.chn",
        source="CafeF",
        related_symbols=["FPT"],
        sentiment_score=0.6,
        sentiment_label="POSITIVE"
    )
    art2 = NewsArticle(
        id="art2",
        title="Thị trường chứng khoán giằng co quanh vùng 1.280 điểm",
        link="https://vietstock.vn/art2.htm",
        source="Vietstock",
        related_symbols=["VNINDEX"],
        sentiment_score=0.0,
        sentiment_label="NEUTRAL"
    )
    state.set_news([art1, art2])

    msg = MagicMock(spec=Message)
    msg.text = "/news"
    msg.answer = AsyncMock()

    await cmd_news(msg, state)
    assert msg.answer.called
    reply = msg.answer.call_args[0][0]
    assert "TIN TỨC THỊ TRƯỜNG" in reply
    assert "FPT" in reply
    assert "CafeF" in reply
    assert "Vietstock" in reply

@pytest.mark.asyncio
async def test_cmd_news_symbol_lookup():
    state = TradingState()
    art = NewsArticle(
        id="hpg_news",
        title="Hòa Phát HPG vượt kế hoạch lợi nhuận năm trước 2 tháng",
        link="https://cafef.vn/hpg.chn",
        source="CafeF",
        related_symbols=["HPG"],
        sentiment_score=0.7,
        sentiment_label="POSITIVE"
    )
    state.set_news([art])

    msg = MagicMock(spec=Message)
    msg.text = "/news HPG"
    msg.answer = AsyncMock()

    await cmd_news(msg, state)
    assert msg.answer.called
    reply = msg.answer.call_args[0][0]
    assert "HPG" in reply
    assert "TÍCH CỰC" in reply or "+0.7" in reply
