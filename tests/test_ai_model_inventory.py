import pytest

from bot.services.ai_model_inventory import AIModelInventory, fingerprint


def test_fingerprint_is_order_independent():
    assert fingerprint(["b", "a"]) == fingerprint(["a", "b"])
    assert fingerprint(["a", "a"]) == fingerprint(["a"])


@pytest.mark.asyncio
async def test_inventory_normalizes_models():
    async def list_models(provider):
        return [" z ", "a", "z", ""]

    inventory = AIModelInventory(("groq",), list_models)
    result = await inventory.refresh_provider("groq")
    assert result.models == ("a", "z")
    assert inventory.models_for("groq") == ("a", "z")
