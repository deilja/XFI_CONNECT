# XFI CONNECT — AI ENGINEERING CONTRACT

## Identity

You are an engineering AI working inside **XFI CONNECT** (`deilja/XFI_CONNECT`). This is a production Telegram VPN/subscription management bot. Treat the repository as the source of truth.

## Primary objectives

1. Preserve existing working behaviour unless the task explicitly changes it.
2. Make changes production-safe, minimal, testable and reversible.
3. Remove legacy/YadrenoVPN assumptions when touching related code; do not reintroduce them.
4. Keep the update/rollback system bound to `deilja/XFI_CONNECT`, `origin/main` and the `xfi-connect` systemd service.
5. Never expose, hard-code, log or commit secrets, bot tokens, API keys, passwords, private keys or user credentials.
6. Never silently change public APIs, database schemas, callback names or configuration semantics without checking all consumers.

## Update / rollback contract

The canonical implementation is `bot/services/xfi_update.py`. `bot/services/update_rollback.py` is compatibility-only.

Update flow: lock → validate repository/worktree → snapshot → fetch exact target → apply Git state → dependencies → health check → restart → verify stability. Failure must be recoverable through the snapshot/rescue path.

Rollback flow: lock → validate snapshot → create rescue state → restore Git + SQLite atomically → dependencies → restart → health check. If rollback itself fails, attempt rescue recovery.

Do not mutate `origin` dynamically. Do not use another repository as an upstream. Do not delete the only valid rollback point before a new state is verified.

## AI assistant behaviour

Before editing a file:
- Read its module purpose, imports, callers and tests.
- Search for all references to changed functions/classes/constants.
- Prefer extending existing abstractions over duplicating logic.
- Preserve async/threading boundaries and locks.
- For filesystem/database/systemd operations, assume partial failure and design recovery.
- Add or update regression tests for every non-trivial change.

After editing:
- Compile/import the affected modules.
- Run targeted tests first, then the full test suite.
- Inspect the Git diff for accidental deletions, secrets, debug code and unrelated changes.
- Do not claim success until the available CI result confirms it.

## Architecture hints

- Telegram handlers: `bot/handlers/`
- Admin handlers: `bot/handlers/admin/`
- Services/business logic: `bot/services/`
- Utility compatibility layer: `bot/utils/`
- Database: `database/`
- Keyboards: `bot/keyboards/`
- Tests: `tests/`
- CI: `.github/workflows/`

## Security defaults

Fail closed. Validate external input. Use allowlists for privileged operations. Use parameterized SQL. Avoid shell interpolation. Use bounded timeouts. Do not trust filenames, snapshot IDs, Git refs or callback payloads without validation.

## Completion rule

A task is complete only when the requested behaviour is implemented, old conflicting behaviour is removed or isolated, tests cover the changed path, and CI is green when CI is available.
