from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    DNSE_API_KEY: str = Field(..., description="DNSE OpenAPI Key")
    DNSE_API_SECRET: str = Field(..., description="DNSE OpenAPI Secret")
    DNSE_ACCOUNT_ID: str = Field(..., description="Custody code, e.g. 064C551408")
    DNSE_SUB_ACCOUNT: str = Field("0001880229", description="Sub-account ID for trading")
    TELEGRAM_BOT_TOKEN: str = Field(..., description="Telegram Bot Token from BotFather")
    TELEGRAM_CHAT_ID: int = Field(..., description="Admin Telegram User ID for whitelist")
    DRY_RUN: bool = Field(False, description="Set True for offline mock testing")
    DB_PATH: str = Field("storage/bot.db", description="Path to local SQLite DB")
    LOG_LEVEL: str = Field("INFO", description="Logging level")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

def get_settings() -> Settings:
    return Settings()

settings = None
try:
    settings = get_settings()
except Exception:
    pass
