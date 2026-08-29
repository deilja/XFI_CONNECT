from bot.services import xfi_health


def test_health_checker_requires_active_service(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setattr(xfi_health, "_root", lambda root=None: tmp_path)
    monkeypatch.setattr(
        xfi_health,
        "_service_active",
        lambda service, root: calls.append(service) or False,
    )

    assert not xfi_health.verify_service("xfi-connect", settle_seconds=1, project_root=tmp_path)
    assert calls == ["xfi-connect"]


def test_health_checker_stays_active(monkeypatch, tmp_path):
    monkeypatch.setattr(xfi_health, "_root", lambda root=None: tmp_path)
    monkeypatch.setattr(xfi_health, "_service_active", lambda service, root: True)
    monkeypatch.setattr(xfi_health.time, "sleep", lambda seconds: None)

    assert xfi_health.verify_service("xfi-connect", settle_seconds=1, interval_seconds=1, project_root=tmp_path)
