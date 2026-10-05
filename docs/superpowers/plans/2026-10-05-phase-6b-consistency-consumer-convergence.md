# Phase 6B Consistency Consumer Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Migrate consistency producers and consumers to typed findings with one deterministic severity owner, clarify CLI/skill actions, and retire legacy Blocker only after all live dependencies are gone.

**Architecture:** P1–P7 emit patch-specific typed observations that normalize through the existing consistency adapter into DetectedFinding. GateSeverityPolicy computes shared severity; each existing consumer uses only the action appropriate to its role. ChapterCommitService remains the sole chapter commit veto owner and receives no consistency finding by default.

**Tech Stack:** Python 3, pytest, Markdown skill instructions, existing Pydantic Gate finding and policy modules.

**Spec:** docs/superpowers/specs/2026-10-05-phase-6b-consistency-consumer-convergence-design.md

## Global Constraints

- Keep .claude/plugins/zhanghui/ as canonical plugin source; do not create another implementation under .Codex/plugins/zhanghui/.
- Keep references/ read-only.
- Do not create GateService, a second finding/severity registry or a global UserConstraint registry.
- Producers do not declare effective severity; GateSeverityPolicy remains deterministic owner.
- Consumer-specific behavior interprets the shared structured action; consumers never implement their own severity mapping.
- ChapterCommitService remains the final chapter acceptance veto owner; no default P1–P7 production connection.
- Do not remove Blocker until the final task and all active consumers have migrated.
- GateDecision remains workflow/infrastructure audit, not Canon.
- Keep Craft, Style and SCORE findings from becoming hard vetoes.
- Maintain a compatibility path until active consumers and package selection are verified.

## Review Focus

- A patch check crash must produce an incomplete infrastructure status plus separate diagnostics, never a story finding/Blocker or a false clean result. It is excluded from GateSeverityPolicy input. Test runner fault isolation and CLI failure status.
- A legacy Blocker must not gain authority through its message text or its old CLI exit status. Test conversion as unknown diagnostic and valid finding exit status 0.
- A human response must not reuse a finding after its source input changes. Test stale fingerprint detection and append-only reevaluation.
- A projection repair finding must not veto chapter acceptance. Test P7 maps to recovery and stays outside commit inputs.
- P1 cycle evidence must be deterministic and stable across ordering changes. Test normalized node/edge order, subject identity and evidence fingerprint.

---

### Task 1: Define typed patch observation and compatibility conversion

**Files:**
- Modify: .claude/plugins/zhanghui/scripts/consistency/core/patch_base.py
- Modify: .claude/plugins/zhanghui/scripts/data_modules/consistency_finding_adapters.py
- Test: tests/unit/consistency/test_patch_base.py
- Test: .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py

**Interfaces:**
- Produces: PatchFinding(patch: str, chapter: int, issue_code: str, message: str, fix_hint: str = "", subject_id: str | None = None, evidence: dict[str, object] via a dataclass default_factory).
- Consumes: Existing P1_P7_MAPPING and adapt_consistency_patch(patch_result, chapter_scope) -> list[DetectedFinding].
- Compatibility: adapt_consistency_patch continues accepting Blocker rows as display-only LEGACY_UNKNOWN diagnostics. It never parses message or fix_hint.

- [ ] **Step 1: Write failing contract tests**

Test PatchFinding dataclass fields and validation for missing issue_code, optional subject and structured evidence. Add an adapter test proving a legacy Blocker without typed fields yields LEGACY_UNKNOWN plus advisory-only action, regardless of wording such as “BLOCKER”.

- [ ] **Step 2: Run the focused tests and verify failure**

Run: PYTHONPATH=.claude/plugins/zhanghui/scripts pytest tests/unit/consistency/test_patch_base.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py -q
Expected: FAIL because PatchFinding and legacy diagnostic conversion are not implemented.

- [ ] **Step 3: Implement the smallest typed model and adapter path**

Add PatchFinding beside the existing Patch protocol. Extend the existing adapter to read dataclass attributes and dicts. Keep issue-code mapping explicit in P1_P7_MAPPING. Make missing/unknown codes diagnostics with no hard action.

- [ ] **Step 4: Run focused tests**

Run the Step 2 command.
Expected: PASS, with existing synthetic mapping tests unchanged.

- [ ] **Step 5: Review rollback**

At this point producers still return Blocker. Reverting this task leaves runtime behavior untouched; do not remove Blocker.

### Task 2: Migrate P1 foreshadow DAG producer

**Files:**
- Modify: .claude/plugins/zhanghui/scripts/consistency/patches/p1_foreshadow_dag.py
- Test: tests/unit/consistency/test_p1_foreshadow_dag.py
- Test: .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py

**Interfaces:**
- Consumes and emits PatchFinding defined in Task 1.
- P1 codes: missing_id, duplicate_id, chronology, overdue, invalid_state, cycle.
- cycle evidence: sorted unique cycle_ids and explicit cycle_edges; subject_id is cycle:<comma-separated sorted ids>.

- [ ] **Step 1: Add producer-native output tests**

For every P1 code, assert exact issue_code, subject_id semantics and evidence keys. Assert cycle result is independent of traversal order. Keep message/fix_hint display-only. Assert check does not mutate state.

- [ ] **Step 2: Run P1 tests and verify failure**

Run: PYTHONPATH=.claude/plugins/zhanghui/scripts pytest tests/unit/consistency/test_p1_foreshadow_dag.py -q
Expected: FAIL because check still emits Blocker.

- [ ] **Step 3: Migrate P1 checks**

Return PatchFinding records with typed evidence. Do not change P1 apply behavior or policy mapping.

- [ ] **Step 4: Run P1 and adapter tests**

Run: PYTHONPATH=.claude/plugins/zhanghui/scripts pytest tests/unit/consistency/test_p1_foreshadow_dag.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py -q
Expected: PASS; adapter receives real P1 producer outputs, not only synthetic rows.

- [ ] **Step 5: Review rollback**

The adapter still accepts old Blocker and P1 only changes result format. Revert P1 independently if downstream integration is not ready.

### Task 3: Migrate P2–P4 with patch-specific evidence

**Files:**
- Modify: .claude/plugins/zhanghui/scripts/consistency/patches/p2_volume_anchor.py
- Modify: .claude/plugins/zhanghui/scripts/consistency/patches/p3_event_matrix.py
- Modify: .claude/plugins/zhanghui/scripts/consistency/patches/p4_pacing_tracker.py
- Test: tests/unit/consistency/test_p2_volume_anchor.py
- Test: tests/unit/consistency/test_p3_event_matrix.py
- Test: tests/unit/consistency/test_p4_pacing_tracker.py

**Interfaces:**
- Each checker returns list[PatchFinding].
- P2 codes: missing_anchor, malformed_anchor, progress_deviation, must_not_reveal, invalid_state.
- P3 codes: malformed_history, consecutive_fast, gentle_quota, invalid_state.
- P4 codes: malformed_history, consecutive_fast, slow_quota, invalid_state.
- Subject/evidence are patch-specific; no shared synthetic subject is invented for quota-level findings.

- [ ] **Step 1: Add P2–P4 tests first**

For every listed code, assert the matching typed code and evidence fields needed to explain/reproduce it. Assert subject_id is stable only when there is a true stable entity. Assert check calls do not mutate state.

- [ ] **Step 2: Run patch tests and verify failure**

Run: PYTHONPATH=.claude/plugins/zhanghui/scripts pytest tests/unit/consistency/test_p2_volume_anchor.py tests/unit/consistency/test_p3_event_matrix.py tests/unit/consistency/test_p4_pacing_tracker.py -q
Expected: FAIL because these checks currently construct Blocker.

- [ ] **Step 3: Convert P2, P3 and P4 check output**

Use PatchFinding and per-code evidence; leave apply methods unchanged.

- [ ] **Step 4: Run the focused tests**

Run the Step 2 command.
Expected: PASS.

- [ ] **Step 5: Review rollback**

Compatibility conversion remains available for unmigrated producers; revert any patch independently if output semantics are unclear.

### Task 4: Migrate P5–P7 with integrity and recovery provenance

**Files:**
- Modify: .claude/plugins/zhanghui/scripts/consistency/patches/p5_state_revision.py
- Modify: .claude/plugins/zhanghui/scripts/consistency/patches/p6_reader_contract.py
- Modify: .claude/plugins/zhanghui/scripts/consistency/patches/p7_derived_views.py
- Test: tests/unit/consistency/test_p5_state_revision.py
- Test: tests/unit/consistency/test_p6_reader_contract.py
- Test: tests/unit/consistency/test_p7_derived_views.py
- Test: .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py

**Interfaces:**
- Each checker returns list[PatchFinding].
- P5 code revision_mismatch includes integer expected_revision and observed_revision.
- P6 codes: high_expectation_debt, unsetup_action, endgame_limit, high_swap_risk, broken_promise, invalid_state.
- P7 code missing_foreshadow_view_row identifies view, foreshadow_id and present=false; include projection/source generation when available.

- [ ] **Step 1: Add P5–P7 typed-output tests**

Assert every listed code has structured evidence. Assert P5 is not inferred from prose. Assert P7 produces a recoverable projection-health finding and its check does not repair files.

- [ ] **Step 2: Run patch tests and verify failure**

Run: PYTHONPATH=.claude/plugins/zhanghui/scripts pytest tests/unit/consistency/test_p5_state_revision.py tests/unit/consistency/test_p6_reader_contract.py tests/unit/consistency/test_p7_derived_views.py -q
Expected: FAIL because checks still emit Blocker.

- [ ] **Step 3: Convert P5–P7 check output**

Return PatchFinding with code-specific evidence. Keep all apply methods and persistence behavior unchanged.

- [ ] **Step 4: Run producer and adapter tests**

Run: PYTHONPATH=.claude/plugins/zhanghui/scripts pytest tests/unit/consistency/test_p5_state_revision.py tests/unit/consistency/test_p6_reader_contract.py tests/unit/consistency/test_p7_derived_views.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py -q
Expected: PASS, including real producer-to-adapter paths.

- [ ] **Step 5: Review rollback**

P5/P6/P7 format changes remain compatible with the old runner boundary. Revert a patch independently without changing severity policy.

### Task 5: Make runner output and infrastructure failures explicit

**Files:**
- Modify: .claude/plugins/zhanghui/scripts/consistency/core/runner.py
- Modify: .claude/plugins/zhanghui/scripts/consistency/core/patch_base.py
- Test: tests/unit/consistency/test_runner.py
- Test: tests/integration/test_runner_e2e.py

**Interfaces:**
- ConsistencyRunner.run_all returns normalized story findings plus evaluation status and a separate infrastructure diagnostics collection.
- A patch exception is not a story finding, Blocker or DetectedFinding and is never passed to GateSeverityPolicy.

- [ ] **Step 1: Add runner tests**

Test all seven typed patch outputs pass unchanged through normalization, an unknown legacy producer becomes diagnostic-only, and a raising patch marks evaluation incomplete rather than clean. Assert check remains read-only.

- [ ] **Step 2: Run runner tests and verify failure**

Run: PYTHONPATH=.claude/plugins/zhanghui/scripts pytest tests/unit/consistency/test_runner.py tests/integration/test_runner_e2e.py -q
Expected: FAIL against the current list[Blocker] return contract.

- [ ] **Step 3: Normalize runner results**

Add a small result envelope at the existing runner boundary. Keep P7 apply/recovery separate. Preserve old Blocker conversion only for the migration window.

- [ ] **Step 4: Run runner tests**

Run the Step 2 command.
Expected: PASS, including explicit partial evaluation.

- [ ] **Step 5: Review rollback**

Keep compatibility conversion enabled. Reverting runner normalization returns callers to old output without altering producer facts.

### Task 6: Converge consistency CLI output and exit semantics

**Files:**
- Modify: .claude/plugins/zhanghui/scripts/consistency/cli.py
- Test: tests/unit/consistency/test_cli.py

**Interfaces:**
- JSON output is a versioned envelope containing status, findings, optional consumer_action and diagnostics.
- check/list successful evaluation returns 0 whether findings are empty, advisory, recoverable, pending-human or policy REJECT.
- Invalid invocation/input returns 2; execution/incomplete evaluation returns 1.
- The structured action, not process status, expresses REJECT / REQUIRE_HUMAN / RECOVER. Any future shell/CI domain-failure exit mapping belongs to an explicit wrapper contract, not the base CLI.
- apply reports per-patch outcomes and partial failure; it does not silently claim full success.

- [ ] **Step 1: Add exit/output matrix tests**

Cover clean result, advisory finding, recovery action, require-human, REJECT, missing project root, malformed state/read error, patch crash and partial apply failure. Assert stdout JSON separates evaluated result from execution error.

- [ ] **Step 2: Run CLI tests and verify failure**

Run: PYTHONPATH=.claude/plugins/zhanghui/scripts pytest tests/unit/consistency/test_cli.py -q
Expected: FAIL where current any-finding exit 1 and output is a bare list.

- [ ] **Step 3: Implement the response envelope and process contract**

Have CLI map runner status/action without changing GateSeverityPolicy. Keep override described as an append-only record; do not make it a severity bypass.

- [ ] **Step 4: Run CLI tests**

Run the Step 2 command.
Expected: PASS.

- [ ] **Step 5: Review rollback**

CLI can retain a temporary output version option for existing callers. Do not ship a default contract switch until skill consumers in Task 7 are migrated.

### Task 7: Migrate active skill consumers

**Files:**
- Modify: .claude/plugins/zhanghui/skills/webnovel-write/SKILL.md
- Modify: .claude/plugins/zhanghui/skills/webnovel-plan/SKILL.md
- Modify: .claude/plugins/zhanghui/skills/webnovel-review/SKILL.md
- Read-only audit: .claude-plugin/marketplace.json (manifest selects the canonical plugin root; do not edit the nested historical snapshot)
- Test: .claude/plugins/zhanghui/scripts/data_modules/tests/test_prompt_integrity.py
- Test: .claude/plugins/zhanghui/scripts/tests/test_run_behavior_evals.py

**Interfaces:**
- Skill callers consume the versioned CLI envelope and structured action.
- Write/plan/review do not use process exit or finding count as severity.
- Skills choose consumer behavior from the shared action and do not recreate severity mapping.
- Package copy scope is gated by verified release/runtime selection. Canonical source remains .claude/plugins/zhanghui/.

- [ ] **Step 1: Add skill contract assertions**

Assert active skills document structured results, retain ChapterCommitService ownership, classify craft feedback as advisory/human-consumed, separate P7 recovery and do not claim CLI exit 1 equals BLOCKER. Add behavior-eval cases for finding present with exit 0 and infrastructure failure.

- [ ] **Step 2: Run skill contract tests and verify failure**

Run: PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_prompt_integrity.py .claude/plugins/zhanghui/scripts/tests/test_run_behavior_evals.py -q
Expected: FAIL on the current prose and status assumptions.

- [ ] **Step 3: Update active skill instructions**

Change only consistency consumer interpretation. Preserve separate anti-slop, artifact and chapter-commit rules. Fix the misleading apply exit contract. Audit plan/review/write calls and make all three consume the same CLI schema without treating their roles as identical.

- [ ] **Step 4: Run skill tests**

Run the Step 2 command.
Expected: PASS.

- [ ] **Step 5: Confirm package boundary**

Verify .claude-plugin/marketplace.json still selects ./.claude/plugins/zhanghui. Do not edit .claude/plugins/zhanghui/6.4.0/ unless a future manifest explicitly selects it; this snapshot is not an active consumer.

### Task 8: Verify commit boundary and end-to-end consumer semantics

**Files:**
- Test: .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py
- Test: .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py
- Test: tests/integration/test_runner_e2e.py
- Test: tests/unit/consistency/test_cli.py

**Interfaces:**
- No consistency finding is passed to ChapterCommitService by default.
- Only a future explicit architecture decision may admit a deterministic finding relevant to the current chapter acceptance. The service receives normalized findings and recomputes GateSeverityPolicy; no CLI/skill result or precomputed external veto is trusted.

- [ ] **Step 1: Add end-to-end tests**

Run one P1 typed finding through producer, runner, adapter, policy and CLI. Verify P1 craft/Intent actions do not veto commit. Verify P1 cycle/P5 integrity mapping remains a tested policy mapping but cannot affect commit unless explicitly wired. Verify P7 maps to recovery and projection maintenance. Verify prior GateDecision records are not changed by another evaluation.

- [ ] **Step 2: Run focused integration tests and verify failure**

Run: PYTHONPATH=.claude/plugins/zhanghui/scripts pytest tests/integration/test_runner_e2e.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py -q
Expected: FAIL on missing live producer path and explicit consumer assertions.

- [ ] **Step 3: Add only the minimum boundary glue**

Wire consumer entrypoints to the shared adapter/policy. Do not connect all consistency checks to ChapterCommitService. If the tests expose a genuine commit invariant requiring integration, stop for design review before adding it; the approved default design has no such input.

- [ ] **Step 4: Run focused integration tests**

Run the Step 2 command.
Expected: PASS with no ChapterCommit consistency input.

- [ ] **Step 5: Review rollback**

Consumer adapters and CLI schema remain separable; reverting a consumer must not change the deterministic policy or durable chapter commit contract.

### Task 9: Retire Blocker compatibility (last)

**Files:**
- Modify: .claude/plugins/zhanghui/scripts/consistency/core/patch_base.py
- Modify: .claude/plugins/zhanghui/scripts/consistency/core/runner.py
- Modify: .claude/plugins/zhanghui/scripts/data_modules/consistency_finding_adapters.py
- Modify: tests/unit/consistency/test_patch_base.py
- Modify: tests/unit/consistency/test_runner.py
- Modify: tests/unit/consistency/test_cli.py
- Modify: tests/unit/consistency/test_p1_foreshadow_dag.py through test_p7_derived_views.py
- Read-only audit: .claude-plugin/marketplace.json (verify release source)

**Interfaces:**
- All active patch, runner, CLI and skill paths use typed result envelopes.
- Blocker and compatibility conversion are deleted only after repository searches and tests prove no active caller.

- [ ] **Step 1: Add retirement guard tests**

Add a test/search guard that fails if production code imports or constructs Blocker or if skill contracts mention its old exit semantics. Keep historical design documents out of this active-code assertion.

- [ ] **Step 2: Run retirement guard and prove remaining consumers**

Run: rg -n 'Blocker|blocker' .claude/plugins/zhanghui/scripts/consistency .claude/plugins/zhanghui/scripts/data_modules/consistency_finding_adapters.py .claude/plugins/zhanghui/skills/webnovel-write .claude/plugins/zhanghui/skills/webnovel-plan .claude/plugins/zhanghui/skills/webnovel-review tests
Expected before removal: only the definition/compatibility tests slated for this task remain; all other runtime and prose matches are resolved.

- [ ] **Step 3: Remove Blocker and compatibility conversion**

Delete old type and conversion only after Tasks 1–8 pass. Update test fixtures to PatchFinding. Do not delete P1–P7 mapping or shared DetectedFinding/Policy.

- [ ] **Step 4: Run targeted consistency and consumer tests**

Run: PYTHONPATH=.claude/plugins/zhanghui/scripts pytest tests/unit/consistency .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_prompt_integrity.py .claude/plugins/zhanghui/scripts/tests/test_run_behavior_evals.py tests/integration/test_runner_e2e.py -q
Expected: PASS and zero active Blocker references.

- [ ] **Step 5: Review rollback**

If any supported caller still requires Blocker, restore the compatibility converter and defer deletion. Never ship a partially retired class with unverified consumer use.

### Task 10: Run final regression and acceptance matrix

**Files:**
- Test: all paths named below
- Record: docs/superpowers/acceptance/Phase 6B acceptance record, if the repository phase process requires a persistent record

- [ ] **Step 1: Run consistency/CLI/skill targeted suite**

Run: PYTHONPATH=.claude/plugins/zhanghui/scripts pytest tests/unit/consistency .claude/plugins/zhanghui/scripts/data_modules/tests/test_consistency_finding_adapters.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_prompt_integrity.py .claude/plugins/zhanghui/scripts/tests/test_run_behavior_evals.py tests/integration/test_runner_e2e.py -q
Expected: PASS.

- [ ] **Step 2: Run Phase 6A canonical regression**

From the repository root run the exact canonical command in docs/superpowers/acceptance/2026-10-05-phase-6a-final-acceptance.md, including the listed 13 Gate, commit, review, adapter and reconciliation test files. Expected: preserve the accepted canonical 125/125 result (update count only if approved test scope changes).

- [ ] **Step 3: Run Phase 0–6A Step 1/2 regression**

Run the exact Step 1/2 command in the same acceptance manifest, including the 9 gate, commit, story-contract and memory adapter test files. Expected: all pass.

- [ ] **Step 4: Review final acceptance matrix**

| Area | Acceptance evidence |
|---|---|
| P1–P7 output | Each producer emits typed code/evidence; tests exercise actual producer through adapter. |
| Shared policy | Craft remains advisory/score; P1 cycle/P5 integrity and P7 recovery retain deterministic mapped actions; no producer severity. |
| CLI | All five successful finding outcomes exit 0; invalid input exits 2; execution/incomplete evaluation exits 1. |
| Skills | Write, plan and review consume typed actions; no generic BLOCKER/exit rule. |
| Chapter commit | No default consistency wire; ChapterCommitService remains sole commit veto and preserves durable boundary. |
| Recovery/staleness | Retry is owner-specific; stale inputs trigger new evaluation; prior audit is retained. |
| Package copies | Manifest selects canonical plugin root; nested 6.4.0 snapshot is not a runtime consumer. |
| Retirement | Blocker definition, construction, imports, tests and live prose consumers are gone; compatibility removal is last. |
| Regression | Targeted tests, canonical Phase 6A suite, Step 1/2 suite, independent review and diff check pass. |

- [ ] **Step 5: Record verification and rollback**

Record tested HEAD, exact commands/results, final diff check and package-selection evidence. If a target or canonical regression fails, restore the compatibility path and do not claim Phase 6B complete.
