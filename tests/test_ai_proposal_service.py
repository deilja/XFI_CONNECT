import json

import pytest

from bot.services.ai_proposal_service import AIProposalService


class FakeAgent:
    async def chat(self, prompt, **kwargs):
        return json.dumps({"summary": "fix", "changes": [{"path": "app.py", "new_content": "print('ok')\n"}]})


@pytest.mark.asyncio
async def test_proposal_service_returns_structured_changes(tmp_path):
    (tmp_path / "app.py").write_text("print('old')\n", encoding="utf-8")
    service = AIProposalService(FakeAgent(), str(tmp_path))
    proposal = await service.propose("fix app")
    assert proposal.summary == "fix"
    assert proposal.changes[0].path == "app.py"
