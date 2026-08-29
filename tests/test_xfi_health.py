from bot.services import xfi_health


def test_health_checker_requires_active_service(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setattr(xfi_health, "_root", lambda root=None: tmp_path)
    monkeypatch.setattr(
        xfi_health,
        "_service_state",
        lambda service, root: calls.append(service) or ("inactive", "dead", 0, 0),
    )

    assert not xfi_health.verify_service("xfi-connect", settle_seconds=1, project_root=tmp_path)
    assert calls == ["xfi-connect"]


def test_health_checker_stays_active(monkeypatch, tmp_path):
    monkeypatch.setattr(xfi_health, "_root", lambda root=None: tmp_path)
    monkeypatch.setattr(xfi_health, "_service_state", lambda service, root: ("active", "running", 0, 1234))
    monkeypatch.setattr(xfi_health.time, "sleep", lambda seconds: None)

    assert xfi_health.verify_service("xfi-connect", settle_seconds=1, interval_seconds=1, project_root=tmp_path)


def test_health_checker_rejects_restart_loop(monkeypatch, tmp_path):
    states = iter([
        ("active", "running", 0, 100),
        ("active", "running", 1, 101),
    ])
    monkeypatch.setattr(xfi_health, "_root", lambda root=None: tmp_path)
    monkeypatch.setattr(xfi_health, "_service_state", lambda service, root: next(states))
    monkeypatch.setattr(xfi_health.time, "sleep", lambda seconds: None)

    assert not xfi_health.verify_service("xfi-connect", settle_seconds=2, interval_seconds=1, project_root=tmp_path)
