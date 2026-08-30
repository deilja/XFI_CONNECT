"""Fixed, application-owned verification suite for AI changes.

The model never supplies commands. Every executable check is hard-coded here.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from bot.services.ai_verifier import VerificationPipeline
from bot.services.xfi_health import SERVICE_NAME, verify_service


DEFAULT_IMPORTS = (
    "main",
    "bot.services.ai_agent",
    "bot.services.ai_autopilot",
    "bot.services.ai_changeset",
    "bot.services.ai_executor",
    "bot.services.ai_verifier",
    "bot.services.xfi_update",
    "bot.services.xfi_health",
)


def _run_fixed(args: list[str], root: Path, timeout: int) -> bool:
    try:
        result = subprocess.run(
            args,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


async def build_production_verifier(root: str | Path, *, include_service_health: bool = True):
    project = Path(root).resolve()
    pipeline = VerificationPipeline()

    async def syntax() -> bool:
        from bot.services.ai_verifier_checks import check_python_syntax
        return await check_python_syntax(project)

    async def imports() -> bool:
        from bot.services.ai_verifier_checks import check_required_imports
        return await check_required_imports(DEFAULT_IMPORTS)

    async def tests() -> bool:
        return await asyncio.to_thread(_run_fixed, [sys.executable, "-m", "pytest", "-q"], project, 300)

    async def ruff() -> bool:
        return await asyncio.to_thread(_run_fixed, [sys.executable, "-m", "ruff", "check", "."], project, 180)

    pipeline.register("python-syntax", syntax)
    pipeline.register("required-imports", imports)
    pipeline.register("pytest", tests)
    pipeline.register("ruff", ruff)

    if include_service_health:
        async def service_health() -> bool:
            return await asyncio.to_thread(verify_service, SERVICE_NAME, project_root=project, settle_seconds=10)
        pipeline.register("xfi-connect-health", service_health)

    async def verify(_plan) -> bool:
        ok, _ = await pipeline.run()
        return ok

    return verify, pipeline
