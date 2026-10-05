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

**Architecture:** Gate/workflow actions (`REJECT`, `REQUIRE_HUMAN`, `RECOVER`, `ALLOW_WITH_ADVISORY`) are distinct from durable chapter outcomes (`accepted`, `rejected`). Every policy evaluation is an immutable, authoritative per-attempt GateDecision artifact. A separate append-only workflow/recovery audit records transient transitions without becoming a second decision owner. `REQUIRE_HUMAN` and `RECOVER` are pre-commit actions and consume no chapter commit slot. Only terminal accepted/rejected outcomes produce `ChapterCommitOutcome` and CHAPTER_COMMIT.

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
- `ChapterCommitOutcome` describes only a durable chapter outcome: `chapter_outcome: Literal["accepted", "rejected"]`, `gate_decision_ref`, and `commit_payload`.
- `WorkflowAttemptResult` describes policy/workflow execution: `action`, `attempt_id`, `gate_decision_ref`, `attempt_status`, and `chapter_outcome: ChapterCommitOutcome | None`. It is not a chapter outcome and carries no commit payload directly.
- Add `ChapterCommitService.evaluate_attempt(...) -> WorkflowAttemptResult` to normalize structured inputs and recompute policy internally.
- `REQUIRE_HUMAN` persists the GateDecision plus pending workflow metadata and returns `action=REQUIRE_HUMAN`, `attempt_status=pending_human`, `chapter_outcome=None`; it never calls `persist_commit()` or projection writers.
- `RECOVER` persists an immutable GateDecision attempt and append-only recovery workflow audit, dispatches only the existing `data_modules.projection_rebuild.rebuild_projections()` capability for projection-health recovery, verifies its structured result, gathers/normalizes findings again, and reevaluates policy as a new attempt. The initial RECOVER attempt never creates a ChapterCommitOutcome or calls `persist_commit()`. Do not invent a generic recovery dispatcher for condition types without an existing safe recovery API; those require plan/design escalation rather than fallback behavior.
- Recovery success is not acceptance: only a subsequent `ALLOW_WITH_ADVISORY` evaluation continues through existing reconciliation and commit validation. Recovery failure becomes structured evidence and is reevaluated; policy may produce `REJECT` or `REQUIRE_HUMAN`, never a rejected commit based solely on an exception class.
- `REJECT` yields `ChapterCommitOutcome(chapter_outcome="rejected")` and the existing immutable `meta.status=rejected` payload. `ALLOW_WITH_ADVISORY` yields an accepted chapter outcome only after existing reconciliation and durable validation. Final commits contain only `gate_decision_ref`, `input_fingerprint`, `policy_version`, and `final_action` bindings.

- [ ] **Step 1: Add failing service tests.** Assert pending writes GateDecision + pending workflow metadata but no chapter commit file, rejection still writes exactly one rejected commit, and acceptance after a prior pending attempt can write an accepted commit because no commit slot was consumed. Assert RECOVER returns a workflow attempt result with no ChapterCommitOutcome and no commit/projection write.
- [ ] **Step 2: Add failing mismatch tests.** Supply stale cached GateDecision and false/true `effective_hard_count`; assert service recomputation controls outcome and a mismatch is recorded.
- [ ] **Step 3: Run both test groups and verify failure.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py -k 'pending or gate_decision or recomput' -q`
Run: `pytest .claude/plugins/zhanghui/scripts/tests/test_chapter_commit_conflict.py -q`
Expected: pending path currently attempts commit or APIs are absent; conflict suite remains baseline evidence for immutable commits.

- [ ] **Step 4: Implement `evaluate_attempt()` and distinct result types.** Persist each GateDecision first. For REQUIRE_HUMAN, append pending workflow metadata and return without a commit. For the projection-health `RECOVER` rule, append a recovery-pending workflow event, call existing `rebuild_projections()` (which owns projection rebuilding), verify its structured result, normalize refreshed findings and reevaluate into a new immutable GateDecision attempt. Record recovery success/failure as append-only workflow audit linked to the RECOVER decision. Do not add a scheduler, generic workflow engine, GateService, generic recovery dispatcher, or new projection recovery implementation. Only final REJECT or accepted action may construct `ChapterCommitOutcome` and call `persist_commit()`; commit stores only the four approved bindings.
- [ ] **Step 5: Update durable commit validation compatibly.** Accept old commits without GateDecision bindings; when bindings exist, validate their types and ensure `final_action` agrees with `meta.status` (`REJECT`↔`rejected`, accepted action↔`accepted`).
- [ ] **Step 6: Test recovery transitions.** Cover the required cases: (A) stale rebuildable projection → RECOVER with no commit → existing recovery succeeds → second immutable attempt reevaluates to ALLOW_WITH_ADVISORY → accepted commit; assert exactly two immutable GateDecision attempts. (B) existing rebuild returns a deterministic projection/integrity failure → normalize its structured projection/error fields as new evidence, reevaluate to HARD_INTEGRITY/REJECT → durable rejected commit. (C) recovery reports a structured ambiguous failure → normalize that evidence and reevaluate to HUMAN_DECISION/REQUIRE_HUMAN → no commit. (D) RECOVER never consumes the chapter slot. (E) recovery success never auto-accepts without a fresh policy evaluation. Mock only the existing recovery boundary where needed; do not implement a new recovery mechanism.

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_schema.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contracts.py .claude/plugins/zhanghui/scripts/tests/test_chapter_commit_conflict.py -q`
Expected: PASS; neither pending nor transient recovery occupies the immutable chapter commit path; every recovery transition has durable audit and a fresh policy attempt.

## Task 3: Persist transient workflow events and preserve pending/rejection semantics

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/gate_decision_store.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/chapter_commit_service.py`
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py`
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py`

**Interfaces:**
- Per-attempt GateDecision artifacts remain the sole authoritative decision records. An append-only workflow event stream may record `pending_human`, `recovery_pending`, `recovery_succeeded`, or `recovery_failed`, always linked to a GateDecision attempt and without effective-severity copies.
- A human response is appended as workflow input linked to finding IDs, then `evaluate_attempt()` reruns `GateSeverityPolicy` into a new attempt.
- Recovery result evidence is appended as workflow input linked to the original RECOVER attempt, then findings are normalized and `GateSeverityPolicy` reruns into a new attempt. Historical RECOVER decisions/events are never overwritten.

- [ ] **Step 1: Add failing tests** for append-only human response, deterministic reevaluation after response, append-only recovery success/failure audit, recovery reevaluation creating a new immutable attempt, pending/recover not creating `chapter_rejected` projection, and final REJECT retaining existing rejected status projection.
- [ ] **Step 2: Run those tests and verify failure.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py -k 'human or pending or rejected' -q`
Expected: FAIL until pending attempt state and response append are implemented.

- [ ] **Step 3: Implement append-only response/recovery records and policy reevaluation.** Store human choice or verified recovery result as workflow input linked to the relevant GateDecision attempt and finding IDs; never edit a prior GateDecision record or write story facts from workflow metadata.
- [ ] **Step 4: Verify pending/rejected projection distinctions.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py -k 'human or pending or rejected' -q`
Expected: pending and recovery attempts leave the chapter slot empty; REJECT still projects `chapter_rejected`; later accepted/rejected results require a fresh policy evaluation and proceed through existing rules.

## Acceptance criteria

- `GateAction` and `ChapterCommitOutcome` are separate concepts. Only durable accepted/rejected commits instantiate `ChapterCommitOutcome`; pre-commit pending/recovery returns a `WorkflowAttemptResult` with `chapter_outcome=None`.
- Each recovery transition is append-only workflow/recovery audit linked to an immutable GateDecision attempt; no second decision owner or duplicated effective-decision snapshot is created.
- RECOVER never writes or occupies a CHAPTER_COMMIT slot. A successful recovery is followed by a new immutable GateDecision attempt and policy reevaluation; it is never auto-accepted.
- Recovery failure is normalized as structured evidence and reevaluated to REJECT or REQUIRE_HUMAN. Exception type alone never writes a rejected commit.
- The requested success, deterministic-failure, ambiguous-failure, no-slot, and mandatory-reevaluation cases all pass, along with REQUIRE_HUMAN/REJECT semantics and Step 1 regression tests.
- Existing reconciliation, durable validation, Canon authority, and Phase 0/1 commit boundaries remain unchanged.

## Step-level commit boundary

One independent implementation subagent executes all Tasks in this Step Plan and creates exactly one commit only after the Step 2 targeted suites and Step 1 regression pass. Do not create task-level commits. A fresh independent reviewer must PASS before Step 3.

```bash
git add .claude/plugins/zhanghui/scripts/data_modules/story_contracts.py .claude/plugins/zhanghui/scripts/data_modules/gate_decision_store.py .claude/plugins/zhanghui/scripts/data_modules/gate_findings.py .claude/plugins/zhanghui/scripts/data_modules/chapter_commit_service.py .claude/plugins/zhanghui/scripts/data_modules/durable_projection.py .claude/plugins/zhanghui/scripts/data_modules/chapter_commit_schema.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contracts.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py .claude/plugins/zhanghui/scripts/tests/test_chapter_commit_conflict.py
git commit -m "feat: persist authoritative gate attempts"
```
