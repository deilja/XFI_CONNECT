"""Model inventory for AI provider selection and change detection."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Awaitable, Callable

ListModels = Callable[[str], Awaitable[list[str]]]


@dataclass(frozen=True)
class ModelInventory:
    provider: str
    models: tuple[str, ...]
    fingerprint: str
    healthy: bool = True


def fingerprint(models: list[str] | tuple[str, ...]) -> str:
    normalized = sorted({str(model).strip() for model in models if str(model).strip()})
    return hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()


class AIModelInventory:
    def __init__(self, providers: tuple[str, ...], list_models: ListModels):
        self.providers = providers
        self.list_models = list_models
        self.current: dict[str, ModelInventory] = {}

    async def refresh_provider(self, provider: str) -> ModelInventory:
        models = await self.list_models(provider)
        normalized = tuple(sorted({m.strip() for m in models if m and m.strip()}))
        inventory = ModelInventory(provider, normalized, fingerprint(normalized), bool(normalized))
        self.current[provider] = inventory
        return inventory

    async def refresh_all(self) -> dict[str, ModelInventory]:
        result = {}
        for provider in self.providers:
            try:
                result[provider] = await self.refresh_provider(provider)
            except Exception:
                result[provider] = ModelInventory(provider, (), fingerprint(()), False)
                self.current[provider] = result[provider]
        return result

    def models_for(self, provider: str) -> tuple[str, ...]:
        inventory = self.current.get(provider)
        return inventory.models if inventory else ()

    def available(self) -> dict[str, tuple[str, ...]]:
        return {p: i.models for p, i in self.current.items() if i.healthy}
