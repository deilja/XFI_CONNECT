"""Post-update service verification for XFI CONNECT.

The verifier is deliberately independent from the bot process.  It is started
before the updater restarts the bot and can therefore recover a bad release
without relying on the updated Python process.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from bot.services.xfi_update import (
    SERVICE_NAME,
    UpdateRollbackError,
    perform_rollback,
    get_rollback_point,
    _root,
    _run,
)

DEFAULT_SETTLE_SECONDS = 20
DEFAULT_INTERVAL_SECONDS = 2


def _service_active(service: str, root: Path) -> bool:
    result = _run(["systemctl", "is-active", service], root, 15)
    return result.returncode == 0 and result.stdout.strip() == "active"


def verify_service(service: str, *, settle_seconds: int = DEFAULT_SETTLE_SECONDS,
                   interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
                   project_root: str | Path | None = None) -> bool:
    root = _root(project_root)
    deadline = time.monotonic() + max(1, int(settle_seconds))
    interval = max(1, int(interval_seconds))
    while time.monotonic() < deadline:
        if not _service_active(service, root):
            return False
        time.sleep(min(interval, max(0.1, deadline - time.monotonic())))
    return _service_active(service, root)


def schedule_post_update_check(snapshot_id: str, *, service_name: str = SERVICE_NAME,
                               project_root: str | Path | None = None,
                               settle_seconds: int = DEFAULT_SETTLE_SECONDS) -> tuple[bool, str]:
    root = _root(project_root)
    # Validate the snapshot before creating an external worker.
    get_rollback_point(snapshot_id, project_root=root, verify_integrity=True)
    unit = f"xfi-connect-health-{snapshot_id[:23].lower()}"
    result = _run([
        "systemd-run", "--quiet", "--collect", f"--unit={unit}",
        "--property=Type=exec", sys.executable, "-m", "bot.services.xfi_health",
        "verify", "--project-root", str(root), "--snapshot-id", snapshot_id,
        "--service-name", service_name, "--settle-seconds", str(int(settle_seconds)),
    ], root, 30)
    if result.returncode:
        return False, (result.stdout + result.stderr).strip() or "Не удалось запустить health-check worker"
    return True, unit


def run_post_update_check(snapshot_id: str, *, service_name: str = SERVICE_NAME,
                          project_root: str | Path | None = None,
                          settle_seconds: int = DEFAULT_SETTLE_SECONDS) -> int:
    root = _root(project_root)
    try:
        get_rollback_point(snapshot_id, project_root=root, verify_integrity=True)
    except UpdateRollbackError as exc:
        print(f"Health-check aborted: {exc}", file=sys.stderr)
        return 2

    if verify_service(service_name, settle_seconds=settle_seconds, project_root=root):
        print("XFI CONNECT health-check: OK")
        return 0

    print("XFI CONNECT health-check: FAILED; starting automatic rollback", file=sys.stderr)
    result = perform_rollback(snapshot_id, project_root=root, service_name=service_name)
    print(result.message, file=sys.stderr if not result.success else sys.stdout)
    return 1 if not result.success else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="XFI CONNECT post-update health checker")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--project-root", required=True)
    verify.add_argument("--snapshot-id", required=True)
    verify.add_argument("--service-name", default=SERVICE_NAME)
    verify.add_argument("--settle-seconds", type=int, default=DEFAULT_SETTLE_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "verify":
        return run_post_update_check(args.snapshot_id, service_name=args.service_name,
                                     project_root=args.project_root,
                                     settle_seconds=args.settle_seconds)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
