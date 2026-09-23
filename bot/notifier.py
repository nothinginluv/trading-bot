import logging
from aiogram import Bot

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, bot: Bot, chat_id: int):
        self.bot = bot
        self.chat_id = chat_id

    async def send_alert(self, title: str, message: str, level: str = "INFO"):
        icon = "ℹ️" if level == "INFO" else ("⚠️" if level == "WARNING" else "🚨")
        text = f"{icon} **{title}**\n──────────────────────\n{message}"
        try:
            await self.bot.send_message(self.chat_id, text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
