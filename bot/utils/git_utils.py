"""Git compatibility API backed by the XFI CONNECT update engine.

This module contains no legacy updater implementation. Public helpers are
retained because existing handlers/extensions import them.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Dict, List, Optional, Tuple

from bot.services.xfi_update import (
    BRANCH,
    REPOSITORY,
    SERVICE_NAME,
    UpdateRollbackError,
    _checked,
    _commit,
    _root,
    _run,
    create_pre_update_snapshot,
    discard_prepared_snapshot,
    finalize_snapshot_after_git,
    update_operation_lock,
)
from bot.services.xfi_health import schedule_post_update_check


def get_project_root() -> str:
    return str(_root())


def run_git_command(args: List[str], timeout: int = 30) -> Tuple[bool, str]:
    try:
        result = _run(["git", *args], _root(), timeout)
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except Exception as exc:
        return False, str(exc)


def check_git_available() -> bool:
    return run_git_command(["--version"])[0]


def get_current_commit(*, full: bool = False) -> Optional[str]:
    try:
        commit = _commit(_root())
        return commit if full else commit[:8]
    except Exception:
        return None


def get_current_branch() -> Optional[str]:
    success, output = run_git_command(["branch", "--show-current"])
    return output if success else None


def get_remote_url() -> Optional[str]:
    success, output = run_git_command(["remote", "get-url", "origin"])
    return output if success else None


def set_remote_url(url: str) -> Tuple[bool, str]:
    """Compatibility API: only accept the canonical XFI CONNECT origin."""
    normalized = (url or "").strip().lower().rstrip("/")
    normalized = normalized[:-4] if normalized.endswith(".git") else normalized
    allowed = (
        "https://github.com/deilja/xfi_connect",
        "git@github.com:deilja/xfi_connect",
    )
    if normalized not in allowed:
        return False, f"origin must remain {REPOSITORY}"
    return run_git_command(["remote", "set-url", "origin", url])


def get_pending_commits_list() -> Tuple[bool, List[Dict[str, str]]]:
    root = _root()
    try:
        _checked(["git", "fetch", "--prune", "origin", BRANCH], root,
                 stage="Fetching XFI CONNECT", timeout=120)
        result = _run(["git", "log", f"HEAD..origin/{BRANCH}", "--format=%H|%s", "--reverse"], root, 30)
        if result.returncode:
            return False, []
        commits: List[Dict[str, str]] = []
        for line in result.stdout.splitlines():
            if "|" in line:
                commit, message = line.split("|", 1)
                commits.append({"hash": commit.strip(), "message": message.strip()})
        return True, commits
    except Exception:
        return False, []


def find_first_blocking_commit(commits: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    for commit in commits:
        if commit.get("message", "").startswith("!"):
            return commit
    return None


def _guard_message() -> Optional[str]:
    try:
        from bot.services.yadreno_admin_core_guard import is_repository_guard_active
        if is_repository_guard_active():
            return "❌ Обновление временно недоступно: защищённая операция ещё выполняется."
    except ImportError:
        pass
    return None


def _apply_target(target: str, *, mode: str, actor: Optional[str]) -> Tuple[bool, str]:
    root = _root()
    blocked = _guard_message()
    if blocked:
        return False, blocked
    try:
        with update_operation_lock(root):
            status = _checked(["git", "status", "--porcelain"], root,
                              stage="Checking worktree", timeout=30)
            if status.strip():
                return False, "❌ Есть локальные изменения. Сделайте commit или stash перед обновлением."
            source = _commit(root)
            snapshot = create_pre_update_snapshot(
                update_mode=mode,
                requested_target=target,
                actor=actor,
                project_root=root,
            )
            try:
                _checked(["git", "reset", "--hard", target], root,
                         stage="Applying XFI CONNECT update", timeout=120)
                try:
                    _checked(
                        [sys.executable, "-m", "pip", "install", "--upgrade", "-r", str(root / "requirements.txt")],
                        root, stage="Installing XFI CONNECT dependencies", timeout=600,
                    )
                except Exception:
                    _checked(["git", "reset", "--hard", source], root,
                             stage="Recovering failed update", timeout=120)
                    discard_prepared_snapshot(snapshot.snapshot_id, project_root=root)
                    raise
                if not finalize_snapshot_after_git(snapshot, git_succeeded=True, project_root=root):
                    raise UpdateRollbackError("XFI update did not change the installed commit")

                health_ok, health_unit = schedule_post_update_check(
                    snapshot.snapshot_id,
                    service_name=SERVICE_NAME,
                    project_root=root,
                    settle_seconds=20,
                )
                if not health_ok:
                    return False, f"❌ Обновление установлено, но health-check worker не запущен: {health_unit}"

                info = get_last_commit_info("HEAD")
                return (
                    True,
                    f"✅ XFI CONNECT обновлён.\n\n<pre>{info}</pre>\n"
                    f"Health-check: <code>{health_unit}</code>\n"
                    "При неудачном старте будет выполнен автоматический rollback.",
                )
    except UpdateRollbackError as exc:
        return False, f"❌ Обновление остановлено: {exc}"
    except Exception as exc:
        return False, f"❌ Ошибка обновления: {exc}"


def pull_to_commit(commit_hash: str, *, update_mode: str = "admin_target_commit", actor: Optional[str] = None) -> Tuple[bool, str]:
    if not isinstance(commit_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit_hash):
        return False, "❌ Некорректный идентификатор коммита"
    root = _root()
    if _run(["git", "cat-file", "-e", f"{commit_hash}^{{commit}}"], root, 30).returncode != 0:
        run_git_command(["fetch", "--prune", "origin", BRANCH], 120)
    if _run(["git", "cat-file", "-e", f"{commit_hash}^{{commit}}"], root, 30).returncode != 0:
        return False, "❌ Целевой коммит недоступен локально"
    return _apply_target(commit_hash, mode=update_mode, actor=actor)


def pull_updates(*, update_mode: str = "admin_pull", actor: Optional[str] = None) -> Tuple[bool, str]:
    root = _root()
    try:
        _checked(["git", "fetch", "--prune", "origin", BRANCH], root,
                 stage="Fetching XFI CONNECT", timeout=120)
        target = _checked(["git", "rev-parse", f"origin/{BRANCH}"], root,
                          stage="Resolving XFI target", timeout=30).splitlines()[0].strip()
    except Exception as exc:
        return False, f"❌ Не удалось получить XFI CONNECT: {exc}"
    return _apply_target(target, mode=update_mode, actor=actor)


def force_pull_updates(*, update_mode: str = "admin_force", actor: Optional[str] = None) -> Tuple[bool, str]:
    return pull_updates(update_mode=update_mode, actor=actor)


def check_for_updates() -> Tuple[bool, int, str, bool, Optional[Dict[str, str]], bool]:
    success, commits = get_pending_commits_list()
    if not success:
        return False, 0, "❌ Не удалось проверить XFI CONNECT", False, None, False
    if not commits:
        return True, 0, "✅ XFI CONNECT уже обновлён", False, None, False
    blocking = find_first_blocking_commit(commits)
    beta_only = all(c.get("message", "").startswith("?") for c in commits)
    lines = [f"📦 Доступно обновлений: {len(commits)}", "", "Последние изменения:"]
    lines.extend(f"{c['hash'][:8]} {c['message']}" for c in commits[-10:])
    return True, len(commits), "\n".join(lines), blocking is not None, blocking, beta_only


def get_last_commit_info(revision: str = "HEAD") -> str:
    success, output = run_git_command(["log", "--format=%h %s", "-n", "1", revision])
    return output if success and output else "Не удалось получить информацию о последнем коммите"


def get_previous_commits_info(limit: int = 5, revision: str = "HEAD") -> str:
    success, output = run_git_command(["log", "--format=%h %s", "--skip=1", "-n", str(limit), revision])
    return output if success and output else "Нет предыдущих коммитов"


def install_requirements() -> Tuple[bool, str]:
    root = _root()
    requirements = root / "requirements.txt"
    if not requirements.is_file():
        return False, "❌ requirements.txt отсутствует"
    try:
        _checked([sys.executable, "-m", "pip", "install", "--upgrade", "-r", str(requirements)], root,
                 stage="Installing dependencies", timeout=600)
        return True, "✅ Зависимости обновлены"
    except Exception as exc:
        return False, f"❌ Ошибка установки зависимостей: {exc}"


def restart_bot() -> None:
    os.execv(sys.executable, [sys.executable, str(_root() / "main.py")])
