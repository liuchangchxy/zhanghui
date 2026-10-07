---
record_type: phase-9-h1-acceptance-template
status: result-free-template
tested_implementation_head: ""
tested_implementation_tree: ""
tested_implementation_parent: ""
---

# Phase 9 H1 Acceptance Template

This template is included in the implementation candidate. Leave every evidence
field empty in H1. Record exact results and artifact identities only in the
external acceptance evidence after the H1 commit has been reviewed.

The interactive check uses a disposable temporary project and a direct human
choice on the exact rendered correction package. It does not use fixture-created
authorization as evidence of human approval. No check may mutate the book project.

## Verification commands

### Phase 8 correction contract regression

```text
PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_schema.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_preview.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_schema.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_runtime_contract_builder.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_runtime_sources.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_story_runtime_health.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py .claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py .claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_documentation.py -q -k 'not test_h1_does_not_include_the_result_filled_h2_record'
```

### Phase 9 correction, activation, ownership, migration, and recovery

```text
PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_correction_activation.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_correction_authorization_workflow.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_schema.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_effective_history.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_generation.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_event_log_store.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_project_migration.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_owned_project_view.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_context_provenance.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_state_manager_extra.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_doctor.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py .claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py .claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_documentation.py .claude/plugins/zhanghui/scripts/tests/architecture/test_phase9_acceptance_template.py -q
```

### Plugin-wide diagnostic and source checks

```text
PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests .claude/plugins/zhanghui/scripts/tests -q --tb=no
git diff --check HEAD^ HEAD
git diff --name-only <H1-parent> <H1> -- .claude/plugins/zhanghui/6.4.0
git stash list --format='%gd %gs'
git status --short --branch
```

### Direct interactive workflow

1. Create a disposable project outside the working tree with one accepted base commit and complete the explicit project migration workflow.
2. Stage one correction and render its canonical review package through the correction workflow.
3. Present the complete package and ask the human to choose `APPROVE` or `REJECT`. Do not synthesize, replay, or infer the answer.
4. Persist the chosen answer with `correction record-decision`; on `APPROVE`, invoke `correction activate` with the exact persisted authorization file.
5. Capture the request, challenge, authorization and correction digests; before/after publication identity; effective revision; seven-domain manifest; active owner overlay; and the direct human interaction surface.
6. Repeat with `REJECT`, no answer, stale parent, altered authorization, and an unavailable interaction surface. Active publication identity and Canon slices must remain unchanged in each non-approval case.

## Evidence fields — populate outside H1 only

```yaml
implementation_branch: ""
implementation_head: ""
implementation_tree: ""
implementation_parent: ""
phase8_command_and_result: ""
phase9_command_and_result: ""
plugin_wide_command_and_result: ""
interactive_workflow_artifact_hashes: ""
interactive_active_before_after_identity: ""
interactive_seven_domain_manifest: ""
independent_review_disposition: ""
stash_identity_and_status: ""
protected_snapshot_diff: ""
working_tree_status: ""
remaining_findings: ""
```
