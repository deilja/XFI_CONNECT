from pathlib import Path

from bot.services.ai_agent import AIAgent, _load_project_contract


def test_project_contract_is_available():
    contract = _load_project_contract()
    assert "XFI CONNECT" in contract
    assert "deilja/XFI_CONNECT" in contract
    assert "Never expose" in contract or "secrets" in contract.lower()


def test_agent_includes_contract_and_module_role(monkeypatch):
    monkeypatch.setattr("bot.services.ai_agent.AIAgent._normalize_provider", lambda cls, provider: "groq")
    agent = object.__new__(AIAgent)
    agent.project_contract = "XFI CONNECT CONTRACT"
    system = agent._system_message("test/module.py")
    assert "XFI CONNECT CONTRACT" in system
    assert "test/module.py" in system
    assert "не выдумывай" in system.lower()


def test_ai_context_map_exists():
    root = Path(__file__).resolve().parents[1]
    context = root / "AI_CONTEXT.md"
    assert context.is_file()
    text = context.read_text(encoding="utf-8")
    assert "bot/services/xfi_update.py" in text
    assert "For every file" in text
