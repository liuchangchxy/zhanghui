# Phase 6B — Consistency Consumer Convergence & Legacy Blocker Retirement

Status: design for review; no runtime changes included.
Audit baseline: origin/main c86b68fba221df9fd9f85d25634d221034cbee47.

## 1. Decision

Keep DetectedFinding and GateSeverityPolicy as the sole shared observation and severity model. Migrate P1–P7 incrementally to structured producer facts, first preserving a compatibility adapter at the consistency boundary. Route those facts to consumers according to their jobs. Write and plan consume craft findings as advice/recovery guidance; review displays findings as evidence. They do not enter ChapterCommitService by default. A future deterministic, chapter-scoped canon contradiction may be provided as an input only if evidence and provenance are sufficient; ChapterCommitService must recompute policy and remain the sole commit veto owner. P7 projection health remains in projection/recovery ownership.

CLI process status reports whether invocation/protocol and checker execution completed successfully; it does not report a domain decision. The structured result action is the domain decision. REJECT, REQUIRE_HUMAN and RECOVER are read from that action and must never be guessed by a skill from exit code. Consumer-specific behavior means deciding what to do with the shared action, not implementing another severity mapping. If shell/CI later needs domain failure to become nonzero, an explicitly named consumer/wrapper contract must translate the structured action; the base CLI process-status contract stays unchanged. Retire Blocker only after producers, consumers, tests, package copies and prose have migrated.

## 2. Baseline and evidence

origin/main is the stated c86b68f baseline. The actual checkout is codex/phase-6a-gate-findings-design at 52059f03238f6445181482053fc5c12e62c10c6e, not descended from origin/main; it removes Phase 6A implementation files relative to that baseline. This audit reads the accepted origin/main tree. Five untracked Phase 6A plan files in the current checkout are unrelated and must be preserved.

Evidence anchors (all at origin/main):

- Producer types/runner: .claude/plugins/zhanghui/scripts/consistency/core/patch_base.py, consistency/core/runner.py, consistency/patches/p1_foreshadow_dag.py through p7_derived_views.py.
- CLI: scripts/consistency/cli.py.
- Phase 6A policy: scripts/data_modules/consistency_finding_adapters.py, gate_findings.py, gate_severity_policy.py, gate_finding_adapters.py, chapter_commit_service.py, gate_decision_store.py.
- Skill callsites: skills/webnovel-write/SKILL.md around 261–275 and 493–503; skills/webnovel-plan/SKILL.md around 291–299; skills/webnovel-review/SKILL.md around 96–105.
- Adapter usage: production definition only; no runner, CLI, review pipeline, write gate, skill wrapper or ChapterCommitService calls adapt_consistency_patch. Its tests use synthetic typed values.
- Tests: tests/unit/consistency/*, tests/integration/test_runner_e2e.py, scripts/data_modules/tests/test_consistency_finding_adapters.py and Gate/commit suites.
- README names .claude/plugins/zhanghui/ as plugin body. .claude-plugin/marketplace.json explicitly selects ./.claude/plugins/zhanghui at version 6.4.0; this is the shipped/runtime source. The nested .claude/plugins/zhanghui/6.4.0/ tree has drift but is not selected by the manifest. Treat it as a historical snapshot, not a live consumer or second canonical source.

## 3. Producer inventory

Every patch currently accepts CheckContext and returns list[Blocker]. Blocker contains only patch, chapter, message, fix_hint. There is no producer-native severity, issue_code, subject_id, structured evidence or provenance. The label Blocker conveys no policy authority.

| Producer | Inputs / current finding facts | Current issue cases | Side effects / use |
|---|---|---|---|
| P1 foreshadow_dag | state.story_craft.foreshadow_chain DAG and chapter | missing_id, duplicate_id, chronology, overdue, invalid_state, cycle | Default runner check; apply updates craft validation metadata. Cycle can be deterministic integrity evidence; others are craft/intent. |
| P2 volume_anchor | volume_anchors, chapter/progress | missing_anchor, malformed_anchor, progress_deviation, must_not_reveal, invalid_state | Check plus apply updating anchors in legacy state. Craft/intent. |
| P3 event_matrix | event_matrix_state type/history and chapter | malformed_history, consecutive_fast, gentle_quota, invalid_state | Check plus apply advancing matrix history. Pacing/craft, not past event truth. |
| P4 pacing_tracker | pacing_history and chapter | malformed_history, consecutive_fast, slow_quota, invalid_state | Check plus apply advancing pacing history. Craft. |
| P5 state_revision | state revision metadata and expected revision | revision_mismatch | Check plus apply stamping revision metadata. Infrastructure consistency. |
| P6 reader_contract | expectation debt, causal credits, endgame reserves, swap debt | high_expectation_debt, unsetup_action, endgame_limit, high_swap_risk, broken_promise, invalid_state | Check plus apply recording craft evaluation in legacy state. Craft/intent. |
| P7 derived_views | filesystem views and craft rows | missing_foreshadow_view_row | Check plus apply rebuilding view files. Projection health/recovery. |
| Runner failure wrapper | patch.check exception | generic message embeds exception type/text and repair hint | Converts crash into ordinary Blocker; loses distinction between infrastructure failure and content finding. |

Target model: producer facts carry checker_id/version, issue_code, scope, optional stable subject_id, typed evidence, input reference and display message/fix_hint. Producers never set effective severity/action. `subject_id` is present only for a real, stable logical subject; it is never fabricated to satisfy the schema or unlock a mapping. Missing subject alone does not make a finding unknown: a known patch + issue_code + structured evidence retains its category/authority mapping, while the separate identity/policy contract decides whether it is veto-capable. Advisory/Score craft findings may therefore be typed without a veto-capable subject. P1 cycle requires deterministic stable cycle identity from canonical node IDs/edges. P5 revision mismatch requires a real stable revision subject (the affected state/revision record with stable provenance); absent that identity it cannot receive deterministic hard/recovery semantics. P7 requires a stable projection/view subject. P2/P3/P4 aggregate craft findings such as quota deviations remain typed Craft findings with no subject where no real entity exists. P2–P7 define evidence per issue code; do not force identical subject semantics. P7 identifies view, missing row and source generation where available. Checker exceptions and incomplete runs are evaluation/infrastructure status with separate diagnostics, outside the story-finding list and outside GateSeverityPolicy input. They must never be fabricated as an ordinary story Blocker or DetectedFinding.

## 4. Consumer inventory and current dataflow

| Consumer | Current path and action | Target |
|---|---|---|
| consistency CLI check/list | cli.main → ConsistencyRunner.run_all → Blocker[] JSON; 1 for any finding, 0 for none, 2 for missing required project root/argparse error | Structured, versioned response. Exit reports invocation/evaluation success only. |
| write skill precheck | Direct Python import of cli.main(check); prose says exit 1 means BLOCKER and must solve before writing | Surface craft advice; independent write prerequisites keep their own authority. Do not treat P1–P7 as universal hard stop. |
| write skill apply | Direct cli.main(apply) post-write; runner isolates patch exceptions and may still return normally; prose says exit 1 means BLOCKER | Separate maintenance/rebuild result from finding action; surface partial recovery failures. |
| plan skill | Direct cli.main(check) per new chapter; nonzero means edit outline until clean | Show planning advice/human decision; no automatic veto for any finding. |
| review skill | Direct cli.main(check), then prints patch/message/fix_hint as BLOCKER | Display structured evidence; reviewer prose cannot elevate effective severity. |
| ChapterCommitService | Receives review/fulfillment/disambiguation/reconciliation and gate inputs; no consistency runner or adapter call | Retain as sole final chapter acceptance owner. Only a separately approved exact chapter-scoped invariant can be proposed as an input. |
| write_gates / review_pipeline / shell entrypoints | No consistency adapter call found; validate their own artifacts/reconciliation/projection duties | Keep boundaries; add an entrypoint only for a demonstrated need. |
| query/resume/init and other skills | No direct P1–P7 CLI call identified | No new consumer required; correct stale claims only if the active path is verified. |
| tests | Patch/runner/CLI tests and synthetic adapter tests | Add real producer-to-adapter-to-consumer coverage; synthetic mapping alone is insufficient. |
| versioned 6.4.0 tree | Duplicate code/prose with observed drift; marketplace manifest selects the canonical plugin root, not this nested tree | Historical snapshot only; do not duplicate implementation changes there. |

Current dataflow in words:

P1–P7 check → Blocker(patch, chapter, message, fix_hint) → runner (patch crashes become Blocker) → CLI JSON + exit 0/1 → write / plan / review prose treats exit or any row as BLOCKER.

The P1–P7 adapter expects issue_code + subject_id + evidence → DetectedFinding → GateSeverityPolicy, but has no production caller and is currently test-only.

ChapterCommitService consumes its existing structured producers/adapters → GateSeverityPolicy → per-attempt GateDecision → commit action. There is no edge from the consistency runner/adapter.

ConsistencyRunner.apply_all → legacy state maintenance or Story System P7 view rebuild; this is distinct from check and chapter commit.

## 5. Blocker lifecycle and retirement graph

Current dependency chain: seven Patch.check producers → ConsistencyRunner.run_all/crash wrapper → CLI JSON/exit → write/plan/review prose → tests and versioned snapshot.

The Phase 6A adapter is not a live bridge: legacy Blocker has none of the typed fields it reads. Missing values become LEGACY_UNKNOWN diagnostics. Existing adapter tests prove synthetic typed mappings, not real producer conversion.

Retirement prerequisites:

1. All active producers emit tested typed facts; runner faults are typed infrastructure diagnostics.
2. A temporary compatibility converter handles old rows as display-only unknown diagnostics; never parse message text for severity.
3. CLI and active skills use typed output/actions; no decision depends on Blocker, message text, list nonemptiness or finding exit status.
4. Runtime constructors/imports and test fixtures migrate. Keep compatibility tests only for proven stored/external callers.
5. Verify runtime package selection; manifest selects the canonical plugin root at version 6.4.0. Treat nested 6.4.0/ as historical and do not modify it absent a new release selector.
6. Repo search and tests show no active dependency. Delete compatibility and Blocker last.

## 6. Phase 6A invariants

- DetectedFinding remains the shared observation envelope; category, authority and explicitness remain separate.
- GateSeverityPolicy alone computes deterministic severity/action. Producer and LLM text cannot declare effective severity.
- SCORE is never a hard veto; ordinary Intent misses remain advisory/score.
- HARD_USER requires stable, explicit, provable USER_EXPLICIT constraints. LLM review alone cannot create HARD_CANON.
- GateDecision is append-only workflow/infrastructure audit, not Canon.
- ChapterCommitService remains the final chapter acceptance veto owner and its durable boundary is not redesigned.
- Shared semantics do not require all checkers to execute in ChapterCommitService.
- No GateService, second finding/severity registry, global UserConstraint registry or policy-as-Canon.

## 7. Alternatives

| Alternative | Ownership/coupling | Migration/compatibility cost | Failure modes |
|---|---|---|---|
| A. Put every P1–P7 check in ChapterCommitService | Commit service owns craft, view health and chapter acceptance; maximum coupling | High; attempt binding and commit artifacts expand, while prewrite/plan still need checks | Craft/stale view blocks chapter, checks duplicate, service becomes universal GateService |
| B. Typed producers + consumer-owned entrypoints (recommended) | Shared envelope/policy; each existing consumer acts within its role | Medium staged migration; temporary converter and parallel formats | Consumer may omit or mishandle action; mitigate with shared response contract and cross-layer tests |
| C. Keep Blocker as permanent facade | Runner/skills continue local authority; adapter remains optional | Lowest initial cost, persistent compatibility | Parallel authority becomes permanent; policy stays test-only and exit code remains semantic veto |

Reject A and C. B gives one severity owner while respecting planning, craft, projection recovery and chapter acceptance as different jobs.

## 8. ChapterCommit and consumer semantics

Consistency does not enter ChapterCommitService by default. Shared severity semantics do not imply a shared execution path.

- P1 cycle and P5 revision mismatch are deterministic candidates but current scope may be craft state or metadata, not the chapter under commit; require provenance and attempt binding first.
- P1 chronology/overdue, P2 anchor/progress/reveal, P3/P4 pacing and P6 reader contract are Craft/Intent by default. Display or invite author revision/human choice; no hard veto based on Blocker label.
- P7 missing derived view belongs to projection health and recovery, not Canon acceptance.
- Missing/corrupt inputs or checker crashes are infrastructure failures; retry/escalate through the owning workflow, not Canon contradiction.
- Only a future explicit architecture decision may admit an exact, deterministic finding whose evidence is relevant to the current chapter acceptance. If admitted, it is normalized and passed as a finding input; ChapterCommitService recomputes the final policy and persists its attempt decision. It never accepts another consumer's precomputed veto conclusion.

Consumer behavior matrix. Each cell describes permitted behavior from the shared `policy_action`; consumers do not recalculate severity. A consumer may stop its own step or request repair/human review without declaring the chapter rejected. Only ChapterCommitService makes the final chapter acceptance/rejection decision.

| Consumer | ALLOW_WITH_ADVISORY | RECOVER | REQUIRE_HUMAN | REJECT |
|---|---|---|---|---|
| write | Show advisory and continue its step. | Ask the owning recovery path to repair/rerun; pause dependent writing while recovery is pending. | Pause the current write step and request a human choice. | Stop the current write step for a real hard finding; do not label the chapter rejected or persist a veto. |
| plan | Show advice and continue planning. | Request owner-managed repair/rerun; pause dependent plan transition. | Pause the affected plan transition for a human choice. | Stop the current planning step on a real hard finding; do not reject a chapter or bypass commit ownership. |
| review | Display finding/evidence as advisory. | Route to projection/recovery owner and report status. | Mark review as awaiting human decision. | Report policy REJECT as a hard finding/evidence and stop review completion; cannot announce final chapter rejection. |
| CLI | Serialize findings and policy result; successful evaluation exits 0. | Serialize `policy_action`; successful evaluation exits 0. | Serialize `policy_action`; successful evaluation exits 0. | Serialize `policy_action`; successful evaluation exits 0. |
| projection/recovery owner | Report no recovery required (and any advisory). | Perform its authorized repair, then rerun against current input fingerprint. | Escalate to the designated human; do not mutate without authorization. | Stop that recovery workflow and report the policy result; no chapter decision. |
| ChapterCommitService | Apply its own commit contract to its inputs. | Not a default route for consistency recovery; preserve existing commit behavior. | Apply its existing human-gate contract to its own attempt. | Sole authority to convert its own recomputed policy result into final chapter rejection. |

`GateSeverityPolicy == REJECT` means the finding has a rejecting policy action. For write/plan/review it permits stopping or withholding completion of that consumer's current workflow step when the finding is genuinely hard; it is never itself a final chapter rejection. Skill consumers do not create a Canon/chapter veto record, raise severity, or bypass ChapterCommitService. Phase 6B does not add persistence for consistency human-response attempts; stale handling is limited to the current consumer workflow/evaluation envelope and its diagnostic log. A response cannot be claimed durable or protected across process restarts under this design.

## 9. Typed migration contract

Normalize patch-specific result records into DetectedFinding at the existing consistency boundary, not a new registry. Fields: checker id/version, issue_code, scope, optional stable subject_id, typed evidence, input/provenance reference, display message and optional fix_hint. A remediation owner identifier may be included, but not an effective severity. Unknown codes or insufficient evidence produce a diagnostic with no hard action.

Sequence: compatibility converter + typed model; migrate P1 first; add real producer/adapter tests; migrate CLI and consumers; migrate P2–P7 by patch-specific evidence; prove no active legacy consumer; remove Blocker last. Do not big-bang rewrite.

## 10. CLI contract

| Result | Exit |
|---|---:|
| Valid evaluation, no findings | 0 |
| Advisory/score findings | 0 |
| Recoverable finding/action | 0 |
| Requires human decision | 0 |
| Policy result REJECT | 0; structured action reports it |
| Invalid command/arguments/chapter/project input | 2 |
| Read/parse failure, incomplete checker execution, serialization failure | 1 |

Return a versioned JSON envelope with status (evaluated / invalid_input / execution_error), findings, `policy_action` (the aggregate action returned by GateSeverityPolicy), and diagnostics. Do not call this field `consumer_action`: consumers decide behavior after reading the policy result. Separate successful evaluation with rejecting result from inability to evaluate. Operational errors go to stderr. apply reports per-patch outcomes and partial failure; do not claim success if isolated exceptions occurred. override currently appends a record but runner does not read it; do not describe it as authority to bypass severity without a real audited consumer.

## 11. Skill contract

Consume structured actions and evidence. Never infer authority from exit status, finding count, message text or “BLOCKER”. No local threshold may promote a finding.

- Write: show craft findings and continue on ALLOW_WITH_ADVISORY; for RECOVER/REQUIRE_HUMAN/REJECT, apply the behavior matrix to the current write step without creating final chapter rejection or persistence. Independent write prerequisites retain their own authority.
- Plan: show chapter findings as advice on ALLOW_WITH_ADVISORY; for RECOVER/REQUIRE_HUMAN/REJECT, apply the matrix to the current planning step without a universal chapter veto.
- Review: include typed findings as evidence and apply the matrix to review completion; reviewer opinion cannot promote severity or announce final chapter rejection.
- Resume/query/init: no new consumer needed; correct stale path claims only when verified.
- Apply/recovery prose must distinguish state/view maintenance from check severity and state what it mutates.

## 12. Failure, retry, source binding and observability

Each evaluation envelope carries a deterministic `source_input_fingerprint` computed by the runner over the exact normalized snapshot the selected checkers read, plus chapter scope and checker id/version. The canonical serialization includes chapter identity/text when read, relevant state fields, outline inputs, previous-chapter inputs, and any external view/projection inputs actually read by a checker; absent inputs are represented explicitly. The fingerprint is over source inputs, not findings or policy output, so changed source cannot appear unchanged merely because it produces the same finding payload. The runner binds every normalized finding and evaluation result to this fingerprint; individual patches do not repeat the full state.

Before a consumer acts on a human response, recovery result, or workflow transition, it compares the current source fingerprint with the evaluation's fingerprint. On mismatch it retains the old envelope for the lifetime of that current workflow context, marks it stale, reruns, and evaluates only the new result; old ALLOW/REJECT/RECOVER is unusable. Phase 6B introduces no persistent consistency human-response attempt store and no second GateDecision store. The persistence boundary is the in-memory consumer workflow envelope plus ordinary diagnostic logging; there is no guarantee across process restarts or for a response submitted later in another process. Acceptance criteria must test this within the live workflow and must not claim durable stale-response protection. Durable human-response attempts require a future architecture decision. Reevaluation is appended to the current workflow's evaluation history/log, not to GateDecision. Ordinary consistency diagnostics never become chapter commit decisions.

Patch crashes make evaluation incomplete, not a story finding, GateSeverityPolicy input, or clean result; record them only in separate infrastructure diagnostics. Retry only through the existing owner. Recovery must be idempotent and verified by rerunning the relevant check. Log checker id/version, issue code, subject, source/evidence fingerprints, duration, completeness, recovery result, consumer and policy action. Avoid full prose/secrets. Track unknown legacy conversions for retirement readiness. GateDecision records remain only for actual commit workflow attempts; do not invent commit attempts for diagnostics.

## 13. Non-goals

No universal GateService, registry or global constraint registry; no forced ChapterCommit execution; no change to durable commit, GateDecision, Canon or projection ordering; no Craft/Style/Score hard veto; no LLM-made hard severity; no big-bang producer rewrite or unrelated .webnovel cleanup; no early Blocker deletion; no runtime change in this design phase.

## 14. Acceptance criteria

1. P1–P7 input/output/evidence contracts are documented and real producer outputs are tested through adapters.
2. Producers do not declare effective severity; policy computes it deterministically.
3. CLI separates successful findings from invalid input and infrastructure failure.
4. Write/plan/review use typed output/action and do not turn generic finding presence into hard veto.
5. ChapterCommitService has explicit boundary decision; default is no consistency input. Any exception is deterministic, evidence-backed, chapter-scoped and recomputed by the service.
6. P7 remains projection/recovery; craft findings remain advisory/human-consumed.
7. Runtime selection is verified from .claude-plugin/marketplace.json; canonical plugin root is selected and nested 6.4.0/ is excluded from runtime migration.
8. No active Blocker dependency remains before its final removal task.
9. Targeted consistency/CLI/adapter/skill/commit tests plus Phase 0–6A regression pass.
10. Crash, partial evaluation, retry, source-fingerprint staleness within the live consumer workflow, unknown code and compatibility are covered; no durable consistency human-response persistence is claimed.

11. Optional-subject semantics preserve known typed Craft mappings without granting veto-capable identity; P1 cycle, P5 revision mismatch and P7 projection recovery each state their stable identity prerequisite.
12. Source fingerprint binds the actual checker input snapshot; stale inputs invalidate prior policy results and require rerun within the live workflow.
13. One explicit runner → adapter → GateSeverityPolicy → CLI policy_action composition is used, with no CLI severity mapping.
14. The write/plan/review/CLI/projection-recovery-owner/ChapterCommitService behavior matrix is tested, including the distinction between stopping a consumer step and final chapter rejection.
