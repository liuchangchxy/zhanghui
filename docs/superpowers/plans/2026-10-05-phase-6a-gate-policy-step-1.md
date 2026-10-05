---
title: "Step Plan 1 — Gate Finding Schema and Policy"
type: "step-plan"
status: "🟢 待开始"
created: "2026-10-05"
parent: "2026-10-05-phase-6a-gate-policy-phase.md"
children: []
tags: ["gate-findings", "policy", "schema"]
---

# Step Plan 1 — Gate Finding Schema and Policy

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development`.

**Goal:** Add a typed, deterministic shared finding and decision policy without changing any checker producer.

**Architecture:** A new pure module owns controlled enums and Pydantic records. Stable logical IDs use gate/subject/scope; evidence and full policy inputs have separate fingerprints. `GateSeverityPolicy.evaluate()` returns a decision per finding plus a deterministic aggregate action.

**Tech Stack:** Python 3, Pydantic 2, hashlib/json, pytest.

**Spec:** `docs/superpowers/specs/2026-10-05-phase-6a-shared-gate-findings-design.md`

---

## Task 1: Define the typed finding and decision records

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/gate_findings.py`
- Create: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py`

**Interfaces:**
- `FindingCategory`, `FindingAuthority`, `Explicitness`, `EffectiveSeverity`, and `WorkflowAction` are string enums matching the approved design exactly.
- `EvidenceRef` carries `kind`, `identity`, `observed`, `expected`, and optional `source_ref` as structured values.
- `DetectedFinding` carries stable identity dimensions, policy dimensions, structured evidence, optional display message and suggested severity.
- `GateDecision` carries finding ID, effective severity/action, policy version, rule ID/reason, evidence/input fingerprints, and optional `score` object.
- `SCORE` requires `score={kind: str, value: finite number, scale: [minimum, maximum]}`; all other effective severities forbid score payload.
- Aggregate action precedence is `REJECT > REQUIRE_HUMAN > RECOVER > ALLOW_WITH_ADVISORY`; no findings yields `ALLOW_WITH_ADVISORY`.

- [ ] **Step 1: Write the failing model tests.** Cover enum separation, unknown enum rejection, structured evidence validation, and score present/absent validation.

```python
import pytest
from pydantic import ValidationError

from data_modules.gate_findings import GateDecision


def test_score_decision_requires_structured_score_payload():
    base = {"finding_id": "gf1_" + "0" * 64, "effective_action": "ALLOW_WITH_ADVISORY",
            "policy_version": "gate-policy/v1", "rule_id": "score.pacing",
            "policy_reason": "Advisory quality score", "decision_scope": {"chapter": 3},
            "evidence_fingerprint": "0" * 64, "input_fingerprint": "1" * 64}
    with pytest.raises(ValidationError):
        GateDecision(**base, effective_severity="SCORE")
    decision = GateDecision(**base, effective_severity="SCORE",
                            score={"kind": "pacing", "value": 0.72, "scale": [0.0, 1.0]})
    assert decision.score.value == 0.72
```

- [ ] **Step 2: Run the model test and verify it fails** because `gate_findings.py` does not exist.

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py -q`
Expected: FAIL at import before implementation.

- [ ] **Step 3: Implement the enums and strict Pydantic models.** Set `extra="forbid"` for policy records, require structured evidence lists, reject non-finite numbers and invalid score scales, and enforce the SCORE-only score invariant in a model validator.

- [ ] **Step 4: Re-run the model tests and verify they pass.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py -q`
Expected: PASS for category/authority separation, invalid enums, and SCORE payload conditions.


## Task 2: Implement stable logical identity and evidence fingerprints

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/gate_findings.py`
- Test: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py`

**Interfaces:**
- `stable_finding_id(*, identity_version: str, gate_id: str, subject_key: str, scope: dict) -> str`
- `fingerprint_evidence(evidence: list[EvidenceRef]) -> str`
- `fingerprint_policy_inputs(findings: list[DetectedFinding], policy_version: str, scope: dict) -> str`

- [ ] **Step 1: Add failing identity/fingerprint tests.** Assert identical stable dimensions yield identical `gf1_` ID despite changed category/authority/evidence/message; assert changed evidence changes `evidence_fingerprint` and `input_fingerprint`; assert missing stable subject key cannot generate a veto-capable finding ID.
- [ ] **Step 2: Run the named tests and verify failure.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py -k 'finding_id or fingerprint or stable_subject' -q`
Expected: FAIL because identity/fingerprint functions are absent.

- [ ] **Step 3: Implement canonical JSON hashing.** Hash only identity version, gate ID, stable subject key and chapter/workflow scope for `finding_id`; hash structured evidence separately; include all normalized policy inputs in `input_fingerprint`. Exclude messages, evidence, ordering, time, and policy version from logical identity.
- [ ] **Step 4: Run the named tests and verify they pass.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py -k 'finding_id or fingerprint or stable_subject' -q`
Expected: PASS; rewrite evidence changes fingerprints but not logical ID.

## Task 3: Implement and test the pure severity policy

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/gate_severity_policy.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py`

**Interfaces:**
- `GateSeverityPolicy()`
- `evaluate(findings: list[DetectedFinding], *, policy_version: str, scope: dict) -> GateDecisionSet`, with per-finding `GateDecision` and aggregate action.
- `GateDecisionSet.hard_count` counts only `HARD_INTEGRITY`, `HARD_CANON`, `HARD_USER`; `SCORE` is never counted.

- [ ] **Step 1: Add failing rule-table tests.** Cover empty findings→ALLOW_WITH_ADVISORY; combined outcomes→the stated precedence; LLM Canon candidate→HUMAN_DECISION/ADVISORY but never HARD_CANON; deterministic accepted-Canon contradiction→HARD_CANON; explicit user contract→HARD_USER; ordinary plan miss→ADVISORY; `CRAFT_HEURISTIC` style/timed-lock findings→ADVISORY; SCORE→ALLOW_WITH_ADVISORY and hard_count 0 at values below/above a configured advisory threshold while remaining within the declared scale; malformed/out-of-scale score schema rejection; workflow integrity vs human-choice mapping; and RECOVERABLE reevaluation inputs.
- [ ] **Step 2: Run the new policy tests and verify failure.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py -k policy -q`
Expected: FAIL because `GateSeverityPolicy` is not implemented.

- [ ] **Step 3: Implement a pure versioned rule table.** Give each outcome stable `rule_id` and reason. Reject LLM authority for HARD_CANON; require typed accepted Canon evidence and deterministic validator identity; allow HARD_USER only with all explicit contract bindings; keep planner Intent misses advisory/score; prevent score threshold escalation. Aggregate outcomes by `REJECT > REQUIRE_HUMAN > RECOVER > ALLOW_WITH_ADVISORY`; return `ALLOW_WITH_ADVISORY` for an empty finding list.
- [ ] **Step 4: Run all finding and policy tests.**

Run: `pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py -q`
Expected: PASS; repeated evaluation of the same inputs and policy version has identical decisions/fingerprints.

## Step-level commit boundary

This entire Step Plan 1 is executed by one implementation subagent and produces exactly one commit, only after Tasks 1–3 and all targeted tests pass. Do not create task-level or slice-level commits. The independent reviewer runs after that commit and before Step 2 starts.

```bash
git add .claude/plugins/zhanghui/scripts/data_modules/gate_findings.py .claude/plugins/zhanghui/scripts/data_modules/gate_severity_policy.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py
git commit -m "feat: add deterministic gate finding policy"
```
