"""Built-in async checks for the AI verification pipeline.

Checks are deliberately bounded and do not execute model-supplied commands.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path


async def check_python_syntax(root: str | Path) -> bool:
    project = Path(root).resolve()
    files = list(project.rglob("*.py"))
    files = [p for p in files if ".venv" not in p.parts and "venv" not in p.parts and ".git" not in p.parts]
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            return False
    return True


async def check_required_imports(modules: tuple[str, ...]) -> bool:
    for module in modules:
        try:
            importlib.import_module(module)
        except Exception:
            return False
    return True


async def check_project_layout(root: str | Path) -> bool:
    project = Path(root).resolve()
    return (project / "bot").is_dir() and (project / "config.py").is_file()
