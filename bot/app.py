from aiogram import Bot, Dispatcher
from bot.middlewares import WhitelistMiddleware
from bot.handlers import basic, portfolio, market, paper

def create_bot_app(settings, client, state, repo, paper_engine=None, paper_repo=None):
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    # Register dependency injection
    dp["state_obj"] = state
    dp["client"] = client
    dp["repo"] = repo
    dp["settings"] = settings
    dp["paper_engine"] = paper_engine
    dp["paper_repo"] = paper_repo

    # Security Whitelist Middleware
    dp.message.middleware(WhitelistMiddleware(admin_id=settings.TELEGRAM_CHAT_ID))
    dp.callback_query.middleware(WhitelistMiddleware(admin_id=settings.TELEGRAM_CHAT_ID))

    # Include routers
    dp.include_router(basic.router)
    dp.include_router(portfolio.router)
    dp.include_router(market.router)
    dp.include_router(paper.router)

    return bot, dp
