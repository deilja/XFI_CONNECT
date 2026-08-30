import hashlib
import json

import pytest

from bot.services.ai_changeset import ChangeSetError
from bot.services.ai_changeset_parser import parse_changeset


def test_parser_accepts_current_hash(tmp_path):
    p = tmp_path / "sample.py"
    content = "print('old')\n"
    p.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode()).hexdigest()
    raw = json.dumps({"rationale": "test", "changes": [{"path": "sample.py", "old_sha256": digest, "new_content": "print('new')\n"}]})
    result = parse_changeset(raw, tmp_path, "fix")
    assert result.changeset.changes[0].path == "sample.py"


def test_parser_rejects_stale_hash(tmp_path):
    p = tmp_path / "sample.py"
    p.write_text("current", encoding="utf-8")
    raw = json.dumps({"changes": [{"path": "sample.py", "old_sha256": "0" * 64, "new_content": "new"}]})
    with pytest.raises(ChangeSetError):
        parse_changeset(raw, tmp_path, "fix")
