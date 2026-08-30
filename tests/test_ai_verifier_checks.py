from pathlib import Path

import pytest

from bot.services.ai_verifier_checks import check_project_layout, check_python_syntax


@pytest.mark.asyncio
async def test_python_syntax_check(tmp_path: Path):
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    assert await check_python_syntax(tmp_path)
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    assert not await check_python_syntax(tmp_path)


@pytest.mark.asyncio
async def test_project_layout_check(tmp_path: Path):
    (tmp_path / "bot").mkdir()
    (tmp_path / "config.py").write_text("", encoding="utf-8")
    assert await check_project_layout(tmp_path)
