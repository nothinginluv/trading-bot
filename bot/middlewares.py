import logging
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)

class WhitelistMiddleware(BaseMiddleware):
    def __init__(self, admin_id: int):
        self.admin_id = admin_id

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = getattr(event, "from_user", None)
        if user and user.id == self.admin_id:
            return await handler(event, data)
        logger.warning(f"Unauthorized access attempt blocked from Telegram ID: {user.id if user else 'Unknown'}")
        return None
