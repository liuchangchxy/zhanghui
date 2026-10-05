---
title: "Step Plan 2 — GateDecision Persistence and Commit Outcomes"
type: "step-plan"
status: "🟢 待开始"
created: "2026-10-05"
parent: "2026-10-05-phase-6a-gate-policy-phase.md"
children: []
tags: ["gate-decision", "chapter-commit", "workflow"]
---

# Step Plan 2 — GateDecision Persistence and Commit Outcomes

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development`.

**Goal:** Persist one authoritative GateDecision per attempt and preserve distinct rejected, pending, and accepted outcomes.

**Architecture:** A unique append-only decision artifact is written before a final chapter commit. The commit contains only the decision reference and binding fields. A pending human decision returns a workflow outcome without calling `persist_commit()` or projection writers.

**Tech Stack:** Python 3, Pydantic, atomic JSON writes, pytest.

**Spec:** `docs/superpowers/specs/2026-10-05-phase-6a-shared-gate-findings-design.md`

---

## Task 1: Add attempt-scoped workflow artifact paths and storage

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/story_contracts.py`
- Create: `.claude/plugins/zhanghui/scripts/data_modules/gate_decision_store.py`
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contracts.py`
- Create: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py`

**Interfaces:**
- `StoryContractPaths.gate_decision_json(chapter: int, attempt_id: str) -> Path` returns a path under `.story-system/reviews/gate-decisions/`.
- `GateDecisionStore.append_attempt(chapter: int, attempt_id: str, decision_set: GateDecisionSet) -> Path` validates and writes a new unique attempt; duplicate attempt IDs fail without overwrite.
- `GateDecisionStore.read_attempt(chapter: int, attempt_id: str) -> GateDecisionSet` validates existing records.

- [ ] **Step 1: Write failing path/store tests.** Cover deterministic path location, unique attempt IDs, append-only refusal on collision, JSON round-trip, and validation failure for a malformed SCORE payload.
- [ ] **Step 2: Run and verify the tests fail.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contracts.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py -q`
Expected: FAIL because GateDecision path/store APIs do not exist.

- [ ] **Step 3: Add the path helper and append-only store.** Use the repository's atomic JSON write helper but check target nonexistence under an exclusive lock; never call overwrite semantics for an existing attempt.
- [ ] **Step 4: Re-run persistence tests and verify they pass.**

## Task 2: Return explicit pending/rejected/accepted attempt outcomes

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/chapter_commit_service.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/durable_projection.py`
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py`
- Test: `.claude/plugins/zhanghui/scripts/tests/test_chapter_commit_conflict.py`

**Interfaces:**
- Add `ChapterCommitOutcome` with `workflow_status: Literal["pending_human", "rejected", "accepted"]`, `gate_decision_ref`, `decision_set`, and `commit_payload: dict | None`.
- Add `ChapterCommitService.evaluate_attempt(...) -> ChapterCommitOutcome` to normalize structured inputs and recompute policy internally.
- `workflow_status="pending_human"` always has `commit_payload=None`; it never calls `persist_commit()` or projection writers.
- `workflow_status="rejected"` builds the existing immutable `meta.status=rejected` payload; accepted/rejected commits contain only `gate_decision_ref`, `input_fingerprint`, `policy_version`, and `final_action` bindings.

- [ ] **Step 1: Add failing service tests.** Assert pending writes GateDecision + pending workflow metadata but no chapter commit file, rejection still writes exactly one rejected commit, and acceptance after a prior pending attempt can write an accepted commit because no commit slot was consumed.
- [ ] **Step 2: Add failing mismatch tests.** Supply stale cached GateDecision and false/true `effective_hard_count`; assert service recomputation controls outcome and a mismatch is recorded.
- [ ] **Step 3: Run both test groups and verify failure.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py -k 'pending or gate_decision or recomput' -q`
Run: `pytest .claude/plugins/zhanghui/scripts/tests/test_chapter_commit_conflict.py -q`
Expected: pending path currently attempts commit or APIs are absent; conflict suite remains baseline evidence for immutable commits.

- [ ] **Step 4: Implement `evaluate_attempt()` and outcome routing.** Persist GateDecision first; return pending immediately for REQUIRE_HUMAN; call `persist_commit()` only for final REJECT or accepted path; store the four binding fields and never duplicate per-finding effective decisions in the commit.
- [ ] **Step 5: Update durable commit validation compatibly.** Accept old commits without GateDecision bindings; when bindings exist, validate their types and ensure `final_action` agrees with `meta.status` (`REJECT`↔`rejected`, accepted action↔`accepted`).
- [ ] **Step 6: Run service/conflict tests and verify all three outcomes.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_schema.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contracts.py .claude/plugins/zhanghui/scripts/tests/test_chapter_commit_conflict.py -q`
Expected: PASS; no pending result occupies the immutable chapter commit path.

## Task 3: Persist pending human metadata and preserve rejection projections

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/gate_decision_store.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/chapter_commit_service.py`
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py`
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py`

**Interfaces:**
- Pending metadata is recorded in the authoritative GateDecision workflow attempt record with status `pending_human` and stable finding IDs; it is not a second decision artifact owner.
- A human response is appended as a new attempt input/response record, then `evaluate_attempt()` reruns `GateSeverityPolicy`.

- [ ] **Step 1: Add failing tests** for append-only human response, deterministic reevaluation after response, pending not creating `chapter_rejected` projection, and final REJECT retaining existing rejected status projection.
- [ ] **Step 2: Run those tests and verify failure.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py -k 'human or pending or rejected' -q`
Expected: FAIL until pending attempt state and response append are implemented.

- [ ] **Step 3: Implement append-only response records and policy reevaluation.** Store the human choice as workflow input linked to finding IDs; never edit a prior GateDecision record or write story facts from the response.
- [ ] **Step 4: Verify pending/rejected projection distinctions.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py -k 'human or pending or rejected' -q`
Expected: pending leaves the chapter slot empty; REJECT still projects `chapter_rejected`; accepted retries after pending proceed normally.

## Step-level commit boundary

One independent implementation subagent executes all Tasks in this Step Plan and creates exactly one commit only after the Step 2 targeted suites and Step 1 regression pass. Do not create task-level commits. A fresh independent reviewer must PASS before Step 3.

```bash
git add .claude/plugins/zhanghui/scripts/data_modules/story_contracts.py .claude/plugins/zhanghui/scripts/data_modules/gate_decision_store.py .claude/plugins/zhanghui/scripts/data_modules/gate_findings.py .claude/plugins/zhanghui/scripts/data_modules/chapter_commit_service.py .claude/plugins/zhanghui/scripts/data_modules/durable_projection.py .claude/plugins/zhanghui/scripts/data_modules/chapter_commit_schema.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contracts.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py .claude/plugins/zhanghui/scripts/tests/test_chapter_commit_conflict.py
git commit -m "feat: persist authoritative gate attempts"
```
