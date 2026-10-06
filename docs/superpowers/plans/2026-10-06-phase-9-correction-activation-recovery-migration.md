# Phase 9 — Correction Activation, Recovery & Migration Implementation Plan

> **For agentic workers:** This plan is execution-ready only after the design is reviewed. Implement task-by-task with test-first changes and focused review. Do not begin until the user approves this design and separately authorizes implementation.

**Goal:** Activate trusted append-only Canon corrections through separate active/candidate histories, immutable publication records, Canon-only projection generations, live mutable owner overlays, and opt-in project migration.

**Architecture:** Keep accepted commits and correction artifacts immutable. Gate production approval on a real host-origin human interaction capability. Separate active and candidate snapshots; freeze activation dependencies in monotonic publication records. Build Canon-only generations, preserve mutable Intent/Craft/Workflow owners in live overlays, and let runtime pin both. Migration preflight, backup, dry-run, and same-semantic recovery use the same ownership-aware publication protocol.

**Tech Stack:** Existing Python data modules, Pydantic schemas, JSON artifacts, SQLite, filesystem atomic rename/fsync, existing pytest architecture and projection suites; no new runtime dependency unless implementation proves a specific gap.

**Spec:** `docs/superpowers/specs/2026-10-06-phase-9-correction-activation-recovery-migration-design.md`

## Global Constraints

- Baseline implementation starts from `63f3cef58090f399e6e8b740e3efebe6e5f3e459`.
- Canonical implementation root is `.claude/plugins/zhanghui/`; never edit `.claude/plugins/zhanghui/6.4.0/**`.
- Never rewrite accepted commits or edit/delete correction artifacts to activate, rebuild, migrate, or roll back.
- No caller-supplied dict, CLI flag, actor_ref, ordinary GateDecision response, skill, or agent artifact may be trusted correction approval; Python types are not a security boundary.
- If no real production host-origin direct-human confirmation capability is available, activation stays disabled and Phase 9 cannot be declared complete/CLOSED.
- All effective-history semantics remain in `canon_correction_resolver.py`; consumers do not reinterpret correction artifacts. Rejected proposals remain non-edges and cannot poison active history.
- Active and candidate snapshots are separate. Proposal append never changes active runtime; active referenced-artifact corruption fails closed.
- Initial correction activation/recovery builds the full sparse history because no verified suffix checkpoint exists.
- Preflight and dry-run are read-only; migration needs a verified backup and a reviewed conflict-free plan.
- Do not bump package or marketplace version without an explicit existing release-policy decision; do not conflate package and project schema versions.
- No Phase 10 Intent/Craft reconciliation, CHANGES retirement, or legacy-support deletion.
- H1 contains implementation plus a result-free template with no H1 SHA/results. Test exact H1 externally, independently review, then create record-only H2 that names tested H1 and evidence.

## Review Focus

- Host identity cannot be authenticated by repository code alone: prove provider-origin interaction evidence cannot be created by normal caller inputs, or keep activation disabled.
- A new correction appearing while a generation builds changes the lineage digest: prove publication rechecks the exact digest under lock.
- A RETRACT removes N's projections but later commits remain: prove full suffix state/lifecycle replay without silently rewriting N+1 Canon.
- Non-Canon project state shares storage with projections: prove backup/staging/restore preserve unowned values and detect post-backup edits.
- Existing readers may bypass the main context builder: enumerate the active ownership inventory and route or explicitly block every Canon reader before enabling activation.

---

## File and interface map

| Area | Active files and responsibility |
|---|---|
| Trusted decision | `scripts/data_modules/canon_correction_store.py` for immutable correction persistence; new `correction_decision_provider.py` for host capability and verifier evidence; correction CLI/command and focused provider tests |
| Effective source | New `effective_history.py` for validated snapshot facade and typed entries; existing `canon_correction_resolver.py` remains the sole semantic interpreter; `durable_projection.py` validates base/effective projection inputs |
| Generation protocol | New `projection_generation.py` for journal, Canon-only manifests, staging validation and monotonic publication records; `projection_rebuild.py`, `projection_log.py`, `projections.py`, and router adapt to generation targets |
| Writers/readers | `chapter_commit_service.py`, state/index/summary/memory/vector writers, `event_log_store.py`, `event_projection_router.py`, `context_provenance.py`, `context_manager.py`, query/recovery entrypoints consume typed snapshot/generation interfaces |
| Mutable owners | New `owned_project_view.py` composes pinned Canon slices with mutable state/index/memory/RAG owner stores |
| Migration | New `project_migration.py` and CLI subcommands for active/candidate preflight, backup verification, dry-run, migration and same-semantic recovery |
| Governance and instructions | `docs/ownership-inventory.json`, `docs/ownership-inventory.schema.json` only if schema needs new fields, active ownership guard/tests, active write/query/resume/recovery instructions and package docs |
| Acceptance | Focused tests in active `scripts/data_modules/tests/`; adversarial integration/recovery tests; H1 result-free template and H2 evidence record created at their respective acceptance stages |

Exact helper names below are the cross-task contract; keep them stable or update all later tasks in the same reviewed change.

## Task 0: Verify production host capability before activation implementation

**Files:**
- Read-only audit: host/plugin API documentation and installed host callback surface available at implementation time
- Evidence: production capability audit record in the acceptance evidence packet (no repository artifact required at this design stage)

**Interfaces:**
- Consumes: actual host API/callback documentation and callable invocation surface.
- Produces: `CAPABILITY_EXISTS` or `CAPABILITY_ABSENT`, with API source, invocation authority, forgery/replay analysis, exact request/auth binding, and unavailable behavior.

- [ ] Trace a callable direct-human confirmation API from the production plugin boundary to a host-origin event. Current repository code does not expose one; do not infer support from a prompt-shaped API.
- [ ] Test whether agents/skills/tool arguments/local files can invoke or synthesize the event. State separately whether this is human-mediated confirmation or cryptographic identity proof.
- [ ] If capability exists, proceed to Task 2 and require tests through that actual production API.
- [ ] If absent, implement only the provider interface/unavailable result and explicitly authorized non-activation infrastructure. Stop activation work and report `PHASE_9_BLOCKED_ON_TRUSTED_HOST_CAPABILITY`; Phase 9 cannot be declared complete/CLOSED. Obtain user direction before adopting a weaker threat model or splitting scope.

## Task 1: Pin the Phase 9 source and inventory all live boundaries

**Files:**
- Modify: `.claude/plugins/zhanghui/docs/ownership-inventory.json`
- Modify: `.claude/plugins/zhanghui/docs/ownership-inventory.schema.json` only if required by the existing schema
- Modify: `.claude/plugins/zhanghui/scripts/tests/architecture/ownership_inventory_guard.py`
- Test: `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py`
- Test: `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_documentation.py`

**Interfaces:**
- Consumes: marketplace-selected active plugin root and current inventory schema.
- Produces: explicit records for effective-history writer/readers, correction decision provider, activation marker, projection-generation writer/readers, and migration paths. Writer, reader, and migration records remain separate.

- [ ] Add failing inventory assertions proving each Canon reader, each correction artifact producer, each activation writer, and each migration path has an owner, authority, mode, fallback, and evidence.
- [ ] Run the focused architecture tests and confirm they fail for missing Phase 9 records.
- [ ] Extend active inventory and drift guard; exclude `6.4.0/**` and tests/vendor paths from active-source discovery.
- [ ] Run focused architecture tests and confirm expected records pass and a synthetic bypass fails.
- [ ] Commit the inventory boundary before implementation tasks use it.

## Task 2: Implement provider-origin evidence only after the capability gate

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/correction_decision_provider.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/canon_correction_store.py`
- Modify: correction CLI/command discovered in Task 1
- Create: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_correction_decision_provider.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py`
- Test: adversarial integration tests under `.claude/plugins/zhanghui/scripts/data_modules/tests/`

**Interfaces:**
- Consumes: `CanonCorrectionRequest`, `CanonCorrectionAuthorization`, exact artifact hashes, and a configured host interaction capability.
- Produces only if Task 0 is positive: `CorrectionDecisionProvider.review(request, authorization) -> VerifiedCorrectionDecision` carrying evidence validated against the actual host-origin event and exact request/auth IDs, digests and choice. Provider unavailable remains typed and fail-closed.
- A local dataclass, private constructor, token, CLI, file, or TTY does not qualify as host evidence.

- [ ] Write failing tests showing dicts, `actor_ref`, GateDecisionStore response JSON, CLI `--approve`, and agent-created files cannot satisfy `append_correction`.
- [ ] Add provider contract tests for APPROVE, REJECT, stale parent, wrong request digest, wrong authorization digest, reused interaction, and unavailable capability.
- [ ] Implement the narrow adapter for the exact audited host callback, full-content challenge and provider-origin evidence verifier. Do not claim cryptographic identity unless the host supplies it.
- [ ] Exercise the real production provider path end-to-end; test fixtures cannot satisfy production activation acceptance.
- [ ] Route the correction review command through the provider; ordinary skills can submit a request but cannot call a constructor or inject verification values.
- [ ] Retain Phase 8 fixture-only tests through an explicit test verifier fixture; ensure production imports cannot select it.
- [ ] Run focused provider/store tests and adversarial CLI tests; commit.

## Task 3: Build one effective-history snapshot facade

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/effective_history.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/canon_correction_resolver.py` only for typed input/result compatibility, not duplicated semantics
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/durable_projection.py`
- Create: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_effective_history.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_durable_projection.py` or current equivalent

**Interfaces:**
- `EffectiveHistoryEntry(chapter, base_commit, base_sha256, status, extraction_result, effective_revision_id, effective_content_sha256, applied_correction_ids)`.
- `ActiveEffectiveHistorySnapshot(ok, chapters, activation_record_id, base_set_digest, correction_lineage_digest, effective_history_digest, generation_id, diagnostics)` and `CandidateEffectiveHistorySnapshot(target_correction_id, chapters, candidate_digest, diagnostics)`.
- `EffectiveHistoryStore.read_active_snapshot(project_root) -> ActiveEffectiveHistorySnapshot`; validates only the frozen active dependency closure.
- `EffectiveHistoryStore.resolve_candidate(project_root, target_correction_id, provider) -> CandidateEffectiveHistorySnapshot`; proposal append never mutates active state.
- `EffectiveProjectionInput(base_commit, effective_entry, snapshot_id, snapshot_digest)` is constructible only through the facade.
- `validate_effective_projection_input(root, value) -> EffectiveProjectionInput` revalidates the on-disk base and effective digests.

- [ ] Test: pending request leaves active unchanged; retained REJECTED request does not poison active/unrelated candidate; valid staged correction is not live; candidate conflict blocks activation while prior active remains usable; mutation/deletion of active-referenced artifact fails closed; append after pin does not change that operation.
- [ ] Candidate-only tests prove malformed/sibling correction artifacts block candidate activation without poisoning a separately verified active snapshot.
- [ ] Implement deterministic full-set discovery and digest computation; delegate operation/lineage semantics only to the existing resolver.
- [ ] Extend durable validation so the immutable disk base must match and effective output must independently match the resolver snapshot; arbitrary dicts fail.
- [ ] Verify rejected commits remain non-effective and correction bases remain accepted-only.
- [ ] Run focused tests plus Phase 8 schema/store/resolver tests; commit.

## Task 4: Introduce Canon-only generations and monotonic publication records

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/projection_generation.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/projection_log.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/event_projection_router.py`
- Create: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_generation.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_log.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py`

**Interfaces:**
- `ProjectionGeneration.begin(snapshot, previous_generation) -> BuildHandle`.
- `BuildHandle.root` is the only Canon projection destination; mutable owner data never enters it. `record_writer(chapter, writer, result)` records snapshot-bound progress.
- `validate_generation(handle, expected_manifest) -> ValidatedGeneration` checks all seven Canon-owned projection domains and output digests.
- `publish_generation(validated, expected_previous_publication, expected_lineage_digest) -> PublicationRecord` atomically creates a monotonic record only after lock-time recheck.
- Each record freezes the base/correction/request/auth/provider evidence, effective revisions/content and generation manifest. Semantic activation ID advances only for a new effective-history digest; same-snapshot replacement retains it.
- Reader: `pin_active_generation(project_root) -> PinnedGeneration`; validates the record chain/closure and pins one immutable publication record plus its generation.

- [ ] Add failure tests for manifest fsync, generation rename, publication-record atomic create, monotonic sequence, lock contention and concurrent candidate append.
- [ ] Prove missing writer/tombstone or digest mismatch prevents publication, and a request to roll back to older semantic activation is rejected.
- [ ] Implement unique staging directories and append-only publication records. Generation includes only Canon slices; mutable owner overlays are separate. Hash all seven Canon projection domains.
- [ ] Implement fsync/atomic create, activation lock, previous-publication comparison and exact lineage digest recheck. Any current-head file is a cache, never semantic authority.
- [ ] Add generation identity fields to projection run logs; legacy commit hash-only logs cannot mark a correction generation healthy.
- [ ] Prove incomplete staging is invisible to readers and a reader pins exactly one publication record/generation pair.
- [ ] Run focused generation/log tests on supported platforms and commit.

## Task 5: Make all projection writers consume typed effective inputs

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/chapter_commit_service.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/state_projection_writer.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/index_projection_writer.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/summary_projection_writer.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/memory_projection_writer.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/vector_projection_writer.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/event_log_store.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/projection_rebuild.py`
- Modify: focused `test_chapter_commit_service.py`, `test_projection_writers.py`, `test_event_log_store.py`, `test_vector_projection_writer.py`, `test_projection_rebuild.py`

**Interfaces:**
- Existing normal commit path: `ChapterCommitService.apply_projection_writers(base_commit)` resolves the base-only/effective active snapshot through the facade and writes into its selected generation.
- Correction path: `apply_effective_projection(EffectiveProjectionInput, BuildHandle)` writes derived payloads but does not persist or mutate `base_commit`.
- Every writer returns a result with `base_sha256`, `effective_revision_id`, `effective_content_sha256`, and `generation_id`.

- [ ] Add failing tests proving all seven writers reject plain corrected dictionaries, mutated base commits, and inputs whose generation digest differs.
- [ ] Add AMEND and RETRACT projection tests proving event file/SQLite, state, index, summary, memory, vector and intent diagnostics use effective values while base bytes remain unchanged.
- [ ] Refactor writer payload access through one effective view; preserve `require_durable_commit_match` on base evidence and validate resolver provenance separately.
- [ ] Ensure retract generates explicit absence/tombstone metadata rather than leaving prior chapter files to be read as current.
- [ ] Make the rebuild coordinator consume one snapshot for every writer and validate the full generation before it can be published.
- [ ] Run focused writer and Phase 8 provenance regressions; commit.

## Task 6: Keep existing mutable owners live beside immutable Canon slices

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/owned_project_view.py`
- Modify: `state_manager.py`, `story_craft.py`, `data_modules/webnovel.py`, `volume_state.py`, `promise_ledger.py`, `update_state.py`, and `consistency/core/runner.py`
- Modify: `index_manager.py`, `sql_state_manager.py`, `memory/store.py`, `memory/writer.py`, `rag_adapter.py`, and every direct writer/reader in the Phase 7 inventory
- Create: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_owned_project_view.py`
- Modify focused state, index, memory and RAG tests under active `scripts/data_modules/tests/`

**Interfaces:**
- `OwnedStateStore.read_view(PinnedGeneration) -> merged state`; owner writes persist only `.webnovel/state-overlay.json` paths allowed by the inventory.
- `OwnedIndexView` reads Canon tables from a generation-local SQLite slice and routes operational/workflow writes to `.webnovel/index.db`.
- `OwnedMemoryView` merges commit-evidence rows from the generation with mutable scratchpad rows; direct writers cannot edit reserved Canon rows.
- `OwnedRAGView` queries Canon commit vectors and mutable non-Canon vectors separately, then merges ranked hits without mutating either store.

- [ ] Add failing tests for a new planning/Craft/workflow write after activation; the next runtime view must see it while generation digest and Canon slices stay unchanged.
- [ ] Test row/table/field collisions. Ambiguous existing overlap blocks migration instead of choosing a winner.
- [ ] Route state writes to mutable overlay, retain old `state.json` unchanged, and compose the familiar merged view for existing reader APIs.
- [ ] Split Canon chapter/index/event/entity outputs into generation-local stores; preserve operational/workflow rows in the mutable index DB.
- [ ] Split commit-derived memory/vector rows from direct/non-Canon rows; preserve provenance and merge query results with explicit authority labels.
- [ ] Prove StateManager, Craft, Promise Ledger, workflow, SQL/IndexManager, direct memory and non-Canon RAG writes/readers continue working after activation.
- [ ] Commit the ownership adapter before changing runtime reader routing.

## Task 7: Route runtime/context/query/recovery through pinned Canon plus owner views

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/context_provenance.py` and `context_manager.py`
- Modify: query/RAG and runtime-source readers enumerated by Task 1
- Modify: `projections.py`, `doctor.py`, recovery reports, and active query/resume/write/recovery instructions
- Add focused context/query/recovery integration tests under active `scripts/data_modules/tests/`

**Interfaces:**
- Runtime pins one active publication and generation and captures each owner-overlay revision once; all reads use this composite view.
- Retry refreshes only failed writers for the exact active semantic ID/digest; correction mismatch stages a same-semantic generation replacement or a new candidate, never raw commit replay.
- Existing owner writes after activation appear in the next operation through mutable overlays without changing Canon generation.

- [ ] Test all inventory reader families, candidate append after pin, active evidence corruption, and owner-overlay update after pin.
- [ ] Route every Canon reader/direct store read through `OwnedProjectView` or return explicit unsupported/blocked state; candidate API is unavailable to runtime.
- [ ] Preserve base-only behavior before activation enrollment. After enrollment, missing active record or active digest mismatch fails closed; no base fallback.
- [ ] Update Doctor/recovery reports with separate active/candidate status, semantic activation ID, effective revision/tip, generation and overlay revisions.
- [ ] Distinguish correction proposal/reject/review/activation in active skills; prohibit agent-issued semantic approval.
- [ ] Test legitimate state, index, memory and RAG owner writes remain visible without changing active Canon; commit.

## Task 8: Implement read-only migration preflight, dry run and verified backup

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/project_migration.py`
- Modify: active CLI dispatcher in `.claude/plugins/zhanghui/scripts/webnovel.py`
- Create: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_project_migration.py`
- Modify: active schema/migration tests only as required by the report contract

**Interfaces:**
- `preflight_project(root) -> PreflightReport` reports separate active health and selected-candidate status, evidence hashes, owner mappings and conflicts.
- `dry_run_migration(root, report_digest) -> MigrationPlan` lists exact Canon slices, mutable overlays, preserved sources, output hashes and unresolved decisions; it is read-only.
- `create_verified_backup(root, plan) -> BackupManifest` verifies files, SQLite integrity, vector sidecars and temporary restore.

- [ ] Hash the project before/after preflight and dry run; test pending, rejected, active correction plus conflicted candidate, active evidence corruption, dirty shared stores, and clean base-only project.
- [ ] Prove pending/rejected proposals do not change `active_status`; candidate conflicts do not invalidate a healthy active record.
- [ ] Implement deterministic classifications and exact ownership/source evidence; preflight and dry run write no project files.
- [ ] Verify backup for `.story-system`, `.webnovel`, vector DB sidecars, overlay inputs and configured source files; any integrity/hash/restore failure stops migration.
- [ ] Report overlay field/table mapping and required human decisions; ambiguous ownership blocks instead of choosing a winner.
- [ ] Run focused preflight/dry-run/backup tests and commit.

## Task 9: Execute opt-in migration and same-semantic operational recovery

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/project_migration.py`
- Modify: active CLI dispatcher and migration command docs
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/projection_generation.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_project_migration.py`
- Add migration end-to-end tests in `.claude/plugins/zhanghui/scripts/data_modules/tests/`

**Interfaces:**
- `migrate_project(root, expected_report_digest, reviewed_plan_digest, backup_manifest) -> MigrationResult` rechecks source hashes and publishes only a validated complete generation.
- `replace_generation(root, generation_id) -> PublicationRecord` accepts only a verified generation with current semantic activation ID and identical effective-history digest; older semantic IDs are rejected.
- Filesystem restore requires backup manifest plus explicit post-backup conflict report; it never removes newer corrections, activation enrollment, or current semantic history.

- [ ] Add failing tests for source hash changes after preflight, human unresolved conflict, unavailable provider, failed generation writer, and stale build digest.
- [ ] Implement revalidation, verified-backup prerequisite, owner-overlay setup, activation-mode enrollment, staged full-history Canon generation, final source/lineage recheck, and immutable publication-record creation.
- [ ] Add legacy/partial/mixed test fixtures proving no silent delete, overwrite, sibling choice or Craft promotion.
- [ ] Add crash tests before/after publication-record creation and same-semantic generation replacement; prove prior semantic activation cannot be selected.
- [ ] Add filesystem migration rollback tests proving activation enrollment, current semantic activation and new corrections remain intact; newer files are preserved and conflicts block restore.
- [ ] Run full migration/recovery focused suites; commit.

## Task 10: Integrate production correction activation last

**Files:**
- Modify: correction command/CLI and `canon_correction_store.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/effective_history.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/projection_generation.py`
- Modify: active ownership inventory/docs and correction review/recovery skills
- Add: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_correction_activation.py`

**Interfaces:**
- `activate_correction(project_root, correction_id, provider) -> ActivationResult` resolves the exact candidate, builds/validates a full Canon-only generation, rechecks candidate/active digests under lock, and creates one immutable publication record.
- A staged append never changes active history; activation failure leaves the active publication and pinned operations unchanged.

- [ ] Add failing end-to-end tests that observe active publication identity, runtime snapshot, mutable owner overlays and every Canon projection domain before/after valid production approval and every failure class.
- [ ] Prove no consumer can observe correction live before a complete publication record and every post-publication consumer reports identical semantic activation/revision/tip/generation.
- [ ] Implement activation by composing Tasks 0 and 2–9; do not introduce per-consumer flags or duplicate resolver logic. A test-only verifier cannot satisfy production acceptance.
- [ ] Add process-crash and candidate-added-during-build tests; prove publication records advance monotonically and correction artifacts obey the specified invariants.
- [ ] Update ownership inventory, drift guard evidence and operator recovery documentation.
- [ ] Run Phase 8 regressions, architecture/projection and owner-overlay suites, real-provider activation attacks and acceptance-template guard. If Task 0 was negative, stop and report `PHASE_9_BLOCKED_ON_TRUSTED_HOST_CAPABILITY`; do not claim closure.
- [ ] Inspect the exact production diff and confirm `.claude/plugins/zhanghui/6.4.0/**` is unchanged; commit implementation candidate H1 with a result-free acceptance template.

## Task 11: Run exact-H1 acceptance, independent review, and record-only H2

**Files:**
- Create in H1: `docs/superpowers/acceptance/phase-9-h1-acceptance-template.md` (result-free)
- Create in H2 only: `docs/superpowers/acceptance/phase-9-h2-evidence.md`
- No production implementation changes in H2.

**Interfaces:**
- H1 template contains commands, suites, environments, evidence fields and binding structure only. It must not contain its own SHA/tree, run/node IDs, results, or PASS/FAIL.
- H2 records only H1 verification/review result, immutable artifact hashes, and reviewer disposition.

- [ ] Verify H1 contains implementation plus result-free template; add a guard test rejecting H1 SHA/tree/results/node IDs/PASS/FAIL in the template.
- [ ] Run the full matrix against exact H1; record H1 SHA, parent/tree, commands, results and node IDs in external/local ignored evidence, not H1.
- [ ] Obtain independent review of exact H1 and external evidence; requested implementation changes create a new H1 and require rerun.
- [ ] Create H2 record-only with `tested_implementation_head = H1`, H1 parent/tree, commands, results, node IDs, hashes and review disposition. Prove H2 is not tested as H1 and contains no production changes.
- [ ] Verify final mainline integration requirements separately; no PR or merge mechanics are implied by this design plan.

## Plan self-review

- Task 0 is a hard closure gate: absent production host capability means Phase 9 is blocked, not complete. Test-only verifier evidence cannot pass production activation acceptance.
- Active/candidate state, rejected proposals, active evidence corruption, monotonic semantic activation, and same-semantic generation replacement have distinct tests/statuses.
- Canon generations contain only Canon slices; state/index/memory/vector owners remain writable and visible after activation without mutating generations.
- Migration is separated into read-only classification/backup and later opt-in execution; every write follows a verified backup and generation validation.
- Phase 8 artifacts stay immutable, Phase 10 and CHANGES stay out of scope, and `6.4.0/**` remains outside the active source set.
- H1 template is result/self-reference-free; exact H1 results and independent disposition are recorded only in H2.
