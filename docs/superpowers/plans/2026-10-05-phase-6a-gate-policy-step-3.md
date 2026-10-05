---
title: "Step Plan 3 — Existing Legacy Veto Migration"
type: "step-plan"
status: "🟢 待开始"
created: "2026-10-05"
parent: "2026-10-05-phase-6a-gate-policy-phase.md"
children: []
tags: ["legacy-adapter", "craft-review", "integration"]
---

# Step Plan 3 — Existing Legacy Veto Migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development`.

**Goal:** Migrate only existing review, fulfillment, disambiguation, and changes/reconciliation veto inputs to normalized findings. P1–P7 consistency adapters remain mapping contracts and pure adapter tests; they are not connected to review or commit production paths in Phase 6A.

**Architecture:** A registry keyed by checker/gate and artifact type maps structured legacy values to findings. The actual Craft path is `run_craft_checks → ReviewIssue → review artifact → ChapterCommit policy`; its stable gate/subject/evidence metadata carries `CRAFT_HEURISTIC` provenance, while display labels never grant blocking authority. Existing fulfillment, disambiguation, and changes/reconciliation findings keep their validated structured mappings. For Changes Gate, only registered failures with structured `severity="blocking"` and stable location evidence can map to HARD_INTEGRITY; advisory, missing, or unknown severity stays non-vetoing, and R8 remains a heuristic advisory. P1–P7 have a complete deterministic mapping contract and pure adapter tests only. User constraints are read from existing Story System contract node metadata.

**Tech Stack:** Python 3, Pydantic, pytest, existing consistency `Patch` records and Story System JSON contracts.

**Spec:** `docs/superpowers/specs/2026-10-05-phase-6a-shared-gate-findings-design.md`

---

## Task 1: Build deterministic legacy artifact adapters

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/gate_finding_adapters.py`
- Create: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_finding_adapters.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/review_schema.py` to carry checker gate/provenance fields without treating `blocking` as authority
- Modify: `.claude/plugins/zhanghui/scripts/review_pipeline.py` to emit stable structured subject/evidence metadata for Story Craft checks and label them `CRAFT_HEURISTIC`
- Test: `.claude/plugins/zhanghui/scripts/tests/integration/test_review_with_craft.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/story_contracts.py` only to validate/preserve optional user-constraint metadata on existing contract nodes; do not add a registry
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contracts.py`
- Read compatibility surfaces: `.claude/plugins/zhanghui/scripts/data_modules/chapter_commit_schema.py`, `review_schema.py`, `artifact_validator.py`

**Interfaces:**
- `adapt_legacy_artifacts(*, chapter, review, fulfillment, disambiguation, gate_registry) -> list[DetectedFinding]`
- Registry keys are exact `(checker_id, gate_id, artifact_type)` tuples; no message/description parsing.
- `LLM_REVIEW.blocking=true` is only a candidate signal and cannot directly yield a hard severity. Story Craft-generated timed-lock, pacing, beat, hook, and style findings carry `CRAFT_HEURISTIC` provenance and map only to `ADVISORY`/`SCORE`.
- Pacing blockers→CRAFT/LEGACY_UNKNOWN/ADVISORY; structured unresolved disambiguation→DISAMBIGUATION/HUMAN_DECISION; missed planner nodes→INTENT_FULFILLMENT/ADVISORY or SCORE; count-only legacy blockers yield a diagnostic and the registered gate default, never invented N findings.

- [ ] **Step 1: Write failing adapter/integration tests** for pacing blocker, pending disambiguation, planner missed node including `must_cover_nodes`, count-only review, unknown checker ID, and message text that contradicts its structured gate ID.
- [ ] **Step 2: Run the adapter and Craft integration tests and verify failure.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_finding_adapters.py .claude/plugins/zhanghui/scripts/tests/integration/test_review_with_craft.py -q`
Expected: FAIL because adapter provenance and structured Craft source metadata are absent.

- [ ] **Step 3: Implement the exact-key registry and typed mapping.** Use existing artifact type and gate identity; preserve evidence pointers and source authority. Never inspect display prose. Extend `ReviewIssue` with optional structured source metadata. Have `run_craft_checks()` retain its existing display lists and add structured check records with stable gate/subject IDs and typed evidence (timed-lock subject uses its persisted lock ID; chapter/rhythm rules use stable rule and chapter IDs). In `_inject_craft_issues`, mark generated rows `gate_id="story_craft.heuristic"`, `authority=CRAFT_HEURISTIC`, `explicitness=UNKNOWN`, and `blocking=False` regardless of display strings. Adapters map this provenance to advisory/score even when the old display text says BLOCKER.
- [ ] **Step 4: Add explicit-user metadata resolution tests.** Prove current master/chapter/volume/review contract layers preserve an optional node `metadata` object through loading/merging. A node only becomes a hard user constraint if it has `authority=USER_EXPLICIT`, `explicitness=EXPLICIT`, stable `constraint_id`, and non-empty `source_ref`; any missing field keeps it non-hard. If current contract representation cannot preserve these fields, extend only that existing node schema/merge path; do not create a global registry.
- [ ] **Step 5: Run adapter tests and verify all mappings.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_finding_adapters.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contracts.py .claude/plugins/zhanghui/scripts/tests/integration/test_review_with_craft.py -q`
Expected: PASS; text-only differences do not change classification.

## Task 2: Define and test P1–P7 consistency mapping contract (no production wiring)

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/consistency_finding_adapters.py`
- Create: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py`
- Read: `.claude/plugins/zhanghui/scripts/consistency/patches/p1_foreshadow_dag.py` through `p7_derived_views.py`

**Interfaces:**
- Adapter fixtures use structured P1–P7 mapping inputs to specify a future contract; Phase 6A does not extend production `Blocker` or P1–P7 producer output.
- The mapping contract uses a stable rule key, logical subject, and structured evidence. None is inferred from `message` or `fix_hint`.
- `P1_P7_MAPPING` has exactly seven entries keyed by stable patch IDs; each declares issue-code→gate-ID mapping, category/authority/explicitness mapping, structured evidence extractor, and policy rule ID. Gate IDs are granular (stable patch name + issue_code), not just `P1` and not prose.
- `adapt_consistency_patch(patch_result, chapter_scope) -> list[DetectedFinding]` emits findings only from typed issue code, stable subject ID, and structured evidence. `finding_id` uses shared stable identity (gate + subject + chapter/workflow scope); evidence values only affect `evidence_fingerprint` / attempt fingerprint.
- If a veto-relevant blocker lacks a known issue code, stable subject, or structured evidence required by its registered mapping, emit a non-deduplicable diagnostic/advisory compatibility finding; it cannot hard-veto, identify overrides, or drive rewrite-loop identity.

- [ ] **Step 1: Add failing mapping contract tests** asserting P1–P7 completeness, granular unique gate IDs, stable subject identity, evidence changes updating fingerprints but not finding_id, multiple subjects in one patch/chapter receiving distinct IDs, and representative mapping outcomes. Assert production `Blocker` remains limited to its four legacy fields; missing structured identity is diagnostic/advisory only.
- [ ] **Step 2: Run and verify the tests fail.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py -q`
Expected: FAIL because the mapping contract is absent.

- [ ] **Step 3: Implement the pure mapping table only.** Use exact `(patch, issue_code)` contract mappings and typed fixture fields only; never inspect `message` or `fix_hint`. Do not edit `Blocker`, P1–P7 producers, CLI output, or production callers. Preserve the approved mapping examples: P1 cycle/corruption to HARD_INTEGRITY, P1 overdue to ADVISORY, P7 stale derived view to RECOVERABLE. These tests prove adapter contracts, not ChapterCommit integration.
- [ ] **Step 4: Run mapping tests plus current P1–P7 unit tests.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py -q`
Expected: PASS; these are pure adapter-contract tests only. P1–P7 production behavior and CLI outputs remain untouched.

## Task 3: Integrate outcome handling into current chapter commit callers

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/chapter_commit.py`
- Modify: `.claude/plugins/zhanghui/scripts/run_behavior_evals.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/memory_contract_adapter.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/webnovel.py` only if outcome serialization/exit status requires a thin forwarding change
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/commit_helpers.py` to return commit payloads only for final accepted/rejected outcomes
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py`
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_contract_adapter.py`
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_user_report.py`

**Interfaces:**
- CLI serializes `accepted`, `rejected`, or `pending_human` outcome distinctly and prints/stores the GateDecision reference.
- Pending is exposed as structured `pending_human` output and is never reported as a durable rejected commit or accepted chapter.
- `changes_gate` produces structured integrity findings that `ChapterCommitService` recomputes; it has no independent final veto at the CLI layer.
- Changes Gate R0 advisory (uninitialized DB), R8 heuristic advisory, and missing/unknown severity never become HARD_INTEGRITY; registered blocking findings require structured location/evidence.
- Chapter-write adapter can stop for human action and resume by appending the human response and reevaluating policy; it does not claim chapter commit success or failure until final action.

- [ ] **Step 1: Add failing caller tests** proving pending output is user-actionable, creates no commit/rejected projection, accepted/rejected outcomes retain existing reporting, and `changes_gate` violations arrive as structured findings for service evaluation instead of an independent CLI veto.
- [ ] **Step 2: Run the selected caller tests and verify failure.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_contract_adapter.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_user_report.py -k 'pending or gate_decision or commit_status or changes_gate' -q`
Expected: FAIL because current callers only understand accepted/rejected commits and `chapter_commit.py` performs its own gate before policy evaluation.

- [ ] **Step 3: Implement thin pending/result propagation.** Keep policy evaluation in `ChapterCommitService`; CLI and adapters only expose the outcome and route explicit user response back as structured workflow input. Convert `changes_gate` findings to typed integrity findings and pass them into `evaluate_attempt()`; do not let the CLI return a separate final rejection.
- Replace all production `build_commit()` callsites (`chapter_commit.py`, `memory_contract_adapter.py`, `run_behavior_evals.py`) with `evaluate_attempt()` and migrate test helpers so no legacy service entrypoint can preserve the old count-based veto.

- [ ] **Step 4: Run caller tests and existing command tests.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_contract_adapter.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_user_report.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_write_gates.py -q`
Expected: PASS; no caller derives veto from blocker counts or cached severity.

## Task 4: Verify the Phase 6A boundary and complete the audit

**Files:**
- Modify: `.claude/plugins/zhanghui/docs/context-provenance.md` only if it documents gate/decision ownership
- Modify: `.claude/plugins/zhanghui/docs/projection-rebuild.md` only if GateDecision ownership affects rebuild documentation
- Test: targeted Phase 6A suite listed in the phase plan

- [ ] **Step 1: Add cross-layer tests** for pending→human response→reevaluation→accepted, rejected commit immutability, GateDecision sole ownership, input mismatch recomputation, and malformed/out-of-scale score rejection plus valid SCORE non-veto behavior.
- [ ] Add a ChapterCommit regression proving a reported P1 overdue, P3 pacing, or P6 reader-contract finding, alongside otherwise acceptable chapter inputs, does not become a Phase 6A commit input.
- [ ] **Step 2: Run the cross-layer tests before any final cleanup and verify failures.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_finding_adapters.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py -k 'pending or human or score or mismatch or rejected' -q`
Expected: FAIL only for the new integration assertions before wiring or on uncovered edge cases.

- [ ] **Step 3: Fix only Phase 6A gaps revealed by the cross-layer tests.** Do not migrate consistency producers, connect the consistency runner to `ChapterCommitService`, add P1–P7 commit inputs, change consistency CLI prerequisites, or retire the legacy `Blocker` type.
- [ ] **Step 4: Run the full focused Phase 6A suite** exactly as listed in `2026-10-05-phase-6a-gate-policy-phase.md` and confirm all tests pass.
- [ ] **Step 5: Inspect the final diff and commit the completed phase** as `feat: enforce shared deterministic chapter gate policy`.

## Acceptance criteria

- P1–P7 each has a stable mapping contract with pure adapter tests. No consistency runner, producer, or adapter is connected to the ChapterCommit production policy inputs in Phase 6A.
- No adapter or policy classification reads message/fix_hint. Producer outputs do not choose severity, authority, explicitness, or blocking.
- Same patch/chapter can produce multiple distinct logical findings; evidence can change across attempts without changing finding_id when logical subject/scope are stable. Missing identity is diagnostic/advisory only.
- LLM blockers, ordinary planner misses, timed-lock/Craft/Style heuristics, and unknown legacy rows retain the approved non-hard behavior. Hard paths remain limited to explicit validated USER constraints and deterministic Canon/Integrity proof under the shared policy.
- Step 3 caller integration respects Step 2 action/outcome semantics and all Step 1/2 regression suites pass. No Phase 6B migration or Phase 0/1/2/3/4/5A boundary change.
- LLM `blocking=true` or critical severity alone cannot veto; Craft/timed-lock/pacing/hook/Scene-Sequel display text (including `BLOCKER`, `BLOCK`, `未声明`, `逾期`) cannot create a veto.
- AUTHOR_PLAN/PLANNER_GENERATED missed nodes remain ADVISORY/SCORE; only a validated USER_EXPLICIT constraint maps to HARD_USER. A genuine unresolved identity maps to HUMAN_DECISION. Legacy `blocking_count` and `blocking` have no standalone authority.
- ChapterCommitService decides only from canonical shared-policy recomputation of its established production inputs, including current review/Craft, fulfillment, disambiguation, and changes/reconciliation findings.

## Phase 6B handoff

Phase 6B may decide whether consistency findings should reach skill, CLI, or workflow consumers, through which entry points, and whether those consumers should share policy evaluation. Shared severity semantics do not imply a shared execution entry point. Until that architecture is explicitly scoped, P1–P7 adapters remain pure contracts and do not enter ChapterCommitService.

P1 typed producer-native metadata (`issue_code`, `subject_id`, structured `evidence`) is deferred: it currently has no review/commit production consumer and serves only the future consistency producer-native migration. Reconsider it in Phase 6B together with the intended producer/consumer path.

## Step-level commit boundary

One independent implementation subagent executes all Tasks in this Step Plan and creates exactly one commit only after all Step 3 targeted suites and Step 1–2 regressions pass. Do not create task-level commits. Afterward, a fresh independent Phase 6A integration reviewer must PASS before any merge to main or any Phase 6B work.

```bash
git add -A
git commit -m "feat: route legacy gates through policy"
```
