# Story projection rebuild

`CHAPTER_COMMIT` files under `.story-system/commits/` are the only chapter-fact recovery source. A rebuild validates the whole commit set before touching projections, resets the owned portions listed below, and replays the same `ChapterCommitService.apply_projection_writers` path used by incremental projection. Run it from the plugin scripts directory with:

```sh
PYTHONPATH=. python3 -m data_modules.projections --project-root /path/to/project rebuild --format text
```

The `EventProjectionRouter.PROJECTION_MANIFEST` is the shared topology source for writer ordering, reset strategy names, and reproducibility class. Rejected commits update state only; they do not create accepted story projections. Chapter numbers need not be continuous: the durable commit creation path permits gaps, so discovery sorts the commits it finds and replays those numbers.

## Projection ownership and reset policy

| Projection | Storage and writer | Input / ownership | Reset boundary and replay | Reproducibility / ordering |
|---|---|---|---|---|
| Event JSON | `.story-system/events/chapter_NNN.events.json`; `EventLogStore` | Accepted commit `accepted_events`; no other production writer found | Remove chapter event mirrors, then rewrite from commits | Strict semantic; chapter order; each write replaces one chapter |
| SQLite events | `.webnovel/index.db:story_events`; `EventLogStore` | Same accepted events | Clear only `story_events`, preserving the shared index DB and every other table | Strict semantic; chapter order; unique event IDs and per-chapter replacement |
| State | `.webnovel/state.json`; `StateProjectionWriter` | Accepted/rejected commits, state deltas, event-derived character/loop/strand updates | Clear `entity_state` and commit-owned progress keys; clear only the known `strand_tracker` projection keys; reset canonical fields on loop rows matched by commit event content; remove protagonist fields named by commit deltas. Other state keys and loop-row annotations are preserved | Strict semantic; normal mode remains ordered; coordinator-only rebuild context allows replay after reset |
| Chapter index | `.webnovel/index.db:chapters, scenes, appearances, state_changes`; `IndexProjectionWriter` | Commit chapter metadata, scenes, appearances, state deltas | Clear only these four story tables; never drop or recreate `index.db` | Strict semantic; upserts and uniqueness prevent repeated rows |
| Entity index | `.webnovel/index.db:entities, aliases, relationships`; `IndexProjectionWriter` plus existing index APIs | Commit entity deltas and relationship data, with legacy/manual index writes also possible | Preserved because the current schema does not identify row ownership. Replay upserts matching commit facts; unrelated or stale legacy rows cannot safely be removed automatically | Incremental upsert is repeatable; a fully clean rebuild of ambiguous legacy rows is intentionally not claimed |
| Summary | `.webnovel/summaries/chNNNN.md`; `SummaryProjectionWriter` | Commit `summary_text`; writer does no model generation | Remove only summary-shaped `chNNNN.md` files and write exact commit text | Strict byte content for each commit summary; ordered by commit |
| Memory | `.webnovel/memory_scratchpad.json`; `MemoryProjectionWriter` / `MemoryWriter` | Deterministic mapping of commit deltas, events, and chapter metadata into memory items | Remove items carrying one of the writer's reserved commit evidence prefixes; preserve entries without those markers and all scratchpad metadata | Semantic projection; timestamps and compaction metadata may vary. Legacy items without writer evidence cannot be distinguished safely and are preserved |
| Vector and BM25 | `.webnovel/vectors.db: vectors, bm25_index, doc_stats`; `VectorProjectionWriter` / `RAGAdapter` | Summary, event, entity-delta, and scene chunks from accepted commits | Remove only rows whose vector `source_file` is `commit:%`, and their BM25/document-stat rows | Regenerable enrichment: embedding service/model can yield different vectors or fail. Replay fails visibly on store errors; retries start by removing known commit chunks |
| Projection run log | `.webnovel/projection_log.jsonl`; `append_projection_run` | Operational record of attempts and outcomes | Preserved and appended to; it is not a story projection | Operational, timestamped, not deterministic |
| Override / debt / review / reader / RAG logs | `.webnovel/index.db` operational tables, including override and debt ledgers, review metrics, `rag_query_log`, tool stats, and checklist scores | Workflow, user, or operational data; amendment proposals may be triggered by accepted events | Preserved. Amendment proposals are idempotently persisted into the operational ledger and are not cleared by projection rebuild | Not part of the rebuildable projection manifest |

The shared `index.db` also contains tables whose provenance is mixed or not recorded. The rebuild does not clear those tables. Likewise, memory entries without the current writer evidence prefixes cannot be reliably classified as commit-owned. These limits are explicit: a successful rebuild means every registered, safely owned projection passed its output validation, not that untagged legacy entity or memory rows were deleted.

## Canon validation and failure behavior

Discovery accepts canonical `chapter_NNN.commit.json` files and their adjacent lock files, rejects other files in the commits directory, duplicate chapter numbers (including differently padded names), unreadable JSON, mismatched filename/meta chapter, unsupported schema/status, and invalid nested chapter artifacts. `projection_status` is stripped from the in-memory validation payload and never treated as Canon. No sequence-gap rule is imposed. An empty commit set is rejected before reset so a wrong or incomplete project root cannot silently erase existing projections.

The coordinator reports the first failed writer with chapter and error, then stops. A later invocation safely resets the registered targets and starts from the first durable commit. It does not rewrite commit files. `projection_log` remains an operational history of both successful and failed runs.

## Use of the rebuild context

The state writer's normal chapter-order guard is unchanged. A context-local rebuild marker is activated only around the full rebuild coordinator's replay loop and is scoped to that resolved project root. It relaxes only the state ordering check; every writer still calls `require_durable_commit_match` and verifies that its payload matches the durable commit on disk.
