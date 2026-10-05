---
title: "Phase Plan — Phase 6A Gate Policy"
type: "phase-plan"
status: "🟢 待开始"
created: "2026-10-05"
parent: "2026-10-05-phase-6a-gate-policy-master.md"
children:
  - "2026-10-05-phase-6a-gate-policy-step-1.md"
  - "2026-10-05-phase-6a-gate-policy-step-2.md"
  - "2026-10-05-phase-6a-gate-policy-step-3.md"
tags: ["phase-6a", "gate-policy"]
---

# Phase 6A Shared Gate Policy — Phase Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to execute the linked step plans in order.

**Goal:** Replace independent legacy veto interpretation with structured findings, deterministic decisions, and one service-owned commit boundary.

**Architecture:** Step 1 creates the typed contract and pure policy. Step 2 adds durable per-attempt workflow decisions and routes final outcomes through `ChapterCommitService`. Step 3 migrates only existing review/Craft, fulfillment, disambiguation, and changes/reconciliation veto inputs. P1–P7 remain mapping contracts and pure adapter tests; they have no Phase 6A production consumer.

**Tech Stack:** Python 3, Pydantic, JSON, pytest.

**Spec:** `docs/superpowers/specs/2026-10-05-phase-6a-shared-gate-findings-design.md`

---

## Implementation Surface

| Area | Existing files to follow | Planned responsibility |
|---|---|---|
| Findings and policy | `.claude/plugins/zhanghui/scripts/data_modules/chapter_commit_schema.py`, `review_schema.py` | Add a focused `gate_findings.py` with category/authority/severity/action/evidence models, stable identity, fingerprints, score payload, and pure policy evaluation. |
| Contract paths and audit | `.claude/plugins/zhanghui/scripts/data_modules/story_contracts.py` | Add per-chapter/per-attempt GateDecision paths and append-only persistence without overwriting earlier attempts. |
| Commit owner | `.claude/plugins/zhanghui/scripts/data_modules/chapter_commit_service.py`, `durable_projection.py` | Introduce a typed attempt outcome; make the service normalize, evaluate, persist GateDecision, and then either persist rejected/accepted commit or return pending without a commit. |
| Entry points | `.claude/plugins/zhanghui/scripts/chapter_commit.py`, `.claude/plugins/zhanghui/scripts/data_modules/memory_contract_adapter.py`, `webnovel.py` | Propagate pending vs accepted/rejected outcome without pretending pending is a commit. Keep current caller-facing behavior where possible. |
| Legacy mapping | New `.claude/plugins/zhanghui/scripts/data_modules/gate_finding_adapters.py` and `.claude/plugins/zhanghui/scripts/data_modules/consistency_finding_adapters.py`; `.claude/plugins/zhanghui/scripts/review_pipeline.py` | Migrate real legacy veto paths with typed identity/provenance. Keep P1–P7 as pure mapping contracts with adapter-only tests; do not modify their producers or connect them to ChapterCommit. |
| Tests | `.claude/plugins/zhanghui/scripts/data_modules/tests/` and `.claude/plugins/zhanghui/scripts/tests/` | Add unit, service, persistence, adapter, and command integration coverage described in the step plans. |

## Execution Order and Dependencies

1. [Step 1](2026-10-05-phase-6a-gate-policy-step-1.md) defines shared models, deterministic IDs/fingerprints, and policy. Its public interfaces are consumed by all later steps.
2. [Step 2](2026-10-05-phase-6a-gate-policy-step-2.md) stores immutable per-attempt decisions and separates transient workflow actions (including recovery and human pending) from terminal accepted/rejected chapter outcomes. RECOVER dispatches existing recovery, verifies, and reevaluates as a new attempt; it never commits directly. It depends on Step 1 types and policy.
3. [Step 3](2026-10-05-phase-6a-gate-policy-step-3.md) adds legacy adapters, explicit user-contract metadata handling, pure P1–P7 mapping contracts, and the current caller integration. It depends on Steps 1 and 2.

## Phase Verification

Run the focused test commands listed in each step after that step. The final Phase 6A acceptance definition is the named-file manifest in `docs/superpowers/acceptance/2026-10-05-phase-6a-final-acceptance.md`. It defines Step 1, Step 2, Step 3, Step 1/2 regression, and pure P1–P7 adapter coverage by exact test files and collected node IDs; counts are recorded outcomes, never targets.

Expected: every manifest command passes; rejected commits remain immutable audit records; REQUIRE_HUMAN produces a durable pending GateDecision and no commit file; later reevaluation can reach accepted/rejected without a pending attempt consuming the commit slot; no Phase 6B CLI/skill retirement has been introduced. Do not require any predetermined test count.

## Phase 6B handoff boundary

Phase 6B must decide whether consistency findings should reach skills, CLI, or workflow consumers, and through which entry points. A shared severity policy standardizes severity semantics; it does not require all checkers to share ChapterCommitService as an execution entry point. P1 typed producer metadata (`issue_code`, `subject_id`, structured `evidence`) is deferred because its only current purpose is producer-native consistency migration and it has no review/commit production consumer. Do not treat P1–P7 adapter tests as production ChapterCommit integration tests.
