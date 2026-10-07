# Phase 10 Intent / Craft Ownership Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile field ownership and lifecycle for Intent, Craft, Canon-derived obligations, and Workflow while preserving the accepted commit boundary and existing persistence owners.

**Architecture:** Keep Canon event history in accepted commits/effective corrections; derive Canon obligations from that history; retain separate planner and Craft records. Route mutable state through the existing owner overlay for enrolled projects, keep current Story System contract files as authored artifacts, and make Context a provenance-carrying read-only composition.

**Tech Stack:** Python 3, JSON owner overlay and Story System artifacts, existing pytest architecture and data-module suites.

**Spec:** `docs/superpowers/specs/2026-10-07-phase-10-intent-craft-ownership-design.md`

## Global Constraints

- Canon past facts come only from accepted durable CHAPTER_COMMIT and effective correction lineage.
- No unified NarrativeObligation authority, common lifecycle, or new Intent/Craft registry/store/database.
- Canon-derived obligations and planner obligations never synchronize automatically; exact explicit cross-reference only.
- Reuse Phase 9 OwnedStateStore/state-overlay.json for enrolled mutable state; reuse the existing Phase 7 ownership inventory and extend it instead of creating another registry.
- Context composes CANON, INTENT, CRAFT, and REFERENCE with owner/provenance; duplicates and conflicts remain visible.
- Unknown legacy fields remain preserved and non-authoritative until explicit mapping; migrations fail closed and never infer meaning from wording.
- Craft/style/quality heuristics are advisory/score unless an explicit, stable user-constraint binding proves elevation.
- `.claude/plugins/zhanghui/6.4.0/**` remains immutable; `/根源牌序` option B remains unchanged.

## Review Focus

- Accepted event correction changes derived Promise/Open Loop lifecycle while leaving planner ledger bytes unchanged; cover in Task 3.
- Conflicting Planner Promise/Foreshadow and volume/outline copies remain separate with diagnostics; cover in Tasks 2 and 5.
- Mixed `story_craft` and `chapter_meta` fields do not inherit a root-level class; cover in Task 4.
- Enrolled-project direct state.json writes cannot falsely succeed when Context reads the owner overlay; cover in Task 5.
- Craft/style warnings cannot trigger commit rejection or mandatory rewrite, while explicit user constraints and integrity checks retain their own actions; cover in Task 7.

---

## File structure

- Extend `.claude/plugins/zhanghui/docs/ownership-inventory.json` and its existing schema/tests as a governance/test-only writer/reader record. It must not drive runtime authority.
- Extend `.claude/plugins/zhanghui/scripts/data_modules/project_migration.py` for explicit field dispositions and fail-closed legacy migration.
- Extend the existing domain writers in `volume_state.py`, `promise_ledger.py`, `story_craft.py`, `webnovel.py`, `state_manager.py`, and `owned_project_view.py`; do not add another store.
- Extend `memory/writer.py`, `intent_reconciliation.py`, `context_provenance.py`, `context_manager.py`, and existing tests for derived lifecycle and Context composition.
- Align only directly affected review/CLI/skill behavior; leave unrelated gate infrastructure and broad documentation cleanup out of scope.

## Task 1: Extend the existing ownership inventory with Phase 10 field ownership

**Files:**
- Modify: `.claude/plugins/zhanghui/docs/ownership-inventory.json`
- Modify: `.claude/plugins/zhanghui/docs/ownership-inventory.schema.json`
- Modify: `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py`
- Modify: `.claude/plugins/zhanghui/scripts/tests/architecture/ownership_inventory_guard.py` only if current record validation cannot express exact field paths

**Interfaces:**
- Consumes: Current writer/reader/migration record families and exact coordinates.
- Produces: Governance records for planner obligations, Canon-derived obligation projection, Story Craft Intent/Craft subfields, mixed chapter_meta, contract files, Context readers, and direct-write compatibility paths.
- Authority boundary: This inventory detects missing ownership declarations; it does not determine runtime data authority.

- [ ] **Step 1: Add failing architecture cases** for one undeclared `chapter_meta` field path, one writer with no replacement/retirement criterion, and one Context read edge that claims authority from an owner projection.
- [ ] **Step 2: Run the focused ownership inventory test** and confirm the new fixtures fail for the missing record fields.
- [ ] **Step 3: Extend existing inventory records and schema** with exact field/source coordinates, semantic claim, current owner, replacement path, active consumers, evidence, compatibility status, and retirement criterion. Keep all claims scoped to verified code paths.
- [ ] **Step 4: Run the focused architecture tests** for ownership schema, reader coverage, writer coverage, and unqualified authority claims. Confirm all new records validate and missing coordinates remain detected.
- [ ] **Step 5: Review the inventory diff** and confirm it is governance-only, does not add runtime routing, and does not create a second ownership registry.

## Task 2: Preserve planner Promise Ledger as an independent owner

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/promise_ledger.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/volume_state.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/project_migration.py`
- Modify: `.claude/plugins/zhanghui/scripts/tests/unit/test_promise_ledger.py`
- Modify: `.claude/plugins/zhanghui/scripts/tests/unit/test_volume_state.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_project_migration.py`

**Interfaces:**
- Consumes: Existing ForeshadowEntry and PromiseLedger APIs plus owner inventory dispositions.
- Produces: Planner-owned edits to deadline and planner lifecycle only; exact optional Canon cross-reference data; no event-derived resolution mutation.

- [ ] **Step 1: Add failing tests** showing an explicit planner deadline/defer/cancel edit preserves an unrelated Canon reference and that malformed/unknown old ledger fields are preserved as migration conflicts.
- [ ] **Step 2: Run only the Promise Ledger and migration tests** and confirm they fail on the missing owner/provenance or disposition behavior.
- [ ] **Step 3: Add the minimum typed planner operations and exact field mapping** without changing Canon lifecycle or merging ForeshadowEntry with event-derived rows. Preserve existing legal status values unless an implementation review approves a migration.
- [ ] **Step 4: Add conflict tests** proving Promise Ledger and Story Craft foreshadow rows with matching prose are not linked or merged without exact IDs.
- [ ] **Step 5: Run the focused Promise Ledger, VolumeStateManager, and project migration tests** and confirm source data remains unchanged on dry-run or ambiguous mapping.

## Task 3: Keep Canon-derived obligation lifecycle reproducible and separate

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/intent_reconciliation.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/memory/writer.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/memory/schema.py` only if current projection evidence fields cannot preserve required origin
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_intent_reconciliation.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py` or the closest existing MemoryWriter tests

**Interfaces:**
- Consumes: Effective accepted event sequence and exact correction-resolved history.
- Produces: Deterministic derived Promise/Open Loop rows keyed by source event identity with source and resolution event IDs.
- Forbidden effect: No write to planner Promise Ledger, Story Craft Intent, or Canon event source.

- [ ] **Step 1: Add failing event replay tests** for rejected event exclusion, accepted create/close transitions, correction removal of a create event, and preservation of planner ledger bytes.
- [ ] **Step 2: Run focused intent reconciliation and projection tests** and verify the correction/planner-isolation cases fail before implementation.
- [ ] **Step 3: Ensure the projection is rebuilt exclusively from effective accepted events** and carries explicit CANON_DERIVED_OBLIGATION provenance and source IDs.
- [ ] **Step 4: Add replay/idempotency and ambiguous legacy-link cases**; require diagnostics rather than choosing a matching row.
- [ ] **Step 5: Run the focused event reconciliation, memory writer, and projection rebuild tests** and confirm planner-owned data is unchanged.

## Task 4: Split Story Craft by exact field ownership

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/story_craft.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/project_migration.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/consistency_finding_adapters.py`
- Modify: `.claude/plugins/zhanghui/scripts/tests/test_story_craft.py`
- Modify: `.claude/plugins/zhanghui/scripts/tests/test_story_craft_extended.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_project_migration.py`

**Interfaces:**
- Consumes: Existing Craft functions and explicit field map ratified from the R0 spec.
- Produces: Distinct Intent/Craft/derived-reference field operations under the existing `story_craft` owner root, with unknown values preserved as UNKNOWN.
- Canon interaction: Occurrence fields are Canon only when linked to an accepted commit; old unlinked data stays UNKNOWN/reference.

- [ ] **Step 1: Add failing field-level tests** for foreshadow plan vs payoff occurrence, timed-lock deadline vs fulfilled claim, character arc target vs quality, thematic target vs chapter manifestation, rhythm/volume-beat advice, and chapter_meta plan/craft/factual fields.
- [ ] **Step 2: Run focused Story Craft and project migration tests** and record which current root-level classifications fail.
- [ ] **Step 3: Add exact field ownership validation** to existing Story Craft operations and migration inventory; do not add a new store or reclassify unknown children from their parent key.
- [ ] **Step 4: Add malformed and unknown nested-shape tests** proving the entire unrecognized source is preserved and reported without partial promotion.
- [ ] **Step 5: Run focused Story Craft, state validation, and migration tests** and verify the supported legacy shapes retain a deterministic disposition.

## Task 5: Route planner and Story Craft writers through the active owner path

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/webnovel.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/state_manager.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/owned_project_view.py`
- Modify: `.claude/plugins/zhanghui/scripts/init_project.py` only for directly affected activation-managed writes
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_ownership_writer_bypass.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_state_manager_extra.py`

**Interfaces:**
- Consumes: Existing `OwnedStateStore.write_owner_values`, active pinned view, and domain-specific Story Craft/VolumeStateManager mutations.
- Produces: One effective write to the existing owner overlay for enrolled projects; explicit base-only compatibility for non-enrolled projects.
- Failure behavior: An enrolled-project legacy-only write fails or reports compatibility-only without claiming persistence.

- [ ] **Step 1: Add failing bypass tests** for each activation-managed CLI mutation and one VolumeStateManager mutation; assert the overlay is the only effective target.
- [ ] **Step 2: Run the owner writer bypass and StateManager tests** and verify direct state.json writes are detected.
- [ ] **Step 3: Route enrolled writes through OwnedStateStore** while preserving the current legacy path only for base-only projects. Keep the domain writer responsible for allowed field transitions.
- [ ] **Step 4: Add read-after-write tests** using `OwnedProjectView.pin_active` and a test activation fixture; assert Context's effective state sees the new value and the legacy file does not win.
- [ ] **Step 5: Run focused owner routing, migration and CLI tests**; verify a failed overlay write never produces a success result.

## Task 6: Add owner/provenance-aware Context composition and conflict diagnostics

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/context_provenance.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/context_manager.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/memory_contract_adapter.py`
- Modify: `.claude/plugins/zhanghui/agents/context-agent.md`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_contract_adapter.py`

**Interfaces:**
- Consumes: Existing ContextItem source roles, exact field ownership map, canonical event projections, and current contract/outline files.
- Produces: Read-only CANON/INTENT/CRAFT/REFERENCE composition with owner reference, source provenance, stable identity when available, and deterministic diagnostics.
- Authority boundary: Context may rank/display items; it may not persist, resolve, satisfy, or rewrite them.

- [ ] **Step 1: Add failing Context tests** for duplicate planner sources, Canon-derived Promise origin, Intent-vs-Craft disagreement, missing owner metadata, and same-ID/different-value conflict.
- [ ] **Step 2: Run focused Context tests** and confirm generic `unverified_plan` and whole-root Craft grouping do not satisfy the new cases.
- [ ] **Step 3: Compose each recognized field separately**; represent Canon-derived obligations under INTENT with their distinct semantic class and event provenance; retain unknown items in REFERENCE/UNKNOWN.
- [ ] **Step 4: Add deterministic conflict diagnostics** that retain all source references and never select by timestamp, filename, source order, or similarity.
- [ ] **Step 5: Run Context and memory adapter tests** and verify the public Context compatibility shape follows the reviewed R0 decision.

## Task 7: Remove local craft-only hard blocks that bypass the shared policy

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/review_pipeline.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/webnovel.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/chunked_write.py` only for the overdue Intent prewrite behavior
- Modify: `.claude/plugins/zhanghui/skills/webnovel-write/SKILL.md`
- Modify: `.claude/plugins/zhanghui/skills/webnovel-plan/SKILL.md` only where Craft counts are presented as blockers
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_write_gates.py`
- Modify: `.claude/plugins/zhanghui/scripts/tests/test_story_craft_extended.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_prompt_integrity.py`

**Interfaces:**
- Consumes: Existing GateSeverityPolicy classification and stable user-constraint contract binding.
- Produces: Craft/style/quality advisory or score outcomes by default; explicit user constraints and plan artifact integrity retain separate actions.

- [ ] **Step 1: Add failing end-to-end gate tests** for overdue timed locks, rhythm threshold, missing hook type, unfilled beats, and an explicit user hard constraint.
- [ ] **Step 2: Run focused write gate and skill integrity tests** and confirm only craft-only rows currently trigger mandatory rewrite/prewrite exit.
- [ ] **Step 3: Route craft findings through existing policy semantics** and split plan-artifact/workflow errors from Craft recommendations. Do not refactor unrelated GateSeverityPolicy classes.
- [ ] **Step 4: Update active skill prose** so advisory Craft output never mandates a chapter rewrite; explicit contract constraints, Canon integrity and missing required artifacts remain clearly distinct.
- [ ] **Step 5: Run focused gate, adapter, and prompt-integrity tests** and verify a Craft score cannot change commit acceptance.

## Task 8: Complete fail-closed migration, rollback, and compatibility retirement guards

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/project_migration.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/owned_project_view.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_project_migration.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_owned_project_view.py`
- Modify: `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py`
- Modify: directly affected active Phase 10 architecture docs only after behavior is verified

**Interfaces:**
- Consumes: Ratified exact field mappings, current Phase 9 preflight/backup/restore, and existing ownership inventory.
- Produces: Base-only and enrolled migration plans that report unknown/ambiguous fields, preserve source hashes, write only to the assigned existing owner, and support rollback.
- Retirement: A writer is guarded/deprecated only after all active consumers and compatibility criteria in the spec are verified.

- [ ] **Step 1: Add failing dry-run and rollback cases** for base-only projects, Phase 9 enrolled projects, nested Promise Ledger, mixed chapter_meta, malformed story_craft, unknown fields, and `/根源牌序` legacy/reference values.
- [ ] **Step 2: Run focused Phase 9 migration and owner-view tests** and verify unknown/ambiguous fields block authority promotion.
- [ ] **Step 3: Extend the existing migration preflight and backup manifest** to identify exact per-field destination, source digest, unresolved decision, and rollback source; do not delete legacy files.
- [ ] **Step 4: Add atomic apply/restore tests** proving a failure restores overlay/source bytes and never mutates commits or correction history.
- [ ] **Step 5: Run focused migration, owner-view, and ownership inventory suites**; confirm base-only compatibility and enrolled read-after-write behavior.

## Task 9: Verify acceptance and prepare review evidence

**Files:**
- Modify: `docs/superpowers/specs/2026-10-07-phase-10-intent-craft-ownership-design.md` only for approved implementation clarifications
- Modify: `docs/superpowers/acceptance/2026-10-07-phase-10-final-acceptance.md`
- Verify: Exact files from Tasks 1–8; no versioned snapshot paths

- [ ] **Step 1: Run the focused Phase 10 tests from Tasks 1–8** and record exact commands and results.
- [ ] **Step 2: Run ownership writer/reader coverage** and confirm every protected writer/reader remains classified in the existing inventory.
- [ ] **Step 3: Run diff checks and inspect the exact changed-path list**; reject changes to `.claude/plugins/zhanghui/6.4.0/**`, Issue #1, or unrelated production paths.
- [ ] **Step 4: Verify active Context and migration behavior** on both a base-only fixture and an enrolled fixture, including rollback and explicit conflict output.
- [ ] **Step 5: Record implementation SHA, test evidence, known limits, and independent reviewer verdict separately; do not claim acceptance until a reviewer supplies that verdict.**

## Review and handoff

This is an implementation plan candidate tied to Design R0. It is not authorization to execute. Before implementation, independent review must settle the open questions listed in the spec, especially planner-only fulfillment wording, exact legacy schemas, Context owner envelope shape, and chapter_meta field provenance. No production work was performed while creating this plan.
