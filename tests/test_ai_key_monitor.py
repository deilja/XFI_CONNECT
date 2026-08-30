import pytest

from bot.services.ai_key_monitor import AIKeyHealthMonitor


class Store:
    def __init__(self, values):
        self.values = values

    def get(self, provider):
        return self.values.get(provider)


@pytest.mark.asyncio
async def test_failed_provider_enters_cooldown():
    async def check(provider):
        return False

    monitor = AIKeyHealthMonitor(Store({"groq": "secret"}), ("groq",), check, cooldown=900)
    status = await monitor.check_provider("groq")
    assert not status.healthy
    assert not status.enabled
    assert monitor.available() == ()


@pytest.mark.asyncio
async def test_healthy_provider_is_available():
    async def check(provider):
        return True

    monitor = AIKeyHealthMonitor(Store({"openai": "secret"}), ("openai",), check)
    status = await monitor.check_provider("openai")
    assert status.healthy
    assert monitor.available() == ("openai",)
