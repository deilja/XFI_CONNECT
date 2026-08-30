import json

import pytest

from bot.services.ai_supervisor_consensus import SupervisorConsensus


class Pool:
    def status(self):
        return {"groq": {"configured": True, "healthy": True, "models": ["test"]}}

    async def chat(self, provider, model, system, prompt):
        return json.dumps({
            "summary": "fix bug",
            "risk": "medium",
            "rationale": "regression",
            "files": ["bot/example.py"],
            "requires_confirmation": False,
        })


@pytest.mark.asyncio
async def test_consensus_forces_confirmation():
    plan, opinions = await SupervisorConsensus(Pool()).propose("fix")
    assert plan.requires_confirmation is True
    assert opinions[0].plan is not None


def test_invalid_risk_rejected():
    with pytest.raises(ValueError):
        SupervisorConsensus._parse(json.dumps({
            "summary": "x", "risk": "unknown", "rationale": "x",
            "files": [], "requires_confirmation": False,
        }))
