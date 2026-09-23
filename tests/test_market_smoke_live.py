import pytest
from config.settings import settings
from storage.db import init_db
from storage.repository import Repository
from core.state import TradingState
from market.client import AsyncMarketClient
from indicators.calculator import compute_technical_summary
from indicators.scanner import scan_vn30_market
from bot.notifier import TelegramNotifier
from aiogram import Bot

@pytest.mark.asyncio
async def test_live_market_smoke_test(tmp_path):
    # 1. Init DB & Repo
    db_file = str(tmp_path / "smoke_market.db")
    await init_db(db_file)
    repo = Repository(db_file)
    state = TradingState()

    # 2. Query 3 representative VN30 stocks live from Entrade
    client = AsyncMarketClient()
    test_symbols = ["FPT", "HPG", "TCB"]
    candles_dict = await client.get_all_vn30_candles(test_symbols)
    
    assert len(candles_dict) == 3
    for s in test_symbols:
        series = candles_dict[s]
        assert len(series) > 0
        await repo.save_candles(s, series)

    # 3. Calculate indicators
    summaries = {}
    for s, series in candles_dict.items():
        summary = compute_technical_summary(series)
        assert summary is not None
        summaries[s] = summary

    state.set_market_data(candles_dict, summaries)
    assert state.get_summary("FPT") is not None

    # 4. Scan
    scan_results = scan_vn30_market(summaries)
    assert scan_results is not None

    # 5. Send Telegram live ping
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    notifier = TelegramNotifier(bot, settings.TELEGRAM_CHAT_ID)
    
    fpt_sum = summaries["FPT"]
    msg = (
        f"• **Mã cổ phiếu:** FPT\n"
        f"• **Thị giá:** `{fpt_sum.price:,.1f} đ` (`{fpt_sum.change_pct:+.2f}%`)\n"
        f"• **RSI (14):** `{fpt_sum.rsi14:.1f}` ({fpt_sum.rsi_status})\n"
        f"• **Xu hướng:** `{fpt_sum.trend}`\n"
        f"• **Tín hiệu:** `{fpt_sum.composite_signal}`\n"
        f"• **Trạng thái Phase 2:** 100% Sẵn sàng hoạt động!"
    )
    await notifier.send_alert("Kiểm Thử Dữ Liệu Thị Trường & Chỉ Báo", msg, level="INFO")

    await bot.session.close()
    await client.close()
