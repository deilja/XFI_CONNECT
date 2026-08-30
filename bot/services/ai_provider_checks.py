"""Authenticated health checks for supported AI providers."""
from __future__ import annotations

from openai import AsyncOpenAI


async def check_openai(api_key: str) -> bool:
    client = AsyncOpenAI(api_key=api_key)
    try:
        response = await client.models.list()
        return bool(getattr(response, "data", None))
    finally:
        await client.close()


async def check_groq(api_key: str) -> bool:
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    try:
        response = await client.models.list()
        return bool(getattr(response, "data", None))
    finally:
        await client.close()


async def check_grok(api_key: str) -> bool:
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
    try:
        response = await client.models.list()
        return bool(getattr(response, "data", None))
    finally:
        await client.close()
