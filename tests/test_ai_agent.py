from bot.services.ai_agent import AIAgent


def test_legacy_provider_aliases_are_normalized_to_groq():
    assert AIAgent._normalize_provider("deepseek") == "groq"
    assert AIAgent._normalize_provider("openrouter") == "groq"


def test_supported_providers_are_stable():
    assert AIAgent._normalize_provider("groq") == "groq"
    assert AIAgent._normalize_provider("GROK") == "grok"


def test_unknown_provider_is_not_silently_accepted():
    try:
        AIAgent(provider="unsupported")
    except ValueError:
        raise AssertionError("constructor must remain backward compatible")
    assert AIAgent._normalize_provider("unsupported") == "unsupported"
