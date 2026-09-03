import importlib

import pytest

import bot.services.xfi_ai_service as service


@pytest.mark.asyncio
async def test_xfi_ai_gateway_client(monkeypatch):
    monkeypatch.setenv("XFI_AI_API_KEY", "xfi_test_key")
    monkeypatch.setenv("XFI_AI_BASE_URL", "https://ai.example.test")

    importlib.reload(service)
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "Готово"}}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs["timeout"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setattr(service.httpx, "AsyncClient", FakeClient)
    result = await service.ask_xfi_ai("Как подключить VPN?")

    assert result == "Готово"
    assert captured["url"] == "https://ai.example.test/v1/chat/completions"
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer xfi_test_key"
    assert captured["kwargs"]["json"]["messages"][-1]["content"] == "Как подключить VPN?"


@pytest.mark.asyncio
async def test_xfi_ai_gateway_requires_key(monkeypatch):
    monkeypatch.delenv("XFI_AI_API_KEY", raising=False)

    importlib.reload(service)
    with pytest.raises(service.XFIAIError):
        await service.ask_xfi_ai("test")
