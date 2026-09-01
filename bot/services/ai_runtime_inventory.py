"""Adapter exposing only healthy, monitored providers/models to AI runtime."""
from __future__ import annotations


class MonitoredModelInventory:
    def __init__(self, monitor, default_models: dict[str, str] | None = None):
        self.monitor = monitor
        self.default_models = default_models or {}

    def available(self) -> dict[str, tuple[str, ...]]:
        result: dict[str, tuple[str, ...]] = {}
        for provider, state in self.monitor.state.items():
            if not state.enabled:
                continue
            models = tuple(state.models) or ((self.default_models.get(provider),) if self.default_models.get(provider) else ())
            if models:
                result[provider] = models
        return result
