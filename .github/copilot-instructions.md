# XFI CONNECT AI instructions

Read `/AGENTS.md` before modifying this repository. It is the authoritative AI engineering contract.

Repository identity: `deilja/XFI_CONNECT`.

Never reintroduce YadrenoVPN legacy updater behaviour. The canonical update engine is `bot/services/xfi_update.py`; compatibility wrappers must remain thin. Update and rollback operations must be transactional, locked, validated and recoverable. Never mutate Git remotes dynamically.

For every code change, inspect callers and tests, preserve existing behaviour, add regression coverage, run targeted tests, then run the full CI suite. Treat secrets and user data as sensitive and never commit or log them.
