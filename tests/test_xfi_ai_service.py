import importlib

import pytest

import bot.services.xfi_ai_service as service


@pytest.mark.asyncio
async def test_xfi_ai_gateway_client(monkeypatch, tmp_path):
    token_file = tmp_path / "xfi_token"
    token_file.write_text("xfi_test_key\n", encoding="utf-8")
    monkeypatch.setenv("XFI_AI_TOKEN_FILE", str(token_file))
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
async def test_xfi_ai_gateway_requires_key(monkeypatch, tmp_path):
    monkeypatch.setenv("XFI_AI_TOKEN_FILE", str(tmp_path / "missing"))
    monkeypatch.delenv("XFI_AI_API_KEY", raising=False)

    importlib.reload(service)
    with pytest.raises(service.XFIAIError):
        await service.ask_xfi_ai("test")


def test_save_gateway_token_is_atomic_and_private(monkeypatch, tmp_path):
    token_file = tmp_path / "nested" / "xfi_token"
    monkeypatch.setattr(service, "XFI_AI_TOKEN_FILE", token_file)

    service.save_gateway_token("xfi_test_token")

    assert token_file.read_text(encoding="utf-8") == "xfi_test_token\n"
    assert (token_file.stat().st_mode & 0o777) == 0o600
    assert not list(token_file.parent.glob("*.tmp"))
