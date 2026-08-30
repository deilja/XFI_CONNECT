"""Admin-facing AI provider key management facade."""
from __future__ import annotations

from bot.services.ai_key_store import AIKeyStore
from bot.services.ai_key_validation import AIKeyValidator
from bot.services.ai_provider_validators import build_validator

SUPPORTED_PROVIDERS = ("groq", "grok", "openai")


class AIKeyManager:
    def __init__(self, store: AIKeyStore, validator: AIKeyValidator | None = None):
        self.store = store
        self.validator = validator or build_validator()

    def providers(self) -> tuple[str, ...]:
        return SUPPORTED_PROVIDERS

    def configured(self) -> dict[str, bool]:
        return {provider: self.store.configured(provider) for provider in SUPPORTED_PROVIDERS}

    async def validate_and_set(self, provider: str, api_key: str) -> bool:
        provider = provider.strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError("Unsupported AI provider")
        valid = await self.validator.validate(provider, api_key)
        if not valid:
            return False
        self.store.set(provider, api_key)
        return True

    def delete(self, provider: str) -> None:
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError("Unsupported AI provider")
        self.store.delete(provider)
