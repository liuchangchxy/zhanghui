# Context Provenance Contract

Phase 4 governs context at read time. It does not change chapter commits, migrate legacy rows, rebuild projections, or write back to story state.

## Envelope and output

`data_modules/context_provenance.py` provides a light `ContextItem` envelope:

- `semantic_role`: `CANON`, `INTENT`, `CRAFT`, `OPERATIONAL`, or `UNKNOWN`.
- `source_role`: `COMMIT`, `PROJECTION`, `CONTRACT`, `OUTLINE`, `USER`, `LEGACY`, `RETRIEVAL`, `REVIEW`, `SUMMARY`, or `CONFIG`.
- `source_ref`, optional `chapter`, `provenance_status`, `evidence`, and optional deterministic `fact_key`.

`ContextManager.build_context()` and `MemoryContractAdapter.load_context()` expose `canon`, `intent`, `craft`, `reference`, `context_diagnostics`, and `context_snapshot`. Existing compatibility sections remain available to non-Writer callers. Writer instructions must use the governed sections for facts. Diagnostics are for debugging and review; they are not included in revision model requests. Deterministic structured Intent claims can report `intent_conflict` or `intent_canon_ambiguity` without failing Canon assembly.

## Authority and precedence

For past facts, only accepted durable commits before the target chapter are canonical authority. Deterministic projections may add evidence only when their structured `(entity, field, value, chapter)` agrees with a commit. A projection cannot establish Canon by itself. Summary, memory, and RAG content are not independent authorities. An RAG similarity score is retrieval ranking only.

For future plans, authoritative contracts and outline are Intent. Derived reminders and memory representations are weaker Intent evidence. Conflicting plan records are surfaced for planning resolution and do not fail Canon validation. Craft guidance and review signals remain advisory.

For a deterministic fact key, the latest commit chapter is current. Older commit facts are historical. Conflicting projections and legacy rows are suppressed in favor of Canon and reported in diagnostics. Equal verified facts are presented once with aggregated evidence. Different verified Canon values at the same chapter fail context construction.

## Mixed provenance and freshness

Entity projection facts are compared field by field. Commit-backed name/realm fields may be used as Canon-derived evidence; unmarked fields remain `UNKNOWN`. Legacy aliases may help resolve an input mention but cannot change canonical identity. Relationships follow the same deterministic commit-first rule.

The snapshot records latest accepted pre-target commit chapter and file hash, plus known state/index/vector projection chapters. A state projection behind or ahead of the commit head is not treated as current. Index and vector lag is diagnosed; context assembly never triggers rebuild. Unknown freshness stays unknown.

## Source inventory (current implementation)

| Input | Storage and reader | Classification |
|---|---|---|
| Latest and older accepted commits, events, state/entity deltas | `.story-system/commits`; provenance loader and runtime source loader | Canon authority, ordered by chapter |
| `state.json` fields and progress | `.webnovel/state.json`; ContextManager, memory orchestrator, entity adapter | Commit-matching deterministic facts are projection evidence; unmatched data is Unknown/Legacy |
| Entities, aliases, relationships, chapters, scenes, appearances, state changes | `.webnovel/index.db`; IndexManager, entity/timeline queries | Projection or Unknown according to available evidence; chronology is retained |
| Summaries and story skeleton | `.webnovel/summaries`; ContextManager, memory orchestrator, extract wrapper | Reference projection; useful for historical reading, not authority |
| Memory scratchpad and project memory | `.webnovel/memory/*`, `.webnovel/project_memory.json`; MemoryOrchestrator and ContextManager | Matching evidence may corroborate Canon; unsupported rows remain Unknown; open loops/payoffs are Intent |
| Vector/BM25 hits | `.webnovel/vectors.db`; RAGAdapter and `extract_chapter_context.py` | Reference retrieval. `source_file=commit:*` is verified against an accepted commit; unknown lineage stays Unknown |
| Master/volume/chapter/review contracts and outline/planned nodes | `.story-system/*.json`, outline files; runtime/context builders | Intent or operational review targets; never past facts |
| Promise ledger, open loops, Story Craft foreshadow/timed locks | `state.json.project_info`, memory scratchpad, `state.json.story_craft`; their owning readers | Promise/open-loop creation is a Canon event; payoff, unresolved status and timed target are Intent; craft state is advisory |
| Style, preferences, genre and writing guidance | settings, preferences, project memory and contracts; ContextManager and Context Agent | Craft |
| Reader signals, review results and fulfillment | index operational tables and review/commit artifacts | Operational/review or Intent-satisfaction record; never Canon |
| Legacy fallback and missing sources | compatibility state/index/memory plus runtime fallback metadata | Unknown and diagnostic; cannot override verified Canon |

`webnovel-write` and `webnovel-fast-write` share the Context Agent and governed `load-context` path. `webnovel-revise` now obtains the same governed bundle and passes only the four sections plus snapshot to the revision writer; it omits diagnostics.
