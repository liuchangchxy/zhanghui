# Story System Architecture Constitution (Phase 0)

This document establishes the ownership rules for chapter facts and derived data. Phase 1 implements the chapter commit boundary; broader state, craft, and workflow migrations remain out of scope.

## Data classes and authority

| Class | Examples | Authority and write rule |
| --- | --- | --- |
| Canon / Past | Accepted events, chapter facts, established entity and plot changes | The durable `.story-system/commits/chapter_NNN.commit.json` record is the canonical transaction for a chapter. Its validated fact payload includes `accepted_events`, `state_deltas`, `entity_deltas`, and any other schema-defined chapter facts. Only `ChapterCommitService` creates this immutable record. |
| Intent | Outlines, chapter goals, story contracts, plans, unresolved obligations | These describe desired or pending work. They may guide drafting and validation but cannot assert that a story event happened. |
| Craft | Voice profiles, style samples, craft guidance | Advisory by default. Craft data may inform prose, but cannot override Canon or silently rewrite it. |
| Projection | `.webnovel/state.json`, `index.db`, chapter event JSON, summaries, memory, vectors, views | Derived and rebuildable. Writers consume the matching durable chapter commit; they do not establish facts. Projection status belongs in `.webnovel/projection_log.jsonl`, not in the canonical commit payload. |
| Infrastructure | Locks, caches, runtime configuration, execution logs | Operational state. It may support execution and recovery but is not story truth. |

The commit file is the transaction boundary and source for replay. The per-chapter event JSON and SQLite `story_events` table mirror its accepted events. Compatibility state, indexes, summaries, memory, vector data, and views are projections. A missing projection run means `pending`, not that the commit is absent or invalid.

## Ownership

- The writer produces chapter prose. The Data Agent extracts proposed artifacts into temporary files; it does not write canonical facts or projections.
- `chapter-commit` validates the review, fulfillment, disambiguation, and extraction artifacts, then persists the chapter transaction before invoking any projection writer.
- Projection writers may run only against a durable matching commit. Retry reads that commit and regenerates projections; it does not repeat extraction or drafting.
- Context and query components read commits, contracts, and projections. They do not write Canon.
- Consistency checks are read-only. In Story System projects, `consistency apply` may regenerate filesystem-only derived views but does not persist patch mutations to `state.json`; patch updates can be inferred from chapter execution and are not safe as a second state writer. Legacy projects retain the previous apply behavior.
- Explicit setup, planning, review-checkpoint, and management commands may maintain configuration, Intent, or workflow metadata. In Story System mode, legacy `StateManager` fact mutators (entity/current, alias, appearance, relationship, state change, progress, committed status, and chapter metadata) fail before mutation; `save_state` and its SQLite sync helpers reject any pending Canon buffers before either store is written. Drafted/reviewed status and disambiguation review signals remain operational metadata. Direct `SQLStateManager` fact APIs and `IndexManager` chapter/entity/relationship writers also fail fast; the latter are available to the canonical `IndexProjectionWriter` only inside its projection write scope. Mixed projects fail fast for legacy fact writes, while non-Canon planning and review metadata operations remain available.

## Transaction and recovery

1. Validate the proposed chapter artifacts and conflict policy.
2. Persist the canonical commit atomically.
3. Apply event, state, index, summary, memory, and vector projections; record each outcome in the projection log.
4. If a projection fails or its log entry is missing, retry from the durable commit. Do not recreate facts from mutable projections.

Ordinary chapter commits reject an existing chapter commit. `--on-conflict=overwrite` is rejected for existing canonical commits; changing accepted history requires a future amend/supersede workflow. `skip` loads the existing durable commit and retries projections from it. New commits and first-time state projections must progress in increasing chapter order; a retry for a chapter older than the projected state is refused rather than allowed to roll state backward. Range replay runs chapters in ascending order but does not reset/rebuild existing projections; historical full repair remains a migration concern. A rejected commit records a rejected decision and is not accepted story history.

## Phase boundary

Phase 0 defines the vocabulary and ownership rules. Phase 1 establishes commit-before-projection ordering, moves projection status out of canonical payloads, makes event stores projection-only, rejects canonical replacement, and prevents consistency apply from persisting patch state in Story System projects. Historical projection repair/rebuild and amendments remain migration/future-phase concerns. Moving all compatibility stores, adding event sourcing, or changing Craft/gate policy requires a later phase.
