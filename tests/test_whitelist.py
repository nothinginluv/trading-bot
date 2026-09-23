import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, User
from bot.middlewares import WhitelistMiddleware

@pytest.mark.asyncio
async def test_whitelist_allows_admin():
    middleware = WhitelistMiddleware(admin_id=7385637982)
    handler = AsyncMock(return_value="OK")
    
    event = MagicMock(spec=Message)
    event.from_user = MagicMock(spec=User)
    event.from_user.id = 7385637982
    
    result = await middleware(handler, event, {})
    assert result == "OK"
    handler.assert_awaited_once()

@pytest.mark.asyncio
async def test_whitelist_blocks_stranger():
    middleware = WhitelistMiddleware(admin_id=7385637982)
    handler = AsyncMock()
    
    event = MagicMock(spec=Message)
    event.from_user = MagicMock(spec=User)
    event.from_user.id = 999999999
    
    result = await middleware(handler, event, {})
    assert result is None
    handler.assert_not_awaited()
