from pathlib import Path

import pytest

from bot.services.ai_changeset import (
    ChangeSet,
    ChangeSetError,
    FileChange,
    begin,
    apply,
    rollback,
)


def test_changeset_apply_and_rollback(tmp_path: Path):
    target = tmp_path / "bot.py"
    target.write_text("old\n", encoding="utf-8")
    import hashlib
    old_hash = hashlib.sha256(b"old\n").hexdigest()
    changes = ChangeSet("fix", (FileChange("bot.py", old_hash, "new\n"),))
    tx = begin(changes, tmp_path)
    apply(tx, changes)
    assert target.read_text(encoding="utf-8") == "new\n"
    rollback(tx)
    assert target.read_text(encoding="utf-8") == "old\n"


def test_hash_mismatch_is_rejected(tmp_path: Path):
    target = tmp_path / "bot.py"
    target.write_text("actual", encoding="utf-8")
    changes = ChangeSet("fix", (FileChange("bot.py", "0" * 64, "new"),))
    with pytest.raises(ChangeSetError):
        begin(changes, tmp_path)


def test_path_escape_is_rejected(tmp_path: Path):
    changes = ChangeSet("fix", (FileChange("../outside.py", "MISSING", "x"),))
    with pytest.raises(ChangeSetError):
        begin(changes, tmp_path)
