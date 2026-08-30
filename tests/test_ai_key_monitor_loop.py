import pytest

from bot.services.ai_key_monitor import AIKeyHealthMonitor
from bot.services.ai_key_monitor_loop import AIKeyMonitorLoop


class Store:
    def __init__(self):
        self.value = "secret"

    def get(self, provider):
        return self.value


@pytest.mark.asyncio
async def test_run_once_notifies_on_health_transition():
    state = {"ok": True}
    events = []

    async def check(provider):
        return state["ok"]

    async def notify(message):
        events.append(message)

    monitor = AIKeyHealthMonitor(Store(), ("groq",), check)
    loop = AIKeyMonitorLoop(monitor, notify, interval=60)
    await loop.run_once()
    state["ok"] = False
    await loop.run_once()
    assert len(events) == 1
    assert "недоступен" in events[0]
