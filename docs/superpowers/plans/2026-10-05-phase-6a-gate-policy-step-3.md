---
title: "Step Plan 3 — Legacy Adapters and Veto-Relevant Integration"
type: "step-plan"
status: "🟢 待开始"
created: "2026-10-05"
parent: "2026-10-05-phase-6a-gate-policy-phase.md"
children: []
tags: ["legacy-adapter", "consistency", "integration"]
---

# Step Plan 3 — Legacy Adapters and Veto-Relevant Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development`.

**Goal:** Convert only existing veto-relevant legacy review, fulfillment, disambiguation, and consistency inputs to normalized findings without rewriting every producer or CLI.

**Architecture:** A registry keyed by checker/gate and artifact type maps structured legacy values to findings. P1–P7 get a complete mapping contract; only paths currently reaching review/commit veto are wired in Phase 6A. User constraints are read from existing Story System contract node metadata.

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

## Task 2: Define and test P1–P7 consistency mapping contract

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/consistency/core/patch_base.py` only to expose stable patch identity/evidence fields if currently absent
- Create: `.claude/plugins/zhanghui/scripts/data_modules/consistency_finding_adapters.py`
- Create: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py`
- Read: `.claude/plugins/zhanghui/scripts/consistency/patches/p1_foreshadow_dag.py` through `p7_derived_views.py`

**Interfaces:**
- `P1_P7_MAPPING` has exactly seven entries keyed by stable patch IDs; each declares category, source authority, evidence extractor, and policy rule ID.
- `adapt_consistency_patch(patch_result, chapter_scope) -> list[DetectedFinding]` emits structured findings from patch IDs and structured patch evidence.

- [ ] **Step 1: Add failing mapping contract tests** asserting P1–P7 completeness, unique gate IDs, stable evidence identity, and representative clean/finding results for each patch type.
- [ ] **Step 2: Run and verify the tests fail.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py -q`
Expected: FAIL because the mapping contract is absent.

- [ ] **Step 3: Implement the mapping table.** Use the seven patch modules' structured IDs/data only; keep CLI output and patch output formats intact. Map pacing-only quality observations to CRAFT/SCORE/ADVISORY, integrity failures to INTEGRITY, projection issues to PROJECTION_HEALTH, and user constraints only when contract provenance proves it.
- [ ] **Step 4: Run mapping tests plus current P1–P7 unit tests.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py .claude/plugins/zhanghui/scripts/tests/unit/consistency/test_p1_foreshadow_dag.py .claude/plugins/zhanghui/scripts/tests/unit/consistency/test_p2_volume_anchor.py .claude/plugins/zhanghui/scripts/tests/unit/consistency/test_p3_event_matrix.py .claude/plugins/zhanghui/scripts/tests/unit/consistency/test_p4_pacing_tracker.py .claude/plugins/zhanghui/scripts/tests/unit/consistency/test_p5_state_revision.py .claude/plugins/zhanghui/scripts/tests/unit/consistency/test_p6_reader_contract.py .claude/plugins/zhanghui/scripts/tests/unit/consistency/test_p7_derived_views.py -q`
Expected: PASS; existing producer behavior and CLI formats remain unchanged.

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
- [ ] **Step 2: Run the cross-layer tests before any final cleanup and verify failures.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_finding_adapters.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py -k 'pending or human or score or mismatch or rejected' -q`
Expected: FAIL only for the new integration assertions before wiring or on uncovered edge cases.

- [ ] **Step 3: Fix only Phase 6A gaps revealed by the cross-layer tests.** Do not migrate every consistency producer, CLI exit code, skill consumer, or legacy `Blocker` type.
- [ ] **Step 4: Run the full focused Phase 6A suite** exactly as listed in `2026-10-05-phase-6a-gate-policy-phase.md` and confirm all tests pass.
- [ ] **Step 5: Inspect the final diff and commit the completed phase** as `feat: enforce shared deterministic chapter gate policy`.

## Step-level commit boundary

One independent implementation subagent executes all Tasks in this Step Plan and creates exactly one commit only after all Step 3 targeted suites and Step 1–2 regressions pass. Do not create task-level commits. Afterward, a fresh independent Phase 6A integration reviewer must PASS before any merge to main or any Phase 6B work.

```bash
git add -A
git commit -m "feat: route legacy gates through policy"
```
