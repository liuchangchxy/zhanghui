# Phase 2: ProposedChanges reconciliation

## Verified flow before Phase 2

`webnovel-write` produced CHANGES with the Step 2A draft; Step 2B could rewrite prose, Step 3 reviewed it, and Step 4 polished and overwrote prose. The changes gate ran after polish, so it validated the block found in the final file but did not refresh a declaration that might refer to the earlier draft. Data Agent then received `chapter_file`, with no instruction to exclude the CHANGES block. It wrote `extraction_result.json`; `ChapterCommitService.build_commit()` validated the extraction schema and copied its event/state/entity arrays directly into the commit. No path reconciled the two artifacts. The precommit gate checked schemas but did not run changes_gate.

## Phase 2 contract

- **ProposedChanges:** the Writer's declaration in `<chapter_changes>`, regenerated after the final prose edit. `changes_gate.py` validates its schema, protocol, and existing ledger rules.
- **ObservedChanges:** the Data Agent's extraction from final prose only. It excludes the CHANGES block and never reads it as evidence.
- **Reconciliation:** deterministic normalization and comparison, persisted as `.webnovel/tmp/reconciliation_result.json`. It includes `matched`, `proposed_not_observed`, `unproposed_observed`, `conflicts`, `accepted_payload`, source indexes, and hashes binding it to the exact final chapter and extraction.
- **Accepted facts:** only observed events, state deltas, and entity deltas in the reconciliation payload can populate `CHAPTER_COMMIT`. A missing proposal is advisory; a proposal without observed support is not committed. A normalized entity/field with incompatible explicit values is a hard conflict and blocks commit.

Matching is deliberately narrow: stable entity IDs, normalized field names, and deterministic value aliases. Narrative claims without a structured target are left unmatched instead of being guessed. Reconciliation cannot edit prose or write Canon, state, indexes, memory, or projections. The durable chapter commit remains the only canonical write boundary.

## Target order

`draft → optional style rewrite → review → polish/final rewrite → refresh CHANGES → changes_gate → Data Agent on final prose only → reconciliation → CHAPTER_COMMIT → projections`

The standalone `webnovel-fast-write` follows the same freshness rule after any rewrite it performs. Commit validates the reconciliation status and the extraction hash; the CLI also checks the final chapter hash before calling the service.
