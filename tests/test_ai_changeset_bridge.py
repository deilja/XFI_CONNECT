from pathlib import Path

import pytest

from bot.services.ai_changeset import ChangeSetError
from bot.services.ai_changeset_bridge import ChangeSetBridge, ProposedChange


def test_build_uses_current_hash(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("old\n", encoding="utf-8")
    bridge = ChangeSetBridge(tmp_path)
    changeset = bridge.build("fix", [ProposedChange("app.py", "new\n")])
    tx = bridge.start(changeset)
    bridge.apply(tx, changeset)
    assert target.read_text(encoding="utf-8") == "new\n"
    bridge.verify_and_commit(tx, changeset, True)


def test_failed_verification_rolls_back(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("old\n", encoding="utf-8")
    bridge = ChangeSetBridge(tmp_path)
    changeset = bridge.build("fix", [ProposedChange("app.py", "new\n")])
    tx = bridge.start(changeset)
    bridge.apply(tx, changeset)
    with pytest.raises(ChangeSetError):
        bridge.verify_and_commit(tx, changeset, False)
    assert target.read_text(encoding="utf-8") == "old\n"
