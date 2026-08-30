from pathlib import Path

from bot.services.ai_key_store import AIKeyStore


def test_key_store_roundtrip_and_permissions(tmp_path: Path):
    path = tmp_path / "secrets" / "ai.keys"
    store = AIKeyStore(path, "x" * 32)
    store.set("groq", "secret-value")
    assert store.get("groq") == "secret-value"
    assert store.configured("groq")
    assert "secret-value" not in path.read_text(encoding="utf-8")
    store.delete("groq")
    assert not store.configured("groq")
