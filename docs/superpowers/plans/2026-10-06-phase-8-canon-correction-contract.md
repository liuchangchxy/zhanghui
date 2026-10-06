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

**Goal:** Add immutable, human-authorized Canon correction artifacts and a deterministic staged effective-history resolver without changing old accepted commits or activating corrections in normal runtime.

**Architecture:** Keep `story-system/v1` chapter commits immutable and add a separately versioned `canon-correction/v1` append-only chain. Validate correction identity, authorization, lineage, and materialized operations, then expose one pure resolver result through read-only staged APIs. Normal runtime and projections continue to consume existing accepted commits until Phase 9.

**Tech Stack:** Existing Python/Pydantic/pytest stack, JSON artifacts, `hashlib.sha256`, existing durable commit canonicalizer/validator, existing gate human-response evidence, atomic file and lock utilities.

**Spec:** `docs/superpowers/specs/2026-10-06-phase-8-canon-correction-contract-design.md`

## Global Constraints

- Baseline: `2b31bfa7bb58e72d3ef86bc582821f16aa486f9b`.
- Never rewrite or delete accepted chapter commit bytes or correction artifacts.
- Base identity uses `durable_projection.canonical_commit_json()` after accepted-commit validation.
- One linear correction chain per exact chapter and base digest. Normal concurrent appends serialize to one append plus `STALE_PARENT`; pre-existing sibling files fail resolution and are not repaired in Phase 8.
- Correction follows an immutable request → human authorization → final correction sequence, with exact request and authorization digest binding.
- Phase 8 APIs are staged/internal and read-only for preview; do not connect normal runtime, write/query/context, ChapterCommitService, event/projection writers, or rebuild.
- Keep Phase 8 production paths free of any `6.4.0/**` change and no package major-version change.
- Do not implement Phase 9 rebuild, migration, recovery, or activation.

## Review Focus

- Canonical digest drift: ignored `projection_status` and JSON formatting must not change base identity; substantive accepted content changes must.
- Authorization scope drift: approval of one request digest must never authorize different correction content.
- Partial materialization: changed-path declarations and digests must exactly describe AMEND's complete result.
- Filesystem races: under the chapter lock one concurrent append succeeds and the stale request writes nothing; pre-existing sibling files are a separate resolver conflict case.
- Hidden activation: no ordinary write/query/context/projection caller may consume correction output in this phase.

---

## File map

| File | Responsibility |
|---|---|
| Create `.claude/plugins/zhanghui/scripts/data_modules/canon_correction_schema.py` | Pydantic models, strict operation-specific shape validation, canonical correction serialization and digests. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/canon_correction_store.py` | Append-only chapter correction artifact IO, locking, idempotent retry, and conflict-safe create. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/canon_correction_resolver.py` | Pure authorization/lineage validation and deterministic effective-history result. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/canon_correction_preview.py` | Read-only loading and preview/inspection API; no regular workflow or runtime wiring. |
| Create `.claude/plugins/zhanghui/docs/canon-correction.schema.json` | Published `canon-correction/v1` artifact schema. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_schema.py` | Schema, canonical identity, and immutability contract tests. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py` | Append, retries, stale parents, races, and no-overwrite tests. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py` | Operations, lineage, authorization, deterministic output, and failure diagnostics. |
| Create `.claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_preview.py` | Read-only preview and no-runtime-activation tests. |
| Create `.claude/plugins/zhanghui/scripts/tests/architecture/test_phase8_acceptance_template.py` | Phase 8 acceptance binding shape; keep the H1 template result-free. |
| Create `docs/superpowers/acceptance/2026-10-06-phase-8-final-acceptance.md` only after H1 review | Separate H2 result record binding results to tested H1; never mutate implementation H1 to claim its own tested SHA. |

All paths above are Phase 8 future implementation scope. The current design task creates none of these implementation files.

## Task 1: Freeze correction schema and canonical identities

**Files:** Create `canon_correction_schema.py`, `canon-correction.schema.json`, `tests/test_canon_correction_schema.py`; reuse `durable_projection.canonical_commit_json()`.

**Interfaces:**
- `canonical_correction_json(artifact: dict) -> str`: deterministic sorted-key compact UTF-8 JSON; rejects non-JSON/non-finite values.
- `correction_digest(artifact: dict) -> str`: SHA-256 of that canonical serialization.
- `base_commit_digest(commit: dict) -> str`: first validates a durable accepted commit, then hashes existing `canonical_commit_json(commit)`.
- `effective_content_digest(status: Literal["accepted", "retracted"], extraction: dict | None) -> str`: hashes the canonical status/content envelope from the spec.
- `CorrectionArtifact` validates common fields, operation, and operation-specific payload shape.

- [ ] **Step 1: Write failing schema and identity tests**

Add tests for valid/invalid schema version, required target/lineage/provenance/authorization fields, positive chapter, safe correction ID, and operation-specific `effective_extraction_result` and `changed_paths`. Add digest vectors proving key-order/whitespace independence, projection-status exclusion for base commits, and digest change for a substantive canonical field change.

- [ ] **Step 2: Run tests to confirm they fail for missing contract**

Run: `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_schema.py -q`
Expected: FAIL because the correction model and helpers do not exist.

- [ ] **Step 3: Implement only schema and digest primitives**

Use `read_validated_chapter_commit()` / `canonical_commit_json()` from `durable_projection.py`; reject non-accepted status before hashing. Keep canonical corrections on a separate schema version and do not change chapter commit models.

- [ ] **Step 4: Run schema tests and existing commit validation tests**

Run the focused test above, then `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py -q`.
Expected: both PASS; old commit schema and behavior remain unchanged.

- [ ] **Step 5: Commit schema boundary**

Commit only schema/helper/tests/docs-schema changes with message `feat: define canon correction artifact schema`.

## Task 2: Implement append-only artifact storage and retry behavior

**Files:** Create `canon_correction_store.py`, `tests/test_canon_correction_store.py`; use `StoryContractPaths` adjacency, existing `FileLock` and atomic-write patterns.

**Interfaces:**
- `correction_dir(root: Path, chapter: int, base_sha256: str) -> Path` resolves `.story-system/corrections/chapter_NNN/<base_sha256>/`, keeping same-chapter, different-base targets physically distinct.
- `append_correction(root: Path, artifact: CorrectionArtifact, *, authorization_evidence: Mapping) -> StoredCorrection` validates target/authorization and current parent under a per-chapter lock, then atomically creates one artifact.
- `list_corrections(root: Path, chapter: int, base_sha256: str) -> list[dict]` reads artifacts without mutation in deterministic ID order (resolver order is independent of this listing order).

- [ ] **Step 1: Write failing append contract tests**

Cover accepted-base required, rejected/missing base refusal, create immutable path, unchanged base commit bytes, exact retry returns same artifact, same ID/different canonical body rejection, malformed/unauthorized artifact leaves no file, and path traversal IDs are rejected.

- [ ] **Step 2: Run tests to confirm they fail**

Run: `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_store.py -q`
Expected: FAIL because the store is not implemented.

- [ ] **Step 3: Implement atomic append under chapter lock**

Before acquiring or while holding the chapter lock, validate the immutable accepted base and artifact structure. Under lock, load and validate existing chain, compare the named parent with current unique tip, then use create-if-absent semantics. If the path exists, compare canonical artifact digests: exact match is idempotent; mismatch is rejected without rewriting bytes. Do not call generic overwrite-capable JSON write helpers.

- [ ] **Step 4: Test concurrent stale-parent behavior and pre-existing sibling files separately**

Add a controlled concurrent API test where two requests target one parent. Under the per-chapter lock, one append succeeds and the other returns `STALE_PARENT` without writing an artifact. Separately seed two pre-existing immutable sibling files (representing corruption, import, old/broken storage, or API bypass) and assert resolution returns `LINEAGE_SIBLING_CONFLICT`, `ok=false`, and no effective result while preserving both files byte-for-byte. Also assert ordinary `append_correction()` refuses the conflicted chain. Phase 8 has no sibling repair protocol.

- [ ] **Step 5: Run store and file-integrity tests**

Run the store test module and the existing `test_gate_decision_store.py` module.
Expected: PASS; correction storage does not mutate gate evidence or chapter commits.

- [ ] **Step 6: Commit append-only store**

Commit store and focused tests with message `feat: add append-only canon correction store`.

## Task 3: Implement exact request-to-human-authorization binding and proposal-only boundaries

**Files:** Extend `canon_correction_schema.py`, `canon_correction_store.py`, `tests/test_canon_correction_store.py`, and `tests/test_canon_correction_resolver.py`; add durable request and authorization artifact schemas/storage as needed within the correction-specific authority boundary.

**Interfaces:**
- `canon-correction-request/v1` records request ID, chapter, exact accepted base digest, parent revision/content digest, operation, full proposed effective content/digest, AMEND changed paths, proposer provenance, and reason. Its canonical digest is `request_sha256`.
- `canon-correction-authorization/v1` records authorization ID, request ID and exact `request_sha256`, `APPROVE`/`REJECT`, human actor reference, and durable identity/provenance. Its canonical digest is `authorization_sha256`.
- `validate_authorization(request, authorization) -> None` verifies the exact request digest, durable human provenance, and explicit choice. Only `APPROVE` permits final append.
- `validate_final_correction(request, authorization, artifact) -> None` verifies that final operation/content/changed paths match the approved request exactly and binds both request and authorization digests.
- Authorization failure raises typed validation error before correction file creation. GateDecisionStore responses may be cited only as supplementary provenance; they are not correction authority.

- [ ] **Step 1: Add failing authorization tests**

Test missing request/authorization, wrong request digest, `REJECT`, invalid durable human provenance, authorization bound to another base/parent/operation/proposed content, changed final content after approval, and a correct exact-scope approval. Assert rejection leaves directory and artifacts unchanged.

- [ ] **Step 2: Run authorization tests to confirm they fail**

Run: `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py -q -k authorization`
Expected: FAIL because correction authorization validation does not exist.

- [ ] **Step 3: Implement correction-specific durable request and authorization artifacts**

Persist immutable `canon-correction-request/v1` and `canon-correction-authorization/v1` records under correction-specific storage. Compute canonical digests and validate exact request binding before final append. Do not extend GateDecision, gate finding persistence, or `GateDecisionStore` for correction authorization; existing gate responses may be optional supplementary provenance only.

- [ ] **Step 4: Assert proposal producers have no append authority**

Add tests proving `AmendProposalTrigger`, consistency findings, reviewer findings, extraction output, and projection repair output do not call the correction store or create correction artifacts. Keep these components proposal/finding-only.

- [ ] **Step 5: Run focused correction authorization tests**

Run the correction authorization selection above and correction storage/resolver suites.
Expected: PASS; ChapterCommit gate storage and human-response semantics remain untouched.

- [ ] **Step 6: Commit request and authorization boundary**

Commit with message `feat: bind canon corrections to exact human authorization`.

## Task 4: Build deterministic lineage validation

**Files:** Create `canon_correction_resolver.py`, extend `tests/test_canon_correction_resolver.py`.

**Interfaces:**
- `validate_lineage(accepted_commit: dict, artifacts: Sequence[dict], authorization_evidence: Mapping) -> ValidatedLineage`.
- `ValidatedLineage` contains immutable base digest, ordered edge artifacts, deterministic revision IDs, and diagnostics; invalid/conflicted lineage contains no chosen tip.

- [ ] **Step 1: Write failing graph tests**

Test base-only path, two-step chain, shuffled input determinism, missing parent, wrong chapter, wrong base digest, stale parent content hash, duplicate ID/same content, duplicate ID/different content, sibling children, disconnected edge, and cycle.

- [ ] **Step 2: Run graph tests to confirm failure**

Run: `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py -q -k lineage`
Expected: FAIL because no lineage validator exists.

- [ ] **Step 3: Implement graph validation without winner selection**

Build parent-to-children adjacency after validating every artifact. Enforce one distinct child per parent and the operation transition rules: AMEND/RETRACT require accepted parent; SUPERSEDE may restore retracted parent; RETRACT cannot follow RETRACT. Walk only the unique base-to-tip chain after proving all artifacts are connected and valid. Sort diagnostics and applied IDs for deterministic output; sorting must never resolve a sibling conflict.

- [ ] **Step 4: Run graph tests with permutations**

Repeat the same fixture with reversed and randomized artifact input order; require byte-identical diagnostics and same ordered chain.
Expected: PASS.

- [ ] **Step 5: Commit lineage validator**

Commit with message `feat: validate linear canon correction lineage`.

## Task 5: Resolve AMEND, RETRACT, and SUPERSEDE

**Files:** Extend `canon_correction_resolver.py`, `tests/test_canon_correction_resolver.py`; use current `ExtractionResult` validation.

**Interfaces:**
- `resolve_effective_history(accepted_commit, correction_artifacts, authorization_evidence) -> EffectiveHistoryResult` returns the exact spec fields: `ok`, `chapter`, `base_commit_sha256`, `effective_revision_id`, `effective_status`, `effective_extraction_result`, `applied_correction_ids`, `effective_content_sha256`, `diagnostics`.

- [ ] **Step 1: Write operation tests before implementation**

Add zero-correction backward-compatibility; deterministic AMEND; exhaustive changed-path/before-after digest validation; AMEND rejects changes to every canonical top-level extraction field; RETRACT output and preserved source artifacts; SUPERSEDE full replacement; correction-of-correction; and invalid result never exposes clean effective Canon.

- [ ] **Step 2: Confirm the operation tests fail**

Run: `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_resolver.py -q -k 'amend or retract or supersede or backward'`
Expected: FAIL because resolution operations are not implemented.

- [ ] **Step 3: Implement pure resolver application**

First validate accepted base, all artifacts, authorization, and the complete unique lineage. Then apply each materialized operation in order. AMEND verifies the recomputed structural diff and preserves at least one canonical top-level extraction field; RETRACT sets status and extraction to retracted/null; SUPERSEDE validates and replaces the whole extraction. Never mutate input dictionaries.

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
- `preview_chapter_corrections(project_root: Path, chapter: int) -> EffectiveHistoryResult` reads validated base, correction artifacts, and referenced authorization evidence, then calls the canonical resolver.
- No function in this task writes a correction, gate response, commit, event, or projection file.

- [ ] **Step 1: Write failing read-only and non-activation tests**

Snapshot all source and projection bytes; run preview; assert exact bytes unchanged. Assert normal `load_runtime_sources()` returns the same snapshot before and after preview. Add a static dependency guard proving no correction module is imported by normal runtime, Context assembly, query/write entrypoints, ChapterCommitService, EventLogStore, projection writers, or projection rebuild.

- [ ] **Step 2: Confirm the guard tests fail before preview exists**

Run: `PYTHONPATH=.claude/plugins/zhanghui/scripts pytest .claude/plugins/zhanghui/scripts/data_modules/tests/test_canon_correction_preview.py -q`
Expected: FAIL because the staged preview and inactive-path guard are absent.

- [ ] **Step 3: Implement read-only discovery and preview**

Load only the specified chapter/base chain and authorization references; call `resolve_effective_history`. Do not register a normal user command, skill step, runtime source, Context input, or projection hook.

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

Test the required resolver fields and deterministic contract consumed by a Phase 9 contract fixture. Test that H1 acceptance template is result-free and cannot claim its own tested commit SHA.

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

- [ ] All 20 test categories in the design's Section 13 pass.
- [ ] Accepted base commit bytes never change.
- [ ] No runtime, projection, rebuild, or user-workflow activation exists in Phase 8.
- [ ] Phase 9 consumes only the canonical resolver output.
- [ ] `.claude/plugins/zhanghui/6.4.0/**` is unchanged.
- [ ] H1/H2 acceptance identity is non-self-referential.
