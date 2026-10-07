---
record_type: phase-9-h2-acceptance-record
status: ready-for-independent-review
tested_implementation_head: 01211707d26957c59c6477c6ae283c0ac5122ff8
tested_implementation_tree: 8a725757d2d7b50c7a72ed4890f13f49489fb8ff
tested_implementation_parent: e9948cfed5a9319a6b69ea3e4fc7f41b9b3a79c6
implementation_branch: codex/phase-9-correction-activation-recovery-migration
baseline_main: 63f3cef58090f399e6e8b740e3efebe6e5f3e459
approved_phase9_design_r3: dc2fd23a0cd3d3e134ddc735686429922ae09a11
independent_review: PASS
implementation_blockers: None
---

# Phase 9 Final Acceptance Record (H2)

This is a record-only H2. It binds the acceptance evidence and independent implementation review to the exact H1″ below. H2 itself is not the tested implementation and does not change the Phase 9 contract.

## Tested implementation identity

- `tested_implementation_head`: `01211707d26957c59c6477c6ae283c0ac5122ff8`
- H1 tree: `8a725757d2d7b50c7a72ed4890f13f49489fb8ff`
- H1 parent: `e9948cfed5a9319a6b69ea3e4fc7f41b9b3a79c6`
- Baseline `origin/main`: `63f3cef58090f399e6e8b740e3efebe6e5f3e459`
- Approved Phase 9 design R3: `dc2fd23a0cd3d3e134ddc735686429922ae09a11`
- Implementation branch: `codex/phase-9-correction-activation-recovery-migration`
- Review history: initial H1 `0947e0a...`; H1 R1 `4f5acc2...`; final accepted H1″ `01211707d26957c59c6477c6ae283c0ac5122ff8`. Only final H1″ is the tested implementation head.
- Independent implementation review: **PASS**.

## Acceptance evidence

The Phase 8 regression command and Phase 9 exact-H1″ acceptance command are the corresponding command groups in the result-free [Phase 9 H1 acceptance template](phase-9-h1-acceptance-template.md). Both ran against the exact H1″ SHA above.

| Evidence group | Result | Disposition |
|---|---:|---|
| Phase 8 correction contract regression | 302 passed | PASS |
| Phase 9 correction, activation, ownership, migration, and recovery acceptance | 373 passed | PASS on exact H1″ `01211707d26957c59c6477c6ae283c0ac5122ff8` |
| Supplementary plugin-wide diagnostic | 1922 passed, 3 skipped, 47 failed | **NOT green; diagnostic only** |

The plugin-wide command was `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests .claude/plugins/zhanghui/scripts/tests -q --tb=no`. Its final and baseline archive logs, including exact failed/error node IDs, were captured locally at `/tmp/zhanghui-phase9-final-pluginwide.log` and `/tmp/zhanghui-phase9-baseline-pluginwide.log` during acceptance. The logs are local evidence and are not committed by this record.

Baseline archive diagnostic: 1900 passed / 3 skipped / 49 failed / 8 errors. Final H1″ diagnostic: 1922 passed / 3 skipped / 47 failed. Exact node-ID comparison found all 47 final failures in the baseline failure set; 10 baseline failure/error IDs were absent from the final set. Those baseline-only hook failures/errors were associated with the archive lacking Git worktree metadata. New Phase 9 regression: **0**. This comparison does not make the plugin-wide suite green.

`git diff --check` passed for the H1 changes. No GitHub workflow run or status was observed for H1: **GitHub-hosted checks: none observed / not part of this acceptance evidence**.

## Independent implementation review findings

### Materialized Canon state

The reviewer confirmed that effective generations are built by sequential replay and store materialized Canon state in an immutable generation. Runtime `OwnedStateStore` reads that snapshot without rerunning the state reducer, while the owner overlay remains independently mutable. Where chapter prose contributes to Canon projection materialization, its exact digest is frozen in the publication dependency closure. AMEND, RETRACT, and SUPERSEDE affect active state only through a newly built generation.

### Exact publication binding

The active snapshot binds the exact publication record ID and SHA, semantic activation ID, effective-history digest, generation ID, base-set identity, and correction-lineage identities. New ChapterCommit and recovery bind to the exact source publication. A changed head reports `PUBLICATION_HEAD_CHANGED`; retry rebuilds from the newest active head, preserving concurrent corrections across a new chapter publication.

### RAG ownership and query closure

Mutable and generation-backed retrieval share a deterministic tokenizer, including the Chinese BM25 path. Canon generations retain correction-aware chunks, embeddings, and index inputs. Mutable owner search filters legacy `commit:*` rows before candidate selection and ranking. Vector, BM25, hybrid, and graph-hybrid paths remain distinct rather than collapsing into token overlap. The pinned generation supplies Canon graph authority, and correction AMEND/RETRACT/SUPERSEDE changes update generation Canon RAG.

### Host confirmation boundary

The Phase 9 core is host-agnostic; Codex Desktop UI is not part of product architecture. `CanonCorrectionAuthorization` remains the sole durable human-decision source, with `decision_provenance.phase9_confirmation` binding the workflow. The review does not claim cryptographic human identity verification.

## Non-claims and remaining boundaries

- GitHub CI and branch-protection checks are not claimed as passed; none were observed for H1.
- The whole plugin-wide suite is not green; 47 baseline-known failures remain.
- The workflow trust model does not defend against a malicious agent with project write access.
- Phase 9 is not merged; Issue #1 is not claimed closed; Phase 10 has not started. Phase 10 Intent/Craft final ownership reconciliation remains pending.
- Historical `.claude/plugins/zhanghui/6.4.0/**` remains a frozen snapshot and was unchanged in H1.

## H2 scope

H2 adds this acceptance record only. It does not alter production implementation, tests, ownership inventory, design, or implementation plan. H1 remains unchanged and is the sole tested implementation head.
