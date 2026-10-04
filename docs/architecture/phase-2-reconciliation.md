# Phase 2: ProposedChanges reconciliation

## Contract

- **ProposedChanges** is the Writer's final `<chapter_changes>` declaration. `changes_gate.py` applies the CHANGES protocol and ledger checks. `ChapterCommitService` independently validates its shape and checks it against the declaration parsed from the supplied final chapter text.
- **ObservedChanges** is extraction from final prose only. `prepare_data_agent_input.py` parses the final chapter and writes a prose-only artifact plus a separate ProposedChanges JSON. The Data Agent receives only the prose-only path.
- **Reconciliation** is a derived audit artifact. It records `matched`, `proposed_not_observed`, `unproposed_observed`, `conflicts`, `accepted_payload`, coverage, source indexes, proposal/extraction hashes, final chapter hash, and prose-only hash. A caller-provided copy cannot authorize a commit.
- `ChapterCommitService.build_commit()` receives final chapter text, ProposedChanges, and extraction. It validates them, recomputes reconciliation, blocks any conflict, and derives the accepted payload itself. If an audit artifact is supplied, it must exactly match that recomputation.
- Any change to final prose requires a new split and extraction. Any change to prose, proposal, or extraction makes the old audit artifact stale. The service owns these checks; the CLI reads files and preserves the separate `changes_gate.py` protocol/ledger gate.

## Deterministic fact coverage (v1)

Normalized facts use `(entity, field, value, source_type, source_index)`.

- `character_state_changes` maps to observed `state_deltas`.
- `entity_deltas` map when a realm is explicit at `patch.realm`, `patch["current.realm"]`, nested `patch.current.realm`, or `current.realm`.
- `power_breakthrough` events map when entity and realm are explicit.

Other proposal categories and unmapped events/entity deltas are opaque and remain visible in audit output; they are not semantically reconciled in v1. `passed` means no conflict within these deterministic mappings, not full semantic coverage of every CHANGES category.

For a repeated `(entity, field)`, different normalized observed values create `observed_internal_conflict` and block the entire commit. Equal values across representations aggregate as evidence. A proposal with a different observed value creates `proposal_observed_conflict`; proposal-only facts remain `proposed_not_observed`; observed-only facts remain `unproposed_observed`. Opaque observations may remain in the accepted extraction payload if no deterministic conflict exists.

Reconciliation never writes Canon or projections. The durable chapter commit remains the only canonical write boundary, preserving `No durable commit, no story fact` and `No matching durable commit, no projection`.

## Target order

`final prose stabilized → split prose / CHANGES → Data Agent on prose-only artifact → ObservedChanges → service recomputes reconciliation → CHAPTER_COMMIT → projections`
