---
title: "Phase 8 — Canon Correction, Lineage & Effective History Contract"
type: "phase-plan"
status: "🟢 待开始"
created: "2026-10-06"
parent: "../specs/2026-10-06-phase-8-canon-correction-contract-design.md"
children: []
tags: ["phase-8", "canon-correction", "effective-history"]
---

# Phase 8 — Canon Correction, Lineage & Effective History Contract Implementation Plan

> **For agentic workers:** Follow the spec linked below. Implement task-by-task with tests first. Do not start Phase 9 activation work.

**Goal:** Add immutable correction request, authorization-decision, and correction artifacts plus a deterministic staged resolver, without treating persisted actor fields as proof of human identity or activating corrections in normal runtime.

**Architecture:** Keep `story-system/v1` chapter commits immutable and add a separately versioned `canon-correction/v1` append-only chain. Validate correction identity, authorization, lineage, and materialized operations, then expose one pure resolver result through read-only staged APIs. Normal runtime and projections continue to consume existing accepted commits until Phase 9.

**Tech Stack:** Existing Python/Pydantic/pytest stack, JSON artifacts, `hashlib.sha256`, existing durable commit canonicalizer/validator, atomic file and lock utilities. Correction requests and authorizations form their own durable authority protocol; GateDecisionStore is not part of it.

**Spec:** `docs/superpowers/specs/2026-10-06-phase-8-canon-correction-contract-design.md`

## Global Constraints

- Baseline: `2b31bfa7bb58e72d3ef86bc582821f16aa486f9b`.
- Never rewrite or delete accepted chapter commit bytes or correction artifacts.
- Base identity uses `durable_projection.canonical_commit_json()` after accepted-commit validation.
- One linear correction chain per exact chapter and base digest. Normal concurrent appends serialize to one append plus `STALE_PARENT`; pre-existing sibling files fail resolution and are not repaired in Phase 8.
- Correction follows an immutable request → human authorization → final correction sequence, with exact request and authorization digest binding.
- Phase 8 persists the asserted decision but does not establish production human identity; no Phase 8 runtime, skill, CLI, or agent workflow may mint production APPROVE decisions or activate correction authority.
- Phase 9 must provide trusted human-decision capture before any correction enters live effective Canon.
- Phase 8 APIs are staged/internal and read-only for preview; do not connect normal runtime, write/query/context, ChapterCommitService, event/projection writers, or rebuild.
- Keep Phase 8 production paths free of any `6.4.0/**` change and no package major-version change.
- Do not implement Phase 9 rebuild, migration, recovery, or activation.

## Review Focus

- Canonical digest drift: ignored `projection_status` and JSON formatting must not change base identity; substantive accepted content changes must.
- Authorization scope and trust drift: caller-supplied `actor_ref` or provenance cannot prove human identity; one exact request digest has at most one distinct decision.
- Partial materialization: changed-path declarations and digests must exactly describe AMEND's complete result.
- Filesystem races: under the chapter lock one concurrent append succeeds and the stale request writes nothing; pre-existing sibling files are a separate resolver conflict case.
- Hidden activation: no ordinary write/query/context/projection caller may consume correction output in this phase.

---

## File map

| File | Responsibility |
|---|---|
| Create `.claude/plugins/zhanghui/scripts/data_modules/canon_correction_schema.py` | Pydantic models, strict operation-specific shape validation, canonical correction serialization and digests. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/canon_correction_store.py` | Append-only request, authorization, and correction IO; staged APIs by task; locking, idempotent retry, and conflict-safe create. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/canon_correction_resolver.py` | Pure structural, authority-contract, lineage validation and deterministic effective-history result. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/canon_correction_preview.py` | Read-only loading and preview/inspection API; no regular workflow or runtime wiring. |
| Create `.claude/plugins/zhanghui/docs/canon-correction.schema.json` | Published request, authorization, and `canon-correction/v1` artifact schemas. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_schema.py` | Schema, canonical identity, and immutability contract tests. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py` | Append, retries, stale parents, races, and no-overwrite tests. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py` | Operations, lineage, authorization, deterministic output, and failure diagnostics. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_preview.py` | Read-only preview and no-runtime-activation tests. |
| Create `.claude/plugins/zhanghui/scripts/tests/architecture/test_phase8_acceptance_template.py` | Phase 8 acceptance binding shape; keep the H1 template result-free. |
| Create `docs/superpowers/acceptance/2026-10-06-phase-8-final-acceptance.md` only after H1 review | Separate H2 result record binding results to tested H1; never mutate implementation H1 to claim its own tested SHA. |

All paths above are Phase 8 future implementation scope. The current design task creates none of these implementation files.

## Task 1: Freeze all correction schemas and canonical identities

**Files:** Create `canon_correction_schema.py`, schemas for all three artifact types, `canon-correction.schema.json`, and `tests/test_canon_correction_schema.py`; reuse `durable_projection.canonical_commit_json()`.

**Interfaces:**
- Models for `canon-correction-request/v1`, `canon-correction-authorization/v1`, and `canon-correction/v1` with strict operation-specific shapes.
- Shared canonical serialization: sorted-key compact UTF-8 JSON; rejects non-JSON/non-finite values.
- `request_sha256`, `authorization_sha256`, and `correction_sha256`: SHA-256 of each artifact's canonical serialization.
- `base_commit_digest(commit: dict) -> str`: first validates a durable accepted commit, then hashes existing `canonical_commit_json(commit)`.
- `effective_content_digest(status: Literal["accepted", "retracted"], extraction: dict | None) -> str`: hashes the canonical status/content envelope from the spec.
- No Task 1 API persists any artifact or writes a semantic correction.

- [ ] **Step 1: Write failing schema and identity tests**

Add tests for valid/invalid schema versions; required fields and path-safe IDs for each artifact; operation-specific request/correction content and changed paths; exact request/authorization references; and digest vectors for all three artifacts. Prove key-order/whitespace independence, projection-status exclusion for base commits, and digest change for substantive content changes.

- [ ] **Step 2: Run tests to confirm they fail for missing contract**

Run: `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_schema.py -q`
Expected: FAIL because the three correction artifact models and identity helpers do not exist.

- [ ] **Step 3: Implement only schema and digest primitives**

Use `read_validated_chapter_commit()` / `canonical_commit_json()` from `durable_projection.py`; reject non-accepted status before hashing. Keep canonical corrections on a separate schema version and do not change chapter commit models.

- [ ] **Step 4: Run schema tests and existing commit validation tests**

Run the focused test above, then `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py -q`.
Expected: both PASS; old commit schema and behavior remain unchanged.

- [ ] **Step 5: Commit schema boundary**

Commit only schema/helper/tests/docs-schema changes with message `feat: define canon correction artifact schema`.

## Task 2: Implement correction-specific request and authorization persistence

**Files:** Extend `canon_correction_store.py`; create/extend `tests/test_canon_correction_store.py`; use the fixed namespace from the spec, existing `FileLock` and atomic-create patterns.

**Interfaces:**
- `correction_target_dir(root, chapter, base_sha256)` resolves `.story-system/corrections/chapter_NNN/<base_commit_sha256>/`.
- `append_correction_request(...)` stores only an immutable request at `requests/<request_id>.request.json`.
- `append_correction_authorization(...)` resolves and verifies the exact request and structurally validates an asserted `APPROVE`/`REJECT` record, then stores only an immutable authorization at `authorizations/<authorization_id>.authorization.json`. It does not authenticate the actor or mint trusted human approval.
- Request and authorization APIs enforce path-safe IDs, canonical-digest binding, idempotent exact retries, and same-ID/different-body conflicts.
- Enforce one-request-one-distinct-decision under the chapter/exact-base lock, re-scanning the full authorization set before atomic create: exact retry is idempotent; a second distinct decision for the same `request_sha256` fails with `AUTHORIZATION_CONFLICT`; REJECT is permanent for that request.
- Persisted `actor_ref`, provenance strings, and caller dictionaries are assertions only. Phase 8 provides no production human-approval minting workflow or trusted identity mechanism.
- Task 2 exposes no API capable of writing `corrections/*.correction.json`.

- [ ] **Step 1: Write failing append contract tests**

Cover request persistence, accepted-base and valid-parent requirements, exact request resolution, authorization for another request/base rejection, both `APPROVE` and `REJECT`, immutable request/authorization paths, exact same-ID/body retry as idempotent, same-ID/different-body conflict, one-request-one-decision including concurrent distinct decisions serialized to one stored decision plus `AUTHORIZATION_CONFLICT`, and path traversal rejection. Explicitly test that `actor_ref="human"` without trusted/test-only verification is not production human proof; arbitrary provenance dictionaries and GateDecisionStore/gate-human-response provenance alone do not acquire authority. After REJECT, a new decision on the same request is forbidden and a new request identity/digest is required. Assert these APIs cannot create a final correction artifact.

- [ ] **Step 2: Run tests to confirm they fail**

Run: `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py -q`
Expected: FAIL because correction request/authorization persistence is not implemented.

- [ ] **Step 3: Implement atomic append under chapter lock**

Implement append-only request and authorization persistence only. Under the chapter/exact-base lock, re-scan all authorization artifacts for the exact request before create. Validate schema, namespace, exact request digest, and decision structure before writes; do not claim that these checks authenticate the human. Use atomic create-if-absent behavior; identical canonical artifact is an idempotent retry, while different content under the same ID or a second distinct decision for one request is rejected without rewriting. Do not implement `append_correction()` or a production approval issuer in this task.

- [ ] **Step 4: Verify authority persistence stays staged**

Do not test or implement final-correction concurrency here. Verify request and authorization artifacts remain immutable and that this task's APIs cannot create sibling correction edges or any final correction.

- [ ] **Step 5: Run store and file-integrity tests**

Run correction request/authorization storage tests.
Expected: PASS; ChapterCommit gate storage and chapter commit bytes remain untouched.

- [ ] **Step 6: Commit append-only store**

Commit request/authorization persistence and focused tests with message `feat: persist correction requests and authorizations`.

## Task 3: Implement final correction append after authority is complete

**Files:** Extend `canon_correction_store.py` and `tests/test_canon_correction_store.py`. This task depends on completed Task 2 request/authorization persistence and validation.

**Interfaces:**
- `append_correction(root, correction, *, request, authorization, decision_verification)` accepts the exact already-persisted request and authorization artifacts plus a trusted decision-verification result from an authority source; it never upgrades raw actor/provenance fields or a caller-supplied dictionary to trusted approval.
- Under the chapter/exact-base lock, re-resolve request and authorization from their fixed namespace and revalidate canonical digests, `APPROVE`, one-request-one-decision uniqueness/no conflict, and same chapter/base namespace.
- Require correction semantic content, operation, and changed paths to exactly equal the approved request; require request parent revision/content digest still equals the unique current tip.
- Any failed check occurs before creating `corrections/<correction_id>.correction.json`. Exact retry is idempotent; same-ID/different-content is rejected. Concurrent requests to the same parent yield one success and one `STALE_PARENT`, with no artifact for the stale request.
- In Phase 8, `decision_verification` is available only through an explicit test fixture for exercising complete lineage; no production provider or minting workflow exists. GateDecisionStore responses may be cited only as supplementary provenance and do not satisfy this requirement.

- [ ] **Step 1: Add failing final-append authorization and lineage tests**

Test absent/mismatched request, absent/mismatched authorization, wrong digest, `REJECT`, missing trusted-decision verification despite `actor_ref="human"`, arbitrary provenance dictionary, GateDecisionStore/gate-human-response evidence alone, cross-base reference, changed final content after approval, authorization conflict, stale parent, exact retry, ID collision, and successful exact-scope test-fixture append. Assert every failure, especially authorization conflict, leaves the final correction path absent or unchanged.

- [ ] **Step 2: Run final-append tests to confirm they fail**

Run: `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py -q -k append_authorized`
Expected: FAIL because the final correction writer does not exist.

- [ ] **Step 3: Implement the final correction writer**

Implement `append_correction()` only after Task 2 persistence exists. Under the lineage lock, reload and validate the persisted request and authorization, require a trusted decision-verification result (test fixture only in Phase 8), require `APPROVE` and authorization uniqueness/no conflict, verify exact digests and semantic equality, re-scan the unique chain tip, then atomically create the final correction artifact. Any failed check, including authorization conflict, leaves zero correction filesystem side effects. Do not extend GateDecision, gate finding persistence, or `GateDecisionStore`.

- [ ] **Step 4: Test concurrent stale-parent behavior**

Add the controlled concurrent API test: one final append succeeds and the stale request returns `STALE_PARENT` without writing an artifact. Add guards proving no normal runtime, skill, CLI, agent workflow, ChapterCommitService, or projection/rebuild path can mint authorization or call final correction append. Test-only verification fixtures must be labeled as test inputs and never as project human-approval evidence in acceptance records. The pre-existing sibling resolver case is tested in Task 4 after lineage validation exists.

- [ ] **Step 5: Assert proposal producers have no append authority**

Add tests proving `AmendProposalTrigger`, consistency findings, reviewer findings, extraction output, and projection repair output do not call the correction store or create correction artifacts. Keep these components proposal/finding-only.

- [ ] **Step 6: Run and commit final append boundary**

Run request/authorization, append, stale-parent, non-authority-path, and fixture-label tests. Expected: only exact requests paired with a unique APPROVE and explicit test verification can produce staged correction artifacts; gate storage remains untouched. Commit with message `feat: append staged canon corrections`.

## Task 4: Build deterministic lineage validation

**Files:** Create `canon_correction_resolver.py`, extend `tests/test_canon_correction_resolver.py`.

**Interfaces:**
- `validate_lineage(accepted_commit, correction_artifacts, correction_requests: Sequence, correction_authorizations: Sequence) -> ValidatedLineage`; these correction-specific sequences retain duplicates for ambiguity detection and never use generic evidence maps.
- `ValidatedLineage` contains immutable base digest, ordered edge artifacts, deterministic revision IDs, and diagnostics; invalid/conflicted lineage contains no chosen tip.

- [ ] **Step 1: Write failing graph tests**

Test base-only path, two-step chain, shuffled input determinism, missing/mismatched request or authorization, request digest mismatch, rejected authorization, correction content differing from approved request, duplicate/conflicting decisions for one request (APPROVE+REJECT and two APPROVE artifacts), arbitrary provenance/`actor_ref` without trusted fixture using an injected test-only authority verifier, wrong chapter/base digest, stale parent content hash, duplicate ID/same content, duplicate ID/different content, sibling children, pre-existing immutable sibling files preserved byte-for-byte with `LINEAGE_SIBLING_CONFLICT`/`ok=false`/no effective result, pre-existing authorization conflicts with `AUTHORIZATION_CONFLICT`/`ok=false`/no effective result, ordinary append refusal on either conflict, disconnected edge, and cycle. These are pre-existing files from corruption/import/old or bypassed storage, distinct from concurrent API append.

- [ ] **Step 2: Run graph tests to confirm failure**

Run: `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py -q -k lineage`
Expected: FAIL because no lineage validator exists.

- [ ] **Step 3: Implement graph validation without winner selection**

Build request-to-authorization indexes from the complete sequences and detect conflicting decisions before lineage resolution. Exact same ID/body retry counts once; any second distinct decision for the same request is `AUTHORIZATION_CONFLICT`. Reject REJECTed requests and corrections whose authorization reference is not the unique matching APPROVE. Then build parent-to-children adjacency and enforce one distinct child per parent plus operation transitions. Walk only the unique base-to-tip chain after proving all artifacts are connected and valid. Sort diagnostics for deterministic output; sorting never resolves authorization or lineage conflicts.

- [ ] **Step 4: Run graph tests with permutations**

Repeat the same fixture with reversed and randomized artifact input order; require byte-identical diagnostics and same ordered chain.
Expected: PASS.

- [ ] **Step 5: Commit lineage validator**

Commit with message `feat: validate linear canon correction lineage`.

## Task 5: Resolve AMEND, RETRACT, and SUPERSEDE

**Files:** Extend `canon_correction_resolver.py`, `tests/test_canon_correction_resolver.py`; use current `ExtractionResult` validation.

**Interfaces:**
- `resolve_effective_history(accepted_commit, correction_artifacts, correction_requests: Sequence, correction_authorizations: Sequence) -> EffectiveHistoryResult` returns the exact spec fields: `ok`, `chapter`, `base_commit_sha256`, `effective_revision_id`, `effective_status`, `effective_extraction_result`, `applied_correction_ids`, `effective_content_sha256`, `diagnostics`.
- Resolve each correction's `request_sha256` to its exact request and each request to its exact authorization digest/identity; require `APPROVE` and exact semantic equality before applying lineage.
- The resolver's internal authority-validation seam may receive an explicit test-only verified-decision fixture in tests; persisted `actor_ref`/provenance alone is never interpreted as human identity proof, and Phase 8 supplies no production verifier.

- [ ] **Step 1: Write operation tests before implementation**

Add zero-correction backward-compatibility; deterministic AMEND; exhaustive changed-path/before-after digest validation; AMEND rejects changes to every canonical top-level extraction field and cannot count an unchanged arbitrary/extra key as a preserved canonical field; resolver detects missing, rejected, wrong-request, ambiguous, APPROVE+REJECT, and two-APPROVE authorization cases with `ok=false` and no effective Canon; exact duplicate authorization retry is idempotent; RETRACT output and preserved source artifacts; SUPERSEDE full replacement; correction-of-correction; and invalid result never exposes clean effective Canon.

- [ ] **Step 2: Confirm the operation tests fail**

Run: `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py -q -k 'amend or retract or supersede or backward'`
Expected: FAIL because resolution operations are not implemented.

- [ ] **Step 3: Implement pure resolver application**

First validate accepted base, all correction artifacts, requests, authorizations, unique authorization decisions, and the complete unique lineage. Then apply each materialized operation in order. AMEND verifies the recomputed structural diff and preserves at least one field declared by the active `ExtractionResult` schema; arbitrary instance keys and `extra="allow"` extensions do not count. RETRACT sets status and extraction to retracted/null; SUPERSEDE validates and replaces the whole extraction. This validates persisted structure and bindings, not real-world human identity. Never mutate input dictionaries.

- [ ] **Step 4: Verify determinism and immutability**

Resolve identical inputs repeatedly and in different artifact orders; compare serialized results. Snapshot commit/correction fixture bytes before and after resolution and require exact equality.
Expected: PASS.

- [ ] **Step 5: Run correction and base artifact validation suites**

Run `test_canon_correction_resolver.py`, `test_canon_correction_schema.py`, and `test_canon_correction_store.py`.
Expected: PASS.

- [ ] **Step 6: Commit operation resolver**

Commit with message `feat: resolve staged effective canon history`.

## Task 6: Add read-only staged preview and prove runtime remains inactive

**Files:** Create `canon_correction_preview.py`, `tests/test_canon_correction_preview.py`; update architecture tests only for activation guards.

**Interfaces:**
- `preview_chapter_corrections(project_root: Path, chapter: int, base_commit_sha256: str) -> EffectiveHistoryResult` reads the accepted base plus corrections, correction requests, and correction authorizations from the fixed namespace, then calls `resolve_effective_history(accepted_commit, correction_artifacts, correction_requests, correction_authorizations)`.
- No function in this task writes a correction, gate response, commit, event, or projection file.

- [ ] **Step 1: Write failing read-only and non-activation tests**

Snapshot all source and projection bytes; run preview; assert exact bytes unchanged. Assert normal `load_runtime_sources()` returns the same snapshot before and after preview. Add a static dependency guard proving no correction module is imported by normal runtime, Context assembly, query/write entrypoints, ChapterCommitService, EventLogStore, projection writers, or projection rebuild.

- [ ] **Step 2: Confirm the guard tests fail before preview exists**

Run: `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_preview.py -q`
Expected: FAIL because the staged preview and inactive-path guard are absent.

- [ ] **Step 3: Implement read-only discovery and preview**

Load only the specified chapter/base namespace and its typed request/authorization/correction artifacts; call the same four-input resolver contract. Do not register a normal user command, skill step, runtime source, Context input, or projection hook.

- [ ] **Step 4: Prove runtime and projections are unchanged**

Run preview on fixtures with no correction, a valid correction, and conflicting correction artifacts. In every case compare commit, correction, response, event, SQLite, and projection snapshots; require unchanged bytes/rows and unchanged normal runtime source output.
Expected: PASS.

- [ ] **Step 5: Commit staged inspection boundary**

Commit with message `feat: add read-only canon correction preview`.

## Task 7: Lock Phase 9 handoff and acceptance binding

**Files:** Update Phase 8 spec/plan only if implementation clarifies a contract; create `test_phase8_acceptance_template.py`; add final H2 acceptance record only after H1 independent review.

**Interfaces:**
- Phase 9 integration consumes `EffectiveHistoryResult`; it does not parse correction artifacts itself.
- Acceptance template has identity and command slots but no results or implementation SHA filled into H1.

- [ ] **Step 1: Add failing handoff and acceptance-template tests**

Test the required resolver fields and deterministic contract consumed by a Phase 9 contract fixture. Test that H1 acceptance template is result-free and cannot claim its own tested commit SHA; test-fixture authorization must be labeled test-only and never described as real project/user human-approval evidence in H1, H2, or acceptance summaries.

- [ ] **Step 2: Run template and handoff tests to confirm failure**

Run: `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/tests/architecture/test_phase8_acceptance_template.py .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py -q -k 'handoff or acceptance'`
Expected: FAIL until the handoff fixture and result-free acceptance contract are implemented.

- [ ] **Step 3: Add the acceptance template and handoff contract**

Record commands and required evidence in the template, leaving result fields empty. Name H1 as the tested implementation only after committing H1 and executing its suite; create a review-approved, record-only H2 that binds the exact H1 SHA/tree. Do not edit acceptance results back into H1.

- [ ] **Step 4: Run complete Phase 8 acceptance suite**

Run all correction schema/store/resolver/preview tests, existing chapter commit/event/rebuild/runtime/context tests, architecture activation guards, and `git diff --check`. Do not run or add Phase 9 projection activation tests as if activation shipped.
Expected: PASS; existing runtime outputs stay unchanged.

- [ ] **Step 5: Verify exclusions and result binding**

Compare H1 against baseline; require no `.claude/plugins/zhanghui/6.4.0/**` paths and no production runtime wiring. Verify the separate H2 tree differs from H1 only in the acceptance record and names `tested_implementation_head` exactly.

- [ ] **Step 6: Commit the acceptance template in H1**

Commit with message `test: add Phase 8 acceptance binding template`. After independent H1 review, create a separate result-only H2 commit according to project acceptance practice.

## Implementation acceptance checklist

- [ ] All 21 test categories in the design's Section 13 pass.
- [ ] Accepted base commit bytes never change.
- [ ] No runtime, projection, rebuild, or user-workflow activation exists in Phase 8.
- [ ] Phase 9 consumes only the canonical resolver output.
- [ ] `.claude/plugins/zhanghui/6.4.0/**` is unchanged.
- [ ] H1/H2 acceptance identity is non-self-referential.
