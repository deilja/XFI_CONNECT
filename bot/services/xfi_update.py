"""Transactional updater/rollback engine for XFI CONNECT.

The updater is intentionally repository-bound: it can operate only on
``deilja/XFI_CONNECT`` and only on the configured ``main`` branch.  It keeps
SQLite and Git changes in one recoverable transaction and never accepts an
arbitrary remote URL or shell command from the administrator UI.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

logger = logging.getLogger(__name__)

REPOSITORY = "deilja/XFI_CONNECT"
BRANCH = "main"
REMOTE_NAME = "origin"
SERVICE_NAME = "xfi-connect"
SNAPSHOT_ROOT = "backup/pre_update"
SNAPSHOT_FORMAT = 2
MAX_ROLLBACK_POINTS = 3
RETENTION_DAYS = 7
DB_NAME = "vpn_bot.db"
MANIFEST_NAME = "manifest.json"
RUNNER_NAME = "rollback_runner.py"
RESULT_NAME = "rollback_result.json"
LOCK_NAME = ".operation.lock"
UNKNOWN_RELEASE = "unknown"
HASH_RE = re.compile(r"^[0-9a-f]{40,64}$", re.I)
SNAPSHOT_RE = re.compile(r"^[0-9]{8}T[0-9]{12}Z_[0-9a-f]{8}$", re.I)


class UpdateRollbackError(RuntimeError):
    """A fail-closed update/rollback error."""


@dataclass(frozen=True)
class PreparedSnapshot:
    snapshot_id: str
    snapshot_dir: Path
    source_commit: str
    source_release: str


@dataclass(frozen=True)
class RollbackPoint:
    snapshot_id: str
    snapshot_dir: Path
    manifest_path: Path
    database_path: Path
    created_at: datetime
    source_release: str
    source_commit: str
    source_short_commit: str
    applied_commit: str
    applied_release: str
    update_mode: str

    @property
    def display_release(self) -> str:
        return (
            f"Версия {self.source_release}"
            if self.source_release != UNKNOWN_RELEASE
            else "Версия не определена"
        )


@dataclass(frozen=True)
class RollbackExecutionResult:
    success: bool
    message: str
    recovered: bool = False


def _root(project_root: str | Path | None = None) -> Path:
    path = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    path = path.resolve()
    if not (path / ".git").is_dir():
        raise UpdateRollbackError(f"Git repository is missing: {path}")
    return path


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise UpdateRollbackError("Invalid snapshot timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UpdateRollbackError("Invalid snapshot timestamp") from exc
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _run(args: Sequence[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        return subprocess.run(
            list(args), cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, env=env,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise UpdateRollbackError(f"Command unavailable: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise UpdateRollbackError(f"Command timed out: {' '.join(args)}") from exc


def _checked(args: Sequence[str], cwd: Path, *, stage: str, timeout: int = 120) -> str:
    result = _run(args, cwd, timeout)
    output = (result.stdout + result.stderr).strip()
    if result.returncode:
        raise UpdateRollbackError(f"{stage} failed (exit {result.returncode}): {output or 'no output'}")
    return output


def _git(root: Path, args: Sequence[str], *, stage: str, timeout: int = 120) -> str:
    return _checked(["git", *args], root, stage=stage, timeout=timeout)


def _commit(root: Path) -> str:
    value = _git(root, ["rev-parse", "HEAD"], stage="Reading current commit").splitlines()[0].strip().lower()
    if not HASH_RE.fullmatch(value):
        raise UpdateRollbackError("Git returned an invalid commit hash")
    return value


def _subject(root: Path, revision: str) -> str:
    result = _run(["git", "show", "-s", "--format=%s", revision], root, 30)
    return result.stdout.strip() if result.returncode == 0 else ""


def _release(subject: str) -> str:
    match = re.match(r"^[!?]?\s*Версия\s+([0-9]+(?:\.[0-9]+)*)\b", subject or "", re.I)
    return match.group(1) if match else UNKNOWN_RELEASE


def get_current_version_identity(project_root: str | Path | None = None) -> tuple[str, str, str]:
    root = _root(project_root)
    commit = _commit(root)
    return _release(_subject(root, commit)), commit, commit[:8]


def _snapshot_root(root: Path) -> Path:
    return root / SNAPSHOT_ROOT


def _db(root: Path) -> Path:
    return root / "database" / DB_NAME


def _inside(path: Path, parent: Path) -> Path:
    resolved = path.resolve()
    base = parent.resolve()
    if resolved != base and base not in resolved.parents:
        raise UpdateRollbackError(f"Path escapes allowed directory: {resolved}")
    return resolved


def _snapshot_dir(root: Path, snapshot_id: str) -> Path:
    if not SNAPSHOT_RE.fullmatch(snapshot_id or ""):
        raise UpdateRollbackError("Invalid rollback snapshot identifier")
    raw = _snapshot_root(root)
    if raw.is_symlink():
        raise UpdateRollbackError("Rollback directory cannot be a symbolic link")
    return _inside(raw / snapshot_id, _inside(raw, root))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_db(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise UpdateRollbackError(f"SQLite backup is missing: {path}")
    try:
        with sqlite3.connect(str(path), timeout=30) as conn:
            row = conn.execute("PRAGMA quick_check").fetchone()
    except sqlite3.Error as exc:
        raise UpdateRollbackError(f"SQLite validation failed: {exc}") from exc
    if not row or row[0] != "ok":
        raise UpdateRollbackError("SQLite quick_check failed")


def _backup_db(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise UpdateRollbackError(f"Bot database is missing: {source}")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with sqlite3.connect(str(source), timeout=30) as src, sqlite3.connect(str(destination), timeout=30) as dst:
            src.backup(dst)
        _check_db(destination)
        destination.chmod(0o600)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as out:
            json.dump(payload, out, ensure_ascii=False, indent=2, sort_keys=True)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        tmp.chmod(0o600)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as source:
            data = json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise UpdateRollbackError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise UpdateRollbackError(f"Invalid JSON object: {path}")
    return data


def _manifest(snapshot: Path) -> dict[str, Any]:
    data = _read_json(snapshot / MANIFEST_NAME)
    if data.get("format_version") != SNAPSHOT_FORMAT or data.get("kind") != "xfi_pre_update":
        raise UpdateRollbackError("Unsupported XFI rollback manifest")
    if data.get("snapshot_id") != snapshot.name:
        raise UpdateRollbackError("Snapshot identifier mismatch")
    return data


def _point(root: Path, snapshot: Path, *, verify: bool = True) -> RollbackPoint:
    data = _manifest(snapshot)
    source = data.get("source")
    update = data.get("update")
    database = data.get("database")
    if not all(isinstance(x, dict) for x in (source, update, database)):
        raise UpdateRollbackError("Incomplete rollback manifest")
    if update.get("status") not in {"applied", "applied_with_errors"}:
        raise UpdateRollbackError("Snapshot is not an applied rollback point")
    source_commit = str(source.get("commit") or "").lower()
    applied_commit = str(update.get("applied_commit") or "").lower()
    if not HASH_RE.fullmatch(source_commit) or not HASH_RE.fullmatch(applied_commit):
        raise UpdateRollbackError("Invalid commit in rollback manifest")
    if str(source.get("short_commit") or "").lower() != source_commit[:8]:
        raise UpdateRollbackError("Invalid short commit in rollback manifest")
    if not _commit_exists(root, source_commit):
        raise UpdateRollbackError("Rollback commit is not available locally")
    if database.get("file") != DB_NAME:
        raise UpdateRollbackError("Invalid rollback database filename")
    db_path = _inside(snapshot / DB_NAME, snapshot)
    expected_size = database.get("size")
    expected_hash = database.get("sha256")
    if not isinstance(expected_size, int) or expected_size <= 0 or db_path.stat().st_size != expected_size:
        raise UpdateRollbackError("Rollback database size is invalid")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash, re.I):
        raise UpdateRollbackError("Rollback database checksum is invalid")
    runner = _inside(snapshot / RUNNER_NAME, snapshot)
    if not runner.is_file() or runner.is_symlink():
        raise UpdateRollbackError("Rollback runner is missing")
    if verify and (_sha256(db_path) != expected_hash):
        raise UpdateRollbackError("Rollback database checksum mismatch")
    if verify:
        _check_db(db_path)
    return RollbackPoint(
        snapshot_id=snapshot.name,
        snapshot_dir=snapshot,
        manifest_path=snapshot / MANIFEST_NAME,
        database_path=db_path,
        created_at=_parse_time(data.get("created_at")),
        source_release=str(source.get("release") or UNKNOWN_RELEASE),
        source_commit=source_commit,
        source_short_commit=source_commit[:8],
        applied_commit=applied_commit,
        applied_release=str(update.get("applied_release") or UNKNOWN_RELEASE),
        update_mode=str(update.get("mode") or "unknown"),
    )


def _commit_exists(root: Path, commit: str) -> bool:
    if not HASH_RE.fullmatch(commit or ""):
        return False
    return _run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], root, 30).returncode == 0


def _origin_is_xfi(root: Path) -> bool:
    result = _run(["git", "remote", "get-url", REMOTE_NAME], root, 30)
    if result.returncode != 0:
        return False
    remote = result.stdout.strip().lower().rstrip("/")
    remote = re.sub(r"\.git$", "", remote)
    return remote.endswith("github.com/deilja/xfi_connect") or remote.endswith("github.com:deilja/xfi_connect")


def ensure_repository(root: Path) -> None:
    if not _origin_is_xfi(root):
        raise UpdateRollbackError(
            "origin не указывает на deilja/XFI_CONNECT; автоматическая замена remote запрещена"
        )
    branch = _git(root, ["branch", "--show-current"], stage="Reading branch", timeout=30).strip()
    if branch and branch != BRANCH:
        raise UpdateRollbackError(f"Updater supports only branch {BRANCH!r}, current branch is {branch!r}")


def _clean_worktree(root: Path) -> None:
    status = _git(root, ["status", "--porcelain"], stage="Checking worktree", timeout=30)
    if status.strip():
        raise UpdateRollbackError("Рабочая копия содержит локальные изменения; обновление остановлено")


@contextmanager
def update_operation_lock(project_root: str | Path | None = None) -> Iterator[None]:
    root = _root(project_root)
    lock_root = _snapshot_root(root)
    if lock_root.is_symlink():
        raise UpdateRollbackError("Rollback directory cannot be a symbolic link")
    lock_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (lock_root / LOCK_NAME).open("a+", encoding="utf-8")
    try:
        if os.name == "posix":
            import fcntl
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise UpdateRollbackError("Другая операция обновления/отката уже выполняется") from exc
        yield
    finally:
        if os.name == "posix":
            try:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        lock.close()


def create_pre_update_snapshot(*, update_mode: str, requested_target: str | None = None,
                               actor: str | None = None,
                               project_root: str | Path | None = None) -> PreparedSnapshot:
    root = _root(project_root)
    ensure_repository(root)
    source_commit = _commit(root)
    source_release = _release(_subject(root, source_commit))
    created = _now()
    snapshot_id = created.strftime("%Y%m%dT%H%M%S%fZ") + "_" + source_commit[:8]
    raw_root = _snapshot_root(root)
    raw_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    final = _snapshot_dir(root, snapshot_id)
    temp = _inside(raw_root / f".{snapshot_id}.tmp-{os.getpid()}", raw_root)
    temp.mkdir(mode=0o700)
    try:
        db_path = temp / DB_NAME
        _backup_db(_db(root), db_path)
        runner = temp / RUNNER_NAME
        shutil.copy2(Path(__file__).resolve(), runner)
        runner.chmod(0o700)
        _write_json(temp / MANIFEST_NAME, {
            "format_version": SNAPSHOT_FORMAT,
            "kind": "xfi_pre_update",
            "snapshot_id": snapshot_id,
            "created_at": _iso(created),
            "repository": REPOSITORY,
            "branch": BRANCH,
            "source": {
                "commit": source_commit,
                "short_commit": source_commit[:8],
                "release": source_release,
            },
            "update": {
                "mode": str(update_mode or "unknown"),
                "requested_target": requested_target,
                "actor": actor,
                "status": "prepared",
                "applied_at": None,
                "applied_commit": None,
                "applied_release": None,
            },
            "database": {
                "file": DB_NAME,
                "size": db_path.stat().st_size,
                "sha256": _sha256(db_path),
            },
        })
        os.replace(temp, final)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return PreparedSnapshot(snapshot_id, final, source_commit, source_release)


def discard_prepared_snapshot(snapshot_id: str, *, project_root: str | Path | None = None) -> None:
    root = _root(project_root)
    path = _snapshot_dir(root, snapshot_id)
    if path.is_symlink():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def mark_snapshot_applied(snapshot_id: str, *, project_root: str | Path | None = None,
                           with_errors: bool = False) -> RollbackPoint:
    root = _root(project_root)
    path = _snapshot_dir(root, snapshot_id)
    data = _manifest(path)
    update = data["update"]
    commit = _commit(root)
    update.update({
        "status": "applied_with_errors" if with_errors else "applied",
        "applied_at": _iso(_now()),
        "applied_commit": commit,
        "applied_release": _release(_subject(root, commit)),
    })
    _write_json(path / MANIFEST_NAME, data)
    cleanup_pre_update_snapshots(project_root=root)
    return _point(root, path)


def finalize_snapshot_after_git(snapshot: PreparedSnapshot, *, git_succeeded: bool,
                                 project_root: str | Path | None = None) -> bool:
    root = _root(project_root)
    current = _commit(root)
    if current == snapshot.source_commit:
        discard_prepared_snapshot(snapshot.snapshot_id, project_root=root)
        return False
    mark_snapshot_applied(snapshot.snapshot_id, project_root=root, with_errors=not git_succeeded)
    return True


def list_rollback_points(*, project_root: str | Path | None = None,
                         verify_integrity: bool = True,
                         now: datetime | None = None) -> list[RollbackPoint]:
    root = _root(project_root)
    raw = _snapshot_root(root)
    if not raw.is_dir() or raw.is_symlink():
        return []
    cutoff = (now or _now()) - timedelta(days=RETENTION_DAYS)
    current = _commit(root)
    points: list[RollbackPoint] = []
    for path in raw.iterdir():
        if not path.is_dir() or path.is_symlink() or not SNAPSHOT_RE.fullmatch(path.name):
            continue
        try:
            point = _point(root, path, verify=verify_integrity)
            if point.created_at >= cutoff and point.source_commit != current:
                points.append(point)
        except (OSError, UpdateRollbackError) as exc:
            logger.warning("Ignoring invalid XFI rollback point %s: %s", path, exc)
    points.sort(key=lambda p: p.created_at, reverse=True)
    return points[:MAX_ROLLBACK_POINTS]


def get_rollback_point(snapshot_id: str, *, project_root: str | Path | None = None,
                       verify_integrity: bool = True) -> RollbackPoint:
    root = _root(project_root)
    path = _snapshot_dir(root, snapshot_id)
    if not path.is_dir() or path.is_symlink():
        raise UpdateRollbackError("Rollback snapshot is unavailable")
    point = _point(root, path, verify=verify_integrity)
    if point.created_at < _now() - timedelta(days=RETENTION_DAYS):
        raise UpdateRollbackError("Rollback snapshot has expired")
    return point


def cleanup_pre_update_snapshots(*, project_root: str | Path | None = None,
                                 retention_days: int = RETENTION_DAYS,
                                 max_points: int = MAX_ROLLBACK_POINTS,
                                 now: datetime | None = None) -> int:
    root = _root(project_root)
    raw = _snapshot_root(root)
    if not raw.exists() or raw.is_symlink():
        return 0
    cutoff = (now or _now()) - timedelta(days=max(0, int(retention_days)))
    entries: list[tuple[Path, datetime, bool]] = []
    for path in raw.iterdir():
        if path.is_dir() and not path.is_symlink() and (path.name.startswith(".") or ".tmp-" in path.name):
            try:
                if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass
            continue
        if not path.is_dir() or path.is_symlink() or not SNAPSHOT_RE.fullmatch(path.name):
            continue
        try:
            data = _manifest(path)
            created = _parse_time(data.get("created_at"))
            update = data.get("update")
            eligible = isinstance(update, dict) and update.get("status") in {"applied", "applied_with_errors"}
        except Exception:
            created = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            eligible = False
        entries.append((path, created, eligible))
    remove = {p for p, created, _ in entries if created < cutoff}
    eligible = sorted(((p, created) for p, created, ok in entries if ok and p not in remove), key=lambda x: x[1], reverse=True)
    remove.update(p for p, _ in eligible[max(0, int(max_points)):])
    count = 0
    for path in remove:
        try:
            _inside(path, raw)
            if path.exists():
                shutil.rmtree(path)
                count += 1
        except OSError:
            logger.warning("Cannot remove rollback point %s", path)
    return count


def _install_requirements(root: Path) -> None:
    requirements = root / "requirements.txt"
    if not requirements.is_file():
        raise UpdateRollbackError("requirements.txt отсутствует после смены кода")
    _checked([sys.executable, "-m", "pip", "install", "--upgrade", "-r", str(requirements)], root,
             stage="Installing dependencies", timeout=600)


def _restore_db(source: Path, destination: Path) -> None:
    _check_db(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".xfi-rollback-", suffix=".db", dir=str(destination.parent))
    os.close(fd)
    temp = Path(name)
    try:
        shutil.copy2(source, temp)
        _check_db(temp)
        for suffix in ("-wal", "-shm"):
            Path(str(destination) + suffix).unlink(missing_ok=True)
        os.replace(temp, destination)
        try:
            destination.chmod(0o600)
        except OSError:
            pass
    finally:
        temp.unlink(missing_ok=True)


def _systemctl(action: str, service: str, root: Path, check: bool = True) -> None:
    result = _run(["systemctl", action, service], root, 60)
    if check and result.returncode:
        output = (result.stdout + result.stderr).strip()
        raise UpdateRollbackError(f"systemctl {action} failed: {output or 'no output'}")


def _wait_active(service: str, root: Path, timeout: int = 30) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _run(["systemctl", "is-active", service], root, 15)
        if result.returncode == 0 and result.stdout.strip() == "active":
            return True
        time.sleep(1)
    return False


def _rescue(root: Path, commit: str) -> Path:
    directory = Path(tempfile.mkdtemp(prefix=".xfi-rescue-", dir=str(_snapshot_root(root))))
    try:
        _backup_db(_db(root), directory / DB_NAME)
        _write_json(directory / "rescue.json", {"commit": commit, "created_at": _iso(_now())})
        return directory
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


def _recover(root: Path, commit: str, rescue: Path, service: str) -> bool:
    try:
        _systemctl("stop", service, root, check=False)
        _git(root, ["reset", "--hard", commit], stage="Recovering Git state")
        _install_requirements(root)
        _restore_db(rescue / DB_NAME, _db(root))
        _systemctl("start", service, root)
        return _wait_active(service, root)
    except Exception:
        logger.exception("XFI automatic recovery failed")
        return False


def perform_rollback(snapshot_id: str, *, project_root: str | Path | None = None,
                     service_name: str = SERVICE_NAME, admin_id: int | None = None,
                     manage_service: bool = True) -> RollbackExecutionResult:
    root = _root(project_root)
    with update_operation_lock(root):
        ensure_repository(root)
        point = get_rollback_point(snapshot_id, project_root=root, verify_integrity=True)
        current = _commit(root)
        if current == point.source_commit:
            raise UpdateRollbackError("Бот уже находится на выбранной версии")
        rescue: Path | None = None
        try:
            rescue = _rescue(root, current)
            if manage_service:
                _systemctl("stop", service_name, root)
            _git(root, ["reset", "--hard", point.source_commit], stage="Applying rollback")
            _install_requirements(root)
            _restore_db(point.database_path, _db(root))
            if manage_service:
                _systemctl("start", service_name, root)
                if not _wait_active(service_name, root):
                    raise UpdateRollbackError("XFI CONNECT service did not become active")
            message = f"Откат выполнен: {point.display_release} ({point.source_short_commit})"
            _write_result(root, admin_id, "success", message, snapshot_id)
            shutil.rmtree(rescue, ignore_errors=True)
            return RollbackExecutionResult(True, message)
        except Exception as exc:
            logger.exception("XFI rollback failed")
            recovered = _recover(root, current, rescue, service_name) if rescue else False
            message = f"Откат не выполнен: {exc}. " + (
                "Исходное состояние восстановлено." if recovered else "Автоматическое восстановление не удалось."
            )
            _write_result(root, admin_id, "failed", message, snapshot_id)
            if recovered and rescue:
                shutil.rmtree(rescue, ignore_errors=True)
            return RollbackExecutionResult(False, message, recovered=recovered)


def _write_result(root: Path, admin_id: int | None, status: str, message: str, snapshot_id: str) -> None:
    if admin_id is None:
        return
    _write_json(_snapshot_root(root) / RESULT_NAME, {
        "format_version": 1, "created_at": _iso(_now()), "admin_id": int(admin_id),
        "status": status, "message": str(message), "snapshot_id": snapshot_id,
    })


def schedule_admin_rollback(snapshot_id: str, admin_id: int, *, project_root: str | Path | None = None,
                            service_name: str = SERVICE_NAME) -> tuple[bool, str]:
    root = _root(project_root)
    point = get_rollback_point(snapshot_id, project_root=root, verify_integrity=True)
    runner = point.snapshot_dir / RUNNER_NAME
    if not runner.is_file():
        return False, "Автономный исполнитель отката отсутствует в backup"
    unit = f"xfi-connect-rollback-{snapshot_id[:23].lower()}"
    result = _run([
        "systemd-run", "--quiet", "--collect", f"--unit={unit}",
        "--property=Type=exec", sys.executable, str(runner), "rollback",
        "--project-root", str(root), "--snapshot-id", snapshot_id,
        "--service-name", service_name, "--admin-id", str(int(admin_id)),
        "--start-delay", "2",
    ], root, 30)
    if result.returncode:
        return False, (result.stdout + result.stderr).strip() or "Не удалось запустить rollback worker"
    return True, unit


async def notify_pending_rollback_result(bot: Any, *, project_root: str | Path | None = None,
                                         pending_timeout_seconds: int = 30) -> bool:
    try:
        root = _root(project_root)
    except UpdateRollbackError:
        return False
    path = _snapshot_root(root) / RESULT_NAME
    if not path.is_file():
        return False
    deadline = time.monotonic() + max(0, pending_timeout_seconds)
    while time.monotonic() < deadline:
        try:
            data = _read_json(path)
        except UpdateRollbackError:
            return False
        if data.get("status") != "pending":
            break
        await asyncio.sleep(1)
    try:
        data = _read_json(path)
        admin_id = int(data["admin_id"])
    except (UpdateRollbackError, KeyError, TypeError, ValueError):
        return False
    if data.get("status") == "pending":
        return False
    success = data.get("status") == "success"
    title = "Откат XFI CONNECT завершён" if success else "Ошибка отката XFI CONNECT"
    text = f"<b>{'✅' if success else '❌'} {title}</b>\n\n{html.escape(str(data.get('message') or 'Нет подробностей.'))}"
    try:
        await bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
    except Exception:
        logger.exception("Cannot notify admin %s about rollback", admin_id)
        return False
    path.unlink(missing_ok=True)
    return True


def _interactive(root: Path, service: str) -> int:
    points = list_rollback_points(project_root=root)
    if not points:
        print("Доступных точек отката нет.")
        return 1
    for index, point in enumerate(points, 1):
        print(f"{index}) {point.display_release} · {point.source_short_commit} · {point.created_at.astimezone():%d.%m.%Y %H:%M:%S}")
    try:
        selected = int(input(f"Выберите [1-{len(points)}]: ").strip())
    except (EOFError, ValueError):
        return 1
    if not 1 <= selected <= len(points):
        return 1
    point = points[selected - 1]
    try:
        confirmation = input("Введите ОТКАТИТЬ для подтверждения: ").strip()
    except EOFError:
        confirmation = ""
    if confirmation != "ОТКАТИТЬ":
        print("Откат отменён.")
        return 0
    result = perform_rollback(point.snapshot_id, project_root=root, service_name=service)
    print(result.message)
    return 0 if result.success else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="XFI CONNECT transactional update/rollback")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--project-root", required=True)
    prepare.add_argument("--mode", required=True)
    prepare.add_argument("--requested-target")
    prepare.add_argument("--actor")
    mark = sub.add_parser("mark-applied")
    mark.add_argument("--project-root", required=True)
    mark.add_argument("--snapshot-id", required=True)
    mark.add_argument("--with-errors", action="store_true")
    interactive = sub.add_parser("interactive")
    interactive.add_argument("--project-root", required=True)
    interactive.add_argument("--service-name", default=SERVICE_NAME)
    rollback = sub.add_parser("rollback")
    rollback.add_argument("--project-root", required=True)
    rollback.add_argument("--snapshot-id", required=True)
    rollback.add_argument("--service-name", default=SERVICE_NAME)
    rollback.add_argument("--admin-id", type=int)
    rollback.add_argument("--start-delay", type=float, default=0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            print(create_pre_update_snapshot(update_mode=args.mode, requested_target=args.requested_target,
                                             actor=args.actor, project_root=args.project_root).snapshot_id)
            return 0
        if args.command == "mark-applied":
            mark_snapshot_applied(args.snapshot_id, project_root=args.project_root, with_errors=args.with_errors)
            return 0
        if args.command == "interactive":
            return _interactive(_root(args.project_root), args.service_name)
        if args.command == "rollback":
            if args.start_delay > 0:
                time.sleep(min(args.start_delay, 10))
            result = perform_rollback(args.snapshot_id, project_root=args.project_root,
                                      service_name=args.service_name, admin_id=args.admin_id)
            print(result.message)
            return 0 if result.success else 1
    except UpdateRollbackError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        logger.exception("Unexpected XFI update error")
        print(f"Критическая ошибка: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
