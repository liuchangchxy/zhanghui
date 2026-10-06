---
title: "Phase 7 — Legacy Ownership, Documentation & Compatibility Closure"
type: "phase-plan"
status: "🟢 待开始"
created: "2026-10-06"
parent: "../specs/2026-10-06-phase-7-ownership-compatibility-closure-design.md"
children: []
tags: ["phase-7", "ownership", "compatibility", "tdd"]
---

# Phase 7 — Legacy Ownership, Documentation & Compatibility Closure — Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` in the current Local checkout. Do not create a Worktree, fork, delegate, hand off, or start another phase.

**Goal:** Make active write ownership explicit and machine-testable, converge active documentation, and define evidence-based CHANGES and plugin compatibility decisions without destructive migration.

**Architecture:** First add the inventory contract and fail-first drift tests, then classify real writers and reproduce any actual Canon bypass before changing runtime guards. Keep document drift and runtime writer coverage as separate test surfaces. Shadow-measure CHANGES without changing commit decisions; retain the existing protocol and compatibility behavior.

**Tech Stack:** Python, pytest, JSON Schema Draft 2020-12, repository Markdown, local acceptance commands (no new runtime dependency).

---

## Execution rules

- Baseline is `e9156f57fe79da63731cbc69c1e5f716c4feb577`. Reconfirm branch, HEAD, clean state, and the preserved stash before implementation.
- Keep implementation changes in `.claude/plugins/zhanghui/`, with only the scoped compatibility update to `docs/architecture/phase-2-reconciliation.md` if needed, the specifically named Phase 7 acceptance manifest, and (only if existing release/version policy requires a bump) `.claude-plugin/marketplace.json` plus `.claude/plugins/zhanghui/.claude-plugin/plugin.json` to keep release identity aligned. Never modify `.claude/plugins/zhanghui/6.4.0/**`. Do not invent a version; inspect repository convention first.
- Keep five version axes distinct: canonical source-tree path/Git identity; source-tree package version; marketplace catalog version; installed host plugin version; project data schema version. A repository manifest cannot prove installed-plugin adoption.
- Follow RED → run and observe failure → GREEN → run and observe pass for each testable step. For documentation steps, first add a failing active-doc assertion, then correct the document and rerun it.
- Runtime guard work is conditional. Reproduce a real bypass through the actual production API/CLI against a valid Story System project before editing a guard. If no bypass reproduces, add regression coverage only and record “no runtime guard change”.
- Never treat a direct write as invalid solely because it targets `state.json` or `index.db`; preserve Intent, Craft, Workflow, setup, migration, and legacy compatibility owners as specified by inventory.
- No user project migration, ChapterCommit major change, CHANGES deletion, full rebuild, amend/supersede implementation, Worktree, PR, or Phase 8+ work.

## Phase A — Inventory contract and writer coverage guard (must precede broad documentation edits)

### Step 1: Add failing inventory contract tests

**Files:** Create `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py`.

1. **RED:** Write tests for missing required fields, unknown domain/status values, duplicate IDs in each record family, unresolved module/API coordinates, absent mode behavior, missing consumers/replacement/retirement criterion, missing evidence, reader sources/authority/fallback, and migration safety fields.
2. **Run → verify FAIL:** Run the new test file; it must fail because the inventory/schema are not present.
3. **GREEN:** Keep validation dependency-free using standard-library JSON plus a repository-owned validator. Model separate `writers[]`, `readers[]`, and `migrations[]`; `writer.active_consumers` is not reader inventory.
4. **Run → verify PASS:** Run the focused file and confirm each invalid fixture is rejected for the intended reason.
5. **REFACTOR:** Keep fixtures small and failure messages pointing to a writer ID/field.

### Step 2: Define and validate the JSON Schema

**Files:** Create `.claude/plugins/zhanghui/docs/ownership-inventory.schema.json`; update `scripts/tests/architecture/test_ownership_inventory.py`.

1. **RED:** Add schema assertions for Draft 2020-12, required top-level `writers`, `readers`, and `migrations` arrays, controlled data-domain/lifecycle/authority enums, and mode-specific reader source, authority, condition, and fallback objects.
2. **Run → verify FAIL:** Run the focused tests and confirm they fail without the schema.
3. **GREEN:** Add the normative schema from design §3.1. Require stable IDs, exact implementation coordinates, per-mode behavior/source/authority/fallback, active consumers, replacement/null, retirement criterion, and source evidence.
4. **Run → verify PASS:** Validate a good minimal record and reject one malformed record per required/enum group.
5. **REFACTOR:** Keep schema validation independent from plugin runtime imports.

### Step 3: Seed the ownership inventory from real source paths

**Files:** Create `.claude/plugins/zhanghui/docs/ownership-inventory.json`; update the inventory tests.

1. **RED:** Add assertions that all required domains appear, including `CANON_COMMIT`, `EVENTS`, every projection domain, `INTENT`, `CRAFT`, `WORKFLOW_METADATA`, `MIGRATION`, and `COMPATIBILITY`.
2. **Run → verify FAIL:** Confirm the tests fail before inventory data exists.
3. **GREEN:** Seed justified writer, reader, and migration records from the verified Phase 7 source audit. Cover Context/runtime source assembly; query/resume; write/plan/review; state/index/summary/memory/vector; Story System commit/projection; legacy fallback. Record mode-specific source, authority, fallback, consumers, and retirement evidence. Include StateManager, IndexManager, SQLStateManager, `update_state.py`, Story Craft, VolumeState/PromiseLedger, consistency apply, EventLogStore, init, and migration paths.
4. **Run → verify PASS:** Assert every inventory path/symbol resolves and every source anchor exists.
5. **REFACTOR:** Split a record when one API writes data with different owners or runtime behavior.

### Step 4: Add fail-first writer and reader coverage scanners

**Files:** Create `.claude/plugins/zhanghui/scripts/tests/architecture/ownership_inventory_guard.py`; update `test_ownership_inventory.py`.

1. **RED:** Add synthetic unregistered writer and reader fixtures. The reader fixture reads legacy state and claims Canon authority. Assert writer and reader coverage fail with path/symbol/authority diagnostics; assert production runtime importing/loading inventory is rejected.
2. **Run → verify FAIL:** Run the test and capture the unregistered-writer diagnostic.
3. **GREEN:** Scan canonical production source for protected writes and known reads, resolve constant/simple aliases, and report unresolved targets. Compare candidates with exact writer/reader coordinates and required reader families. Add a separate static isolation check forbidding shipped runtime imports/reads and runtime decisions based on inventory fields; runtime authority stays in actual services/guards/contracts. Require exact reason-coded exceptions and tests for dynamic targets.
4. **Run → verify PASS:** Add explicit inventory records for synthetic candidates and confirm they pass. Confirm the false Canon reader remains rejected, a Story System divergent legacy sentinel is not returned as Canon, and a legacy-mode fallback reports legacy compatibility. Confirm a reason-coded log/cache/test-fixture exclusion is not treated as a story writer.
5. **REFACTOR:** Keep the sink family registry narrow and explicit; reject broad directory exclusions.

### Step 5: Prove legitimate writer classes remain distinct

**Files:** Update `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py`; add focused tests under existing StateManager, IndexManager/SQLStateManager, EventLogStore, consistency, and migration test directories only where a missing behavior assertion is found.

1. **RED:** Add tests asserting classification and current behavior for commit-owned facts, review/workflow metadata, Story Craft/Intent writes, setup/migration writes, EventLogStore projection writes, and legacy-only compatibility.
2. **Run → verify FAIL:** Run the focused writer tests and identify any unrepresented or misclassified path.
3. **GREEN:** Add only the missing inventory/test assertions. Do not change production behavior merely to make classifications uniform.
4. **Run → verify PASS:** Verify Canon direct writes fail in Story System mode where guarded, valid non-Canon operations remain possible, and legacy mode behavior stays explicitly tested.
5. **REFACTOR:** Ensure the test names identify the project mode and semantic domain.

### Step 6: Test the real-bypass decision gate

**Files:** Create `.claude/plugins/zhanghui/scripts/data_modules/tests/test_ownership_writer_bypass.py`; update the ownership inventory only if evidence changes classification.

1. **Probe:** Construct a valid Story System project fixture and call each remaining candidate Canon writer through its real public API/CLI; compare Canon-owned bytes/rows before and after without a matching durable commit.
2. **Decision:** If a mutation reproduces, write a regression that expects rejection and verify it fails before the guard. If no mutation reproduces, write guard-coverage tests that pass against current behavior and record “no production guard change”.
3. **GREEN (reproduction only):** Add the narrowest pre-side-effect guard at the owning boundary; keep Intent/Craft/Workflow/migration pathways available.
4. **Run → verify PASS:** Re-run the exact reproduction and relevant projection/workflow regression tests. If no bypass reproduced, run all guard-coverage tests and verify no production source changed.
5. **REFACTOR:** No source-wide write prohibition and no guard based only on filename/extension.

### Step 5A: Add reader-family coverage and authority regressions

**Files:** Reader coverage helper and `test_ownership_inventory.py`; focused Context/query/resume/projection/legacy reader fixtures.

1. **RED:** Omit each required reader family in turn and add an unregistered legacy-state reader claiming `CANON_AUTHORITY`; assert both fail. Add a Story System fixture with divergent durable-commit and legacy-state sentinels.
2. **Run → verify FAIL:** Confirm family omissions and authority mismatch are reported.
3. **GREEN:** Inventory each reader's mode-specific source, authority, condition, fallback, active consumers, replacement, and retirement criterion. Story System Canon reads resolve to accepted commit or commit-verified projections; legacy source cannot be silently promoted.
4. **Run → verify PASS:** Confirm all required families are covered, false Canon authority fails, mode behavior is correct, and production code has no inventory dependency.
5. **REFACTOR:** Keep reader coverage, writer coverage, and active-document drift independently reported.

## Phase B — Active-document drift guard (still before document edits)

### Step 7: Add failing active-document assertions

**Files:** Create `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_documentation.py`.

1. **RED:** Assert marketplace-selected active docs contain the current positive owner contract and flag synthetic unqualified claims that Data Agent alone writes projections or that state.json is Canon authority.
2. **Run → verify FAIL:** Confirm the test catches the existing review-skill statement and synthetic bad write-skill completion wording.
3. **GREEN:** Implement path selection from `.claude-plugin/marketplace.json` and narrowly scoped assertion rules for active skills, agents, loaded references, and architecture docs.
4. **Run → verify PASS:** Labeled historical examples pass only when marked legacy/historical and not used as active instructions.
5. **REFACTOR:** Keep document drift tests separate from runtime writer coverage tests.

### Step 8: Validate historical-text handling and snapshot exclusion

**Files:** Update `test_ownership_documentation.py`.

1. **RED:** Add a fixture proving a mislabeled active paragraph fails, a clearly labeled historical workflow description passes, and nested `6.4.0` text does not become part of active-source evaluation.
2. **Run → verify FAIL:** Run the focused test before implementing the source-selection/historical-label rules.
3. **GREEN:** Use marketplace-selected canonical root as the active-path boundary; require an explicit legacy label for old paths.
4. **Run → verify PASS:** Confirm active root changes alter the test set and nested historical files remain excluded.
5. **REFACTOR:** Report the exact failing path and ownership claim.

## Phase C — Direct-writer audit and active documentation convergence

### Step 9: Complete the mode-aware direct-writer matrix

**Files:** `.claude/plugins/zhanghui/docs/ownership-inventory.json`; ownership inventory tests.

1. **RED:** Add a required-family checklist from Issue #1: StateManager, IndexManager, SQLStateManager, every `update_state.py` option group, story_craft, volume_state/promise_ledger, consistency apply, event-store direct API, init and migration paths.
2. **Run → verify FAIL:** Confirm any missing family fails the inventory test.
3. **GREEN:** Record each API/caller, data fields/tables, owner, SS mode, legacy mode, active consumers, lifecycle status, replacement, and retirement evidence. Split `update_state.py` options so foreshadow/strand options are not assumed to share Canon semantics solely because the current CLI groups them behind one mode guard.
4. **Run → verify PASS:** Assert no family is marked deprecated without a replacement and measurable retirement criterion.
5. **REFACTOR:** Split mixed-domain APIs into distinct writer records.

### Step 10: Correct write and review ownership language

**Files:** `.claude/plugins/zhanghui/skills/webnovel-write/SKILL.md`; `.claude/plugins/zhanghui/skills/webnovel-review/SKILL.md`; `test_ownership_documentation.py`.

1. **RED:** Add exact regressions for the review skill's false unique-writer claim and the write completion gate's actor-ambiguous “回写” condition.
2. **Run → verify FAIL:** Confirm both assertions fail against the current active documents.
3. **GREEN:** State that Data Agent only creates temporary artifacts and ChapterCommitService/projection writers own commit-backed persistence. Phrase completion as verification of the expected projections for the accepted commit or successful retry; keep failure visible.
4. **Run → verify PASS:** Confirm the outdated ownership phrases are gone and all five projection outputs remain covered by completion verification.
5. **REFACTOR:** Do not duplicate competing ownership tables inside the two skills; link to the canonical ownership contract.

### Step 11: Converge plan and init instructions

**Files:** `skills/webnovel-plan/SKILL.md`; `skills/webnovel-init/SKILL.md`; documentation drift tests.

1. **RED:** Add checks distinguishing planning/Craft/Intent writes and project setup from Canon commits.
2. **Run → verify FAIL:** Verify stale or ambiguous claims are caught.
3. **GREEN:** Label Promise Ledger, Story Craft, and initialization mutations by owner/domain; retain valid planning and setup operations.
4. **Run → verify PASS:** Verify none asserts those writes create chapter Canon.
5. **REFACTOR:** Link procedural detail to inventory/architecture docs.

### Step 12: Converge query, resume, agent, and shared references

**Files:** `.claude/plugins/zhanghui/skills/webnovel-query/SKILL.md`; `skills/webnovel-query/references/system-data-flow.md`; `skills/webnovel-query/references/tag-specification.md`; `skills/webnovel-init/references/system-data-flow.md`; `skills/webnovel-resume/SKILL.md`; `skills/webnovel-resume/references/system-data-flow.md`; `skills/webnovel-resume/references/workflow-resume.md`; `agents/context-agent.md`; `agents/data-agent.md`; `references/shared/core-constraints.md`; `.claude/plugins/zhanghui/docs/context-provenance.md`; `docs/architecture/architecture-constitution.md`; documentation drift tests.

1. **RED:** Add per-path regression cases for active data-source, write-owner, and recovery claims, including all three system-data-flow documents, the tag specification, and shared core constraints.
2. **Run → verify FAIL:** Run tests before edits to identify the remaining inaccurate or unclear active assertions.
3. **GREEN:** Correct active claims; preserve old query behavior only as clearly labeled legacy compatibility; describe resume from durable commit plus workflow metadata, and distinguish author-selected prose rollback from Canon/projection recovery.
4. **Run → verify PASS:** Scan all active paths and run focused documentation tests.
5. **REFACTOR:** Keep one canonical flow reference; other skills link to it rather than copying mutable owner prose.

## Phase D — CHANGES shadow evidence and compatibility contract

### Step 13: Add failing shadow-report fixtures

**Files:** Create `.claude/plugins/zhanghui/scripts/data_modules/changes_shadow_report.py`, `.claude/plugins/zhanghui/scripts/changes_shadow_report.py`, and `.claude/plugins/zhanghui/scripts/data_modules/tests/test_changes_shadow_report.py`.

1. **RED:** Add synthetic cases for match, proposal-only, observation-only, hard conflict, opaque category, stale hash/schema, and extraction infrastructure failure.
2. **Run → verify FAIL:** Confirm there is no read-only category-level report yet.
3. **GREEN:** Implement an opt-in analyzer consuming existing artifacts only. It must not write Canon, update ledgers, change workflow action, or affect ChapterCommitService decisions.
4. **Run → verify PASS:** Assert hashes/version binding, numerator/denominator behavior, opaque separation, and infrastructure/semantic separation.
5. **REFACTOR:** Store aggregate category data by default; require explicit export for prose excerpts.

### Step 14: Verify shadow mode cannot affect commit decisions

**Files:** Shadow-report tests; ChapterCommitService/CLI integration regression only if a hook was introduced.

1. **RED:** Assert the analyzer has no commit/policy side effect and cannot modify chapter, CHANGES, extraction, reconciliation, or project state bytes.
2. **Run → verify FAIL:** Use sentinel files and before/after hashes.
3. **GREEN:** Keep the tool read-only and outside commit call paths; require explicit inputs and stale-artifact rejection.
4. **Run → verify PASS:** Re-run sentinel and commit behavior checks; compare the generated report on repeated inputs.
5. **REFACTOR:** Keep “measurement” commands visibly separate from write gates.

### Step 15: Encode metrics, sample protocol, and adoption/rollback gate

**Files:** Shadow report schema/module/tests; `docs/architecture/phase-2-reconciliation.md` or a linked Phase 7 compatibility section.

1. **RED:** Add report assertions for per-mode/category coverage, frozen proposal and observation denominators, matches, one-sided changes, conflict adjudication, opaque/unmapped items, stale/schema failures, and migration compatibility.
2. **Run → verify FAIL:** Confirm incomplete reports do not claim full coverage or eligibility to discuss retirement.
3. **GREEN:** Record the pilot protocol (target 60 chapters/3 opted-in projects; below either target or missing mode/category cell is `INSUFFICIENT`), frozen denominators that retain opaque/unmapped items, category-level ≥95% coverage only to open retirement discussion, full adjudication of conflict candidates, zero known false hard blocks, and rollback/migration evidence from the spec.
4. **Run → verify PASS:** Test threshold boundaries and the “insufficient sample” result.
5. **REFACTOR:** Treat thresholds as eligibility to discuss a separate decision, never as automatic deletion or policy change.

## Phase E — Plugin/version compatibility and final acceptance

### Step 16: Add source-resolution, version-axis, and mode-matrix tests

**Files:** Update `.claude-plugin/marketplace.json` and `.claude/plugins/zhanghui/.claude-plugin/plugin.json` only if existing release/version policy requires a bump; update `test_ownership_inventory.py` and `test_ownership_documentation.py`; compatibility documentation. Never modify `.claude/plugins/zhanghui/6.4.0/**`.

1. **RED:** Test that marketplace source resolves to `.claude/plugins/zhanghui`, canonical source-tree identity/path, package version, marketplace version, installed host version, and project schema version are not conflated, the nested `6.4.0` snapshot is not active, and project modes distinguish new Story System, existing Story System, legacy, and mixed/partial projects.
2. **Run → verify FAIL:** Confirm unverified source/version or implicit mixed-mode selection is rejected.
3. **GREEN:** First inspect repository version policy; do not guess a version. If required, update exactly the two named manifests and test their agreement. Document installed-plugin update/reload checks and a non-destructive existing-project upgrade/migration contract.
4. **Run → verify PASS:** Validate canonical source, snapshot exclusion, and all supported-mode fixtures.
5. **REFACTOR:** Do not claim the repository can know the user's installed plugin version without a host-side check.

### Step 17: Test migration/retirement evidence contract

**Files:** Compatibility/migration schema tests; inventory tests; architecture documentation.

1. **RED:** Add fixtures rejecting a migration without stable ID, source/target, mode predicate, backup, idempotency, postcondition, rollback, ambiguous-row report, unsupported-commit-schema rejection, and no-op plugin upgrade behavior for unchanged project formats.
2. **Run → verify FAIL:** Run the tests before defining the record contract.
3. **GREEN:** Define the migration evidence record and retirement checklist. Do not execute migrations or remove compatibility paths in Phase 7.
4. **Run → verify PASS:** Test a complete record and reject each missing safety/evidence field.
5. **REFACTOR:** Distinguish source-tree version selection, installed plugin update, and project data migration as separate compatibility axes.

### Step 18: Bind acceptance without a self-referential SHA

**Files:** Create `docs/superpowers/acceptance/2026-10-06-phase-7-final-acceptance.md`.

1. **RED:** Add manifest completeness tests/checklist for baseline SHA, exact commands, focused inventory/drift suites, real-bypass verdicts, CHANGES denominators/corpus counts/limitations, source/mode matrix, reviewer verdict, and known limits. Results and `tested_implementation_head` are absent from the implementation template.
2. **Run → verify FAIL:** Confirm the manifest is incomplete before results are recorded.
3. **GREEN/H1:** Commit all implementation, tests, docs, inventory, any policy-required two-manifest version update, and a result-free acceptance template as immutable implementation commit H1.
4. **Test H1:** Run complete acceptance on H1. Record exact commands, node IDs, corpus denominators and limitations (`INSUFFICIENT` where applicable), reviewer evidence, and results outside the tracked record while validating.
5. **Record/H2:** Update only the acceptance record with `tested_implementation_head: H1` and results; commit that file alone as record-only H2. Verify `git diff H1 H2 -- production/runtime paths` is empty and H1/H2 production/runtime trees are identical.
6. **Bind final result:** Use a Git note or Issue/PR completion record to record H2 or later merge SHA and any required final-head verification. Never claim a tracked file contains its own commit SHA.
7. **Verify:** Check manifest completeness, exact H1 binding, H2 record-only scope, acceptance results, and `git diff --check`.
8. **REFACTOR:** Keep the acceptance record separate from implementation state and avoid self-reference.

## Required verification commands (final values fixed when implementation starts)

At minimum, the Phase 7 implementation must define and run commands for:

```bash
PYTHONPATH=.claude/plugins/zhanghui/scripts pytest \
  .claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py \
  .claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_documentation.py -q
```

Plus focused production API regressions for every guarded writer family changed, CHANGES shadow-report tests, relevant projection rebuild/context/commit suites, active-skill prompt integrity, the exact Phase 7 final acceptance manifest command, and:

```bash
git diff --check
```

The manifest must name exact test files and show collection counts/node IDs; broad suite totals alone are insufficient.

## Current turn deliverable boundary

This file is an implementation plan only. The current design turn creates and commits only this plan and the matching Phase 7 design spec. No implementation steps above are executed as part of creating this plan.
