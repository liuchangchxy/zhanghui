# Phase 8 — Canon Correction, Lineage & Effective History Contract

Status: design for independent review; no implementation included.
Baseline: `origin/main` at `2b31bfa7bb58e72d3ef86bc582821f16aa486f9b`.
Phase 7 status: CLOSED; Issue #1 remains OPEN.

## 1. Purpose and verified starting point

Phase 8 defines how a human-authorized correction can coexist with immutable chapter commits. It adds an append-only correction history and one deterministic resolver contract. It does not make corrections part of normal runtime Canon in this phase.

The final Phase 7 merge baseline was checked before this design was written:

- `ChapterCommitService.persist_commit()` rejects `overwrite`, does not provide append semantics, and uses `skip` only to reuse the existing chapter artifact. `apply_projections()` persists the commit before invoking projection writers.
- `AmendProposalTrigger` creates `AmendProposal` records from selected accepted events. The resulting records are persisted as pending rows in `override_contracts`; this is a workflow/planning proposal, not a Canon amendment or lineage record.
- Event JSON and SQLite `story_events` are projections. `EventLogStore.write_events()` requires a matching durable accepted commit. `projection_rebuild.py` validates durable commits and already rebuilds events and other read models from them.
- `story_runtime_sources.py` finds ordinary commits by searching backward by chapter and accepted status. It has no amendment, retraction, supersede, or effective-revision handling.

No code-level contradiction to the reviewed starting facts was found. Phase 8 preserves them. In particular, historical accepted commit bytes remain immutable.

## 2. Goals

1. Specify a versioned correction artifact independent of `story-system/v1` chapter commits.
2. Bind each correction to one exact immutable accepted base commit and one exact parent effective revision.
3. Define a linear, deterministic per-chapter correction chain with explicit conflict failure.
4. Define complete materialized semantics for AMEND, RETRACT, and SUPERSEDE.
5. Require explicit human authorization and preserve actor, authorization, reason, and evidence provenance.
6. Provide a pure effective-history resolver and read-only validation/preview contract.
7. Keep Phase 8 staged: no normal write/query/context/projection consumer applies correction output.
8. Hand Phase 9 one canonical resolver output instead of requiring it to reinterpret correction artifacts.

## 3. Non-goals and safety boundary

Phase 8 does not implement correction-aware projections, event mirror changes, recovery/full rebuild, historical bulk migration, legacy-to-Story-System migration, Intent/Craft reconciliation, CHANGES retirement, promise/open-loop/foreshadow model consolidation, package major-version changes, amendments to old commit files, or Phase 9/10 activation.

Phase 8 must not connect effective corrections to normal writing, query, context, runtime source, or projection paths. Resolver and preview APIs are staged/internal and read-only. No normal skill, agent, CLI workflow, or projection writer may invoke them as live Canon. Event JSON, `story_events`, state, index, summary, memory, and vector stores remain derived from the current durable accepted commits until Phase 9.

## 4. Versioned artifact and storage contract

Use schema identifier `canon-correction/v1`. Do not add correction fields to old `story-system/v1` commits or reinterpret their historical meaning.

Suggested append-only path:

```text
.story-system/corrections/chapter_NNN/<base_commit_sha256>/<correction_id>.correction.json
```

One artifact is one immutable edge in a correction chain. The canonical artifact contains:

- `schema_version`: exactly `canon-correction/v1`.
- `correction_id`: path-safe stable identifier, unique within the exact chapter/base target.
- `chapter`: positive chapter number.
- `base_commit_sha256`: exact digest of the immutable accepted commit's canonical identity serialization.
- `parent_revision_id` and `parent_effective_content_sha256`: exact parent edge and materialized parent content identity.
- `operation`: `AMEND`, `RETRACT`, or `SUPERSEDE`.
- `effective_extraction_result`: complete validated `ExtractionResult` for AMEND and SUPERSEDE; null for RETRACT.
- `changed_paths`: required for AMEND; an exhaustive sorted set of changed JSON paths relative to the parent ExtractionResult. Each path carries before/after SHA-256 digests. It is empty for RETRACT and SUPERSEDE.
- `request_sha256`: digest of the exact approved `canon-correction-request/v1` artifact.
- `authorization_ref` and `authorization_sha256`: identity and digest of the exact `canon-correction-authorization/v1` artifact approving that request.
- `provenance`: correction-specific source/evidence references and the producing actor/tool; never copy the base commit's review, reconciliation, or extraction provenance as if it described the corrected material.
- `actor_ref` and `reason`: authoring attribution and explanation. The author need not be the human authorizer.

The final correction's operation, proposed effective content/digest, and `changed_paths` must exactly match the approved request. The request and authorization artifacts are immutable durable records and are retained with the correction history.

Correction artifacts are Canon history/audit lineage, not replacement commit files. Creation is append-only and collision-safe. No API edits or deletes a committed artifact.

## 5. Canonical identity and hashing

Use the existing `durable_projection.canonical_commit_json()` implementation for the base identity. It sorts keys, uses compact JSON separators and UTF-8-compatible JSON, and excludes mutable `projection_status`. Compute:

```text
base_commit_sha256 = SHA256(UTF8(canonical_commit_json(validated_commit)))
```

First validate the commit using the existing durable commit validator and require `meta.status == "accepted"`. Do not use mtime, path timestamps, or formatted file bytes as identity. A same-chapter commit with another canonical digest is a different target; corrections for it cannot attach to this chain.

Canonicalize correction artifacts independently with sorted keys, compact separators, UTF-8, and no non-finite JSON numbers. `correction_artifact_sha256` is SHA-256 of that serialization. The effective content digest is SHA-256 of canonical JSON for the pair:

```json
{"effective_status":"accepted|retracted","extraction_result":{...}|null}
```

This makes a retracted revision's content identity deterministic as well. `parent_effective_content_sha256` must equal the resolver-computed digest for the exact named parent.

Revision IDs are deterministic and contain no timestamp choice: the base revision is `base:<base_commit_sha256>`; a correction revision is `correction:<base_commit_sha256>:<correction_id>`. The correction artifact digest is calculated separately for content identity and idempotency. Timestamps may be retained as audit metadata but never order or select lineage.

## 6. Per-chapter linear lineage

Each correction always names the same immutable root base commit, even when it is based on a previous correction. The first edge names the base revision. Later edges name the immediately preceding correction revision and its effective-content digest.

The resolver constructs a graph from the base and all candidate correction artifacts for that chapter and exact base digest, then validates it before producing an effective result:

- Every correction has the matching chapter and root base digest.
- Every parent exists and is either that base or a valid correction revision in the same root chain.
- The parent content digest matches exactly.
- A correction ID has one canonical artifact identity. Identical retries are the same edge; different content under the same ID is an error.
- There is at most one distinct child of any parent. Two already-existing sibling files are a lineage conflict; never choose by file order, creation time, or last-write-wins.
- Cycles, disconnected edges, missing parents, stale parents, malformed artifacts, and unknown schema versions fail resolution.
- The valid chain is the unique path from base to its sole tip. It is applied in parent order, not directory or timestamp order.

On any conflict or invalid edge, return diagnostics and an unresolved result; do not expose a clean effective Canon while silently ignoring the problem. Phase 8 provides no sibling repair. Ordinary append refuses a conflicted chain. A future administrative conflict-repair/merge protocol must be designed separately; artifacts are not deleted, overwritten, or bypassed with a single-parent correction.

## 7. Operation semantics

### 7.1 AMEND

AMEND corrects part of the chapter's canonical extraction while retaining the rest of the effective parent result. The artifact stores the complete materialized resulting `ExtractionResult`; the resolver does not replay JSON Patch operations or unstable list indices.

The validator recomputes a structural diff from the parent result. Its changed path set and each before/after digest must exactly match `changed_paths`. At least one canonical top-level extraction field remains unchanged, and no unlisted path changes. If the interpretation requires replacing every canonical extraction field, use SUPERSEDE. The materialized result must validate under the current extraction-result schema. Each before/after digest is SHA-256 over canonical JSON for the addressed value; additions and removals use an explicit canonical absent-value marker so they cannot collide with JSON null.

The correction has its own provenance and authorization. The resolver must not represent the original commit's review, reconciliation, or extraction provenance as evidence that the amended result passed those original checks. This Phase 8 result is staged and is not a newly gate-approved CHAPTER_COMMIT.

### 7.2 RETRACT

RETRACT removes the entire chapter's contribution from effective Canon. It carries no replacement extraction result and has no partial-event mode. The base commit and all prior correction artifacts remain unchanged and inspectable. The resulting revision has `effective_status = "retracted"` and `effective_extraction_result = null`.

To withdraw or correct only selected facts while retaining the chapter, use AMEND with a complete materialized ExtractionResult. RETRACT is never implemented by deleting commit/event files or editing a projection. AMEND may only parent an `accepted` revision. SUPERSEDE may parent either `accepted` or `retracted` and is the only operation that restores a retracted chapter; RETRACT may parent only an `accepted` revision. RETRACT cannot parent another RETRACT.

### 7.3 SUPERSEDE

SUPERSEDE replaces the chapter's complete effective canonical interpretation with a complete validated `ExtractionResult`. It is appropriate when the prior interpretation as a whole is invalid. It records a new provenance and authorization while preserving the base commit and every earlier correction in lineage. It does not erase history or silently make the old commit's provenance apply to the replacement.

## 8. Rejected commits and proposal-only components

A rejected commit is never a correction target. Correction validation requires a durable, schema-valid `accepted` base. Promoting a rejected attempt would bypass ChapterCommitService gate authority. If rejected-commit retry behavior needs work, record a separate workflow finding; do not solve it through Canon correction.

Consistency, reviewer, extraction, projection recovery, and `AmendProposalTrigger` can produce proposals or findings only. None can create a durable semantic correction. The existing `AmendProposal` name remains reserved for its current workflow/planning proposal meaning.

## 9. Correction request and human authorization contract

Correction authorization is an independent post-acceptance protocol. `GateDecisionStore` and `gate-human-response/v1` belong to ChapterCommit gate workflow; neither is the authority for changing accepted Canon. Existing gate responses may be cited as provenance/source evidence, but cannot alone authorize a correction. Do not extend GateDecision or finding persistence for correction authorization, and do not use `GateSeverityPolicy` to decide it.

### 9.1 `canon-correction-request/v1`

A request means “propose this exact change”; it does not authorize Canon mutation. It is immutable and contains at least:

- `request_id`, `chapter`, `base_commit_sha256`, `parent_revision_id`, and `parent_effective_content_sha256`.
- `operation` and the complete proposed effective content (null for RETRACT) plus its canonical digest.
- `changed_paths` for AMEND, following the final correction contract.
- `proposer_provenance` and non-empty `reason`.

The canonical request digest, `request_sha256`, is SHA-256 over its canonical JSON serialization. A human, reviewer, consistency process, or other proposer may create a request; proposal authorship has no mutation authority.

### 9.2 `canon-correction-authorization/v1`

This is a separate immutable durable artifact recording a human decision on one exact request. It contains at least `authorization_id`, `request_id`, `request_sha256`, `choice` (`APPROVE` or `REJECT`), `actor_ref`, and durable identity/provenance for the human decision. Its own canonical digest is `authorization_sha256`. Only `APPROVE` authorizes a final correction; `REJECT` never does. The authorization must identify the exact request digest, not merely a chapter or generic proposal.

### 9.3 Exact binding of final correction

`canon-correction/v1` must bind both `request_sha256` and the exact authorization artifact identity/digest. Before append, validate that the authorization approves that request and that every final semantic field is identical to the approved request. An authorization for request A cannot authorize different content B. Missing, rejected, mismatched, or unverifiable authorization fails before filesystem side effects. Automated agents and repair services cannot be the authorizing actor.

Proposal, decision, and final append are separate stages. A proposal can be rejected or superseded without altering Canon. Gate human responses may be included only as supplementary provenance and never as the sole correction authority.

## 10. Append, retry, concurrency, and failure behavior

The append contract is:

- Same correction ID plus byte-equivalent canonical artifact: idempotent retry; return the existing artifact identity without another edge.
- Same correction ID plus different canonical content: reject and preserve the original bytes.
- Parent digest differing from the current unique chain tip: reject as stale; caller must resolve again and obtain fresh authorization.
- Concurrent API appends targeting the same parent: serialize by per-chapter lock, re-scan the unique tip, let the first valid append create one artifact, and return `STALE_PARENT` to the later request; the stale request writes no artifact. Normal API concurrency must not create siblings.
- Two sibling files already present when resolving: preserve both, return `LINEAGE_SIBLING_CONFLICT` with `ok=false` and no effective Canon, and do not select a winner. Ordinary `append_correction()` refuses to write to this conflicted chain. This pre-existing state can result only from manual corruption, external/imported files, an old/broken implementation, or bypass of the storage API. Phase 8 does not repair it.
- Missing base/parent, rejected base, invalid authorization, malformed artifact, unsafe ID/path, or cycle: reject before writes when detectable; invalid pre-existing artifacts make resolution fail with diagnostics.
- Serialize per-chapter append/lineage checks with a lock and use atomic create semantics that cannot replace an existing artifact. Re-scan and verify the chain under the lock before final append to close races.

A partial failed append must leave either no artifact or one complete validated immutable artifact. Retrying a complete existing artifact is idempotent; a different body under that ID never repairs or replaces it.

## 11. Effective-history resolver API

Provide one pure resolver boundary in the Phase 8 implementation, conceptually:

```python
resolve_effective_history(
    accepted_commit: dict[str, Any],
    correction_artifacts: Sequence[dict[str, Any]],
    authorization_evidence: Mapping[str, dict[str, Any]],
) -> EffectiveHistoryResult
```

Inputs are already discovered/read; the resolver performs schema, identity, authorization, graph, digest, and operation validation without filesystem writes. Store and preview layers may load data but must not mutate commits, corrections, events, projections, or workflow evidence during resolution.

The result contains at least:

- `ok` and `diagnostics` (structured error code, correction/revision reference, and actionable conflict details).
- `chapter` and `base_commit_sha256`.
- `effective_revision_id` (null on unresolved conflict).
- `effective_status`: `accepted` or `retracted` only on a clean resolution.
- `effective_extraction_result`: complete result or null for retraction; null when unresolved.
- `applied_correction_ids` in exact lineage order.
- `effective_content_sha256` on clean results.

With zero corrections, the result equals the validated accepted base extraction and is backward-compatible. Invalid or ambiguous inputs never return a result that appears clean. Output ordering and bytes are deterministic independent of directory order, file iteration, and timestamps.

Expose this only through staged/internal libraries and read-only validate/preview/inspect functions. Do not wire it to `story_runtime_sources`, Context, query, write flows, ChapterCommitService, EventLogStore, projection writers, or `projection_rebuild.py` in Phase 8.

## 12. Phase 9 handoff

Phase 9 consumes the `EffectiveHistoryResult` contract above as its single input for chapter-effective Canon. It must not implement another correction parser or choose lineage independently.

Phase 9 owns correction-aware projection rebuild, event JSON and SQLite mirror rebuild, runtime source integration, recovery, full historical rebuild, existing-project migration, and activation of a user-visible semantic correction workflow. Before activation it must prevent mixed output in which the resolver says corrected history while state/index/events/memory/vector still represent the old history.

## 13. Implementation acceptance coverage

The Phase 8 plan must add tests for all of the following:

1. Accepted base commit bytes remain byte-for-byte immutable after correction append and resolution.
2. Exact canonical base SHA binding; same chapter with a different base digest is a distinct target and cannot attach.
3. Zero-correction output is backward-compatible with the current accepted commit.
4. AMEND resolves deterministically from complete materialized extraction.
5. RETRACT preserves base/correction history but yields no effective chapter contribution.
6. SUPERSEDE deterministically returns the complete replacement extraction.
7. Multi-step base → correction A → correction B resolves in exact chain order.
8. Identical duplicate retry is idempotent.
9. Same correction ID with different content is rejected without changing stored bytes.
10. Stale parent digest is rejected.
11. Sibling children produce explicit conflict, never last-write-wins.
12. Cycles and nonexistent base/parent are rejected.
13. Rejected base cannot be corrected.
14. Missing, mismatched, or unscoped human authorization is rejected.
15. Consistency, reviewer, extraction, and projection repair can propose/find but cannot append semantic correction.
16. Normal runtime source and user workflows remain unchanged/unactivated in Phase 8.
17. Resolve/preview does not mutate accepted commit, event JSON, `story_events`, or projection files.
18. Phase 9 consumes one canonical resolver result contract.
19. `.claude/plugins/zhanghui/6.4.0/**` remains unchanged.
20. Acceptance binding avoids self-reference: implementation H1 is tested first, and any result-filled H2 record binds explicitly to H1 in a separate record-only commit.
