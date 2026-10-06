# Phase 9 — Correction Activation, Recovery & Migration Implementation Plan

> **For agentic workers:** This plan is execution-ready only after the design is reviewed. Implement task-by-task with test-first changes and focused review. Do not begin until the user approves this design and separately authorizes implementation.

**Goal:** Activate trusted append-only Canon corrections through one effective-history snapshot and one atomic, fully validated projection-generation pointer, with safe recovery and opt-in project migration.

**Architecture:** Keep accepted commits and correction artifacts immutable. Add a host-backed trusted decision capability, one production effective-history facade, typed correction-aware projection inputs, and generation-scoped projection writers. Build and validate a complete generation off-path, then atomically publish one pointer; readers pin one generation per operation. Migration preflight, backup, dry-run, and rollback use that same generation protocol.

**Tech Stack:** Existing Python data modules, Pydantic schemas, JSON artifacts, SQLite, filesystem atomic rename/fsync, existing pytest architecture and projection suites; no new runtime dependency unless implementation proves a specific gap.

**Spec:** `docs/superpowers/specs/2026-10-06-phase-9-correction-activation-recovery-migration-design.md`

## Global Constraints

- Baseline implementation starts from `63f3cef58090f399e6e8b740e3efebe6e5f3e459`.
- Canonical implementation root is `.claude/plugins/zhanghui/`; never edit `.claude/plugins/zhanghui/6.4.0/**`.
- Never rewrite accepted commits or edit/delete correction artifacts to activate, rebuild, migrate, or roll back.
- No caller-supplied dict, CLI flag, actor_ref, ordinary GateDecision response, skill, or agent artifact may be trusted correction approval.
- If no direct unsynthesizable human interaction capability is available, activation stays disabled and verifier-unavailable fails closed.
- All effective-history semantics remain in `canon_correction_resolver.py`; consumers do not reinterpret correction artifacts.
- Every consumer pins one effective snapshot/generation; no partial or mixed generation may report healthy.
- Initial correction activation/recovery builds the full sparse history because no verified suffix checkpoint exists.
- Preflight and dry-run are read-only; migration needs a verified backup and a reviewed conflict-free plan.
- Do not bump package or marketplace version without an explicit existing release-policy decision; do not conflate package and project schema versions.
- No Phase 10 Intent/Craft reconciliation, CHANGES retirement, or legacy-support deletion.
- H1 is the exact implementation plus result-free acceptance template; run acceptance on H1, independently review, then create record-only H2.

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
| Generation protocol | New `projection_generation.py` for journal, generation manifests, staging validation and atomic pointer; `projection_rebuild.py`, `projection_log.py`, `projections.py`, and router adapt to generation targets |
| Writers/readers | `chapter_commit_service.py`, state/index/summary/memory/vector writers, `event_log_store.py`, `event_projection_router.py`, `context_provenance.py`, `context_manager.py`, query/recovery entrypoints consume typed snapshot/generation interfaces |
| Migration | New `project_migration.py` and CLI subcommands for preflight/report, backup verification, dry-run, migration and operational rollback |
| Governance and instructions | `docs/ownership-inventory.json`, `docs/ownership-inventory.schema.json` only if schema needs new fields, active ownership guard/tests, active write/query/resume/recovery instructions and package docs |
| Acceptance | Focused tests in active `scripts/data_modules/tests/`; adversarial integration/recovery tests; H1 result-free template and H2 evidence record created at their respective acceptance stages |

Exact helper names below are the cross-task contract; keep them stable or update all later tasks in the same reviewed change.

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

## Task 2: Define provider-issued, request-bound human decision evidence

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/correction_decision_provider.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/canon_correction_store.py`
- Modify: correction CLI/command discovered in Task 1
- Create: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_correction_decision_provider.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py`
- Test: adversarial integration tests under `.claude/plugins/zhanghui/scripts/data_modules/tests/`

**Interfaces:**
- Consumes: `CanonCorrectionRequest`, `CanonCorrectionAuthorization`, exact artifact hashes, and a configured host interaction capability.
- Produces: `CorrectionDecisionProvider.review(request, authorization) -> VerifiedCorrectionDecision`; provider evidence binds request ID/hash, authorization ID/hash, choice, provider/version, interaction ID, and declared identity/provenance strength.
- Provider failure: typed `CorrectionDecisionUnavailable`; never return a synthetic verified result.

- [ ] Write failing tests showing dicts, `actor_ref`, GateDecisionStore response JSON, CLI `--approve`, and agent-created files cannot satisfy `append_correction`.
- [ ] Add provider contract tests for APPROVE, REJECT, stale parent, wrong request digest, wrong authorization digest, reused interaction, and unavailable capability.
- [ ] Verify host documentation/source for the actual direct human interaction callback supported at implementation time. If none exists, implement an unavailable provider and keep activation disabled; do not substitute TTY, flag, or file-based evidence.
- [ ] Implement the narrow host adapter, exact full-content challenge, opaque provider evidence, and process-local verified result. Do not claim cryptographic identity unless the host actually supplies it.
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
- `EffectiveHistorySnapshot(ok, chapters, base_set_digest, correction_lineage_digest, effective_history_digest, snapshot_id, diagnostics)`.
- `EffectiveHistoryStore.read_snapshot(project_root, decision_provider) -> EffectiveHistorySnapshot`.
- `EffectiveProjectionInput(base_commit, effective_entry, snapshot_id, snapshot_digest)` is constructible only through the facade.
- `validate_effective_projection_input(root, value) -> EffectiveProjectionInput` revalidates the on-disk base and effective digests.

- [ ] Add failing tests for sparse commits, base-only digest stability, exact correction resolution, all namespaces including unreferenced/staged artifacts, sibling conflict, corrupt artifact, stale authorization, provider unavailable, and concurrent artifact digest change.
- [ ] Add tests proving a namespace with invalid staged artifacts cannot silently fall back to base-only history.
- [ ] Implement deterministic full-set discovery and digest computation; delegate operation/lineage semantics only to the existing resolver.
- [ ] Extend durable validation so the immutable disk base must match and effective output must independently match the resolver snapshot; arbitrary dicts fail.
- [ ] Verify rejected commits remain non-effective and correction bases remain accepted-only.
- [ ] Run focused tests plus Phase 8 schema/store/resolver tests; commit.

## Task 4: Introduce immutable projection generations and freshness manifests

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/projection_generation.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/projection_log.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/event_projection_router.py`
- Create: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_generation.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_log.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py`

**Interfaces:**
- `ProjectionGeneration.begin(snapshot, previous_generation) -> BuildHandle`.
- `BuildHandle.root` is the only writer destination; `record_writer(chapter, writer, result)` records snapshot-bound progress.
- `validate_generation(handle, expected_manifest) -> ValidatedGeneration` checks all seven domains and output digests.
- `publish_generation(validated, expected_previous_pointer, expected_lineage_digest) -> ActivationPointer` atomically publishes only after lock-time recheck.
- Reader: `pin_active_generation(project_root) -> PinnedGeneration`; returned handle does not reread the pointer mid-operation.

- [ ] Add failing crash-boundary tests for temporary manifest write, fsync failure, staging rename, lock contention, pointer rename, and concurrent correction append.
- [ ] Add tests proving one missing required writer, missing tombstone/absence row, or mismatched digest prevents validation.
- [ ] Implement unique staging directories, append-only build journal, canonical generation manifest and file hashing for events JSON, story-event/index SQLite, state, summaries, memory, vectors/BM25, and diagnostics.
- [ ] Implement fsync/atomic rename on the project filesystem, activation lock, previous-pointer comparison, and exact lineage digest recheck.
- [ ] Add generation identity fields to projection run logs; legacy commit hash-only logs cannot mark a correction generation healthy.
- [ ] Prove incomplete staging is invisible to readers and a reader pins exactly one pointer/generation.
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

## Task 6: Route runtime, context, query and recovery reads through a pinned snapshot

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/context_provenance.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/context_manager.py`
- Modify: query/RAG and runtime-source builders enumerated by Task 1
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/projections.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/doctor.py` and health/report code
- Modify: active `webnovel-query`, `webnovel-resume`, write/recovery skill docs as needed
- Add focused context/query/recovery tests under `.claude/plugins/zhanghui/scripts/data_modules/tests/`

**Interfaces:**
- Runtime entrypoint obtains `PinnedGeneration` once and passes it through context assembly, Canon facts, event retrieval, summaries, and RAG source attribution.
- `retry` may refresh operationally failed writers only when the current generation/snapshot identity matches; correction freshness mismatch routes to generation recovery, never raw commit replay.
- `replay(start, end)` is base-only incremental recovery or a staged candidate build; correction activation still builds all seven domains in a full generation.

- [ ] Add failing integration tests that put a correction in one namespace and prove no context/query/resume path returns base chapter N with corrected projections or the inverse.
- [ ] Inventory and test every Canon reader and direct `.webnovel`/commit read; route to the pinned generation or return an explicit unsupported/blocked result.
- [ ] Make base-only path preserve current behavior where no activation marker/correction namespace exists.
- [ ] On invalid active pointer/generation or staged conflict, block Canon runtime reads and explain recovery; never silently fallback.
- [ ] Update Doctor and recovery reports to show base digest, effective revision/tip, generation identity, and complete-set health.
- [ ] Update active skills to distinguish correction proposal/review from ordinary GateDecision workflow and prohibit agent-issued semantic approval.
- [ ] Run context/query/recovery and existing projection regression tests; commit.

## Task 7: Implement read-only migration preflight, deterministic dry run and verified backup

**Files:**
- Create: `.claude/plugins/zhanghui/scripts/data_modules/project_migration.py`
- Modify: `.claude/plugins/zhanghui/scripts/webnovel.py` or the active CLI dispatcher discovered in Task 1
- Create: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_project_migration.py`
- Modify: migration/schema compatibility tests in active `scripts/data_modules/tests/`

**Interfaces:**
- `preflight_project(root) -> PreflightReport` is read-only and returns stable category, evidence hashes, conflicts and report digest.
- `dry_run_migration(root, report_digest) -> MigrationPlan` is read-only and lists exact generated outputs/retained sources/conflicts.
- `create_verified_backup(root, plan) -> BackupManifest` validates copied files, hashes, SQLite integrity and temporary restore.
- No migration write interface is exposed until report and backup are valid.

- [ ] Add failing read-only tests: hash whole project before/after preflight and dry run; include corrupt commits, correction conflicts, stale mirrors, mixed Craft data, unknown schema and valid clean base-only project.
- [ ] Add backup tests for every owned source class, SQLite/vector sidecars, hash mismatch, disk failure, and restore verification failure.
- [ ] Implement deterministic project classification and preserve unknown/unowned data as conflicts.
- [ ] Implement backup manifest and verified temporary restore; fail before any write on incomplete backup.
- [ ] Implement exact dry-run report with required human decisions, retained data, outputs and rollback target.
- [ ] Run migration preflight/dry-run/backup tests and ensure no input mutation; commit.

## Task 8: Execute opt-in migration and operational rollback through the generation pointer

**Files:**
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/project_migration.py`
- Modify: active CLI dispatcher and migration command docs
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/projection_generation.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_project_migration.py`
- Add migration end-to-end tests in `.claude/plugins/zhanghui/scripts/data_modules/tests/`

**Interfaces:**
- `migrate_project(root, expected_report_digest, reviewed_plan_digest, backup_manifest) -> MigrationResult` rechecks source hashes and publishes only a validated complete generation.
- `rollback_projection(root, generation_id) -> ActivationPointer` only points to a validated immutable generation.
- Filesystem restore requires backup manifest plus explicit post-backup conflict report; it never removes newer corrections.

- [ ] Add failing tests for source hash changes after preflight, human unresolved conflict, unavailable provider, failed generation writer, and stale build digest.
- [ ] Implement revalidation, verified-backup prerequisite, staged full-history generation, final source/lineage recheck, and pointer-only publish.
- [ ] Add legacy/partial/mixed test fixtures proving no silent delete, overwrite, sibling choice or Craft promotion.
- [ ] Add crash tests before/after pointer rename and recovery to prior verified generation.
- [ ] Add filesystem rollback conflict tests proving a newer human file/correction is preserved and restore blocks for explicit review.
- [ ] Run full migration/recovery focused suites; commit.

## Task 9: Integrate production correction activation last

**Files:**
- Modify: correction command/CLI and `canon_correction_store.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/effective_history.py`
- Modify: `.claude/plugins/zhanghui/scripts/data_modules/projection_generation.py`
- Modify: active ownership inventory/docs and correction review/recovery skills
- Add: `.claude/plugins/zhanghui/scripts/data_modules/tests/test_correction_activation.py`

**Interfaces:**
- `activate_correction(project_root, correction_id, provider) -> ActivationResult` re-resolves the entire snapshot, builds/validates a full generation, rechecks the candidate lineage under lock, and publishes one pointer.
- A staged append never changes the active pointer; an activation failure leaves it byte-identical.

- [ ] Add failing end-to-end tests that observe the active pointer, runtime snapshot and every projection domain before/after valid approval and every failure class.
- [ ] Prove no consumer can observe correction live before a complete pointer publication and every post-publication consumer reports the identical effective revision/tip/generation.
- [ ] Implement activation by composing Tasks 2–8; do not introduce per-consumer feature flags or duplicate resolver logic.
- [ ] Add process-crash and correction-added-during-build tests; prove pointer and correction artifacts obey the specified invariants.
- [ ] Update ownership inventory, drift guard evidence and operator recovery documentation.
- [ ] Run Phase 8 regressions, architecture/projection suite, activation adversarial suite and acceptance-template checks.
- [ ] Inspect the exact production diff and confirm `.claude/plugins/zhanghui/6.4.0/**` is unchanged; commit implementation candidate H1 with a result-free acceptance template.

## Task 10: Run exact-H1 acceptance, independent review, and record-only H2

**Files:**
- Create in H1: `docs/superpowers/acceptance/phase-9-h1-acceptance-template.md` (result-free)
- Create in H2 only: `docs/superpowers/acceptance/phase-9-h2-evidence.md`
- No production implementation changes in H2.

**Interfaces:**
- H1 template names exact H1 SHA, acceptance commands, environments, required outputs, migration fixtures, and evidence locations without claiming results.
- H2 records only H1 verification/review result, immutable artifact hashes, and reviewer disposition.

- [ ] Freeze exact H1 SHA and verify H1 contains implementation plus result-free template only.
- [ ] Run the complete acceptance matrix against H1, including independent-project e2e attacks and recovery/migration scenarios; save raw outputs and artifact hashes.
- [ ] Obtain independent review of H1 and its evidence; record requested changes as a new implementation commit/H1 before acceptance if needed.
- [ ] Create H2 containing only final evidence and review records referring to exact H1; prove H2 is not included in the tested H1 and contains no production changes.
- [ ] Verify final mainline integration requirements separately; no PR or merge mechanics are implied by this design plan.

## Plan self-review

- Trusted-human authority precedes effective history, writers and runtime. If it cannot be supplied, the typed provider stays unavailable and Task 9's activation tests must prove fail-closed behavior.
- Generation staging/provenance lands before any consumer can use corrections; runtime reader routing lands before the activation orchestrator. Activation is the last production switch.
- The plan tests correction-at-N effects on suffix state, memory, vectors and cross-chapter intent; first release does full history because there is no proven checkpoint.
- Migration is separated into read-only classification/backup and later opt-in execution; every write follows a verified backup and generation validation.
- Phase 8 artifacts stay immutable, Phase 10 and CHANGES stay out of scope, and `6.4.0/**` remains outside the active source set.
- H1/H2 acceptance explicitly prevents self-reference and separates tested implementation from evidence recording.
