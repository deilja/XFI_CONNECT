"""Minimal provider validators used before storing an API key."""
from __future__ import annotations

from openai import AsyncOpenAI

from bot.services.ai_key_validation import AIKeyValidator


async def _validate_groq(key: str) -> bool:
    client = AsyncOpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
    response = await client.models.list()
    return bool(getattr(response, "data", None))


async def _validate_grok(key: str) -> bool:
    client = AsyncOpenAI(api_key=key, base_url="https://api.x.ai/v1")
    response = await client.models.list()
    return bool(getattr(response, "data", None))


async def _validate_openai(key: str) -> bool:
    client = AsyncOpenAI(api_key=key)
    response = await client.models.list()
    return bool(getattr(response, "data", None))


def build_validator() -> AIKeyValidator:
    validator = AIKeyValidator()
    validator.register("groq", _validate_groq)
    validator.register("grok", _validate_grok)
    validator.register("openai", _validate_openai)
    return validator
