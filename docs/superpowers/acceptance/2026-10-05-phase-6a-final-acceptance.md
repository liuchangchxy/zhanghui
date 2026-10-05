# Phase 6A Final Acceptance Manifest

Status: baseline definition; execution evidence is attached to the tested commit as a Git note after the final run.

## Binding

- Target branch: `codex/phase-6a-gate-policy-implementation`
- Acceptance is bound to the exact committed HEAD under test. The manifest definition is committed before execution; results and all collected node IDs are saved in a Git note attached to that HEAD so recording evidence does not change the tested commit.
- No product code changes are permitted during acceptance.
- Historical `110 passed` is an unverifiable historical execution result; superseded by final reproducible acceptance baseline. Neither 110 nor 87 is an acceptance target.

## Canonical file groups

| Group | Test files | Coverage |
|---|---|---|
| A — Step 1 shared finding/policy | `test_gate_findings.py` | Finding schema/identity; category, authority, explicitness; severity policy; HARD_USER provenance; SCORE; legacy-policy and recovery edge cases. |
| B — Step 2 decision/commit outcome | `test_gate_decision_store.py`, `test_chapter_commit_service.py`, `test_chapter_commit_schema.py`, `test_story_contracts.py`, `test_story_contract_schema.py`, `test_chapter_commit_conflict.py`, `test_rejection_contract.py` | GateDecision persistence and binding; commit-service recomputation; pending/no-commit and rejected/durable behavior; recovery/reevaluation; commit schema. |
| C — Step 3 production veto migration | `test_gate_finding_adapters.py`, `test_review_schema.py`, `test_review_author_view.py`, `test_review_with_craft.py` | Review adapters and LLM blocking compatibility; Craft provenance; fulfillment/disambiguation; timed-lock, pacing, hook, Scene-Sequel no text-derived veto; Changes Gate R0–R8 and legacy count/bool compatibility. |
| D — Step 1/2 cross-step regression | Groups A and B plus `test_memory_contract_adapter.py` | Regression coverage across shared policy, persistence, commit callers and schema. This named-file set replaces any unverifiable historic count. |
| E — P1–P7 mapping contract | `test_consistency_finding_adapters.py`, `test_gate_finding_adapters.py` | P1–P7 mapping contract and pure adapters only. No `tests/unit/consistency` directory is included. |

Canonical suite is the union of A, B, C and E, with duplicate files listed once. D is run separately as the Step 1/2 regression command.

## Exact canonical command

Run from repository root:

```bash
pytest \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_schema.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contracts.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contract_schema.py \
  .claude/plugins/zhanghui/scripts/tests/test_chapter_commit_conflict.py \
  .claude/plugins/zhanghui/scripts/tests/test_rejection_contract.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_finding_adapters.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_review_schema.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_review_author_view.py \
  .claude/plugins/zhanghui/scripts/tests/integration/test_review_with_craft.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py \
  -q
```

## Exact collection command

```bash
pytest \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_schema.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contracts.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contract_schema.py \
  .claude/plugins/zhanghui/scripts/tests/test_chapter_commit_conflict.py \
  .claude/plugins/zhanghui/scripts/tests/test_rejection_contract.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_finding_adapters.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_review_schema.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_review_author_view.py \
  .claude/plugins/zhanghui/scripts/tests/integration/test_review_with_craft.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py \
  --collect-only -q
```

## Exact Step 1/2 regression command

```bash
pytest \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_findings.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_gate_decision_store.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_schema.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contracts.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_contract_schema.py \
  .claude/plugins/zhanghui/scripts/tests/test_chapter_commit_conflict.py \
  .claude/plugins/zhanghui/scripts/tests/test_rejection_contract.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_contract_adapter.py \
  -q
```

## Recorded acceptance result

Execution evidence must record the tested HEAD SHA, exact commands, canonical collected count, every collected node ID, pass/fail counts, Step 1/2 regression result, independent review verdict, A–K verdicts, workspace status and diff check. Store that evidence as a Git note on the tested HEAD. A document-only correction that changes HEAD requires rerunning both commands above on the new HEAD before acceptance.
