import pytest

from jaguar.core.http_client import HttpClient, HttpClientConfig


class FakeCookie:
    def __init__(self, key, value, attrs):
        self.key = key
        self.value = value
        self.attrs = attrs
    def get(self, k, default=""):
        return self.attrs.get(k, default)

class FakeResponse:
    def __init__(self):
        self.history = []
        self.url = "https://example.com"
        self.headers = {}
        self.status = 200
        self.content_type = "text/html"
    async def text(self, *args, **kwargs):
        return "hello"

class FakeContext:
    async def __aenter__(self):
        return FakeResponse()
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

class FakeSession:
    def __init__(self, cookies):
        self.cookie_jar = cookies
    def request(self, *args, **kwargs):
        return FakeContext()

@pytest.mark.asyncio
async def test_http_client_cookie_parsing_bool():
    config = HttpClientConfig()
    client = HttpClient(config)

    cookie = FakeCookie("test_cookie", "test_value", {"secure": True, "httponly": True})
    client._session = FakeSession([cookie])

    res = await client.get("https://example.com", use_cache=False)

    assert len(res.cookies) == 1
    assert res.cookies[0]["name"] == "test_cookie"
    assert res.cookies[0]["secure"] is True
    assert res.cookies[0]["httponly"] is True

@pytest.mark.asyncio
async def test_http_client_cookie_parsing_str():
    config = HttpClientConfig()
    client = HttpClient(config)

    cookie = FakeCookie("test_cookie", "test_value", {"secure": "secure", "httponly": "HttpOnly"})
    client._session = FakeSession([cookie])

    res = await client.get("https://example.com", use_cache=False)

    assert len(res.cookies) == 1
    assert res.cookies[0]["secure"] is True
    assert res.cookies[0]["httponly"] is True
