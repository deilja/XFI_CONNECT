from pathlib import Path

from bot.services.ai_repo_auditor import RepositoryAuditor


def test_auditor_detects_syntax_and_eval(tmp_path: Path):
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "eval.py").write_text("def run():\n    return eval('1+1')\n", encoding="utf-8")
    report = RepositoryAuditor(tmp_path).audit()
    assert report.files_scanned == 2
    assert any(f.title == "Не удалось разобрать Python-файл" for f in report.findings)
    assert any(f.title == "Найден eval()" for f in report.findings)


def test_auditor_does_not_scan_excluded_dirs(tmp_path: Path):
    excluded = tmp_path / ".venv"
    excluded.mkdir()
    (excluded / "x.py").write_text("eval('1')", encoding="utf-8")
    report = RepositoryAuditor(tmp_path).audit()
    assert report.files_scanned == 0
