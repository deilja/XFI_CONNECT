import pytest

from bot.services.ai_key_autodiscovery import ProviderProbe, autodetect_provider


@pytest.mark.asyncio
async def test_unknown_key_is_not_persisted_or_identified(monkeypatch):
    async def fake_probe(probe, api_key, timeout=8.0):
        return probe.provider == "groq"

    monkeypatch.setattr("bot.services.ai_key_autodiscovery.probe_api_key", fake_probe)
    assert await autodetect_provider("gsk_" + "x" * 30) == "groq"


@pytest.mark.asyncio
async def test_ambiguous_match_fails_closed(monkeypatch):
    async def fake_probe(probe, api_key, timeout=8.0):
        return True

    monkeypatch.setattr("bot.services.ai_key_autodiscovery.probe_api_key", fake_probe)
    assert await autodetect_provider("sk-" + "x" * 30) is None
