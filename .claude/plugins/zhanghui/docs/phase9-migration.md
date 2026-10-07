# Phase 9 project migration and recovery

Run these commands from the active plugin scripts directory, or use the same
arguments through `scripts/webnovel.py`. Preflight and dry run are read-only.
The `migrate` command is an explicit project write: review the report and plan,
create the matching verified backup, and pass their exact digests and backup
directory.

```bash
python3 -m data_modules.webnovel --project-root "$PROJECT" phase9-migration preflight
python3 -m data_modules.webnovel --project-root "$PROJECT" phase9-migration dry-run \
  --report-digest "$REPORT_DIGEST"
python3 -m data_modules.webnovel --project-root "$PROJECT" phase9-migration backup \
  --report-digest "$REPORT_DIGEST"
python3 -m data_modules.webnovel --project-root "$PROJECT" phase9-migration migrate \
  --report-digest "$REPORT_DIGEST" --plan-digest "$PLAN_DIGEST" \
  --backup-path "$BACKUP_DIRECTORY"
```

Migration stops when the report or plan is stale, the backup does not match the
current project, or ownership decisions remain unresolved. It preserves legacy
source files and publishes only after a complete Canon generation is staged.

For operational recovery, build and validate a replacement generation from the
current active snapshot, then publish it with:

```bash
python3 -m data_modules.webnovel --project-root "$PROJECT" phase9-migration \
  replace-generation --generation-id "$GENERATION_ID"
```

Replacement keeps the active semantic activation and effective-history digest.
It rejects missing, corrupt, or semantically different generations.

Filesystem-layout rollback is limited to the owner overlay. Review post-backup
changes first and pass the exact overlay SHA-256 from the migration result as the
expected current file digest. The command blocks when that file changed or when
the active semantic identity no longer matches:

```bash
python3 -m data_modules.webnovel --project-root "$PROJECT" phase9-migration \
  restore-layout --backup-path "$BACKUP_DIRECTORY" \
  --overlay-sha256 "$EXPECTED_OVERLAY_SHA256" \
  --semantic-activation-id "$ACTIVE_SEMANTIC_ID" \
  --effective-history-digest "$ACTIVE_HISTORY_DIGEST"
```

This operation does not restore commits, corrections, activation enrollment,
publication records, or Canon generations.
