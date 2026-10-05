# Phase 5A Intent Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile canonical Open Loop and Promise events into identity-aware, provenance-linked state and memory projections while keeping the Promise Ledger planner-owned.

**Architecture:** Use each canonical create event's persisted `event_id` as the loop/promise identity. Explicit close/payoff events reference that ID; legacy events use exact-content linkage only when there is exactly one eligible candidate, with all ambiguity and orphan cases recorded as projection diagnostics. Rebuild replays accepted CHAPTER_COMMITs to restore state and memory lifecycle without editing Canon.

**Tech Stack:** Python 3, Pydantic event schema, JSON StateProjectionWriter and memory scratchpad projections, pytest, existing projection rebuild.

**Spec:** `docs/superpowers/specs/2026-10-05-phase-5a-intent-identity-design.md`

## Global Constraints

- Do not create `NarrativeObligation` or unify Promise, Open Loop, Foreshadow, or Timed Lock.
- Do not modify historical CHAPTER_COMMIT files or bump the CHAPTER_COMMIT major version.
- Do not fuzzy-match, embedding-match, or LLM-match event linkage. Data Agent must not guess IDs; the current prose-only production path has no stable source ID unless an upstream structured artifact supplies one.
- Preserve Phase 3 rebuild and Phase 4 Canon/Intent separation.
- Keep `project_info.promise_ledger` planning-owned; Canon events never create or status-mutate ledger entries. A planner-paid-off row never synthesizes a Canon event.
- Keep changes in `.claude/plugins/zhanghui/`; do not edit the versioned 6.4.0 copy or anything under `references/`.
- Branch: `codex/intent-identity-reconciliation`; base: `4bb0e805ee330112544788df7c4e0703c6d20585`.
- Do not create a PR, merge main, or begin Phase 6. Push the completed branch and await independent Review.

## Review Focus

- Two loops with identical text remain distinct; a close keyed by ID resolves only the selected loop.
- Legacy close with zero or multiple exact candidates stays unlinked and cannot fabricate or resolve a loop.
- Rebuild preserves manually evidenced memory rows while replacing only commit-owned loop lifecycle rows.
- Payoff-only Promise events and unlinked legacy payoffs never produce active promise memory.
- Targeted rebuild does not erase non-Canon planner fields or mutate `project_info.promise_ledger` statuses.

---

### Task 1: Make identity/link resolution deterministic and diagnostic

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/intent_reconciliation.py`
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_intent_reconciliation.py`
- Modify: `.claude/plugins/zhanghui/agents/data-agent.md` to prohibit inferred linkage and explain explicit-ID/diagnostic behavior
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/chapter_commit_schema.py` only if an additive accepted-event helper/schema normalization is required; preserve existing schema version

**Interfaces:**
- Consumes: normalized accepted StoryEvent dictionaries with `event_id`, `chapter`, `event_type`, `subject`, and `payload`.
- Produces: a pure function `reconcile_intent_events(events: list[dict]) -> dict` returning ordered `open_loops`, `reader_promises`, and `diagnostics` records. Each lifecycle row uses `identity_id`, `source_event_id`, `source_chapter`, semantic status, optional resolution fields, and `link_status`.
- A loop create's `identity_id` is its `event_id`. Explicit close reads `payload.loop_id` (and accepted alias `source_event_id` if normalized); it never chooses by content.
- Legacy fallback considers only previous unmatched creates with exact trimmed content and only links when the candidate count is one. Current Data Agent has no structured intent-ID input; absent an explicitly supplied ID, a new close/payoff receives no guessed link and depends on this legacy rule or an unlinked diagnostic.

- [ ] **Step 1: Add failing pure-function tests** for create identity, explicit close, same-text duplicate creates, reworded linked close, exact unique legacy close, zero-candidate orphan, multiple-candidate ambiguity, repeated close, explicit nonexistent ID, Promise create/payoff, payoff-only, and stable event ordering.
- [ ] **Step 2: Run the focused test file** with `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_intent_reconciliation.py -q`; confirm the new imports/function fail before implementation.
- [ ] **Step 3: Implement deterministic one-pass reconciliation** with no storage I/O. Preserve both event IDs (source create and resolution event), exact candidates, and stable diagnostic reason codes (`orphan_close`, `ambiguous_legacy_close`, `duplicate_resolution`, `unlinked_payoff`). Never mutate input events.
- [ ] **Step 4: Run the focused test file** and confirm all cases pass, including replaying the same input twice yields equal output.
- [ ] **Step 5: Update Data Agent instructions** to carry an ID only when explicitly present in structured input; never infer it from prose. Report close/payoff without an ID for deterministic resolver handling.
- [ ] **Step 6: Commit the pure reconciliation module, tests and producer instruction** as `feat: reconcile intent event identity`.

### Task 2: Project identity-aware Open Loop lifecycle into State

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/intent_reconciliation.py` to seed resolution from previously projected identity rows during incremental apply
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/state_projection_writer.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/projection_rebuild.py`
- Runtime output: `.story-system/projections/intent-diagnostics.json` (generated per project; do not check in runtime data)
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/event_projection_router.py` to register diagnostic reset ownership in the existing manifest
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py`
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py`

**Interfaces:**
- Consumes: Task 1 reconciliation output and the existing accepted durable commit payload.
- Produces: `plot_threads.foreshadowing` identity rows keyed by `loop_id`, carrying `source_event_id`, `source_chapter`, status, and optional `resolution_event_id`/`resolved_chapter`.
- Rebuild reset must identify commit-owned rows by canonical IDs/provenance, not by a set of contents. Legacy content-only rows may be upgraded only from a unique deterministic commit match; otherwise make them non-authoritative if they may duplicate a verified Canon identity.

- [ ] **Step 1: Add failing State projection tests** for two equal-content create IDs, explicit close of only one, reworded close by ID, unique legacy close, ambiguous legacy close, orphan close (no fabricated resolved row), and idempotent in-order rebuild.
- [ ] **Step 2: Run those named tests** with `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py -k 'open_loop or foreshadow' -q` and `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py -k rebuild -q`; verify expected failures.
- [ ] **Step 3: Replace content identity in StateProjectionWriter** with Task 1 results. Preserve rows that do not carry commit projection provenance and avoid deleting manual rows during reset.
- [ ] **Step 4: Update rebuild reset/replay** so State upgrades only uniquely attributable legacy rows, resets Canon-owned identity rows, and replay reconstructs exact identity/lifecycle; keep old event payloads untouched.
- [ ] **Step 5: Register diagnostics reset in the existing projection manifest** and regenerate the complete diagnostics file from validated accepted commits after replay, including an empty file; do not add a second coordinator.
- [ ] **Step 6: Add tests proving stale diagnostics disappear and unchanged rebuilds are byte-identical.**
- [ ] **Step 7: Re-run the focused State and rebuild tests** and verify exact duplicate-content and orphan behavior.
- [ ] **Step 8: Commit** as `feat: project open loop identity into state`.

### Task 3: Project lifecycle and provenance into memory and Context

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/memory/writer.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/memory/schema.py` only if status/category compatibility requires it
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/projection_rebuild.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/memory_contract_adapter.py` only if Context needs explicit provenance fields or filtering beyond active status
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py`
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_writer.py`
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py` or `.claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_contract.py`

**Interfaces:**
- Consumes: Task 1 `open_loops` lifecycle rows plus commit provenance markers.
- Produces: one memory item per canonical loop identity, `payload.loop_id`, source/resolution event IDs and chapters, semantic `lifecycle_status`, `link_status`, and active/non-active `MemoryItem.status`.
- Existing manually evidenced memory rows remain preserved by `_upsert`/controlled rebuild semantics.
- Context's existing `get_open_loops(status="active")` remains the urgent loop source but filters legacy duplicates when verified Canon identity/status supersedes them.

- [ ] **Step 1: Add failing tests** for create item identity based on event ID, resolve exactly one same-content row, reworded close, active query exclusion for resolved rows, unlinked/orphan diagnostic exclusion, and preservation of manual evidence during rebuild.
- [ ] **Step 2: Run focused tests** with `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py -k 'memory or open_loop' -q`, `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_writer.py -q`, and the selected Context test; confirm the failures.
- [ ] **Step 3: Update `MemoryWriter.apply_commit_projection()`** to use Task 1 records, replacing content/chapter loop IDs only for new commit-owned projections. Keep terminal semantic lifecycle in payload and use a non-active compatible memory status for resolved rows.
- [ ] **Step 4: Persist deterministic reconciliation diagnostics** in the rebuild-owned diagnostics output with event IDs, chapter, candidate IDs and reason. Do not add them to Writer story facts or Context urgent loop results.
- [ ] **Step 5: Update rebuild reset** to upgrade uniquely attributable content-derived rows in place, remove/replay only commit-owned lifecycle items and diagnostics, and preserve manual/unknown legacy items without letting duplicates retain active authority.
- [ ] **Step 6: Add a legacy projection → rebuild test** for old content+chapter item IDs and State rows; assert no duplicate active obligation remains when Canon resolves that loop.
- [ ] **Step 7: Add a Context fallback test** proving an ambiguous legacy duplicate cannot become active alongside a verified Canon row.
- [ ] **Step 8: Run focused memory and Context tests** and verify Context returns only unresolved active loops.
- [ ] **Step 9: Commit** as `feat: reconcile open loop memory lifecycle`.

### Task 4: Separate Promise creation and payoff projections; preserve planning ownership

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/memory/writer.py`
- Preserve without modifying: `.claude/plugins/zhanghui/scripts/data_modules/promise_ledger.py` and `volume_state.py`; Canon projection must not call their mutation APIs
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_writer.py`
- Test: `.claude/plugins/zhanghui/scripts/tests/unit/test_promise_ledger.py`
- Test: `.claude/plugins/zhanghui/scripts/tests/unit/test_volume_state.py`

**Interfaces:**
- Consumes: Task 1 reader Promise lifecycle records.
- Produces: Promise memory items keyed by create `event_id` with creation/resolution provenance and `active|paid_off` semantic lifecycle.
- The Promise Ledger schema and planner ID/status transitions remain unchanged; optional `promise_id` cross-reference stays only in event-derived Memory projection payload.

- [ ] **Step 1: Add failing tests** proving create is active, linked payoff makes only the matching row paid off, payoff-only/unlinked payoff adds no active row, legacy exact-unique payoff resolves only its unique candidate, and explicit Promise Ledger upsert/read round-trips provenance while event projection does not mutate ledger status or create rows.
- [ ] **Step 2: Run focused Promise/memory tests** and verify failures.
- [ ] **Step 3: Implement Promise projection lifecycle** from Task 1 output. For existing rows with no safe link, retain current data conservatively and emit diagnostics; do not create a new active item from payoff.
- [ ] **Step 4: Keep Promise Ledger planning-owned**; confirm event projection never invokes its mutation APIs and an explicit ledger row's status/bytes remain unchanged when its related Canon Promise projects.
- [ ] **Step 5: Run the existing Promise Ledger and VolumeStateManager tests** to verify planner lifecycle behavior is unchanged and manual `paid_off` remains a planning-only transition.
- [ ] **Step 6: Commit** as `feat: distinguish promise creation and payoff`.

### Task 5: Rebuild, regression, docs, and delivery

**Files:**
- Modify: `.claude/plugins/zhanghui/docs/projection-rebuild.md`
- Modify: `.claude/plugins/zhanghui/docs/context-provenance.md`
- Modify: relevant tests in `.claude/plugins/zhanghui/scripts/data_modules/tests/`

**Interfaces:**
- Consumes: Tasks 1–4 complete projections and rebuild behavior.
- Produces: documented identity/provenance rules, legacy limitations, diagnostic location, and repeatable regression evidence.

- [ ] **Step 1: Add end-to-end fixtures** with creates in chapters 1 and 2 (same content), a linked reworded close for only chapter 2's event ID, an unlinked ambiguous legacy close, one promise create plus explicitly linked payoff, one payoff-only event, and legacy content-derived State/Memory rows for loops that later resolve.
- [ ] **Step 2: Run the end-to-end fixture before rebuilding** and assert State/Memory/Context expected lifecycle plus no ledger mutation and no duplicate active legacy obligations.
- [ ] **Step 3: Run projection rebuild twice**; compare State-owned lifecycle, memory-owned rows, and diagnostic outputs for deterministic equality; assert stale diagnostic entries are removed after the accepted commit fixture changes. Confirm Canon commit files are byte-identical.
- [ ] **Step 4: Run regressions**: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_writer.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_contract_adapter.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py .claude/plugins/zhanghui/scripts/tests/unit/test_promise_ledger.py .claude/plugins/zhanghui/scripts/tests/unit/test_volume_state.py -q`.
- [ ] **Step 5: Run Phase 3/4 regressions** covering canonical commit validation, rebuild determinism, Context provenance and Canon/Intent separation using the repository's existing focused tests; capture exact results.
- [ ] **Step 6: Update projection and Context docs** to say event create IDs own loop identity, close links explicitly, legacy matching is exact-and-unique only, Context urgent loops are active memory projection records, and Promise Ledger remains planning-owned.
- [ ] **Step 7: Run `python -m compileall -q .claude/plugins/zhanghui/scripts/data_modules` and `git diff --check`; fix any reported issues.**
- [ ] **Step 8: Review the complete diff against every acceptance criterion and non-goal; confirm no versioned plugin, references, Canon history, PR, main merge, or Phase 6 change.**
- [ ] **Step 9: Commit documentation/regression follow-up** with a concise Phase 5A message.
- [ ] **Step 10: Push `codex/intent-identity-reconciliation` and report commits, tests, limitations, and independent Review handoff; do not create a PR or merge.**
