import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from jaguar.core.http_client import HttpClient, HttpClientConfig

@pytest.mark.asyncio
async def test_http_client_cookie_parsing_bool():
    config = HttpClientConfig()
    client = HttpClient(config)
    await client.start()
    
    # Mock the session and cookie_jar
    mock_cookie = MagicMock()
    mock_cookie.key = "test_cookie"
    mock_cookie.value = "test_value"
    
    def get_attr(key, default=""):
        if key == "secure":
            return True
        if key == "httponly":
            return True
        return default
        
    mock_cookie.get.side_effect = get_attr
    
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = "hello"
    mock_resp.history = []
    mock_resp.headers = {}
    mock_resp.url = "https://example.com"
    mock_resp.content_type = "text/html"
    
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_resp
    
    mock_session = MagicMock()
    mock_session.request = MagicMock(return_value=mock_ctx)
    
    # Patch cookie_jar as property
    type(mock_session).cookie_jar = PropertyMock(return_value=[mock_cookie])
    
    client._session = mock_session
    
    res = await client.get("https://example.com", use_cache=False)
    
    assert len(res.cookies) == 1
    assert res.cookies[0]["name"] == "test_cookie"
    assert res.cookies[0]["secure"] is True
    assert res.cookies[0]["httponly"] is True

@pytest.mark.asyncio
async def test_http_client_cookie_parsing_str():
    config = HttpClientConfig()
    client = HttpClient(config)
    await client.start()
    
    mock_cookie = MagicMock()
    mock_cookie.key = "test_cookie"
    mock_cookie.value = "test_value"
    
    def get_attr(key, default=""):
        if key == "secure":
            return "secure"
        if key == "httponly":
            return "HttpOnly"
        return default
        
    mock_cookie.get.side_effect = get_attr
    
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = "hello"
    mock_resp.history = []
    mock_resp.headers = {}
    mock_resp.url = "https://example.com"
    mock_resp.content_type = "text/html"
    
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_resp
    
    mock_session = MagicMock()
    mock_session.request = MagicMock(return_value=mock_ctx)
    type(mock_session).cookie_jar = PropertyMock(return_value=[mock_cookie])
    
    client._session = mock_session
    
    res = await client.get("https://example.com", use_cache=False)
    
    assert len(res.cookies) == 1
    assert res.cookies[0]["secure"] is True
    assert res.cookies[0]["httponly"] is True
