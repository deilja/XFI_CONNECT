"""Read-only periodic audit for XFI CONNECT.

The auditor never writes files or executes commands. Findings are returned as
structured data so Telegram/UI layers can turn them into approval-gated tasks.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuditFinding:
    severity: str
    path: str
    title: str
    detail: str


@dataclass(frozen=True)
class AuditReport:
    files_scanned: int
    findings: tuple[AuditFinding, ...]
    fingerprint: str


class RepositoryAuditor:
    EXCLUDED = {".git", ".venv", "venv", "node_modules", "data", "logs", "__pycache__"}
    MAX_FILE = 512 * 1024

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _files(self):
        for path in self.root.rglob("*.py"):
            if any(part in self.EXCLUDED for part in path.parts):
                continue
            try:
                if path.stat().st_size <= self.MAX_FILE:
                    yield path
            except OSError:
                continue

    def audit(self) -> AuditReport:
        findings: list[AuditFinding] = []
        scanned = 0
        for path in self._files():
            scanned += 1
            rel = str(path.relative_to(self.root))
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=rel)
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                findings.append(AuditFinding("high", rel, "Не удалось разобрать Python-файл", type(exc).__name__))
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not ast.get_docstring(node):
                    if not node.name.startswith("_"):
                        findings.append(AuditFinding("low", rel, "Публичная функция без docstring", node.name))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "eval":
                    findings.append(AuditFinding("high", rel, "Найден eval()", "Проверить необходимость динамического выполнения"))
        payload = "\n".join(f"{f.severity}|{f.path}|{f.title}|{f.detail}" for f in findings)
        fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return AuditReport(scanned, tuple(findings), fingerprint)
