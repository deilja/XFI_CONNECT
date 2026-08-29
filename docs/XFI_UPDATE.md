# XFI CONNECT update / rollback

The updater is repository-bound and does not use the old YadrenoVPN update protocol.

## Source of truth

- Repository: `deilja/XFI_CONNECT`
- Branch: `main`
- Remote: `origin`
- Service: `xfi-connect`

The updater refuses to mutate a worktree whose `origin` is another repository and never replaces `origin` automatically.

## Update transaction

1. Acquire the update/rollback lock.
2. Verify the repository identity and clean worktree.
3. Create a verified SQLite snapshot.
4. Fetch `origin/main`.
5. Resolve the exact target commit.
6. `git reset --hard` to that commit.
7. Install `requirements.txt`.
8. Publish the snapshot as an applied rollback point.
9. The existing admin handler restarts the bot after the transaction succeeds.

If dependency installation fails, the Git worktree is restored to the source commit and the prepared snapshot is discarded.

## Rollback

Rollback uses a verified snapshot and runs outside the bot service through a transient `systemd-run` worker. It restores Git and SQLite, reinstalls dependencies, starts `xfi-connect`, and waits for the service to become active.

Before changing anything during rollback, a rescue snapshot of the current database and commit is created. If rollback fails, the engine attempts automatic recovery to that rescue state.

## Retention

- Maximum verified rollback points: 3
- Retention: 7 days
- SQLite: SHA-256 + `PRAGMA quick_check`
- Snapshot IDs are strict opaque identifiers.

## Compatibility

`bot/services/update_rollback.py` is now only a compatibility façade for existing imports. All implementation is in `bot/services/xfi_update.py`.
