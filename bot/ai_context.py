"""Per-module AI context for XFI CONNECT.

The resolver gives the assistant a concise role and safety contract for the
file being discussed. It does not execute tools or mutate the repository.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_COMMON = """Project: deilja/XFI_CONNECT.
Source of truth: main branch.
Preserve existing behavior unless explicitly requested otherwise.
Never expose secrets. Never invent command/CI/runtime results.
Inspect callers and tests before changing public behavior.
Add regression tests for behavior changes.
Destructive, update and rollback operations require explicit authorization.
"""

_RULES = {
    "bot/services/xfi_update.py": "Canonical update/rollback transaction engine. Preserve locking, snapshots, Git identity checks, SQLite verification and recovery semantics.",
    "bot/services/update_rollback.py": "Compatibility façade only. Do not put new updater logic here; route through xfi_update.",
    "bot/services/xfi_health.py": "Post-update health verification. Treat crash loops and unstable systemd state as failure.",
    "bot/handlers/admin/system.py": "Telegram admin UI. Enforce existing admin authorization and delegate privileged work to services; do not implement shell/Git transactions inline.",
    "bot/services/ai_agent.py": "AI provider adapter. Keep project contract injection, provider isolation, secret safety and bounded history.",
    "bot/handlers/admin/ai_assistant.py": "AI interaction layer. Pass the relevant module context to the agent; do not grant the model implicit execution privileges.",
    "database/": "Database layer. Preserve schema compatibility, transactions and parameterized queries. Avoid destructive migrations without an explicit migration path.",
    "tests/": "Regression/integration tests. Prefer deterministic tests and mock external services, Git and systemd.",
    "config.py": "Runtime configuration and secrets. Never commit real credentials; preserve compatibility with config.py.example.",
    "install.sh": "Production installer. Must be idempotent, fail closed and keep XFI CONNECT identity; never resurrect legacy YadrenoVPN updater behavior.",
    ".github/": "CI and AI policy. CI must validate imports, syntax and tests without requiring production secrets.",
}


def context_for(path: str | Path) -> str:
    try:
        relative = Path(path).resolve().relative_to(ROOT).as_posix()
    except (ValueError, OSError):
        relative = str(path).replace("\\", "/")
    rule = "General XFI CONNECT module: preserve architecture and existing contracts."
    for prefix, value in _RULES.items():
        if relative == prefix or relative.startswith(prefix):
            rule = value
            break
    return f"{_COMMON}\nModule role: {rule}\nTarget path: {relative}"
