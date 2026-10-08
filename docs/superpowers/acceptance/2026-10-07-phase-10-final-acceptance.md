# Phase 10 Final Acceptance Evidence

## Verdict

- Implementation verification: **COMPLETE**
- Local acceptance candidate: **READY_FOR_INDEPENDENT_REVIEW**
- Independent reviewer verdict: **PENDING**
- Final status: **PHASE_10_TASK_9_ACCEPTANCE_READY_FOR_REVIEW**

This record documents the Phase 10 implementation and Task 9 checks. It does not claim independent acceptance.

## Implementation lineage and freeze

- Design R0: `b18ba71239f09bb1c9c7748aa1b3ce30598ef453`.
- Design R1 / frozen: `75ab6615ede8a6c2a011988297bf2304a28f2846`.
- Task 9 tested implementation HEAD: `7df95b819b359bb04f2e9f841ae309955b706a31`.
- Previous implementation tip: `bc48a33964af41c8b38a6118b030421c962cd051`.

Complete Phase 10 lineage from `6f04925a321a01f72c6d00b127d6ab2d2e8ce7aa`:

| Commit | Responsibility |
|---|---|
| `b18ba71239f09bb1c9c7748aa1b3ce30598ef453` | Add Phase 10 Intent/Craft design R0. |
| `75ab6615ede8a6c2a011988297bf2304a28f2846` | Freeze reviewed R1 design decisions. |
| `c0b88e09a6dd2e9da76a30e71519593fe2bdeb55` | Add field ownership inventory and governance checks. |
| `b9f45934c99c65aa55899170726e53c2add35750` | Preserve planner Promise Ledger ownership and schema handling. |
| `8de0eced7219a95b7384dbb33ce4899fcda93829` | Derive obligation lifecycle from effective accepted Canon history. |
| `b609f1f57180bf0981a78de5b7022dc71e67b529` | Classify Story Craft fields by owner and authority. |
| `902207c5e646a13e5d3c029a2bcaad8223eeffbe` | Close Slice A review blockers and add migration/effective-history coverage. |
| `48ab254d9d51cf150f2ca78297bd5ab2ecd90f67` | Align Story Craft migration to frozen R1 mapping. |
| `506bc5659c4bfe487dcb214eb820892a80117b85` | Validate StoryEvent occurrence evidence. |
| `8dfff1217cb85f15653a1167d56d0ea47ca679c0` | Bind StoryEvent chapter to the effective containing chapter; Slice A accepted tip. |
| `3373a2e82adab2f3d87829ff7bed85edab8f6982` | Route enrolled owner mutations to the overlay. |
| `2fa4a508f3119954248f3d18c0210c9c504ff6da` | Compose provenance-aware Context. |
| `17f118f190bf9763ad143800c73ca526835d26a5` | Keep Craft findings advisory in runtime gates and skill guidance. |
| `7d9c8584db28f2506d0c2fc9d1f0f174f04dd70b` | Report owner migration compatibility. |
| `a65cc1d0244c81dabc87a57bf5ef56290847f205` | Close Slice B ownership and Context parity review points. |
| `bc48a33964af41c8b38a6118b030421c962cd051` | Bind owner writes to the original read revision (CAS). |
| `7df95b819b359bb04f2e9f841ae309955b706a31` | Keep base initializer runtime-light; close Python 3.9 regression. |

Slice A accepted tip is `8dfff1217cb85f15653a1167d56d0ea47ca679c0`; Slice B accepted tip before Task 9 is `bc48a33964af41c8b38a6118b030421c962cd051`. The CAS and initializer compatibility commits are part of the final implementation lineage.

## Initializer compatibility regression closure

The Slice B enrollment guard initially imported `ProjectionGeneration` from the base initializer. Its dependency chain failed under the supported system Python 3.9.6 and made the existing writer-profile initialization tests fail.

The fix checks only the authoritative marker path:

```text
.story-system/effective-history/enrollment.json
```

Final behavior is existence-based and fail-closed:

- Marker absent: base-only initialization proceeds.
- Marker present: base-only reinitialization is refused.
- Empty or malformed marker: reinitialization is still refused; this initializer does not repair activation state.
- No activation runtime, migration, or correction module is imported for this check.

Evidence: at `6f04925`, `writer_profile_init` was **3 passed**; at `bc48a339` it was **3 failed**; at `7df95b8`, using `/usr/bin/python3` **3.9.6** for the subprocess, it is **3 passed**. The new parameterized marker test covers both an empty file and malformed JSON; the static assertion prevents reintroducing the activation runtime import. The base-only initializer tests also pass.

## Commands and results

Commands were run from the repository root with `PYTHONPATH=.claude/plugins/zhanghui/scripts` where shown.

### Python 3.9 initializer regression

```bash
PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/tests/test_writer_profile_init.py -q --tb=short
```

Result: **3 passed**. Its subprocess uses `python3`, resolved in this environment to `/usr/bin/python3` 3.9.6.

### Initialization behavior

```bash
PYTHONPATH=.claude/plugins/zhanghui/scripts pytest \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_init_project_pruning.py \
  .claude/plugins/zhanghui/scripts/tests/test_writer_profile_init.py \
  .claude/plugins/zhanghui/scripts/tests/integration/test_init_multi_volume.py \
  .claude/plugins/zhanghui/scripts/tests/integration/test_e2e_multi_volume_init.py \
  .claude/plugins/zhanghui/scripts/tests/integration/test_plan_all_volumes.py \
  -q --tb=short
```

Result: **31 passed**. This includes base-only initialization, empty/malformed enrollment-marker refusal, no activation-runtime import, and Python 3.9 writer-profile initialization.

### Phase 10 focused acceptance collection

```bash
PYTHONPATH=.claude/plugins/zhanghui/scripts pytest \
  .claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py \
  .claude/plugins/zhanghui/scripts/tests/unit/test_promise_ledger.py \
  .claude/plugins/zhanghui/scripts/tests/unit/test_volume_state.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_intent_reconciliation.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_effective_history.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_generation.py \
  .claude/plugins/zhanghui/scripts/tests/test_story_craft_extended.py \
  .claude/plugins/zhanghui/scripts/tests/test_story_craft.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_owned_project_view.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_state_manager_extra.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_contract_adapter.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_correction_activation.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_write_gates.py \
  .claude/plugins/zhanghui/scripts/tests/integration/test_review_with_craft.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_prompt_integrity.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_project_migration.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_ownership_writer_bypass.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_memory_contract.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_init_project_pruning.py \
  .claude/plugins/zhanghui/scripts/tests/test_writer_profile_init.py \
  .claude/plugins/zhanghui/scripts/tests/integration/test_e2e_macro_micro.py \
  -q --tb=short --junitxml=/tmp/zhanghui-phase10-focused-final.xml
```

Result: **687 passed / 3 failed**. The three failures are the exact ownership inventory coverage nodes listed below; all other Phase 10 owner, migration, Context, correction, Story Craft, gate, and initializer checks passed.

### Architecture suite

```bash
PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/tests/architecture -q --tb=short
```

Result: **77 passed / 5 failed**. All five exact nodes also failed at `6f04925`; the coverage scanner produced the same missing-coordinate set on both revisions.

### Full plugin suite

```bash
PYTHONPATH=.claude/plugins/zhanghui/scripts pytest \
  .claude/plugins/zhanghui/scripts/data_modules/tests \
  .claude/plugins/zhanghui/scripts/tests \
  -q --tb=no --junitxml=/tmp/zhanghui-phase10-final.xml
```

Result: **2018 passed / 60 failed / 3 skipped** (2081 collected). The 60 failed node IDs are exactly the same 60 failure nodes as baseline `6f04925`. There are no current-only failures.

### Static checks

```bash
python3 -m compileall -q \
  .claude/plugins/zhanghui/scripts/init_project.py \
  .claude/plugins/zhanghui/scripts/data_modules/tests/test_init_project_pruning.py \
  .claude/plugins/zhanghui/scripts/tests/integration/test_e2e_macro_micro.py
git diff --check
```

Both commands passed.

## Focused failure classification

These three exact nodes fail on the final implementation HEAD:

| Test node | Assertion and uncovered coordinates | Baseline and Phase 10 relevance | Frozen invariant |
|---|---|---|---|
| `test_ownership_inventory.py::test_inventory_records_resolve_and_cover_required_reader_families` | `writer_coverage(...) == []` fails for `index_manager.py::_ReadOnlyConnection.execute` and `_ReadOnlyCursor.execute`, domain `COMPATIBILITY`. Reader coverage also reports the coordinates below. | Test existed and failed at `6f04925`. The baseline scanner returns the same coordinates. `index_manager.py` and the scanner are unchanged from baseline. | No Phase 10 owner/writer path is involved; no new Phase 10 authority is uncovered. Historical inventory coverage debt. |
| `test_ownership_inventory.py::test_phase9_confirmation_reuses_existing_correction_decision_owner` | Same `reader_coverage(...) == []` assertion includes the two `index_manager.py` coordinates plus `project_migration.py::_report_body` (`CANON_COMMIT`/`glob`, `COMPATIBILITY`/`read_bytes`, `STATE_JSON`/`read_bytes`). | Test existed and failed at `6f04925`. A detached baseline checkout run of the exact scanner returned the identical five-coordinate set. The migration report reads/hashes and commit glob were already present at baseline. | No Phase 10 reader coverage regression; no frozen invariant violation. |
| `test_ownership_inventory.py::test_dynamic_protected_exception_requires_owner_link_and_classification` | The test's final `writer_coverage(...) == []` assertion reports the same two `index_manager.py` compatibility execute edges. | Test existed and failed at `6f04925`; identical scanner results. | No Phase 10 writer path involved; no frozen invariant violation. |

The inventory failures are not waived based only on a general claim of historical debt: the baseline test run and direct baseline scanner execution both returned the same exact failures and coordinate set.

## Full-suite and baseline audit

Baseline was run in a detached temporary worktree at `6f04925a321a01f72c6d00b127d6ab2d2e8ce7aa` with the same full-suite command:

```text
Baseline: 1911 passed / 62 failed / 3 skipped / 8 errors (1984 tests)
Final:    2018 passed / 60 failed / 3 skipped / 0 errors (2081 tests)
```

The 60 final failures are all common with baseline. The ten baseline-only nodes are `test_precommit_manifest_guard.py::test_hook_in_worktree_blocks_manifest_broken_in_that_worktree`, `::test_hook_in_worktree_allows_commit_when_only_main_workspace_is_dirty`, `::test_hook_blocks_manifest_broken_only_in_the_index`, `::test_hook_allows_manifest_broken_only_in_the_worktree`, `::test_hook_skips_validation_when_only_skill_content_changed`, `::test_hook_validates_when_declared_command_dir_becomes_empty`, `::test_hook_skips_validation_for_non_plugin_files`, `::test_hook_does_not_advertise_no_verify_bypass`, `::test_hook_source_does_not_mention_no_verify`, and `::test_tracked_hook_source_exists_and_stays_in_sync_with_installed`. All ten fail because the detached worktree exposes `.git` as a file, while these tests try to access `.git/hooks/pre-commit` as a directory (`NotADirectoryError`); eight are setup errors and two are failures during hook-path access. All ten pass in the primary checkout. The temporary baseline worktree was removed after comparison.

### Exact current failure groups (60)

All 44 `data_modules` failures are baseline failures:

- `test_api_client.py` (13): `test_embedding_client_success_and_retry`, `test_embedding_client_timeout_and_error`, `test_embedding_batch`, `test_rerank_client_success`, `test_rerank_retry_and_empty`, `test_modal_client_warmup_and_passthrough`, `test_embedding_empty_and_error_paths`, `test_embedding_exception_and_close`, `test_rerank_non_retry_error`, `test_embedding_session_parse_and_retry_paths`, `test_embedding_exception_retry_and_batch`, `test_rerank_modal_retry_and_warmup`, `test_modal_client_helpers`. All fail because this environment has no async pytest plugin (`async def functions are not natively supported`).
- `test_config.py` (2): `test_config_paths_and_defaults`, `test_get_config_and_set_project_root`. The assertions compare macOS `/var/...` paths with their `/private/var/...` resolved paths; same baseline failures.
- `test_extract_chapter_context.py` (2): `test_build_chapter_context_payload_includes_contract_sections`, `test_build_chapter_context_payload_exposes_latest_rejected_commit`. Legacy fixtures fail durable-commit schema validation (`review_result` is not a JSON object); same baseline failures.
- `test_projection_log.py` (1): `test_chapter_commit_service_writes_projection_log`. Fixture expected `rejected`, actual result is `accepted`; same baseline failure.
- `test_projection_schema_compat.py` (11): `test_state_writer_accepts_field_path_alias`, `test_state_writer_accepts_flat_field_legacy`, `test_state_writer_handles_array_value_in_field_path`, `test_state_writer_mirrors_protagonist_state_when_entity_is_protagonist`, `test_state_writer_recognizes_protagonist_via_tier_zhujue`, `test_state_writer_recognizes_protagonist_via_canonical_name_match`, `test_memory_writer_preserves_entity_type_for_organization`, `test_memory_writer_accepts_field_path_in_state_delta`, `test_memory_writer_extracts_open_loop_from_description_when_no_content`, `test_memory_writer_extracts_world_rule_from_rule_content`, `test_integration_real_deepseek_commit_projects_full_state`. Legacy unversioned commit fixtures fail the durable validator (`unsupported schema version None`); this is existing fixture/contract debt, not a Phase 10 change.
- `test_rag_adapter.py` (11): `test_store_and_search`, `test_store_chunks_with_embedding_failure`, `test_hybrid_search_full_scan`, `test_hybrid_search_prefilter`, `test_search_respects_chapter_filter_across_strategies`, `test_graph_hybrid_search_with_entity_expansion`, `test_search_auto_uses_graph_strategy_when_enabled`, `test_graph_hybrid_search_fallback_when_graph_disabled`, `test_graph_hybrid_search_rerank_failure_uses_candidates`, `test_search_unknown_strategy_falls_back_to_hybrid`, `test_search_with_backtrack`. All fail because this environment has no async pytest plugin.
- `test_vector_projection_writer.py` (3): `test_rejected_commit_returns_not_applied`, `test_store_zero_for_required_chunks_is_error`, `test_run_store_coro_works_inside_active_event_loop`. Two use unversioned invalid commit fixtures; the async test lacks an async pytest plugin. Same baseline failures.
- `test_webnovel_unified_cli.py` (1): `test_projections_retry_cli_runs`. Its legacy unversioned commit fixture is rejected as `unsupported schema version None`; same baseline failure.

The remaining 16 failures are baseline failures in plugin-level tests:

- `tests/architecture/test_ownership_inventory.py` (3): the exact nodes and baseline coordinate comparison are documented above.
- `tests/architecture/test_phase7_acceptance_template.py::test_h1_acceptance_template_is_complete_and_result_free`: stale assertion requires the literal phrase `exact commands`; baseline failure.
- `tests/architecture/test_phase8_acceptance_template.py::test_h1_does_not_include_the_result_filled_h2_record`: stale assertion expects the existing Phase 8 H2 acceptance record not to exist; baseline failure.
- `tests/test_atomic_write_crash_safety.py::test_summary_projection_survives_kill`: child process fails before the crash-safety assertion because the fixture has no durable chapter commit; summary writer is unchanged by Phase 10; same baseline failure.
- `tests/test_check_plan_artifacts.py`: `test_no_md_returns_empty_list`, `test_partial_md_lists_existing`, `test_output_includes_last_modified`.
- `tests/test_check_volume_md.py::test_check_volume_warns_missing_md`.
- `tests/test_snapshot_manager_conflict.py`: `test_default_refuses_rmtree`, `test_skip_keeps_existing_snapshot`, `test_overwrite_replaces_snapshot`.
- `tests/test_update_master_outline_conflict.py`: `test_default_runs_raises_file_exists_error`, `test_skip_does_not_modify`, `test_overwrite_modifies`.

The nine check-plan/check-volume/snapshot/outline failures use an unavailable hard-coded plugin path `/Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui`; the active checkout is `/Users/chang/Desktop/Code/zhanghui`. They are identical baseline failures.

### Stale E2E expectation aligned to frozen R1

The pre-existing `tests/integration/test_e2e_macro_micro.py::test_e2e_full_flow` expected an overdue planned foreshadow to be `BLOCKER`. Frozen R1 §10, §11, §12 and §16 classify missed planner deadlines and ordinary planner misses as plan deviation/advisory; `chunked_write.evaluate_pre_write_gates()` now emits `ADVISORY`, and the active write skill says advisory does not block. The E2E test is an active integration contract, so its assertion and comment were updated to expect `ADVISORY`. The targeted E2E test now passes. This updates a stale expectation; it does not weaken a gate or change production behavior.

## Architecture suite failure classification (5)

1. `test_ownership_inventory.py::test_inventory_records_resolve_and_cover_required_reader_families` — baseline coverage gaps; no new candidate coordinates.
2. `test_ownership_inventory.py::test_phase9_confirmation_reuses_existing_correction_decision_owner` — same baseline reader coverage set; baseline scanner is byte-for-byte equivalent in its findings.
3. `test_ownership_inventory.py::test_dynamic_protected_exception_requires_owner_link_and_classification` — same baseline `index_manager.py` writer coverage gap.
4. `test_phase7_acceptance_template.py::test_h1_acceptance_template_is_complete_and_result_free` — Phase 7 document assertion mismatch, failed at baseline.
5. `test_phase8_acceptance_template.py::test_h1_does_not_include_the_result_filled_h2_record` — Phase 8 template assertion conflicts with the existing H2 record, failed at baseline.

None is a Phase 10 regression. No scanner suppression, xfail, broad exception, or inventory weakening was applied.

## Acceptance smoke evidence by invariant

The focused collection above includes these isolated-fixture checks; all passed except for the three unrelated, baseline-identical inventory nodes:

- **Base-only and migration:** `test_clean_base_only_preflight_and_dry_run_are_read_only_and_deterministic`, `test_dry_run_rejects_stale_preflight_report`, `test_unknown_state_owner_and_mixed_memory_evidence_are_explicit_conflicts`, `test_verified_backup_copies_sqlite_and_all_sidecars_and_restores_hashes`, `test_explicit_migration_requires_verified_backup_and_publishes_complete_generation`, `test_migration_moves_known_owner_state_to_overlay_without_rewriting_legacy_state`, `test_migration_detects_post_backup_file_edits_before_enrollment`, and `test_promise_unknown_field_blocks_preflight_and_migration_without_rewriting_source`.
- **Enrolled owner overlay/CAS:** `test_late_owner_write_is_visible_without_changing_pinned_canon`, `test_owned_index_routes_canon_reads_and_blocks_canon_writes`, `test_owner_overlay_expected_revision_conflict_fails_closed`, `test_state_manager_stale_owner_revision_fails_closed_for_same_or_disjoint_edits`, `test_state_manager_sequential_owner_writes_refresh_read_snapshot`, `test_state_manager_rejects_publication_change_since_load`, and `test_story_craft_cli_stale_publication_fails_without_writing_new_publication`.
- **Context provenance:** `test_governed_context_splits_intent_craft_and_rag_reference`, `test_context_uses_reconciled_open_loop_and_reader_promise_lifecycle`, `test_stale_runtime_copy_is_diagnostic_not_authoritative_intent_conflict`, `test_conflicting_authoritative_intents_are_exposed_without_failing_canon`, `test_exact_identity_and_scope_diagnose_stale_root_contract_copy`, and `test_context_occurrence_is_reference_only_when_exact_event_is_accepted` plus invalid/retracted-event cases in `test_context_provenance.py`.
- **Correction replay and planner isolation:** `test_context_obligations_follow_effective_correction_replay_without_merging_planner_rows` creates and resolves obligations, retracts the resolution to reactivate them, retracts the source to remove them, and verifies the planner-owned Promise Ledger row remains separate.
- **Story Craft occurrence authority:** `test_exact_accepted_occurrence_ref_trusts_sibling_buried_chapter_claim`, invalid/wrong-chapter/duplicate occurrence tests in `test_project_migration.py`, and trusted/retracted event tests in `test_context_provenance.py`. Trusted occurrence remains `DERIVED_REFERENCE`.
- **Gates:** `test_craft_findings_have_stable_structured_identity_and_never_block`, `test_craft_display_veto_words_never_change_policy_classification`, overdue timed-lock review cases, and integrity/workflow blocking cases in `test_write_gates.py` and `test_review_with_craft.py`.

Rollback evidence covers mutable layout and owner persistence only. It does not roll back or delete Canon commits, correction records, authorization, publication history, or generation history.

## Frozen invariant summary

- **Canon:** Accepted-commit containment alone does not grant field-level authority. Validated factual evidence establishes past facts. Commit-carried Craft stays Craft; plan snapshots stay Intent/history-of-plan; unsupported occurrence flags never become Canon.
- **Canon-derived obligations:** Open Loop and Reader Promise lifecycles derive from effective accepted Canon history. Reconciliation is deterministic; one creation identity yields one lifecycle row; close/payoff is resolution evidence, not a second obligation. Planner Promise Ledger bytes and lifecycle remain independently planner-owned.
- **Planner Intent:** Explicit Canon cross-reference does not transfer planner authority. Generated runtime briefs/contracts are derived copies unless bound to exact authored authority. Stale copies emit `stale_runtime_copy`; `intent_conflict` requires exact identity, scope, and independent authored sources.
- **Story Craft:** Classification is field-level. Trusted occurrence chain is effective accepted chapter → schema-valid StoryEvent → event chapter matches containing chapter → unique event ID → explicit occurrence reference → exact occurrence chapter. Trusted occurrence is Derived Reference, never Canon; unknown nested fields fail closed.
- **Owner writes:** Enrolled writes use pinned owner snapshot, mutation, original revision/publication CAS, overlay write, and read-after-write. Tests cover stale revision, publication change, same-field and disjoint-field concurrent edits, sequential writes, overlay-only persistence, and restart visibility. Base-only compatibility is preserved.
- **Context:** CANON / INTENT / CRAFT / REFERENCE remain explicit and read-only. Canon-derived lifecycle uses shared reconciliation/projection; planner Intent remains separate; Craft disagreement cannot overwrite Intent; no recency, file-order, or fuzzy winner selection.
- **Gates:** Craft-only findings remain advisory; missed timed-lock deadlines are plan deviation; rhythm/hook/Scene-Sequel/beat heuristics do not block; an explicit stable user constraint can remain hard; Canon, integrity, and workflow blockers remain separately typed. Active skill prose matches runtime behavior.
- **Migration:** Exact field mapping, unknown-data preservation and promotion blocking, known Promise Ledger schema, nested Story Craft fail-closed behavior, chapter_meta report/apply parity, CRAFT/INTENT-only chapter_meta overlay, verified backup, source-hash and stale-plan fail-closed checks, one-time enrollment, and single migration/store mechanism are covered by the migration suite.

## Known historical validation debt

`durable_projection.validate_chapter_commit_payload()` does not uniformly re-run `StoryEvent.model_validate()` over every historical `accepted_events` row. Task 9 did not change this debt. The Phase 10 trusted occurrence resolver independently validates StoryEvent schema, containing chapter validity, unique event ID, explicit `occurrence_ref`, and exact chapter match before it grants Derived Reference status. The historical gap does not cross that occurrence authority boundary.

## `/根源牌序` compatibility and external state

The existing decision remains OPTION B: chapters 1/2 are legacy/reference only, are not Canon, and are not automatically imported; `_rerun_at = UNKNOWN / PRESERVED / NOT IMPORTED`. No destructive smoke or Phase 10 import was performed. A read-only status check showed the separate `/Users/chang/Desktop/根源牌序` worktree contains user data changes; this task did not modify those files.

Issue #1 was not modified; its current state was read as OPEN. No PR was created. The existing stash was not changed. The Task 9 temporary baseline worktree was removed. No Phase 10 change is present under `.claude/plugins/zhanghui/6.4.0/**`.

## Changed-path audit

Compared `6f04925a321a01f72c6d00b127d6ab2d2e8ce7aa` → `7df95b819b359bb04f2e9f841ae309955b706a31`, plus the Task 9 E2E assertion update and this acceptance record. The only extra Task 9 test change aligns the old overdue-foreshadow assertion to frozen R1.

- **Production implementation:** `.claude/plugins/zhanghui/scripts/data_modules/chunked_write.py`, `context_provenance.py`, `intent_reconciliation.py`, `memory/writer.py`, `memory_projection_writer.py`, `owned_project_view.py`, `project_migration.py`, `promise_ledger.py`, `state_manager.py`, `story_craft_evidence.py`, `webnovel.py`, `scripts/init_project.py`, `scripts/review_pipeline.py`, `scripts/story_craft.py`.
- **Tests:** All paths below are relative to `.claude/plugins/zhanghui/`: `scripts/data_modules/tests/test_context_provenance.py`, `test_correction_activation.py`, `test_effective_history.py`, `test_init_project_pruning.py`, `test_intent_reconciliation.py`, `test_owned_project_view.py`, `test_project_migration.py`, `test_projection_writers.py`; `scripts/tests/architecture/ownership_inventory_guard.py`, `test_ownership_inventory.py`; `scripts/tests/integration/test_review_with_craft.py`, `test_e2e_macro_micro.py`, `scripts/tests/test_story_craft_extended.py`; `scripts/tests/unit/test_chunked_write.py`, `test_promise_ledger.py`.
- **Active agent/skill guidance:** `.claude/plugins/zhanghui/agents/context-agent.md`, `.claude/plugins/zhanghui/skills/webnovel-plan/SKILL.md`, `.claude/plugins/zhanghui/skills/webnovel-write/SKILL.md`.
- **Governance inventory/schema:** `.claude/plugins/zhanghui/docs/ownership-inventory.json`, `.claude/plugins/zhanghui/docs/ownership-inventory.schema.json`.
- **Design and plan:** `docs/superpowers/specs/2026-10-07-phase-10-intent-craft-ownership-design.md`, `docs/superpowers/plans/2026-10-07-phase-10-intent-craft-ownership.md`.
- **Acceptance evidence:** `docs/superpowers/acceptance/2026-10-07-phase-10-final-acceptance.md`.

No binary, cache, temporary report, backup, `node_modules`, or generated artifact is in the Git change set. `.claude/plugins/zhanghui/6.4.0/**` is unchanged.
