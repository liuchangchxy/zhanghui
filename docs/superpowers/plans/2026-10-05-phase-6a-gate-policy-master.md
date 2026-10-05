---
title: "Phase 6A Shared Gate Findings and Deterministic Severity Policy"
type: "master-plan"
status: "🟢 待开始"
created: "2026-10-05"
parent: ""
children:
  - "2026-10-05-phase-6a-gate-policy-phase.md"
tags: ["phase-6a", "gate-policy", "chapter-commit"]
---

# Phase 6A Shared Gate Findings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement the linked phase plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make chapter veto decisions deterministic, auditable, and owned by `ChapterCommitService`, while preserving the immutable chapter commit boundary.

**Architecture:** Normalize checker outputs into `DetectedFinding`, evaluate them with a pure versioned `GateSeverityPolicy`, and persist one authoritative per-attempt `GateDecision` artifact. The service writes rejected or accepted `CHAPTER_COMMIT` records only for final `REJECT` or accepted actions; `REQUIRE_HUMAN` persists pending workflow state without consuming the chapter commit slot.

**Tech Stack:** Python 3, Pydantic, JSON workflow artifacts, pytest, existing Story System contracts and chapter commit services.

**Spec:** `docs/superpowers/specs/2026-10-05-phase-6a-shared-gate-findings-design.md`

## Global Constraints

- Keep `.claude/plugins/zhanghui/` as the canonical plugin source; do not edit `.claude/plugins/zhanghui/6.4.0/`, `.Codex/plugins/zhanghui/`, or `references/`.
- Do not create a unified `GateService` or global `UserConstraint` registry.
- `ChapterCommitService` recomputes policy from structured findings and owns final veto; `blocking`, `blocking_count`, checker strings, and external `effective_hard_count` have no authority.
- Persist GateDecision as the sole authoritative full policy decision record; commits carry only `gate_decision_ref`, `input_fingerprint`, `policy_version`, and `final_action`.
- `REJECT` keeps the existing durable `meta.status=rejected` commit semantics; `REQUIRE_HUMAN` writes durable pending workflow state and no `CHAPTER_COMMIT`.
- Keep category, authority, explicitness, structured evidence, and suggested severity separate; never classify findings from free-form messages.
- `HARD_CANON` requires accepted Canon provenance, deterministic linkage, and deterministic contradiction evidence. LLM review cannot assert it.
- Planner/author Intent misses are only `ADVISORY` or `SCORE`; only explicitly linked `USER_EXPLICIT` constraints can become `HARD_USER`.
- LLM `blocking` flags, timed-lock expiry, and Craft/Style heuristics never create a hard veto without the explicit user-constraint proof required by policy.
- `SCORE` carries kind/value/scale only when effective severity is `SCORE`; it never enters hard counts, rejects, or auto-escalates by threshold.
- Keep the Phase 6A/6B boundary and the existing recovery sequence `RECOVERABLE → recover → verify → reevaluate`.

## Review Focus

- A pending human decision leaves the chapter commit slot available; pin this in service and CLI integration tests.
- A misleading `blocking_count` or `effective_hard_count` cannot alter service recomputation; pin in `test_chapter_commit_service.py`.
- A repeated logical issue keeps `finding_id` across changed evidence while its evidence fingerprint changes; pin in `test_gate_findings.py`.
- `SCORE` requires a well-formed structured score and never vetoes at a configured value; malformed/out-of-scale values fail schema validation; pin both in score policy tests.
- Unknown legacy blockers stay diagnostic/advisory unless a registered gate mapping plus structured evidence requires human action; pin in adapter tests.
- Simultaneous policy outcomes resolve with documented aggregate precedence and an empty finding set allows advisory-only continuation; pin in policy tests.

## Plan Tree

1. [Phase plan: shared finding policy, audit persistence, and commit integration](2026-10-05-phase-6a-gate-policy-phase.md)
2. [Step plan 1: finding schema, stable identity, and severity policy](2026-10-05-phase-6a-gate-policy-step-1.md)
3. [Step plan 2: GateDecision persistence and ChapterCommitService outcomes](2026-10-05-phase-6a-gate-policy-step-2.md)
4. [Step plan 3: legacy adapters and veto-relevant P1–P7 integration](2026-10-05-phase-6a-gate-policy-step-3.md)

## Completion Gate

Phase 6A is complete when all acceptance criteria in the design spec are covered by passing focused and regression tests, pending human decisions do not occupy commit slots, historical GateDecision artifacts remain authoritative, and the implementation remains within the stated 6A boundary. Do not begin 6B migrations as part of this plan.
