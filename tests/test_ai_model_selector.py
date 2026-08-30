from bot.services.ai_model_selector import AIModelSelector


class Inventory:
    def available(self):
        return {"groq": ("llama-3.1-8b-instant", "llama-3.3-70b-versatile")}


def test_selector_prefers_large_model_for_analysis():
    choice = AIModelSelector(Inventory()).choose("analysis")
    assert choice.provider == "groq"
    assert choice.model == "llama-3.3-70b-versatile"


def test_selector_respects_preferred_provider():
    class Multi:
        def available(self):
            return {"openai": ("gpt-4.1-mini",), "groq": ("llama-3.3-70b-versatile",)}

    choice = AIModelSelector(Multi()).choose("fast", preferred_provider="openai")
    assert choice.provider == "openai"
