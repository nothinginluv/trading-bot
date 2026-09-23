import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
import os

from config.settings import settings
from storage.db import init_db
from storage.repository import Repository
from core.state import TradingState
from core.scheduler import setup_scheduler
from dnse.client import DNSEClient
from dnse.mock_client import MockDNSEClient
from bot.app import create_bot_app
from bot.notifier import TelegramNotifier
from core.market_hours import MarketHours
from market.client import AsyncMarketClient
from storage.repository import Repository, PaperTradingRepository
from strategy.paper_engine import PaperEngine
from strategy.auto_trader import AutoTrader

def setup_logging():
    os.makedirs("logs", exist_ok=True)
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler("logs/tradingbot.log", maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
    ]
    logging.basicConfig(level=settings.LOG_LEVEL, format=log_format, handlers=handlers)

async def main():
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("Initializing AI Auto Trading Bot (Phase 1: Read-Only MVP)...")

    # 1. Initialize SQLite Database
    await init_db(settings.DB_PATH)
    repo = Repository(settings.DB_PATH)
    await repo.log_audit("INFO", "SYSTEM", "Bot started on Windows machine")

    # 2. State & DNSE Client
    state = TradingState()
    if settings.DRY_RUN:
        logger.info("Running in DRY_RUN mode (Mock Client)")
        client = MockDNSEClient()
    else:
        logger.info("Connecting to LIVE DNSE OpenAPI...")
        client = DNSEClient(
            api_key=settings.DNSE_API_KEY,
            api_secret=settings.DNSE_API_SECRET
        )

    # Initial sync
    try:
        account_info = await client.get_accounts()
        state.set_account(account_info)
        logger.info(f"Connected to DNSE! Account: {account_info.name} ({account_info.custodyCode})")
        sub_id = account_info.accounts[0].id
        bal = await client.get_balances(sub_id)
        pos = await client.get_positions(sub_id)
        state.set_balance(bal)
        state.set_positions(pos)
        await repo.save_balance_snapshot(sub_id, bal.stock.totalCash, bal.stock.availableCash, bal.stock.totalDebt, bal.stock.withdrawableCash)
    except Exception as e:
        logger.error(f"Failed initial DNSE connection: {e}")
        await repo.log_audit("ERROR", "DNSE_API", f"Initial sync failed: {e}")

    # 3. Paper Trading Engine (Simulation with 5,000,000 VND)
    paper_repo = PaperTradingRepository(settings.DB_PATH)
    paper_engine = PaperEngine(paper_repo)
    await paper_engine.initialize(5_000_000.0)

    # 4. Telegram Bot
    bot, dp = create_bot_app(settings, client, state, repo, paper_engine=paper_engine, paper_repo=paper_repo)
    notifier = TelegramNotifier(bot, settings.TELEGRAM_CHAT_ID)

    # 5. Auto-Trader Service
    auto_trader = AutoTrader(
        engine=paper_engine,
        state=state,
        notify_func=lambda msg: notifier.send_alert("Tín Hiệu Auto-Trade Giả Lập", msg, level="INFO")
    )

    # 6. Background Scheduler & Market Client
    market_client = AsyncMarketClient()
    scheduler = setup_scheduler(client, state, repo, notifier, market_client=market_client, auto_trader=auto_trader)
    scheduler.start()

    # Trigger initial market sync in background
    from core.scheduler import sync_market_data_job
    asyncio.create_task(sync_market_data_job(market_client, state, repo, notifier, None, auto_trader))

    # 5. Startup Notification
    acc_name = state.account.name if state.account else 'Chưa kết nối'
    sub_id = state.account.accounts[0].id if (state.account and state.account.accounts) else 'N/A'
    custody = state.account.custodyCode if state.account else 'N/A'
    cash = state.balance.stock.availableCash if state.balance else 0
    session_text = MarketHours.get_session_display()
    
    await notifier.send_alert(
        "Hệ Thống Đã Khởi Động Thành Công",
        f"• **Máy chủ:** Windows Local PC\n"
        f"• **Chủ tài khoản:** {acc_name} (`{custody}`)\n"
        f"• **Tiểu khoản:** `{sub_id}`\n"
        f"• **Tiền khả dụng:** `{cash:,.0f} đ`\n"
        f"• **Phiên thị trường:** {session_text}\n"
        f"• **Chế độ:** READ_ONLY (An toàn vốn)",
        level="INFO"
    )

    # 6. Run Polling
    try:
        logger.info("Starting Telegram Bot Polling...")
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down...")
        scheduler.shutdown()
        await client.close()
        await market_client.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
