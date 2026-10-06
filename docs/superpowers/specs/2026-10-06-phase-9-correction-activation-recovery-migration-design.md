# Phase 9 — Human-Confirmed Correction Activation, Projection Recovery & Existing-Project Migration

**Status:** Design ready for review
**Baseline:** `origin/main` at `63f3cef58090f399e6e8b740e3efebe6e5f3e459`
**Scope:** Design and implementation plan only. No production implementation is authorized by this document.

## 1. Goal and invariants

Phase 8 introduced immutable, staged Canon correction request, authorization, and correction artifacts. Phase 9 defines how a correction can become the runtime's effective chapter history without rewriting an accepted chapter commit or allowing consumers to disagree about which history is live.

The production boundary is:

```text
validated accepted commits + immutable correction artifacts
        + durable, request-bound human workflow decision
        -> candidate effective-history snapshot
        -> staged, validated Canon projection generation
        -> one immutable, atomically published activation record
        -> active runtime pinned to that semantic activation and generation
```

Required invariants:

1. `.story-system/commits/chapter_NNN.commit.json` remains immutable accepted evidence. Correction artifacts are append-only. Neither is rewritten or deleted to activate, recover, or roll back a correction.
2. Proposal/request staging, approved/final correction staging, candidate resolution, semantic activation, and projection generation are distinct states. A staged artifact is never implicitly live Canon.
3. An immutable publication record freezes the exact dependency closure for one active semantic snapshot and its complete Canon projection generation. Runtime pins that record and its generation once per operation; it never scans newer candidate artifacts to choose active Canon.
4. Every effective chapter record retains its original base-commit digest and separately names its effective revision and effective-content digest. Writers validate both the base provenance and the resolution proof; correction support must not weaken durable-commit validation.
5. An unverified, ambiguous, corrupt, stale, or unavailable candidate blocks activation of that candidate, but does not poison a different verified active snapshot. If evidence explicitly referenced by the active publication record is missing or hash-mismatched, active Canon reads fail closed; they never fall back to base commits or an older semantic activation.
6. Projection outputs are replaceable derived data. Rebuilding or replacing a generation for recovery must preserve the exact active semantic snapshot. A failed build never changes Canon history or publishes a partial generation as healthy.
7. Immutable generations contain only Canon-owned projection slices. Current Intent/Craft/Workflow/compatibility owners write mutable overlays/sidecars and runtime composes those owner-scoped values with a pinned Canon generation.
8. Migration preserves all source data until explicit, reviewed resolution. It never infers Canon from Craft/planning data or chooses a sibling correction winner.

## 2. Verified current architecture (baseline audit)

### 2.1 Correction artifacts and current resolver

The canonical implementation is `.claude/plugins/zhanghui/scripts/data_modules/` (marketplace-selected plugin root: `.claude/plugins/zhanghui`). The nested `.claude/plugins/zhanghui/6.4.0/` tree is a historical snapshot and is excluded from this design's implementation paths.

Phase 8 stores namespaces under `.story-system/corrections/chapter_NNN/<base-commit-sha256>/`, with separate `requests/`, `authorizations/`, and `corrections/` JSON artifacts. `canon_correction_schema.py` validates exact base/revision digests and AMEND, RETRACT, and SUPERSEDE shapes. `canon_correction_store.py` appends artifacts immutably and requires a typed `VerifiedCorrectionDecision` to append a semantic correction. `canon_correction_resolver.py` validates the full namespace and computes `EffectiveHistoryResult`; it rejects invalid/disconnected/cyclic/sibling lineages and invalid operation transitions. `canon_correction_preview.py` reads a chapter namespace and resolves a preview.

This resolver is currently a staged API only. No production runtime, context reader, projection writer, retry, replay, or rebuild calls it. Correction request persistence can use the resolver to validate staged lineage, but this does not activate an effective Canon source.

### 2.2 Human confirmation and threat model

Phase 9 uses a single-user workflow trust model. The current Local host has an interactive user-input UI available to the agent, but repository Python cannot verify that a durable record was created by that UI rather than supplied as ordinary input. This is an explicit limit, not a host-authentication capability.

- `GateDecisionStore.append_attempt` writes a validated GateDecision set and workflow status as immutable JSON. It proves the record was structurally accepted by that API and binds policy output to a stored attempt; it does not prove who supplied the inputs or who operated the host.
- `append_human_response` checks that an attempt is pending, the finding belongs to it, and non-empty `choice` and `actor_ref` are supplied. It persists those caller-supplied strings. It does not authenticate a person or bind a response to exact correction content.
- `ChapterCommitService.evaluate_after_human_response` delegates to that store, then reevaluates the normal write gate. This is gate workflow evidence, not correction semantic approval.
- A confirmation assembled from a UI answer, workflow event, provenance dictionary, `actor_ref="human"`, local JSON, CLI input, or caller mapping is not proof of authenticated identity. Under this phase's workflow model it is an auditable decision record whose consistency Python validates; it is not an unforgeable credential.
- `VerifiedCorrectionDecision` is a frozen in-process dataclass in `canon_correction_store.py`. Its constructor checks strings and status but establishes no identity. Phase 9 may minimally adapt the existing seam to consume a durable `CorrectionConfirmationRecord`; it must not treat either Python type as an authentication boundary or rewrite the Phase 8 artifact model unnecessarily.

**Task 0 finding retained:** the current host does not provide a credential that repository Python can verify as an unforgeable host-origin identity assertion. The interactive UI is usable for explicit human-mediated workflow confirmation. This finding selects the workflow trust model below and is not a Phase 9 closure blocker.

**In scope:** Phase 9 must prevent:

1. Semantic correction activation without explicit user confirmation.
2. Agent-inferred APPROVE.
3. Reuse of an old confirmation for another request.
4. Request/auth digest mismatch.
5. Stale parent or stale candidate activation.
6. APPROVE/REJECT conflicts.
7. Treating REJECT as APPROVE.
8. Changing correction content after confirmation without a new review.
9. Crash/retry causing duplicate or incorrect semantic activation.
10. Runtime treating staged corrections as live Canon.
11. Silent fallback after correction or active evidence corruption.
12. Ordinary writing, planning, review, or query flows accidentally triggering correction activation.

**Explicitly out of scope:** an agent with project-file write authority that deliberately forges approval records; a compromised Local host; OS/root attackers; malicious changes to production Python; and cryptographic real-world identity authentication. In this single-user local writing system, an attacker who can arbitrarily modify code and project data cannot be isolated by another local JSON record, dataclass or token. A future requirement to resist that attacker needs a separately designed external signer or authenticated service.

### 2.3 Base Canon and context reads

`durable_projection.py` validates `story-system/v1` chapter commits, chapter identity, status, GateDecision binding shape, and result schemas. `discover_validated_chapter_commits()` validates the complete commit directory before returning a sparse sorted set. `require_durable_commit_match()` requires a writer payload to canonically equal the on-disk commit after excluding mutable `projection_status`.

`context_provenance.load_commit_fact_items()` currently discovers accepted durable commits and assembles Canon context directly from each commit's extraction result. It does not read corrections. Other context and runtime builders consume state, index, summaries, memory, vectors, contracts, and retrieval through current project paths. Therefore adding correction lookup to only one context builder would create mixed authority.

### 2.4 Projection and recovery reads/writes

`ChapterCommitService` persists accepted chapter commits and runs `state`, `index`, `summary`, `memory`, and `vector` writers. Each writer currently calls `require_durable_commit_match`; `EventLogStore` also validates the original durable commit. The event router's rebuild manifest adds the `events` JSON/SQLite mirror and `intent_diagnostics`, for seven rebuild domains total:

| Domain | Current stored projection | Current incremental sensitivity |
|---|---|---|
| events | `.story-system/events/chapter_NNN.events.json`; `story_events` table in `.webnovel/index.db` | Chapter-scoped event content, plus shared SQLite mirror |
| state | `.webnovel/state.json` | Cumulative ordered application; earlier delta/retraction can change later state |
| index | chapters/scenes/appearances/state_changes tables in `.webnovel/index.db` | Chapter rows are scoped; state-change tables and shared DB require exact reconciliation |
| summary | `.webnovel/summaries/chNNNN.md` | Chapter-scoped |
| memory | `.webnovel/memory_scratchpad.json` | Lifecycle reconciliation and legacy overlays can depend on full history |
| vector | vector/BM25/doc-stat stores | Commit chunks can be chapter-derived; corpus statistics and referenced chunks are shared |
| intent diagnostics | `.story-system/projections/intent-diagnostics.json` | Reconciliation spans events across chapters |

`projections retry` rereads one raw commit and calls normal writers. Range replay repeats this for an explicit chapter interval; the state writer refuses out-of-order writes unless a controlled rebuild is active. `projections rebuild` validates all commits before reset, then destructively resets the above targets and replays sparse commits in order. It validates event JSON and SQLite rows, index rows, summaries, state chapter status, and intent diagnostics. It is not a staged multi-target transaction: after a reset or mid-replay failure, some outputs can be new and others absent/old. Projection status/log records writer outcomes, but current freshness identity is only a commit hash/status and does not include a correction tip or generation-wide set hash.

`EventLogStore` verifies an incoming event payload against the durable commit before writing the JSON event file and SQLite mirror. It does not validate that the existing JSON and SQLite copies agree on every normal read. `projection_log.jsonl` is operational evidence, not an activation authority.

### 2.5 Project and version rules

The source plugin manifest `.claude/plugins/zhanghui/.claude-plugin/plugin.json` and marketplace catalog `.claude-plugin/marketplace.json` both currently say `6.4.0`; marketplace selects `.claude/plugins/zhanghui`. Installed host version is external to the repository. Chapter commits use `story-system/v1`; several independent stores have their own schemas (for example `webnovel-projection-log/v1`, `webnovel-projections/v1`, and RAG schema `2`). The audited Story System files do not establish one project-wide migration/activation version marker. Phase 9 must add a project-data activation manifest/version that is independent from package/release versions and must not assume a package bump.

## 3. Chosen architecture and effective Canon boundary

### 3.1 Active snapshot and candidate snapshot are different APIs

Expose two explicitly different views. `read_active_snapshot()` reads the latest valid immutable activation record and validates only its frozen dependency closure. It does not enumerate newer, unreferenced proposal/candidate artifacts to decide what runtime should read. For an unactivated project with no activation history, the compatibility path exposes the validated base-only snapshot. Once an activation record exists, a missing, corrupt, or hash-mismatched record or active dependency is an integrity failure; it must never be interpreted as “no activation yet.”

`resolve_candidate(target_correction_id)` is used only by review, preflight, and activation. It discovers the complete sparse base set and the exact candidate correction namespace/lineage, delegates all semantic operations to `canon_correction_resolver.resolve_effective_history`, and returns diagnostics. It does not mutate or invalidate the active snapshot. A malformed/ambiguous correction artifact in the candidate's base namespace blocks activation because a competing branch cannot safely be excluded. New pending requests are proposals with no correction edge and do not change candidate effective history. A valid REJECTED request/confirmation is terminal proposal evidence, not a correction edge; it remains auditable and does not poison active history or future independent candidates. A final correction lacking a matching valid confirmation record is an unactivatable candidate, but does not affect active history. Siblings/conflicts block a candidate activation, not reads pinned to a different valid active record.

The active snapshot contains ordered sparse chapter entries and the exact activation record identity. The candidate snapshot contains the same effective chapter fields plus its candidate target and diagnostics. Both include base commit digest, effective status/content/revision, applied correction IDs, and deterministic `base_set_digest` and `effective_history_digest`. Only candidate resolution reads latest staging state. Only a successfully published activation record can make a candidate the new active semantic history.

Every activation record freezes, by exact ID and digest: the complete sparse base commit set; the ordered correction IDs and artifact hashes; the linked request, authorization, and confirmation record IDs/hashes for each correction; each chapter's effective revision/status/content digest; candidate lineage digest; effective history digest; and the projection generation manifest digest. The active reader reopens and hashes precisely these referenced files. Appending an unrelated request or candidate artifact cannot change a pinned active operation. Mutating/removing an artifact referenced by the active record makes active reads fail closed.

Only the existing resolver interprets AMEND/RETRACT/SUPERSEDE, parent, sibling, and lineage semantics. Consumers never parse correction artifacts or reimplement operations.

### 3.2 Effective projection input without forged commits

Introduce a typed `EffectiveProjectionInput` containing the unchanged validated base commit and its `EffectiveHistoryEntry`, plus active/candidate snapshot identity. `require_durable_commit_match` remains the base-integrity check; a second validator verifies that the effective entry's base digest, chapter, activation-record closure, applied correction chain, schema, extraction, status, and effective digest recompute exactly. Python dataclass/type construction is not an authentication boundary. Production Python validates the durable confirmation record's structure, canonical digests, bindings, freshness, lineage, decision consistency and activation invariants; it does not claim to prove who created that record.

Projection writers receive this typed input or a narrow projection payload derived from it. They never persist a modified base commit and never accept a bare corrected dictionary. This retains strict base validation while adding independently checked correction provenance.

### 3.3 Runtime consumption

All Canon-bearing runtime/context builders acquire and pin one `ActiveEffectiveHistorySnapshot` for the operation. Candidate resolution is not available through the runtime reader interface. Pending/rejected proposals, unactivated valid corrections, and candidate conflicts do not alter or invalidate a separately verified active snapshot. If the active record or one of its exact dependencies is missing/corrupt, Canon reads fail closed. Canon facts, recent chapter material, event retrieval, and correction-derived content use active effective entries. Planning/Craft/Workflow inputs remain on mutable owner paths and are composed by the ownership view described in §5.4; they are not promoted by the Canon facade. No per-consumer feature flag is used.

## 4. Human confirmation and staging protocol

**Task 0 decision:** retain the audit result that no unforgeable host-origin identity credential is verifiable by repository Python. Phase 9 adopts the explicit workflow trust model in §2.2; this does not disable activation or block Phase 9 closure. The current host's interactive user-input UI is the required confirmation step in the normal correction workflow. The resulting answer and record are ordinary application data, not authenticated identity evidence.

The normal correction workflow adapter (skill/agent orchestration) constructs and displays the challenge, invokes the current host's user-input UI, then passes the answer and challenge digest to Python to persist. Python does not invoke or authenticate the UI. The immutable `CorrectionConfirmationRecord` (or the smallest compatible extension of the Phase 8 decision seam) binds at least: `request_id`, `request_sha256`, `authorization_id`, `authorization_sha256`, operation, target chapter and base digest, parent revision, proposed/effective content digest, AMEND changed paths, displayed challenge digest, `APPROVE|REJECT`, a unique workflow-generated confirmation interaction/audit ID (correlation only, not host-issued identity), recorded provenance, and timestamp. The timestamp is audit metadata only. Canonical challenge digest covers the exact review package, including semantic before/after or complete effective diff. The normal workflow displays operation, target/base, parent, changed paths, full semantic diff, and request/auth identities before prompting.

After the answer, Python recomputes request, authorization, challenge and proposed-content digests from the supplied workflow data. Any mismatch or payload change invalidates the confirmation and requires a new interaction. One request has at most one terminal decision; interaction IDs are unique, and consumed/replayed or conflicting decisions are rejected. An identical retry may return the already persisted decision record but cannot append another decision or publish another semantic activation. If the input UI is unavailable or the user does not answer, the request remains pending and unactivated. These controls establish consistency in the normal workflow, not proof that a hostile project-writer did not fabricate the supplied UI result.

Protocol:

1. **Proposal:** an agent/skill may append a schema-valid request. Pending proposal state is auditable but is not an effective-history edge and does not change active runtime.
2. **Human decision:** the normal activation workflow presents the exact challenge described above through the current host's interactive user-input UI and asks for APPROVE or REJECT. The agent may explain the proposal but must not infer or supply the answer. Persist a durable record with exact bindings. A REJECTED request remains immutable audit evidence, is terminal, and is not a correction edge.
3. **Final correction staging:** only a consistent APPROVE record allows the store to append a final correction artifact, and the final artifact must exactly match the confirmed proposal. The artifact is still staged; it is not live Canon.
4. **Candidate resolution:** activation names an exact candidate correction tip. The resolver validates its complete base-bound lineage and exact request/auth/confirmation record. Missing, stale, conflicting, cross-bound, rejected, mutated-after-confirmation, malformed or corrupt evidence blocks this candidate. It does not modify a separate valid active record. Pending and REJECTED requests remain auditable non-edges.
5. **Build:** produce the candidate's complete Canon-only projection generation and validate it. Recheck candidate hashes and current active publication sequence under the project lock.
6. **Publish semantic activation:** atomically create one immutable, no-replace publication record only after the complete generation exists and validates. The record contains the exact dependency closure in §3.1, semantic activation ID/sequence, generation ID/manifest digest, previous publication-record digest, and publication kind (`semantic_activation` or `same_semantics_generation_replacement`). Creating that immutable record is the semantic activation boundary. Any current-head cache is checked against the latest contiguous record and is never authority. Public APIs may advance to a new semantic activation only; replacing the generation for an existing semantic activation must preserve its exact history digest. No rollback API may point back to an earlier semantic activation.
7. **Pin and recover:** a runtime operation pins the latest publication record, its exact active artifacts, generation, and per-domain mutable overlay versions. A candidate append after pinning does not alter that operation. If the latest active record or referenced artifact is missing/corrupt, fail closed. Recovery may rebuild the same `effective_history_digest` and append a new publication record that retains the same semantic activation ID but names the replacement generation. It cannot point back to an earlier semantic activation. A new chapter commit in activation-managed mode also becomes effective only through a complete candidate generation and publication record; until then it remains pending publication and later Canon writes wait.

Base-only projects without activation history keep the compatibility path. Once activation-managed mode begins, all Canon readers/writers must use the publication protocol. No individual feature flag or consumer-specific switch exists.

## 5. Projection recovery and replay semantics

### 5.1 Scope after correction at chapter N

The data dependencies differ; “retry N” is not a safe global correction strategy.

| Projection | Dependency conclusion if N changes | Required Phase 9 operation |
|---|---|---|
| Per-chapter event JSON | N's effective accepted events only | Regenerate N; a retracted N has an explicit empty chapter event set/manifest entry |
| SQLite story-event mirror | Rows are chapter-keyed, but DB is shared | Replace N in the staged generation; validate the complete event mirror against all effective entries before publish |
| Chapter/scenes/appearances index rows | Row content is chapter-derived | Replace/remove N in the staged generation; compare the complete owned table set before publish |
| State projection | Sequential cumulative deltas, tracker, chapter status, protagonist/entity state | Replay N through the latest sparse commit, or full history if no verified state checkpoint exists. Current code has no effective-history checkpoint, so Phase 9 uses full replay. |
| Summary files | One chapter extraction summary per file | Regenerate/remove N; publish as part of the complete generation |
| Memory | Event lifecycle, exact identity reconciliation, retained non-Canon rows and legacy shadowing | Current implementation has no correction-aware checkpoint or suffix proof; recompute full history and preserve non-Canon rows under explicit ownership filters |
| Vector chunks | Chapter-derived content can be replaced at N; shared BM25/doc stats and cross-chapter graph/query state need coordinated rebuild | Build full vector/query generation initially; optimize N-scoped replacement only with global-index validation and atomic set publication |
| Intent diagnostics | Reconciles events and links across chapters | Recompute from N through tip only if a verified pre-N diagnostic checkpoint exists; none exists today, so recompute all accepted effective events |

The launch path therefore stages and validates **all seven projection domains for the complete sparse effective history**. It does not destructively reset live paths. The validated generation includes exact absence/tombstone entries for retracted or rejected chapters so consumers do not fall back to stale files.

RETRACT removes chapter N's effective events, summary, index content, memory contributions and vector chunks from the rebuilt generation, and marks N retracted in the effective manifest. It does not delete or rewrite the base accepted commit. Chapters after N remain their accepted base/effective records: Phase 9 does not infer or rewrite later chapters. Their cumulative projections are replayed from the full effective sequence; semantic inconsistencies caused by later prose that depended on the retracted fact are surfaced by normal diagnostics and require a separate correction request if Canon itself must change. SUPERSEDE supplies a complete replacement ExtractionResult for N; projections derive that replacement and then replay later chapters in order. AMEND uses the resolver's validated full effective extraction and changed-path contract.

### 5.2 Staging, validation, publication, and crash recovery

Each build uses a unique `.story-system/projections/generations/<generation-id>.staging/` directory for **Canon-owned projection slices only**, outside active generation paths. Writers consume typed effective inputs and write to these staging slices. The build journal is operational metadata; it cannot publish a candidate. The coordinator validates the complete required output set, fsyncs files/manifests, then atomically renames the completed directory into an immutable generation location. It then creates the immutable publication record described in §4 with exclusive create/atomic rename. The publication record is the single commit point; an incomplete staging directory or a completed but unpublished generation is never active.

Published records form a monotonic digest chain with increasing publication sequence. Semantic activation sequence/ID advances only when `effective_history_digest` changes. A same-semantics recovery generation retains the active semantic activation ID/digest and appends a later publication record that points to the replacement generation. The reader selects the latest contiguous valid record, validates its previous-record digest, activation record, exact dependency closure, and generation manifest. It never falls back to an earlier semantic activation if the latest publication is missing, malformed, or corrupt. A mutable head pointer, if kept as a cache, must equal this derived tip and cannot select a different semantic identity.

On restart, incomplete staging is never read; it may resume only if its snapshot and every completed-output digest revalidate, otherwise it is abandoned. If the current generation is damaged, runtime blocks while recovery builds from the exact active semantic snapshot. It may publish a verified replacement generation only with the same `effective_history_digest`; otherwise runtime remains blocked pending a new semantic correction/activation. No projection error changes correction history.

### 5.3 Freshness identity

Healthy means every required writer output is bound to the same tuple:

```text
project_data_schema
base_set_digest
effective_history_digest / snapshot_id
per-chapter effective_revision_id + effective_content_sha256
correction_lineage_digest + correction_tip
projection_manifest_digest
generation_id
```

Projection status/log entries add these identities and generation ID. Existing `projection_status` remains mutable execution state and cannot establish Canon authority. `healthy` is a set-level validation result, not “every writer returned done at some point.” The validator rejects a mixed generation even if individual legacy logs say done.

### 5.4 Canon projection slices and mutable owner overlays

The Phase 7 ownership inventory shows that `.webnovel` stores are shared by projection writers and still-active Intent/Craft/Workflow/compatibility owners. Phase 9 therefore does not copy those whole stores into an immutable Canon generation. It publishes only Canon-derived slices and exposes an `OwnedProjectView` that composes one pinned Canon generation with current owner-scoped mutable overlays. Every read captures the generation ID and each overlay revision/digest once; a later operation sees subsequent legitimate owner writes without mutating the generation. An owner write cannot alter Canon bytes or Canon freshness.

| Physical domain | Immutable Canon slice in generation | Mutable owner path after opt-in | Writer/reader rule |
|---|---|---|---|
| `state.json` | Canon projection paths written by `StateProjectionWriter`: chapter status/progress, entity/protagonist state, and commit-derived strand/loop state only where the inventory assigns it to Canon | New `.webnovel/state-overlay.json` holds `StateManager` workflow metadata and only inventory-owned Intent/Craft/Workflow fields, including `story_craft`, planning/Promise Ledger and review state | `OwnedStateStore` provides the familiar merged state shape to readers. After preflight/backup, owner APIs write only overlay paths; Canon fields are read from the pinned generation and cannot be overwritten by an overlay. Legacy `state.json` remains preserved as source/compatibility snapshot, not the live Canon source in activation-managed mode. Ambiguous overlapping fields block migration pending explicit ownership mapping. |
| `index.db` | Generation-local read-only SQLite slice for commit-derived `chapters`, `scenes`, `appearances`, `state_changes`, event mirror, and Canon-derived entity delta rows written by the commit projection pipeline | Existing `.webnovel/index.db` remains writable for operational/workflow ledgers and rows owned by `IndexManager`, `SQLStateManager`, review metrics, debt/telemetry, and non-Canon maintenance | `OwnedIndexView` attaches/queries the generation slice read-only for Canon tables and the mutable DB for operational tables. Canon projection writers never update the mutable DB after activation. Guarded owner writes remain guarded; colliding IDs/fields use inventory column/row ownership and surface conflicts instead of overlay precedence. |
| Memory scratchpad | Generation-local rows derived only from validated commits/corrections, identified by the current `COMMIT_PROJECTION_EVIDENCE_PREFIXES` ownership evidence | `.webnovel/memory_scratchpad.json` remains mutable for direct/user, planning, legacy bridge, and other non-Canon memory rows | `OwnedMemoryView` merges stable IDs with Canon rows reserved to the generation. `ScratchpadManager` reads/writes only the mutable slice in activation-managed mode; any attempt to change a reserved Canon row is rejected and the write preserves it. Unowned/ambiguous old rows remain visible as legacy/conflict data, never promoted to Canon. |
| Vector/RAG | Generation-local commit-source vectors and their corresponding BM25/document statistics, bound to effective chapter digests | Existing mutable RAG store retains non-Canon/user/document vectors, schema metadata, operational telemetry, and maintenance state | `OwnedRAGView` queries both stores separately, merges ranked hits deterministically, and labels source/authority; it never mutates either generation from a read. `VectorProjectionWriter` writes only the staged Canon vector slice. Existing RAG migration and non-Canon writers continue on their mutable DB. |
| Events and summaries | Generation-local event JSON/SQLite mirror and per-chapter summaries; only commit-derived outputs | No current non-Canon owner writes these domains in Story System mode; legacy originals are retained for compatibility | Readers resolve these paths through the pinned generation. Legacy mode keeps existing paths and writers. |

Activation preflight extracts existing non-Canon fields from shared legacy stores into overlays without deleting or rewriting source data, records source hashes and ownership mapping, and blocks on ambiguous overlap. After activation, every inventory-listed allowed mutable writer/reader must route through `OwnedProjectView`/its domain store; direct writes to frozen Canon slices are rejected. Runtime combines Canon slices with only the relevant owner's overlay. Phase 10 may later change ownership of fields, but cannot be a prerequisite for Phase 9's correct physical separation.

## 6. Existing-project migration contract

### 6.1 Preflight and report

`migrate preflight` is read-only and returns a deterministic report plus digest. It scans, without repair or rewrite:

- every sparse durable commit and full schema/filename/base validity;
- activation-mode marker and immutable publication-record chain, the exact active record closure/generation, and any missing or hash-mismatched active dependency;
- all correction namespaces and proposal statuses, distinguishing pending/rejected requests from final correction candidates; active runtime health depends only on the current active record closure, while a selected candidate is independently validated for conflicts;
- event JSON/SQLite, state, index, summary, memory, vectors, mutable overlays, intent diagnostics and freshness against their separate Canon and non-Canon owners;
- `.story-system` contract/schema marker, `.webnovel` files, plugin/project format indicators and supported schemas;
- ownership/provenance of legacy or mixed data and all fields that would move to mutable overlays.

The report carries separate `active_status` and `candidate_status`. Categories include `ACTIVE_VALID`, `ACTIVE_CORRUPT_BLOCKED`, `NO_ACTIVE_BASE_COMPAT`, `CANDIDATE_PENDING`, `CANDIDATE_REJECTED`, `CANDIDATE_READY`, `CANDIDATE_UNVERIFIED`, `CANDIDATE_CONFLICT`, `READY_NOOP`, `READY_REBUILD`, `LEGACY_OFFER`, `MIXED_BLOCKED`, `CORRUPT_CANON`, `PROJECTION_DRIFT`, and `UNSUPPORTED_SCHEMA`. A pending/rejected proposal is informational and cannot poison active status or unrelated candidates. Any active dependency mismatch blocks active Canon reads. Any selected candidate conflict blocks that activation only. Reports include exact file evidence, hashes, ownership classification, conflicts and recommended action. Preflight never selects a sibling, imports Craft as Canon, deletes data, or writes migration state.

### 6.2 Backup and dry run

Before any migration that changes project data or creates the first immutable publication record (activation enrollment), create a dated backup containing the complete `.story-system` correction/commit/contract trees, `.webnovel` state/index/memory/summaries/event-related files, vector DB and its sidecars, relevant project configuration, and any exact legacy sources the migration intends to read. Preserve file metadata where supported and include a content manifest with relative path, file type, size, and SHA-256. A backup counts as successful only after the manifest is reread, all files/hash entries verify, SQLite files pass integrity checks, and a restore-to-temporary-location verification passes. If disk space or verification fails, stop before mutation.

Dry run computes the candidate snapshot, exact generation output set and digests, files to create/replace in the new generation, retained legacy/non-Canon data, unsupported/conflicting items, required user decisions, backup location estimate, and rollback target. It writes only to an explicitly requested report destination outside the project data tree, or prints the report; default is read-only. The user reviews conflicts before execution. Dry run is not approval to migrate.

### 6.3 Migration execution and rollback

Execution revalidates the report and plan digests and unchanged source hashes, creates and verifies backup, then constructs a Canon-only generation plus owner-scoped mutable overlays. It preserves legacy sources and never overwrites an unowned value. First opt-in to activation-managed mode writes a durable activation-mode enrollment marker before changing read/write routing; after enrollment, absence/corruption of every publication record is fail-closed, never a signal to fall back to base-only semantics. The new marker, overlay layout, generation, and initial publication are prepared under the project activation lock; readers either remain on the prior mode before enrollment or report migration/recovery in progress after enrollment. Only a complete publication record makes the new active snapshot readable.

Rollback classes:

- **Projection recovery / operational generation replacement:** rebuild the current active semantic snapshot or publish another already-verified generation with the *same* `semantic_activation_id` and `effective_history_digest`. Never change the active semantic activation. If no same-snapshot generation is valid, block runtime until one is rebuilt.
- **Filesystem layout migration rollback:** restore mutable overlay/storage layout only after backup verification and post-backup conflict checks. Preserve activation-mode enrollment, the latest semantic activation record, all active corrections, and the active effective history. Reconstruct a compatible owner view for that same semantic history. Do not restore a pre-activation pointer, disable enrollment, or expose pre-correction Canon. If the prior physical layout cannot serve the same active semantic history, remain blocked and rebuild the current generation in that layout.
- **Semantic Canon reversal:** issue a new correction request, obtain an explicit interactive user decision, append a new correction, and publish a new semantic activation. No pointer or filesystem rollback performs this action.

A restore never overwrites or deletes post-backup human changes or correction artifacts. Compare current hashes with the backup manifest and report conflicts before restoring each path. Rollback that cannot preserve the exact current semantic activation stops and reports blocked; it does not silently downgrade.

### 6.4 Compatibility matrix

| Project state | Expected Phase 9 behavior |
| Clean Story System, no corrections | Base-only effective snapshot; behavior unchanged. Preflight `READY_NOOP`; no data migration. |
| Valid corrections with matching explicit confirmation records | Preflight `READY_ACTIVATE`; build complete generation, validate, then atomic activation. |
| Pending/rejected proposal or valid staged but unactivated correction | Active runtime remains unchanged; selected unverified candidate cannot activate; proposals remain auditable. |
| Active record or active-referenced artifact corrupted | `ACTIVE_CORRUPT_BLOCKED`; fail closed without base or older-semantic fallback. |
| Sibling/conflicted/corrupt correction lineage | `CORRECTION_CONFLICT`; block activation, preserve every artifact, require human-led new resolution design. |
| Valid history with stale projections | `READY_REBUILD` / `PROJECTION_DRIFT`; backup, dry-run, rebuild generation, publish only after validation. |
| Legacy project with no Story System commits | Continue supported legacy behavior; `LEGACY_OFFER`; explicit opt-in migration only. |
| Mixed/partial project | `MIXED_BLOCKED`; produce conflict report, preserve both ownership domains, no automatic conversion. |
| Invalid durable commit / unsupported schema | `CORRUPT_CANON` / `UNSUPPORTED_SCHEMA`; fail closed and report exact file; do not repair or delete. |

## 7. Failure and recovery matrix

| Failure | Canon history / candidate | Active projection and runtime | Human action | Retry/recovery |
|---|---|---|---|---|
| Interactive confirmation unavailable or no answer | Request remains pending; no correction edge or semantic activation | Existing active record/generation remains available if its exact closure validates | User may retry when the interaction is available | Fail closed for this candidate; do not infer approval |
| Confirmation replay or conflicting second decision | Candidate decision rejected; original immutable record retained | Active history unchanged | Required only to submit a new request if the user intends a different decision | Reject consumed interaction IDs and conflicting decisions; identical retry is idempotent |
| Confirmed payload changes before correction append/publication | Confirmation is stale for the changed payload; candidate blocked | Existing active record/generation remains available | User must review and confirm the new exact challenge | Recompute all bindings and request a fresh interaction |
| Pending request appended | Proposal only; no effective-history edge | Active snapshot and pinned operations unchanged | None unless user chooses to review | Wait, approve, reject, or leave pending |
| REJECTED request retained | Terminal proposal evidence; never an effective-history edge | Does not poison active snapshot or unrelated candidate | None | Keep immutable record; no special recovery |
| Authorized final correction staged but not activated | Candidate only; active semantic history unchanged | Active generation continues; candidate append does not alter an operation already pinned | Human review is needed to activate the candidate | Resolve and build exact candidate; publish only after validation |
| Missing confirmation, stale/missing auth, or digest conflict | Selected candidate rejected; artifacts preserved | Prior active record remains available if its closure validates | User must review the current exact challenge | Re-review exact current parent and create a new matching record; never infer approval |
| Sibling or corrupt candidate lineage | Candidate blocked; no sibling winner | Prior active semantic snapshot remains available and is not marked stale solely due to the new unreferenced branch | Required for any future semantic repair | Preserve evidence; candidate activation remains blocked |
| Active record references missing/tampered artifact or confirmation record | Active evidence corrupt | Fail closed for active Canon; do not fall back to base or older semantic record | Operator must inspect/restore exact bytes from verified backup/evidence | Restore the exact referenced evidence or remain blocked; semantic changes require a new correction |
| Corrupt base commit in active record | Active source evidence corrupt | Fail closed; no projection reset or base fallback | Required under separately reviewed source-repair procedure | Revalidate the whole exact active closure before rebuilding |
| Rebuild writer failure / partial stage | No semantic history change; candidate remains unactivated | Existing active generation remains usable if valid; partial stage is invisible | Usually none | Validate/resume stage or abandon and rebuild |
| Process crash before publication record | Candidate remains staged; no semantic activation occurred | Previous active record/generation remains active | None | Validate staging journal then resume or rebuild |
| Disk/fsync failure before publication | No semantic activation | Previous active generation remains active if its closure validates | Repair storage if needed | Revalidate files and build again; never infer success from log status |
| Publication record latest but its generation corrupt | Semantic activation record exists and remains active | Block Canon reads; never select an older semantic activation. Rebuild same active digest or use a verified generation for that same activation only | Operator notified; human only if active evidence/source also needs repair | Append a new monotonic publication record with same activation ID after same-snapshot generation validates |
| Candidate artifact appended while operation is pinned | Candidate set changes; pinned active identity does not | Pinned operation continues on its exact active record/generation/overlay versions; next operation pins the same active record until explicit publication | Approval only if activating new candidate | Resolve separately; append does not cause implicit switch |
| Candidate artifact appended while build runs | Candidate build becomes stale if exact candidate digest changes | Active record/generation remains active | None for append itself | Discard/re-resolve/rebuild candidate and recheck under lock |
| Operational generation replacement requested | No semantic history change | Replacement allowed only for same `semantic_activation_id` and same `effective_history_digest` | None for same-snapshot recovery | Append monotonic publication record; reject prior semantic IDs |
| User requests semantic correction reversal | New candidate correction required | Current active stays active until new generation validates and new semantic record publishes | Explicit interactive user confirmation required | Append AMEND/SUPERSEDE correction, build and activate; no pointer-only undo |
| Migration conflict / unowned mutable data | No semantic history change | Prior active remains if valid; migration does not publish | Human maps or preserves conflicts explicitly | Update report, backup and dry run; retry only after decisions |
| Filesystem migration rollback | Corrections and active semantic identity remain unchanged | Keep activation enrollment and same active history; otherwise block | Required for post-backup path conflicts | Restore only non-conflicting storage and regenerate same-semantic views; never revert to base Canon |

A prior generation is eligible for operational replacement only when its `semantic_activation_id`, `effective_history_digest`, exact correction closure, and base-set digest equal the active record. “Verified prior generation” alone is insufficient.

## 8. Version and compatibility decision

Phase 9 introduces a separate project activation/data marker, proposed schema `story-system-effective-history/v1`, and generation manifest schema `story-system-projection-generation/v1`. It does not alter `story-system/v1` accepted commit schema. An immutable activation-mode enrollment marker distinguishes never-activated base-only projects from projects whose activation record is missing/corrupt; after enrollment, an empty/broken record chain is fail-closed. Each publication record stores minimum reader capability and its generation; older plugin runtimes that do not understand publication records must refuse correction-aware project reads with an actionable unsupported-project-activation error. They must not treat corrected projection files as base-only projections.

Keep these version identities separate:

1. Git/source-tree identity and commit SHA;
2. canonical plugin package version (`.claude/plugins/zhanghui/.claude-plugin/plugin.json`);
3. marketplace catalog version (`.claude-plugin/marketplace.json`);
4. installed host/plugin version, observable only from that host;
5. project data schemas (`story-system/v1`, correction schemas, activation/generation schemas, and individual SQLite/file schemas).

Current source/marketplace versions both read `6.4.0`; this design does not prescribe a version bump. Implementation must check release policy. Project activation enrollment/schema is created only during explicit opt-in migration immediately before activation-managed routing; plugin installation alone never mutates user project data. Existing base-only projects use a no-op compatibility path. `6.4.0/**` remains untouched and is not a second implementation target.

## 9. Ownership, non-goals, and Phase 10 handoff

Update the active ownership inventory and drift guard for the effective-history reader, correction confirmation workflow/record, immutable publication records, Canon projection generations, mutable owner overlays, and migration surfaces. Record writers, readers, migration paths, workflow authority, modes/fallbacks, and evidence separately. Planning/Craft and legacy writers remain under their owners; they cannot write correction artifacts or be elevated into Canon by migration.

Phase 9 explicitly does not:

- merge Intent/Craft models or unify Promise/Open Loop/foreshadow/timed-lock fields;
- perform Phase 10 ownership reconciliation or retire legacy support;
- retire CHANGES;
- mutate accepted chapter commits or rewrite/delete correction artifacts;
- define a sibling-conflict semantic repair protocol;
- introduce a big-bang storage rewrite;
- perform destructive migration without a conflict report and verified backup.

**Phase 10 handoff:** Intent/Craft Field Reconciliation & Selective Migration/Retirement. Phase 10 may consume Phase 9's preflight, backup, generation, and rollback machinery, but this design does not pre-decide field ownership changes or retirement.

## 10. Phase 9 implementation acceptance design

Implementation acceptance is bound using H1/H2:

- **H1:** exact implementation commit plus a result-free acceptance template; do not put test outcomes into the template before execution.
- Run acceptance against that exact H1. Preserve commands, environment, outputs, artifacts and hashes as evidence.
- Independent review examines H1 and the evidence.
- **H2:** record-only evidence commit referring to H1 and its acceptance evidence. H2 must not contain implementation changes or be included in the tested H1. No self-reference.

Acceptance must prove all of the following, including adversarial end-to-end paths rather than only unit tests:

1. The real interactive confirmation workflow is exercised end-to-end: the exact challenge is displayed, the user explicitly answers, and a complete durable audit record is written. Tests verify the workflow path and do not claim resistance to a malicious project-writer agent.
2. Production Python validates exact request/auth IDs and hashes, operation, current parent, proposed/effective content digest, changed paths, displayed challenge digest, APPROVE/REJECT consistency, interaction/audit ID uniqueness, provenance fields, freshness and lineage. Timestamp is audit metadata only. Stale, cross-request, cross-auth, cross-content, conflicting, replayed and mutated-after-confirmation records fail.
3. Production Python does not authenticate the real-world identity of the person or prove that a malicious agent with project write access did not fabricate the record. Such attackers and compromised hosts are explicitly out of scope.
4. Base-only projects preserve Phase 8 pre-activation behavior and project files; no package update performs project migration.
5. Valid AMEND, RETRACT, and SUPERSEDE produce correct live effective history; correction artifacts and base commit remain byte-identical.
6. Pending requests, permanently retained REJECTED requests, and valid but unactivated corrections do not change active runtime. A conflicted candidate blocks that activation while prior valid active remains usable. An active record dependency hash mismatch fails closed. Candidate confirmation failure, sibling branch, corrupt candidate lineage, authorization conflict, and corrupt active base each produce their scoped behavior.
7. Every runtime/context/recovery/projection reader is routed through one snapshot and consumes the same effective revision.
8. Correction at N produces the designed per-chapter replacement plus full replay where no verified suffix checkpoint exists; test changed N+1 cumulative state, memory lifecycle, intent links and shared stores.
9. Event JSON, SQLite story-event mirror, state, index, summary, memory, vector/BM25, and intent diagnostics match the same effective snapshot and generation manifest.
10. Crash/retry before and after each build/publication boundary never marks mixed outputs healthy; candidate appends do not change already pinned active operations; semantic publication and same-semantic generation replacement preserve their distinct IDs.
11. Projection staging is isolated, all required outputs validate before atomic publication-record creation, and a partial generation is never runtime-visible.
12. Migration preflight is read-only and deterministic; dry run records exact impacts/conflicts and cannot mutate source data.
13. Backup manifest hashes, SQLite integrity, restore verification, filesystem rollback conflict detection, and same-semantic-only operational generation replacement are tested; no recovery path can re-expose a prior semantic Canon.
14. Legacy, clean Story System, staged correction, stale projection, mixed, corrupt and unsupported-schema compatibility matrix cases are exercised.
15. Historical accepted commit bytes and all correction artifact bytes remain unchanged through activation, rebuild, failure, retry, and rollback.
16. Ownership inventory and drift guard cover new producers/readers/migrations and exclude noncanonical/versioned paths.
17. Every inventory-listed planning/Craft/Workflow writer still writes to its mutable owner overlay after activation, and readers see that new value with the pinned Canon generation; attempts to write Canon-owned paths are rejected. No such writer can enter correction/effective history.
18. `.claude/plugins/zhanghui/6.4.0/**` is unchanged.
19. Phase 8 schema/store/resolver/preview regression and existing architecture/projection/rebuild regression pass.

## 11. Design self-check

- Task 0 found no Python-verifiable unforgeable host identity credential; this is retained as evidence for the explicitly adopted workflow trust model, not a closure gate. The normal activation path still requires an explicit interactive user decision and a durable exact-bound audit record.
- The threat model prevents workflow mistakes and stale/mismatched/replayed decisions; it does not claim to withstand a malicious agent with project write authority, a compromised host, or code/filesystem attackers.
- All correction semantics stay in the existing resolver behind one facade; consumers do not implement a second AMEND/RETRACT/SUPERSEDE interpreter.
- Semantic activation is an immutable monotonic publication record created only after whole-generation validation. Mutable generation caches can change only within the same semantic activation; no pointer rollback or consumer-by-consumer switch can undo Canon.
- Projections are derived and disposable, never Canon authority. Generation directories contain Canon-owned slices only; mutable owner overlays remain live and separately versioned.
- Chapter N can alter cumulative state and cross-chapter memory/intent. First release uses a full rebuild because there is no proven checkpoint; chapter-only replay is reserved for demonstrably independent outputs.
- Migration preflight, verified backup, dry run, ownership-specific overlays, preserved originals, and conflict checks prevent silent data loss or Craft-to-Canon promotion.
- Phase 10 remains separate; release versions and `6.4.0/**` remain untouched absent independent policy.
