# Phase 5A — Intent Identity, Provenance & Resolution Reconciliation

## Goal and scope

Give Open Loop and reader Promise projections deterministic identity and provenance, and reconcile their lifecycle from accepted CHAPTER_COMMIT events. Canonical events remain past facts; loop/promise lifecycle and `project_info.promise_ledger` remain Intent. Do not create `NarrativeObligation`, combine Promise/Open Loop/Foreshadow/Timed Lock, rewrite Canon history, fuzzy-match content, upgrade CHAPTER_COMMIT, or start Phase 6.

## Verified current behavior

- `chapter_commit_schema.normalize_accepted_events()` validates/normalizes extracted events before commit construction. Missing `event_id` is generated as `evt-ch{chapter}-{index}-{sha1(normalized event JSON)[:10]}`. The normalized accepted event is stored in the durable CHAPTER_COMMIT extraction payload; rebuild validates and replays those same events, so the persisted ID is stable for replay. Explicit event IDs are retained.
- `open_loop_created` and `open_loop_closed` event payloads are open dictionaries. Existing close events need not carry any future field. Their `event_id` is a Canon event identity, but is not itself a loop identity; proposed semantics use the create event's ID as the loop identity.
- Current production instructions give Data Agent prose-only chapter input and ask it to emit create/close event types; no producer passes a stable existing loop/promise ID into extraction. Commit normalization generates an ID for each event but cannot infer that a later close should reference an earlier event. Phase 5A will not ask Data Agent to infer it. Linkage is available only when an upstream structured artifact explicitly supplies the source ID. Otherwise exact-unique legacy resolution applies; if it cannot safely resolve, the event is unlinked and diagnosed.
- `StateProjectionWriter._apply_foreshadowing()` currently matches `content` / `description` / subject exactly. Create deduplicates by content; close resolves the first exact-content row, or inserts a resolved row when none exists. This can conflate duplicate content and invent a lifecycle for orphan closes.
- `MemoryWriter.apply_commit_projection()` currently projects `open_loop_created` into `memory_scratchpad.json.open_loops`, using a content-derived memory item ID; it ignores `open_loop_closed`. `MemoryItem` already has `payload`, `status`, `source_chapter`, and `evidence`. `MemoryProjectionWriter` delegates accepted commits to it.
- `MemoryContractAdapter.load_context()` gets urgent loops from `get_open_loops(status="active")`, which queries the memory scratchpad category `open_loop`; it returns the first three. Thus Context currently consumes the memory projection, not `state.json.plot_threads.foreshadowing`.
- `promise_created` and `promise_paid_off` currently both become `reader_promises` memory facts and active `reader_promise` items; no resolution linkage is applied. Separately, `VolumeStateManager` owns `state.json.project_info.promise_ledger`. Entries are `ForeshadowEntry` records with `id`, type, depth, planted/payoff chapter and volume, status (`pending|advanced|paid_off|overdue`), notes and audit log. Explicit planner APIs mutate and persist this Intent ledger. Chapter event projection does not currently write it.
- Projection rebuild validates accepted durable commits, resets/replays state and memory projections in canonical order. It removes commit-provenance memory rows before replay; state reset currently identifies canonical loops by content.

## Design

### Ownership and data flow

Keep accepted `StoryEvent`s in durable CHAPTER_COMMIT as Canon. Open Loop and Promise lifecycle are Intent projections with source/resolution links back to those events. `MemoryWriter` owns the read-model lifecycle projection; `StateProjectionWriter` keeps a compatibility foreshadowing view with identity/provenance fields. `project_info.promise_ledger` remains planner-owned: event projections may attach optional event provenance/resolution metadata to a matching explicit ledger entry only when a deterministic link is already supplied; they do not create entries, choose a ledger entry by prose, or alter its planned status. Where there is no explicit ledger ID/link, the event-derived reader-promise memory projection carries the lifecycle.

No automatic synchronization from Canon into Promise Ledger. A promise event records a past utterance/action; a Promise Ledger row is a planned future target. `promise_paid_off` is itself a Canon event and updates the event-derived Promise memory row to paid off when its `promise_id`/`source_event_id` identifies a prior creation. It must never create a new active promise.

### Open Loop identity and event linkage

- Stable loop identity: `loop_id = open_loop_created.event_id`. The event ID already exists in canonical history and is replay-stable. It is not a new CHAPTER_COMMIT version or a new obligation ontology.
- New explicit close event: payload includes `loop_id` equal to the create event ID. Optional `source_event_id` may be accepted as an alias only if the implementation normalizes it to `loop_id`. Preserve the close event's own event ID as resolution provenance.
- New create projections carry `loop_id`, `source_event_id` (the same create event ID), `source_chapter`, and current status. New close projections carry `resolution_event_id` and `resolved_chapter` on the matching row.
- Duplicate wording is harmless when IDs differ. A linked close closes exactly one identity even when other loops share content. Reworded closes work because content is not the linkage key.
- A second create with identical wording remains a separate loop. Do not content-dedupe identity-bearing rows.

### Legacy compatibility and safe association

- Legacy creates: use their already persisted canonical `event_id` as the stable identity. No backfill into CHAPTER_COMMIT is required.
- Legacy closes lacking `loop_id`: resolve only if an exact normalized content key maps to exactly one eligible unmatched prior create in canonical chapter/event order. Attach a projection-only `legacy_exact_unique` link and diagnostic; do not mutate the old event. If there are zero or multiple candidates, preserve a resolution record as `unlinked`/`orphan_close` diagnostic and do not close any loop or fabricate a resolved loop row. Do not use semantic/reworded similarity.
- Legacy duplicate create events with identical exact content stay distinct. An old close against that ambiguous key is unlinked. Manual resolution is outside this phase.
- A close that explicitly references a nonexistent create ID is `orphan_close`; it cannot change a row. A close targeting an already resolved loop is recorded as a duplicate resolution diagnostic and does not change lifecycle.
- Keep unknown/legacy memory items without canonical event provenance conservative: do not infer a create-to-close mapping. Preserve them as legacy context only under existing behavior; they are not rewritten or deleted by the new reconciliation.

### Projection contracts

**State (`plot_threads.foreshadowing`)**: identity-bearing rows include `loop_id`, `content`, `status` (`active|resolved`), `source_event_id`, `source_chapter`, optional `resolution_event_id`, `resolved_chapter`, target/tier fields. During rebuild, derive legacy content-only rows from canonical commits, remove or upgrade only rows whose deterministic content/chapter/source evidence identifies one canonical create, and replay by ID. If multiple creates match, do not assign an arbitrary ID: mark the legacy row non-authoritative for active Context and retain its legacy/unlinked diagnostic. Preserve unrelated manually curated state. Remove current content-set reset as the lifecycle identity mechanism.

**Memory (`open_loops`)**: item identity is deterministic from `loop_id` rather than content/chapter tuple. Store `payload.loop_id`, `source_event_id`, `resolution_event_id`, `resolved_chapter`, `link_status` (`linked|legacy_exact_unique|unlinked|orphan_close` as applicable), and content/urgency/planted chapter. `MemoryItem.status` is `active` while unresolved and a non-active terminal status (`outdated` is existing-compatible) after payoff; payload retains semantic `lifecycle_status=resolved` to avoid confusing memory retention status with story status. Active Context query then naturally excludes resolved loops. Before replacing old content-derived items, rebuild maps commit evidence to an exact single canonical create; matching rows are consumed/upgraded into the event-ID keyed row. Ambiguous or unprovable old rows remain legacy/unlinked and are made non-authoritative for active retrieval when a verified Canon row covers their source evidence. Unrelated legacy rows remain fallback context only when no verified Canon row supersedes them. Context de-duplicates by source event/identity and cannot let a legacy duplicate reactivate a verified resolved row. Store diagnostics at `.story-system/projections/intent-diagnostics.json`, a deterministic JSON projection. Its owner is `ProjectionRebuild` through the existing `EventProjectionRouter.PROJECTION_MANIFEST` reset topology: add an `intent_diagnostics` reset entry; the existing coordinator resets it before replay, then regenerates the complete file from validated accepted commits after replay, including an empty document when there are no findings. Rebuild replaces the same owned output, cannot retain stale diagnostics, and never edits source events.

**Promise memory**: deterministic identity derives from `promise_created.event_id`; store `source_event_id`, optional ledger `promise_id`, `resolution_event_id`, `source_chapter`, `resolved_chapter`, `lifecycle_status=active|paid_off`, and linkage status. `MemoryItem.status` active only for unresolved promises. A payoff references `promise_id` or `source_event_id`; legacy payoff can associate only by unique exact content against a prior unmatched creation, otherwise is unlinked diagnostic and does not create a promise item. `promise_paid_off` without a safe target never appears as active promise memory.

**Promise Ledger**: preserve the existing schema, planning fields and methods unchanged. Promise event provenance stays on the event-derived reader-promise Memory projection, where an explicitly supplied `promise_id` may be retained as a cross-reference. Projection must not set/advance/payoff/overdue the ledger based solely on Canon events. A planner's manual `paid_off` transition does not synthesize a Canon event.

### Rebuild and Context behavior

Rebuild processes validated accepted commits by chapter and accepted-event order, creates rows keyed by create event IDs, applies explicit links, then applies legacy exact-unique matching. It produces the same active/resolved lifecycle, provenance, and diagnostics on repeat rebuild. Rejected commits do not participate. Rebuild clears/replays Canon-owned loop/promise memory and state data without rewriting Canon or deleting unlinked legacy rows.

Context continues to source urgent loops from `MemoryContractAdapter.get_open_loops(status="active")`, now backed by identity-aware memory rows. Verified Canon-linked rows have authority; legacy rows are fallback-only and are suppressed when deterministic source evidence maps them to a verified Canon identity, including when that Canon identity is resolved. Ambiguous legacy rows cannot coexist as active authority with verified rows they may duplicate. It exposes only active unresolved loops. Resolved and orphan-only records stay out of urgent loop output. Diagnostics remain available through projection diagnostics, not injected as story facts.

## Acceptance criteria

1. Open Loop identity is the canonical create `event_id`; close references that identity, and event identity differs from loop ID only for resolution events.
2. Legacy create IDs work as identity without CHAPTER_COMMIT edits; legacy close is compatible only through unique exact content, otherwise diagnosed unlinked.
3. Duplicate content creates distinct rows; a linked or reworded close closes only its referenced create; no fuzzy matching occurs.
4. State and Memory projections expose source/resolution event IDs and chapters; resolved loops are not returned by Context urgent-loop query.
5. Rebuild reproduces state, memory, and diagnostics deterministically from accepted commits; old Canon bytes remain untouched.
6. Promise created/paid-off lifecycles remain distinct; payoff never creates an active promise.
7. `project_info.promise_ledger` remains planning-owned and is never automatically created or status-mutated by Canon projection.
8. Orphan, ambiguous, duplicate resolution, and unlinked payoff are observable diagnostics and do not silently bind.
9. Phase 3 rebuild's existing coordinator/manifest resets diagnostics and regenerates them from accepted commits on every rebuild; no second coordinator exists.
10. Legacy content-derived State/Memory rows do not produce duplicate active obligations after rebuild when canonical evidence identifies or supersedes them; unresolved legacy ambiguity cannot shadow verified Canon lifecycle.
11. The production chain does not ask Data Agent to guess stable IDs. Explicit IDs flow from structured inputs; absent those, close/payoff is exact-unique legacy-linked or diagnosed unlinked.
12. Phase 4 Canon/Intent boundaries continue to hold.

## Migration and non-goals

No data migration command and no bulk legacy relinking. Existing Canon events are read as written; memory/state Canon-owned views are rebuilt on demand through the established rebuild operation. Legacy records lacking enough evidence remain legacy/unlinked. No `NarrativeObligation`, unified Intent model, Story Craft `foreshadow_chain` change, timed lock/gate/outline/character-arc changes, embedding/LLM linkage, broad legacy cleanup, or CHAPTER_COMMIT major version.

## Risks and mitigations

- Generated IDs depend on event order and normalized payload. Once committed they are stable; future edits cannot alter them because Canon is immutable. Use persisted IDs, never regenerate for history.
- Exact text normalization can itself accidentally broaden matching. Limit normalization to trim plus Unicode normalization already specified in implementation tests; do not casefold or remove punctuation unless demonstrated safe, and require one candidate.
- Old memory items may have content-derived IDs and mixed provenance. Canon evidence upgrades uniquely attributable rows; manual/legacy evidence is preserved and cannot override verified lifecycle in Context.
- Promise Ledger records can represent foreshadow or callback rather than reader promise; do not infer type from prose or update the ledger without an explicit identifier.

## Verified code paths

- `.claude/plugins/zhanghui/scripts/data_modules/chapter_commit_schema.py`
- `.claude/plugins/zhanghui/scripts/data_modules/story_event_schema.py`
- `.claude/plugins/zhanghui/scripts/data_modules/state_projection_writer.py`
- `.claude/plugins/zhanghui/scripts/data_modules/memory/writer.py`
- `.claude/plugins/zhanghui/scripts/data_modules/memory/schema.py`
- `.claude/plugins/zhanghui/scripts/data_modules/memory/store.py`
- `.claude/plugins/zhanghui/scripts/data_modules/memory_contract_adapter.py`
- `.claude/plugins/zhanghui/scripts/data_modules/promise_ledger.py`
- `.claude/plugins/zhanghui/scripts/data_modules/volume_state.py`
- `.claude/plugins/zhanghui/scripts/data_modules/projection_rebuild.py`
