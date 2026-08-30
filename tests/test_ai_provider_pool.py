import time

import pytest

from bot.services.ai_provider_pool import AIProviderPool


class FakeStore:
    def __init__(self, keys):
        self.keys = keys

    def configured(self, provider):
        return provider in self.keys

    def get(self, provider):
        return self.keys.get(provider)


@pytest.mark.asyncio
async def test_pool_reports_configured_and_healthy():
    pool = AIProviderPool(FakeStore({"groq": "x", "openai": "y"}))
    assert pool.configured() == ("groq", "openai")
    assert pool.healthy() == ("groq", "openai")


def test_failure_enters_cooldown():
    pool = AIProviderPool(FakeStore({"groq": "x"}), cooldown_seconds=60)
    pool._failure("groq", RuntimeError("rate limit"))
    assert pool.healthy() == ()
    assert pool.states["groq"].last_error == "RuntimeError"
    pool.states["groq"].cooldown_until = time.monotonic() - 1
    assert pool.healthy() == ("groq",)
