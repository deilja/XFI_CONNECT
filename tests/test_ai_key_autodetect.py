from bot.services.ai_key_autodetect import AIKeyAutoDetector, PROBES


def test_prefixed_key_checks_matching_provider_first():
    candidates = AIKeyAutoDetector._candidates("gsk_example")
    assert candidates[0].provider == "groq"


def test_unknown_prefix_checks_all_supported_providers():
    candidates = AIKeyAutoDetector._candidates("unknown_example")
    assert {item.provider for item in candidates} == {item.provider for item in PROBES}
