from config.settings import Settings
from config.constants import VN30_SYMBOLS, HOSE_HOURS

def test_settings_loaded():
    settings = Settings(
        DNSE_API_KEY="test_key",
        DNSE_API_SECRET="test_secret",
        DNSE_ACCOUNT_ID="064C551408",
        TELEGRAM_BOT_TOKEN="12345:ABCDE",
        TELEGRAM_CHAT_ID=7385637982,
        DRY_RUN=False
    )
    assert settings.DNSE_API_KEY == "test_key"
    assert settings.TELEGRAM_CHAT_ID == 7385637982
    assert len(VN30_SYMBOLS) == 30
    assert "HPG" in VN30_SYMBOLS
    assert HOSE_HOURS["morning_start"] == "09:00"
