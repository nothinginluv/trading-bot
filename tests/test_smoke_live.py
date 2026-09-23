import pytest
from config.settings import settings
from storage.db import init_db
from storage.repository import Repository
from core.state import TradingState
from dnse.client import DNSEClient
from bot.notifier import TelegramNotifier
from aiogram import Bot

@pytest.mark.asyncio
async def test_live_smoke_startup(tmp_path):
    # 1. Init DB
    db_file = str(tmp_path / "test_smoke.db")
    await init_db(db_file)
    repo = Repository(db_file)
    
    # 2. Live DNSE Client
    client = DNSEClient(
        api_key=settings.DNSE_API_KEY,
        api_secret=settings.DNSE_API_SECRET
    )
    
    # 3. Fetch account
    accounts = await client.get_accounts()
    assert accounts.custodyCode == "064C551408"
    assert len(accounts.accounts) > 0
    
    sub_id = accounts.accounts[0].id
    bal = await client.get_balances(sub_id)
    pos = await client.get_positions(sub_id)
    
    # 4. Save to DB
    await repo.save_balance_snapshot(
        sub_id,
        bal.stock.totalCash,
        bal.stock.availableCash,
        bal.stock.totalDebt,
        bal.stock.withdrawableCash
    )
    
    latest = await repo.get_latest_snapshot(sub_id)
    assert latest is not None
    assert latest["account_no"] == sub_id
    assert latest["available_cash"] == bal.stock.availableCash
    
    # 5. Send Telegram live ping
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    notifier = TelegramNotifier(bot, settings.TELEGRAM_CHAT_ID)
    await notifier.send_alert(
        "Kiem thu Live Smoke Test",
        f"• Tai khoan: {accounts.name} ({accounts.custodyCode})\n• Tieu khoan: {sub_id}\n• Tien kha dung: {bal.stock.availableCash:,.0f} d\n• Trang thai: 100% San sang!",
        level="INFO"
    )
    
    await bot.session.close()
    await client.close()
