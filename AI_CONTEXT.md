# XFI CONNECT AI context map

This file is the compact map an AI assistant should consult when a task touches a file.

| Path | Required mindset |
|---|---|
| `bot/handlers/**` | Telegram presentation/orchestration; preserve FSM, callback contracts and authorization. |
| `bot/handlers/admin/**` | Privileged UI; keep `is_admin` checks and confirmation flows. |
| `bot/services/**` | Business/integration layer; handlers should call services rather than duplicate logic. |
| `bot/services/xfi_update.py` | Security-critical transaction engine; exact Git targets, snapshots, locks, health and recovery. |
| `bot/services/xfi_health.py` | Independent post-update verification; detect inactive states and crash loops. |
| `bot/services/ai_agent.py` | AI policy/provider boundary; inject project contract, protect secrets, never invent execution results. |
| `bot/services/update_rollback.py` | Compatibility façade only; no legacy implementation. |
| `bot/utils/**` | Generic reusable helpers; validate inputs and avoid shell/SQL injection. |
| `database/**` | Persistence; preserve data, transactions and compatibility. |
| `bot/keyboards/**` | Telegram UI contracts; do not casually rename callback data. |
| `tests/**` | Encode regression, security and recovery guarantees. |
| `.github/workflows/**` | CI must reproduce a clean supported installation and validate the application. |
| `docs/**` | Document actual behaviour, not planned behaviour. |
| `install.sh` | Safe fresh/migration installer; preserve existing secrets/config. |
| `config.py.example` | Template only; never contain real credentials. |

## For every file

1. Read `AGENTS.md`.
2. Identify the file's role from this map.
3. Search callers/consumers before changing public names or data contracts.
4. Preserve unrelated behaviour.
5. Add regression coverage when behaviour changes.
6. Verify compile/import/tests/CI as applicable.
