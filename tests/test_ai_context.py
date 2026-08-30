from bot.ai_context import context_for


def test_update_module_context():
    text = context_for("bot/services/xfi_update.py")
    assert "Canonical update/rollback transaction engine" in text
    assert "locking" in text


def test_admin_handler_context():
    text = context_for("bot/handlers/admin/system.py")
    assert "Telegram admin UI" in text
    assert "privileged work to services" in text


def test_unknown_file_gets_common_contract():
    text = context_for("some/new_module.py")
    assert "deilja/XFI_CONNECT" in text
    assert "Never expose secrets" in text
