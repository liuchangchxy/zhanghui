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

**Architecture:** Step 1 creates the typed contract and pure policy. Step 2 adds durable per-attempt workflow decisions and routes final outcomes through `ChapterCommitService`. Step 3 maps legacy artifacts and P1–P7 identities into structured findings for only the paths that currently affect review/commit veto.

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
| Legacy mapping | New `.claude/plugins/zhanghui/scripts/data_modules/gate_finding_adapters.py`; `.claude/plugins/zhanghui/scripts/consistency/core/patch_base.py`; `.claude/plugins/zhanghui/scripts/consistency/patches/p1_foreshadow_dag.py` through `p7_derived_views.py` | Register deterministic source/gate/artifact mappings; expose P1–P7 mapping contract; migrate only veto-relevant paths. |
| Tests | `.claude/plugins/zhanghui/scripts/data_modules/tests/` and `.claude/plugins/zhanghui/scripts/tests/` | Add unit, service, persistence, adapter, and command integration coverage described in the step plans. |

## Execution Order and Dependencies

1. [Step 1](2026-10-05-phase-6a-gate-policy-step-1.md) defines shared models, deterministic IDs/fingerprints, and policy. Its public interfaces are consumed by all later steps.
2. [Step 2](2026-10-05-phase-6a-gate-policy-step-2.md) stores decisions and enforces accepted/rejected/pending semantics. It depends on Step 1 types and policy.
3. [Step 3](2026-10-05-phase-6a-gate-policy-step-3.md) adds legacy adapters, explicit user-contract metadata handling, P1–P7 mappings, and current caller integration. It depends on Steps 1 and 2.

## Phase Verification

Run the focused test commands listed in each step after that step. At phase end run:

```bash
pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_finding_adapters.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_schema.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contracts.py -q
pytest .claude/plugins/zhanghui/scripts/tests/unit/consistency -q
pytest .claude/plugins/zhanghui/scripts/tests/test_chapter_commit_conflict.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_contract_adapter.py -q
```

Expected: all targeted tests pass; rejected commits remain immutable audit records; REQUIRE_HUMAN produces a durable pending GateDecision and no commit file; later reevaluation can reach accepted/rejected without a pending attempt consuming the commit slot; no Phase 6B CLI/skill retirement has been introduced.
