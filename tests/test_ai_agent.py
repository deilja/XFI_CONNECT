from bot.services.ai_agent import AIAgent


def test_legacy_provider_aliases_are_normalized_to_groq():
    assert AIAgent._normalize_provider("deepseek") == "groq"
    assert AIAgent._normalize_provider("openrouter") == "groq"


def test_supported_providers_are_stable():
    assert AIAgent._normalize_provider("groq") == "groq"
    assert AIAgent._normalize_provider("GROK") == "grok"


def test_set_provider_rejects_unknown_provider():
    agent = AIAgent(provider="groq")
    try:
        agent.set_provider("unsupported")
    except ValueError:
        return
    raise AssertionError("unsupported provider was accepted")
