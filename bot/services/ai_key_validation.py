"""Provider key validation with no key disclosure."""
from __future__ import annotations

from typing import Awaitable, Callable

Validator = Callable[[str], Awaitable[bool]]


class AIKeyValidator:
    def __init__(self):
        self._validators: dict[str, Validator] = {}

    def register(self, provider: str, validator: Validator) -> None:
        if provider in self._validators:
            raise ValueError(f"Validator already registered: {provider}")
        self._validators[provider] = validator

    async def validate(self, provider: str, api_key: str) -> bool:
        validator = self._validators.get(provider)
        if validator is None:
            raise ValueError(f"Unsupported AI provider: {provider}")
        return bool(await validator(api_key))
