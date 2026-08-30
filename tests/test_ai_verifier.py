import pytest

from bot.services.ai_verifier import VerificationPipeline


@pytest.mark.asyncio
async def test_pipeline_requires_registered_passing_check():
    pipeline = VerificationPipeline()
    ok, results = await pipeline.run()
    assert not ok
    assert results == ()


@pytest.mark.asyncio
async def test_pipeline_reports_failed_check():
    pipeline = VerificationPipeline()

    async def check():
        return False

    pipeline.register("health", check)
    ok, results = await pipeline.run()
    assert not ok
    assert results[0].name == "health"
    assert not results[0].passed
