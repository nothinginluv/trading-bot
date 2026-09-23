from aiogram import Bot, Dispatcher
from bot.middlewares import WhitelistMiddleware
from bot.handlers import basic, portfolio

def create_bot_app(settings, client, state, repo):
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    # Register dependency injection
    dp["state_obj"] = state
    dp["client"] = client
    dp["repo"] = repo
    dp["settings"] = settings

    # Security Whitelist Middleware
    dp.message.middleware(WhitelistMiddleware(admin_id=settings.TELEGRAM_CHAT_ID))
    dp.callback_query.middleware(WhitelistMiddleware(admin_id=settings.TELEGRAM_CHAT_ID))

    # Include routers
    dp.include_router(basic.router)
    dp.include_router(portfolio.router)

    return bot, dp
