from pathlib import Path

import pytest

from bot.services import xfi_update


def test_snapshot_path_rejects_traversal(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    monkeypatch.setattr(xfi_update, "_snapshot_root", lambda _: root / "backup" / "pre_update")

    with pytest.raises(xfi_update.UpdateRollbackError):
        xfi_update._snapshot_dir(root, "../../etc")


def test_snapshot_path_rejects_symlinked_root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    real = tmp_path / "real-backups"
    real.mkdir()
    backup = root / "backup"
    backup.mkdir()
    (backup / "pre_update").symlink_to(real, target_is_directory=True)

    with pytest.raises(xfi_update.UpdateRollbackError):
        xfi_update._snapshot_dir(root, "20260829T123456789012Z_deadbeef")


def test_snapshot_identifier_cannot_be_empty_or_non_hex():
    assert not xfi_update.SNAPSHOT_RE.fullmatch("")
    assert not xfi_update.SNAPSHOT_RE.fullmatch("20260829T123456789012Z_zzzzzzzz")
    assert not xfi_update.SNAPSHOT_RE.fullmatch("20260829T123456789012Z_deadbeef/extra")


def test_restore_db_uses_atomic_replace_and_removes_sidecars(tmp_path):
    import sqlite3

    source = tmp_path / "backup.db"
    destination = tmp_path / "vpn_bot.db"
    with sqlite3.connect(source) as conn:
        conn.execute("create table t(value text)")
        conn.execute("insert into t values ('safe')")

    destination.write_bytes(b"old")
    Path(str(destination) + "-wal").write_bytes(b"stale")
    Path(str(destination) + "-shm").write_bytes(b"stale")

    xfi_update._restore_db(source, destination)

    with sqlite3.connect(destination) as conn:
        assert conn.execute("select value from t").fetchone() == ("safe",)
    assert not Path(str(destination) + "-wal").exists()
    assert not Path(str(destination) + "-shm").exists()


def test_repository_guard_rejects_non_xfi(monkeypatch, tmp_path):
    class Result:
        returncode = 0
        stdout = "https://github.com/example/other.git\n"
        stderr = ""

    monkeypatch.setattr(xfi_update, "_run", lambda *args, **kwargs: Result())
    with pytest.raises(xfi_update.UpdateRollbackError):
        xfi_update.ensure_repository(tmp_path)
