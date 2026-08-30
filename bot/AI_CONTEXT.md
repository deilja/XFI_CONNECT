# XFI CONNECT AI module context

Use this file together with `/AGENTS.md` when working on `bot/`.

- This package is the Telegram application layer for XFI CONNECT.
- Handlers orchestrate requests; services own business logic; utilities should remain reusable and side-effect conscious.
- Admin operations are privileged and must validate `is_admin` before mutation.
- Do not put provider credentials or tokens in source code.
- Do not bypass the canonical update/rollback engine.
- Preserve aiogram async semantics; blocking I/O belongs behind `asyncio.to_thread` or an async API.
- When changing callback data, search all producers/consumers before editing.
- When changing database access, inspect migrations/schema and all request helpers.
- AI assistant modules must treat model output as untrusted input and validate any requested operation before execution.
