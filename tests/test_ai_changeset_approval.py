import pytest

from bot.services.ai_changeset import ChangeSet, FileChange
from bot.services.ai_changeset_approval import ChangeSetApprovalStore


def cs(content="new"):
    return ChangeSet("fix", (FileChange("app.py", "abc", content),))


def test_approval_requires_same_changeset():
    store = ChangeSetApprovalStore()
    record = store.issue("t1", cs())
    assert store.is_approved("t1", cs()) is False
    store.approve("t1", record.token, cs())
    assert store.is_approved("t1", cs()) is True
    assert store.is_approved("t1", cs("tampered")) is False


def test_wrong_token_rejected():
    store = ChangeSetApprovalStore()
    store.issue("t1", cs())
    with pytest.raises(PermissionError):
        store.approve("t1", "wrong", cs())
