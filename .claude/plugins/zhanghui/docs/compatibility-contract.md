# Phase 7 compatibility contract

## Version axes

These values describe different things and must be checked independently:

| Axis | Repository evidence | What it does not prove |
|---|---|---|
| Git/source-tree identity | Canonical source is `.claude/plugins/zhanghui`; record the exact Git commit | Which plugin a host has loaded |
| Plugin package version | `.claude/plugins/zhanghui/.claude-plugin/plugin.json` | Marketplace catalog state or project data format |
| Marketplace catalog version | `.claude-plugin/marketplace.json` selects `./.claude/plugins/zhanghui` | Installed host version |
| Installed host plugin version | Check the plugin manager's installed entry and active source on that host, then restart/reload if required | Project schema migration state |
| Project data schema version | Existing commit records declare `story-system/v1`; projection payloads use their own schema such as `webnovel-projections/v1` | Plugin package or installed host version |

The current repository's package and marketplace versions are both `6.4.0`. The release helper `scripts/sync_plugin_version.py` synchronizes those manifests together with the README release row and badge when performing a release. No repository rule requires a version bump for every source-tree commit. Phase 7 is not a release, so it leaves both manifests unchanged. The nested `6.4.0/` directory is a historical snapshot and is not the marketplace-selected source.

## Supported project modes

| Mode | Read/write contract | Upgrade behavior |
|---|---|---|
| New Story System | Accepted chapter facts go through `chapter-commit`; projections are derived from accepted commits. Intent, Craft, and workflow data keep their own owners. | Initialize contracts and defaults without fabricating chapter facts. |
| Existing Story System | Accepted commits remain immutable. Current compatible formats need no data rewrite on plugin update. | Preflight the commit and projection schemas. If no disk format changed, take a no-op path. Unsupported commit schemas fail with an actionable compatibility error; they are never rewritten by plugin upgrade. |
| Legacy | Existing supported legacy behavior remains available, including explicitly classified legacy writers/readers. | A source or package update alone does not migrate project files. No automatic opt-in to Story System occurs. |
| Mixed/partial | Detect missing or contradictory mode markers explicitly. Do not choose Canon authority from whichever file happens to exist. | Stop in a named diagnostic state until an explicit repair/migration is designed and approved. |

## Migration safety

Phase 7 performs no user-project migration. Any future existing-project upgrade must be non-destructive, additive and idempotent, preserve every accepted commit byte, and skip writes when no on-disk format change is needed. Legacy-to-Story-System conversion requires a later explicit opt-in design with a dry-run conflict report, backup, preservation of legacy data, contract/bootstrap checks, provenance verification, and tested rollback. Ambiguous records are listed for a human; migration code must not silently pick a winner.

The current `migrate_story_craft.py` makes a `.bak` before writing, but replaces a non-object `story_craft` field with defaults. Treat that path as guarded compatibility behavior: inspect and preserve the backup, and do not claim it is a lossless Story System migration. `migrate_state_to_sqlite` is likewise an explicit conversion path, not a side effect of plugin update.

## Release and host check

For a release, use the repository version-sync helper and its check mode so the package manifest, marketplace catalog, README badge, and current release row agree. For a normal source-tree change, record Git identity without inventing a package version. After a host update, verify the installed plugin entry and source path in that host, then reload/restart where the host requires it. Repository tests cannot observe an external host's installed version or prove user adoption.
