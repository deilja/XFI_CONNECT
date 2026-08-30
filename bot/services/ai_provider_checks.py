"""Authenticated health and model inventory checks for AI providers."""
from __future__ import annotations

from openai import AsyncOpenAI


async def _models(client: AsyncOpenAI) -> list[str]:
    try:
        response = await client.models.list()
        return [item.id for item in getattr(response, "data", []) if getattr(item, "id", None)]
    finally:
        await client.close()


async def list_openai_models(api_key: str) -> list[str]:
    return await _models(AsyncOpenAI(api_key=api_key))


async def list_groq_models(api_key: str) -> list[str]:
    return await _models(AsyncOpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1"))


async def list_grok_models(api_key: str) -> list[str]:
    return await _models(AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1"))


async def check_openai(api_key: str) -> bool:
    return bool(await list_openai_models(api_key))


async def check_groq(api_key: str) -> bool:
    return bool(await list_groq_models(api_key))


async def check_grok(api_key: str) -> bool:
    return bool(await list_grok_models(api_key))
