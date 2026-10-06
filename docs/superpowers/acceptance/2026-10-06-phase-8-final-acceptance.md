---
record_type: phase-8-h2-acceptance-record
status: ready-for-review
tested_implementation_head: fe5505a4f71b2be52f662168843f6668908475e2
tested_implementation_tree: b6ea2c084a0a26b94763c77ff208482089c02067
tested_implementation_parent: 8673e09fcd4481f04fe4752ce480bf344f06f003
implementation_branch: codex/phase-8-canon-correction-contract
independent_review: PASS
implementation_blockers: None
---

# Phase 8 Final Acceptance Record (H2)

This record binds acceptance evidence to the independently reviewed H1 implementation. It records results obtained on H1 and does not change or redefine the Phase 8 contract. H2 itself is not the tested implementation.

## Tested implementation identity

- `tested_implementation_head`: `fe5505a4f71b2be52f662168843f6668908475e2`
- H1 tree: `b6ea2c084a0a26b94763c77ff208482089c02067`
- H1 parent: `8673e09fcd4481f04fe4752ce480bf344f06f003`
- Implementation branch: `codex/phase-8-canon-correction-contract`
- Independent review: **PASS**
- Remaining implementation blockers: **None**

## Binding acceptance

Exact command executed on H1:

```text
PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_schema.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_preview.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_schema.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_runtime_contract_builder.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_runtime_sources.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_runtime_health.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py .claude/plugins/zhanghui/scripts/tests/architecture/test_phase8_acceptance_template.py .claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py .claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_documentation.py -q
```

Result: **304 passed / 0 failed / 0 skipped** (304 collected).

Exact acceptance node IDs:

- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_schema.py::test_request_schema_requires_version_fields_and_path_safe_id`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_schema.py::test_operation_specific_shapes_and_authorization_references_are_strict`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_schema.py::test_canonical_artifact_digests_and_effective_digest_are_stable`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_schema.py::test_each_versioned_artifact_digest_is_sha256_of_its_canonical_body`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_schema.py::test_base_identity_uses_validated_commit_and_excludes_projection_status`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_schema.py::test_published_json_schema_enforces_artifact_shapes_and_tracks_pydantic`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_request_is_immutable_retryable_and_conflicts_on_id_reuse`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_authorization_is_one_request_one_decision_and_never_writes_correction`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_rejects_cross_request_binding_and_path_unsafe_ids`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_concurrent_distinct_authorizations_store_one_decision`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_append_authorized_correction_requires_typed_verification`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_proposal_and_runtime_producers_do_not_import_final_correction_writer`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_concurrent_final_appends_have_one_success_and_one_stale_parent`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_public_store_apis_persist_two_amends_and_retry_old_request_after_tip_advances`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_public_store_apis_allow_retract_then_supersede_and_reject_stale_request`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_final_append_rejects_invalid_amend_semantics_before_correction_write[unchanged]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_final_append_rejects_invalid_amend_semantics_before_correction_write[bad_changed_path_digest]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_final_append_rejects_invalid_amend_semantics_before_correction_write[replaces_all_fields]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_final_append_rejects_illegal_transition_before_correction_write`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_valid_amend_is_semantically_validated_before_write_and_resolves_same_tip`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py::test_final_append_refuses_preexisting_authorization_conflict_without_correction_write`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_lineage_base_only_is_clean_without_verification`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_lineage_requires_exact_typed_human_verification`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_lineage_sibling_is_conflict_independent_of_input_order_and_preserves_files`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_lineage_reports_authorization_conflict_without_selecting_a_winner`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_lineage_artifact_permutations_produce_identical_order_and_diagnostics`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_lineage_rejects_rejected_base_missing_parent_and_cycles`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_backward_compatible_base_and_unverified_correction_have_exact_result_shape`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_retract_and_supersede_resolve_in_chain_order`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_amend_requires_exact_exhaustive_changed_path_digests_and_preserves_schema_field`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_same_id_different_bodies_are_permutation_independent_and_select_no_winner[request]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_same_id_different_bodies_are_permutation_independent_and_select_no_winner[authorization]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_same_id_different_bodies_are_permutation_independent_and_select_no_winner[correction]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_resolver_rejects_unreferenced_cross_chapter_request_and_orphan_authorization`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py::test_resolver_rejects_unreferenced_artifact_with_foreign_revision_namespace`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_preview.py::test_preview_is_read_only_and_runtime_sources_do_not_change`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_preview.py::test_zero_correction_preview_returns_clean_base_without_writes`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_preview.py::test_preview_preserves_preexisting_sibling_corrections_and_never_selects_a_winner`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_preview.py::test_normal_runtime_has_no_import_path_to_correction_modules`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_schema.py::test_artifact_models_preserve_valid_top_level_payloads`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_schema.py::test_artifact_models_reject_nested_wrappers_and_missing_core_fields`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_schema.py::test_accepted_event_model_normalizes_aliases_before_story_event_validation`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_schema.py::test_accepted_event_model_rejects_malformed_event_collections`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_schema.py::test_accepted_event_model_rejects_blank_subject_and_unknown_type`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_planner_missed_node_does_not_veto_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_commit_service_accepts_when_all_checks_pass`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_commit_service_rejects_missing_original_reconciliation_inputs_even_with_no_artifact`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_commit_service_rejects_conflicted_reconciliation`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_service_recomputes_and_rejects_forged_passed_artifact`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_require_human_persists_pending_attempt_without_consuming_commit_slot`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_reject_keeps_immutable_rejected_commit_and_binding_only`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_service_recomputes_policy_and_records_cached_count_mismatch`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_stale_cached_decision_and_false_external_count_cannot_suppress_reject`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_recover_success_creates_two_attempts_and_only_then_commits`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_recovery_success_requires_fresh_policy_result_before_terminal_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_missing_recovery_finding_refresher_reevaluates_as_pending_human`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_human_response_is_appended_then_policy_is_reevaluated_as_new_attempt`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_recover_failure_is_structured_and_reevaluated[report0-REJECT-rejected]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_recover_failure_is_structured_and_reevaluated[report1-REQUIRE_HUMAN-pending_human]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_service_detects_stale_prose_and_proposal_against_audit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_service_detects_stale_extraction_against_audit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_commit_service_includes_volume_ref_and_write_fact_provenance`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_commit_service_rejects_malformed_gate_artifacts`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_commit_service_rejects_nested_extraction_result_shape`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_commit_service_rejects_extraction_wrapper_even_with_empty_core_fields`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_commit_service_rejects_extraction_result_missing_core_fields`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_commit_service_rejects_non_object_extraction_items`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_commit_service_rejects_non_object_accepted_event_items`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_commit_service_normalizes_accepted_events_before_projection`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_apply_projections_normalizes_events_before_router_inspection`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_apply_projections_updates_state_for_rejected_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_chapter_commit_cli_ignores_consistency_fields_and_preserves_changes_advisories`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_apply_projections_writes_events_and_amend_proposals`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_commit_is_durable_before_any_projection_side_effect`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_failed_commit_persistence_runs_no_projection`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py::test_projection_failure_does_not_mutate_durable_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py::test_event_log_store_writes_per_chapter_file_and_sqlite_mirror`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py::test_event_log_store_rejects_events_without_a_durable_accepted_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py::test_event_log_store_rejects_events_that_differ_from_the_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py::test_event_log_store_generates_missing_event_id_and_chapter`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py::test_event_log_store_normalizes_llm_alias_event_shape`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py::test_event_log_store_rejects_unknown_event_type_after_normalization`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py::test_event_log_store_rejects_non_list_event_collection`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py::test_event_log_store_rejects_non_object_event_items`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py::test_event_log_store_rejects_blank_event_subject`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py::test_event_log_store_ignores_duplicate_event_id`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py::test_event_log_store_recent_and_health_use_sqlite_mirror`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py::test_event_log_store_recent_and_health_without_table`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py::test_story_events_cli_reads_chapter_file`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py::test_router_maps_power_breakthrough_to_state_and_memory`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py::test_router_maps_relationship_changed_to_index`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py::test_router_maps_world_rule_broken_to_memory_only`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py::test_router_collects_required_writers_from_commit_payload`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py::test_router_maps_power_breakthrough_to_state_memory_vector`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py::test_router_maps_relationship_changed_to_index_and_vector`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py::test_required_writers_includes_vector_for_key_events`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py::test_required_writers_includes_index_for_accepted_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py::test_router_ignores_unknown_and_non_dict_events`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py::test_manifest_is_the_ordered_rebuild_topology`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py::test_manifest_declares_rebuild_owned_intent_diagnostics_projection`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_state_projection_rejects_fake_payload_before_state_write`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_index_projection_rejects_fake_payload_before_index_write`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_projection_rejects_corrupt_durable_commit_before_state_write`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_projection_writers_reject_mismatched_payload_before_side_effects`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_summary_memory_and_vector_writers_reject_payload_without_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_projection_writers_accept_matching_durable_payload_and_ignore_projection_status`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_state_projection_writer_handles_rejected_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_state_projection_writer_applies_accepted_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_state_projection_writer_rejects_out_of_order_retry`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_legacy_chapter_index_writer_rejects_story_system_project`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_accepted_chapter_commits_advance_progress_and_word_count`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_reapplying_accepted_chapter_commit_does_not_double_count_words`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_state_projection_writer_derives_delta_from_power_breakthrough_event`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_state_projection_writer_updates_strand_tracker`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_state_projection_writer_rejects_changed_payload_for_same_chapter`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_accepted_commit_updates_state_json_end_to_end`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_index_projection_writer_applies_entity_delta`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_index_projection_writer_registers_stable_protagonist_aliases`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_entity_delta_without_protagonist_flag_preserves_existing_protagonist`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_index_projection_writer_derives_relationship_from_event`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_index_projection_writer_derives_artifact_entity_from_event`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_accepted_commit_writes_chapter_index_tables`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_index_projection_writer_is_idempotent_for_replay`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_index_projection_writer_records_state_change_from_event`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_summary_projection_writer_writes_summary_markdown`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_summary_projection_writer_replay_overwrites_not_appends`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_memory_projection_writer_maps_commit_into_scratchpad`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_memory_projection_writer_is_idempotent_for_replay`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_vector_projection_writer_is_idempotent_for_replay`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_memory_projection_writer_maps_open_loop_event_into_scratchpad`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_state_writer_aggregates_foreshadowing_from_open_loop_events`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_state_writer_foreshadowing_replay_is_idempotent`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_state_writer_foreshadowing_orphan_close_does_not_fabricate_loop`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_state_writer_keeps_identical_content_loops_distinct_and_closes_by_id`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_router_routes_open_loop_events_to_state`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_memory_projection_keeps_duplicate_loop_text_distinct_and_closes_by_identity`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_memory_projection_orphan_close_does_not_resolve_an_unlinked_legacy_identity`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_memory_projection_tracks_promise_create_and_linked_payoff_without_ledger_write`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_payoff_only_event_does_not_create_reader_promise_memory`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py::test_promise_paid_off_with_legacy_exact_unique_content_updates_same_memory_identity`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rejected_projection_fixture_is_bound_to_a_service_owned_hard_veto`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_retry_projection_replays_existing_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_retry_projection_rebuilds_event_read_models_from_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_retry_projection_replay_keeps_event_read_models_aligned_and_unique`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_retry_legacy_commit_with_projection_status_preserves_its_bytes`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_retry_repairs_divergent_event_file_and_sqlite_from_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_retry_after_event_mirror_failure_repairs_and_preserves_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_retry_projection_reports_missing_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_replay_projections_runs_range`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_full_rebuild_discovers_sparse_commit_sequence_and_preserves_canon`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_full_rebuild_validates_every_commit_before_reset`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_full_rebuild_is_repeatable_and_preserves_operational_index_data`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_full_rebuild_reports_projection_and_chapter_on_failure`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_full_rebuild_refuses_empty_or_noncanonical_commit_sets_before_reset`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_full_rebuild_preserves_incremental_foreshadowing_semantics`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_full_rebuild_validates_scenes_appearances_and_state_change_index`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_full_rebuild_validates_index_field_values`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_regenerates_intent_diagnostics_and_clears_stale_rows`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_writes_empty_intent_diagnostics_projection`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_upgrades_unique_legacy_state_loop_row_to_event_identity`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_upgrades_legacy_state_description_alias_for_structured_loop_content`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_upgrades_legacy_state_question_alias_for_structured_loop_content`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_keeps_unprovable_legacy_state_row_non_authoritative`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_shadows_mixed_evidence_legacy_memory_row_when_canon_resolves_loop`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_resolves_description_alias_before_context_exposes_legacy_loop`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_migrates_only_exact_historical_memory_aliases[content-\u7389\u4f69\u4e3a\u4f55\u53d1\u70ed]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_migrates_only_exact_historical_memory_aliases[description-\u7389\u4f69\u4e3a\u4f55\u53d1\u70ed]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_migrates_only_exact_historical_memory_aliases[unanswered_question-\u7389\u4f69\u4e3a\u4f55\u53d1\u70ed\uff1f]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_migrates_only_exact_historical_memory_aliases[normalized-mystery\uff1a\u7389\u4f69\u4e3a\u4f55\u53d1\u70ed]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_does_not_bind_ambiguous_or_wrong_chapter_legacy_memory_alias`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_keeps_payoff_only_diagnostic_without_creating_active_promise`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_reconciles_duplicate_loops_promises_and_legacy_rows_without_duplicate_active_context`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py::test_rebuild_upgrades_legacy_reader_promise_memory_without_duplicate_active_rows`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_runtime_contract_builder.py::test_runtime_contract_builder_creates_volume_and_review_contracts`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_runtime_contract_builder.py::test_runtime_contract_builder_surfaces_review_extracted_anti_patterns`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_story_runtime_sources.py::test_load_runtime_sources_prefers_latest_accepted_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_story_runtime_health.py::test_story_runtime_health_reports_missing_commit_as_not_ready`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_story_runtime_health.py::test_story_runtime_health_prefers_latest_story_system_chapter_over_state_projection`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_build_and_filter`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_uses_memory_orchestrator_for_working_when_enabled`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_skips_memory_orchestrator_when_disabled`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_loads_volume_outline_file`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_includes_story_contract_and_prewrite_validation`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_prefers_contract_route_over_legacy_genre_profile`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_exposes_latest_rejected_commit_not_last_accepted`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_story_system_reader_never_promotes_divergent_legacy_state_to_canon`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_blocks_when_story_contract_missing`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_query_router`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_applies_ranker_and_contract_meta`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_includes_reader_signal_and_genre_profile`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_genre_section_and_refs_extraction`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_reader_signal_with_debt_and_disable_switch`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_includes_writing_guidance`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_dynamic_weights_and_composite_genre`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_genre_alias_guidance_and_heading_extraction`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_genre_aliases_normalized_for_profile_lookup`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_enables_methodology_for_xianxia`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_enables_methodology_for_non_xianxia_by_default`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_allows_methodology_whitelist_restriction`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_persist_writing_checklist_score_logs_failure`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_composite_genre_boundary_three_plus`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_dynamic_weights_from_config_override`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_genre_profile_fallbacks_to_project_info`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_genre_profile_prefers_project_info_over_project`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py::test_context_manager_includes_plot_structure_when_outline_has_nodes`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_commit_suppresses_conflicting_legacy_and_keeps_diagnostic`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_latest_chapter_fact_beats_historical_retrieval`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_identical_projection_is_deduplicated_with_all_evidence`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_conflicting_same_chapter_verified_canon_fails_fast`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_malformed_canonical_commit_blocks_context_and_rebuild[missing_outer_schema]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_malformed_canonical_commit_blocks_context_and_rebuild[wrong_schema]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_malformed_canonical_commit_blocks_context_and_rebuild[filename_meta_mismatch]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_malformed_canonical_commit_blocks_context_and_rebuild[invalid_extraction]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_malformed_canonical_commit_blocks_context_and_rebuild[invalid_review]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_malformed_canonical_commit_blocks_context_and_rebuild[invalid_fulfillment]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_malformed_canonical_commit_blocks_context_and_rebuild[invalid_disambiguation]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_malformed_canonical_commit_blocks_context_and_rebuild[noncanonical_filename]`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_accepted_rejected_future_and_target_commits_share_fact_and_snapshot_boundary`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_valid_accepted_commit_is_loaded_for_next_chapter`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_projection_never_becomes_canon_without_matching_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_governed_context_uses_commit_over_state_and_marks_stale`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_governed_context_splits_intent_craft_and_rag_reference`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_promise_event_is_canon_while_payoff_target_is_intent`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_future_planned_death_does_not_become_a_canon_fact`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_entity_fields_require_commit_evidence_individually`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_matching_memory_projection_deduplicates_with_commit_evidence`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_memory_without_evidence_stays_unknown_reference`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_relationship_projection_conflict_is_suppressed`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_structured_intent_canon_ambiguity_is_diagnostic_not_canon_failure`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_conflicting_authoritative_intents_are_exposed_without_failing_canon`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_relationship_commit_suppresses_conflicting_legacy_row`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_rag_similarity_does_not_grant_authority`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py::test_rag_commit_lineage_requires_a_matching_accepted_commit`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_phase8_acceptance_template.py::test_phase9_handoff_consumes_only_the_effective_history_result_contract`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_phase8_acceptance_template.py::test_h1_acceptance_template_is_result_free_and_non_self_referential`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_phase8_acceptance_template.py::test_h1_does_not_include_the_result_filled_h2_record`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_inventory_schema_and_records_exist`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_schema_declares_draft_2020_12_and_separate_record_families`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_invalid_domains_and_missing_reader_authority_are_rejected`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_missing_required_ownership_fields_are_rejected[writers-owner]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_missing_required_ownership_fields_are_rejected[writers-replacement]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_missing_required_ownership_fields_are_rejected[writers-retirement_criterion]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_missing_required_ownership_fields_are_rejected[writers-evidence]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_missing_required_ownership_fields_are_rejected[writers-active_consumers]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_missing_required_ownership_fields_are_rejected[readers-read_edges]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_missing_required_ownership_fields_are_rejected[readers-lifecycle_status]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_missing_required_ownership_fields_are_rejected[migrations-backup]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_missing_required_ownership_fields_are_rejected[migrations-rollback]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_missing_required_ownership_fields_are_rejected[migrations-ambiguity_handling]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_duplicate_ids_are_rejected_per_record_family[writers-writer_id]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_duplicate_ids_are_rejected_per_record_family[readers-reader_id]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_duplicate_ids_are_rejected_per_record_family[migrations-migration_id]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_legacy_state_reader_cannot_claim_story_system_canon_authority`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_inventory_records_resolve_and_cover_required_reader_families`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_direct_memory_store_reader_cannot_claim_verified_projection`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_reader_exact_coordinate_authority_conflict_requires_machine_discriminator`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_reader_inventory_coordinate_removal_exposes_protected_read`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_unregistered_protected_writer_candidate_fails_until_classified`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_ast_scanner_discovers_new_state_writer_in_source`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_ast_scanner_finds_actual_archive_and_memory_writers`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_reader_scanner_detects_new_protected_file_reader`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_unresolved_protected_reader_source_requires_exact_classification`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_writer_scanner_detects_new_protected_sql_mutator`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_unresolved_protected_writer_target_requires_exact_reason_coded_exception`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_production_runtime_does_not_consult_inventory`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_inventory_has_required_domains_and_unique_stable_ids`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_inventory_has_mode_aware_records_and_resolvable_evidence`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_compatibility_contract_separates_version_axes_and_project_modes`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_marketplace_source_and_repository_versions_resolve_without_snapshot_activation`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_open_scanner_uses_target_and_mode_separately[path.open('a')-write]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_open_scanner_uses_target_and_mode_separately[path.open('w')-write]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_open_scanner_uses_target_and_mode_separately[path.open('r')-read]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_open_scanner_uses_target_and_mode_separately[path.open()-read]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_open_scanner_uses_target_and_mode_separately[path.open(mode='a')-write]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_open_scanner_uses_target_and_mode_separately[open(path, 'a')-write]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_open_scanner_uses_target_and_mode_separately[open(path, mode='r')-read]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_open_scanner_uses_target_and_mode_separately[open(path)-read]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_source_coordinate_cannot_be_attached_to_wrong_same_domain_owner`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_state_manager_cannot_have_conflicting_shadow_writer_contract`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_conflicting_same_implementation_domain_requires_distinct_selector`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_inventory_has_no_mechanically_generated_source_records`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_non_commit_reader_edges_cannot_claim_canon_authority[plan-reader-INTENT]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_non_commit_reader_edges_cannot_claim_canon_authority[state-reader-STATE_JSON]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_non_commit_reader_edges_cannot_claim_canon_authority[review-reader-WORKFLOW_METADATA]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_non_commit_reader_edges_cannot_claim_canon_authority[index-reader-INDEX_DB]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_style_samples_table_is_not_misclassified_as_index_db`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_override_proposals_and_style_samples_have_distinct_owner_contracts`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_state_manager_state_json_reader_is_discovered_and_bound_to_projection_edge`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_consistency_runner_intent_reader_uses_intent_authority`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_discovered_projection_readers_keep_domain_authority[state-reader-STATE_JSON-/state_manager.py-VERIFIED_PROJECTION]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_discovered_projection_readers_keep_domain_authority[review-reader-WORKFLOW_METADATA-/review_pipeline.py-WORKFLOW]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_discovered_projection_readers_keep_domain_authority[index-reader-INDEX_DB-/sql_state_manager.py-VERIFIED_PROJECTION]`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_non_story_exceptions_have_distinct_target_specific_rationales`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_dynamic_protected_exception_requires_owner_link_and_classification`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_projection_log_append_is_not_misclassified_as_reader`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_dynamic_reader_exception_requires_owner_and_exact_read_edge`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_generic_dynamic_exception_rationale_does_not_replace_ownership`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_writer_coverage_requires_exact_sink_coordinate`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_reader_coverage_requires_exact_sink_coordinate`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py::test_stale_dynamic_exception_is_rejected`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_documentation.py::test_marketplace_selects_canonical_active_root_and_excludes_snapshot`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_documentation.py::test_active_docs_keep_commit_and_projection_ownership_contract`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_documentation.py::test_ownership_document_rule_rejects_unqualified_false_claim_but_allows_labeled_history`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_documentation.py::test_all_selected_active_paths_have_no_unqualified_ownership_claims`

## Supplemental acceptance

Exact command executed on H1:

```text
PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_commit_artifacts.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_event_schema.py -q
```

Result: **4 passed / 0 failed / 0 skipped** (4 collected).

Supplemental node IDs:

- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_commit_artifacts.py::test_extraction_result_prefers_canonical_nested_payload`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_commit_artifacts.py::test_extraction_result_keeps_read_compatibility_for_legacy_commit_payload`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_story_event_schema.py::test_story_event_supports_power_breakthrough`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_story_event_schema.py::test_story_event_rejects_unknown_event_type`

## Diff check

Command executed on H1:

```text
git diff --check HEAD^ HEAD
```

Result: **PASS**.

## Supplementary plugin-wide diagnostic

This broader run is supplementary diagnostic evidence, not binding Phase 8 acceptance:

```text
PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests .claude/plugins/zhanghui/scripts/tests -q --tb=no
```

Result: **46 failed / 1818 passed / 3 skipped**. Its 46 failed node IDs exactly match the previous H1 plugin-wide run; **new Phase 8 regressions: 0**. These unchanged baseline/environment and non-binding suite failures do not change the binding acceptance result. The test environment lacks `pytest-asyncio`, and the repository does not declare it; pytest reports unknown `asyncio` marks. Other remaining failures are in the pre-existing config, fixture, legacy projection/RAG/CLI, Phase 7 template, and crash-safety suites. No unrelated tests or production code were changed to address them.

Failed node IDs (identical to the previous H1 run):

- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_api_client.py::test_embedding_client_success_and_retry`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_api_client.py::test_embedding_client_timeout_and_error`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_api_client.py::test_embedding_batch`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_api_client.py::test_rerank_client_success`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_api_client.py::test_rerank_retry_and_empty`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_api_client.py::test_modal_client_warmup_and_passthrough`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_api_client.py::test_embedding_empty_and_error_paths`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_api_client.py::test_embedding_exception_and_close`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_api_client.py::test_rerank_non_retry_error`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_api_client.py::test_embedding_session_parse_and_retry_paths`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_api_client.py::test_embedding_exception_retry_and_batch`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_api_client.py::test_rerank_modal_retry_and_warmup`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_api_client.py::test_modal_client_helpers`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_config.py::test_config_paths_and_defaults`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_config.py::test_get_config_and_set_project_root`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_extract_chapter_context.py::test_build_chapter_context_payload_includes_contract_sections`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_extract_chapter_context.py::test_build_chapter_context_payload_exposes_latest_rejected_commit`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_log.py::test_chapter_commit_service_writes_projection_log`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_schema_compat.py::test_state_writer_accepts_field_path_alias`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_schema_compat.py::test_state_writer_accepts_flat_field_legacy`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_schema_compat.py::test_state_writer_handles_array_value_in_field_path`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_schema_compat.py::test_state_writer_mirrors_protagonist_state_when_entity_is_protagonist`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_schema_compat.py::test_state_writer_recognizes_protagonist_via_tier_zhujue`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_schema_compat.py::test_state_writer_recognizes_protagonist_via_canonical_name_match`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_schema_compat.py::test_memory_writer_preserves_entity_type_for_organization`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_schema_compat.py::test_memory_writer_accepts_field_path_in_state_delta`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_schema_compat.py::test_memory_writer_extracts_open_loop_from_description_when_no_content`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_schema_compat.py::test_memory_writer_extracts_world_rule_from_rule_content`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_schema_compat.py::test_integration_real_deepseek_commit_projects_full_state`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_rag_adapter.py::test_store_and_search`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_rag_adapter.py::test_store_chunks_with_embedding_failure`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_rag_adapter.py::test_hybrid_search_full_scan`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_rag_adapter.py::test_hybrid_search_prefilter`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_rag_adapter.py::test_search_respects_chapter_filter_across_strategies`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_rag_adapter.py::test_graph_hybrid_search_with_entity_expansion`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_rag_adapter.py::test_search_auto_uses_graph_strategy_when_enabled`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_rag_adapter.py::test_graph_hybrid_search_fallback_when_graph_disabled`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_rag_adapter.py::test_graph_hybrid_search_rerank_failure_uses_candidates`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_rag_adapter.py::test_search_unknown_strategy_falls_back_to_hybrid`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_rag_adapter.py::test_search_with_backtrack`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_vector_projection_writer.py::test_rejected_commit_returns_not_applied`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_vector_projection_writer.py::test_store_zero_for_required_chunks_is_error`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_vector_projection_writer.py::test_run_store_coro_works_inside_active_event_loop`
- `.claude/plugins/zhanghui/scripts/data_modules/tests/test_webnovel_unified_cli.py::test_projections_retry_cli_runs`
- `.claude/plugins/zhanghui/scripts/tests/architecture/test_phase7_acceptance_template.py::test_h1_acceptance_template_is_complete_and_result_free`
- `.claude/plugins/zhanghui/scripts/tests/test_atomic_write_crash_safety.py::test_summary_projection_survives_kill`

## Architecture and runtime boundaries

- Ownership inventory validation: PASS.
- Writer coverage: `[]`; reader coverage: `[]`; reader-family coverage: `[]`.
- Stale reader exceptions: `0`; total reader exceptions: `39`; exact-coordinate authority conflicts: `0`.
- Ownership inventory runtime references: `0`.
- Production human verifier: **None**.
- Live correction activation: **None**.
- Phase 9 handoff: **Required before any correction can affect live Canon**. Phase 8 staged validation/preview does not activate corrections as Canon authority.
- `.claude/plugins/zhanghui/6.4.0/**`: unchanged.
- Stash `pre-phase7-preserve-untracked-2026-10-06`: untouched.

## H2 closure

This H2 is a record-only commit. It records the tested H1 identity above; it does not claim or reference its own commit SHA as tested implementation. No PR is created and no merge or Phase 9 implementation is included.
