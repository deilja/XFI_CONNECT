import pytest

from bot.services.ai_supervisor_pipeline import AISupervisorPipeline


class Plan:
    summary = "fix test"
    rationale = "regression"
    risk = "low"
    requires_confirmation = True


class Consensus:
    async def plan(self, request):
        return type("Result", (), {"plan": Plan(), "providers_used": ("groq", "openai")})()


@pytest.mark.asyncio
async def test_propose_confirm_and_execute():
    executed = []

    async def build(request, summary):
        return {"request": request, "summary": summary}

    async def execute(payload):
        executed.append(payload)
        return True

    pipeline = AISupervisorPipeline(Consensus(), build, execute)
    decision = await pipeline.propose("fix test")
    assert decision.requires_confirmation
    assert decision.providers_used == ("groq", "openai")
    assert await pipeline.confirm(decision.changeset_payload)
    assert executed[0]["summary"] == "fix test"


@pytest.mark.asyncio
async def test_reject_discards_pending():
    async def build(request, summary):
        return object()

    async def execute(payload):
        raise AssertionError("must not execute")

    pipeline = AISupervisorPipeline(Consensus(), build, execute)
    decision = await pipeline.propose("reject me")
    pipeline.reject(decision.changeset_payload)
    with pytest.raises(ValueError):
        await pipeline.confirm(decision.changeset_payload)
