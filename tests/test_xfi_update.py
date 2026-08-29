from bot.services import xfi_update


def test_repository_identity_is_fixed():
    assert xfi_update.REPOSITORY == "deilja/XFI_CONNECT"
    assert xfi_update.BRANCH == "main"
    assert xfi_update.REMOTE_NAME == "origin"


def test_snapshot_identifier_is_strict():
    assert xfi_update.SNAPSHOT_RE.fullmatch("20260829T123456789012Z_deadbeef")
    assert not xfi_update.SNAPSHOT_RE.fullmatch("../../rollback")
    assert not xfi_update.SNAPSHOT_RE.fullmatch("deadbeef")


def test_release_parser():
    assert xfi_update._release("Версия 2.14.7 security") == "2.14.7"
    assert xfi_update._release("! Версия 3.0") == "3.0"
    assert xfi_update._release("ordinary commit") == "unknown"


def test_origin_validation(monkeypatch, tmp_path):
    class Result:
        returncode = 0
        stdout = "https://github.com/deilja/XFI_CONNECT.git\n"
        stderr = ""

    monkeypatch.setattr(xfi_update, "_run", lambda *args, **kwargs: Result())
    assert xfi_update._origin_is_xfi(tmp_path)


def test_origin_validation_rejects_other_repo(monkeypatch, tmp_path):
    class Result:
        returncode = 0
        stdout = "https://github.com/example/other.git\n"
        stderr = ""

    monkeypatch.setattr(xfi_update, "_run", lambda *args, **kwargs: Result())
    assert not xfi_update._origin_is_xfi(tmp_path)
