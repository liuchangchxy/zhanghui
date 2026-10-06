# Phase 9 — Trusted Correction Activation, Projection Recovery & Existing-Project Migration

**Status:** Design ready for review
**Baseline:** `origin/main` at `63f3cef58090f399e6e8b740e3efebe6e5f3e459`
**Scope:** Design and implementation plan only. No production implementation is authorized by this document.

## 1. Goal and invariants

Phase 8 introduced immutable, staged Canon correction request, authorization, and correction artifacts. Phase 9 defines how a correction can become the runtime's effective chapter history without rewriting an accepted chapter commit or allowing consumers to disagree about which history is live.

The production boundary is:

```text
validated accepted commits + immutable correction artifacts
        + trusted decision evidence
        -> one EffectiveHistorySnapshot
        -> staged, validated projection generation
        -> one atomic activation pointer
        -> runtime and projection readers pinned to that generation
```

Required invariants:

1. `.story-system/commits/chapter_NNN.commit.json` remains immutable accepted evidence. Correction artifacts are append-only. Neither is rewritten or deleted to activate, recover, or roll back a correction.
2. The staged correction namespace is not live Canon. A correction is live only when a validated activation pointer identifies its effective-history snapshot and a complete, validated projection generation.
3. Runtime reads and every projection reader resolve the same immutable generation once per operation. They cannot independently interpret correction files or independently choose a base/corrected chapter payload.
4. Every effective chapter record retains its original base-commit digest and separately names its effective revision and effective-content digest. Writers validate both the base provenance and the resolution proof; correction support must not weaken durable-commit validation.
5. Any unverified, ambiguous, corrupt, stale, or unavailable evidence blocks activation. Existing active state remains usable only if its own pointer and generation validate; otherwise Story System reads fail closed and report recovery required.
6. Projection outputs are replaceable derived data. A failed build never changes Canon history or publishes a partial generation as healthy.
7. Migration preserves all source data until explicit, reviewed resolution. It never infers Canon from Craft/planning data or chooses a sibling correction winner.

## 2. Verified current architecture (baseline audit)

### 2.1 Correction artifacts and current resolver

The canonical implementation is `.claude/plugins/zhanghui/scripts/data_modules/` (marketplace-selected plugin root: `.claude/plugins/zhanghui`). The nested `.claude/plugins/zhanghui/6.4.0/` tree is a historical snapshot and is excluded from this design's implementation paths.

Phase 8 stores namespaces under `.story-system/corrections/chapter_NNN/<base-commit-sha256>/`, with separate `requests/`, `authorizations/`, and `corrections/` JSON artifacts. `canon_correction_schema.py` validates exact base/revision digests and AMEND, RETRACT, and SUPERSEDE shapes. `canon_correction_store.py` appends artifacts immutably and requires a typed `VerifiedCorrectionDecision` to append a semantic correction. `canon_correction_resolver.py` validates the full namespace and computes `EffectiveHistoryResult`; it rejects invalid/disconnected/cyclic/sibling lineages and invalid operation transitions. `canon_correction_preview.py` reads a chapter namespace and resolves a preview.

This resolver is currently a staged API only. No production runtime, context reader, projection writer, retry, replay, or rebuild calls it. Correction request persistence can use the resolver to validate staged lineage, but this does not activate an effective Canon source.

### 2.2 Human authority

Repository code has workflow capture paths, not an authenticated human identity boundary:

- `GateDecisionStore.append_attempt` writes a validated GateDecision set and workflow status as immutable JSON. It proves the record was structurally accepted by that API and binds policy output to a stored attempt; it does not prove who supplied the inputs or who operated the host.
- `append_human_response` checks that an attempt is pending, the finding belongs to it, and non-empty `choice` and `actor_ref` are supplied. It persists those caller-supplied strings. It does not authenticate a person, capture a host-authenticated UI event, or bind a response to the exact correction request/authorization digests.
- `ChapterCommitService.evaluate_after_human_response` delegates to that store, then reevaluates the normal write gate. This is gate workflow evidence, not correction semantic approval.
- GateDecision records, workflow events, provenance dictionaries, `actor_ref="human"`, local JSON, CLI flags, agent-generated files, and caller-supplied mappings are not trusted correction decisions.
- `VerifiedCorrectionDecision` is a frozen in-process dataclass in `canon_correction_store.py`. Its constructor checks non-empty strings and one of two status names; it has no private constructor, MAC/signature, host callback proof, or persisted verifier log. Repository tests instantiate it directly. It is therefore a type-level seam for Phase 8 tests, not production identity evidence.

The repository does not expose a Claude Code authenticated-human identity API or trusted approval callback usable by this code. Phase 9 must not claim cryptographic identity authentication. The implementable first boundary is **explicit human-mediated confirmation**, supplied by a production host adapter that obtains a fresh direct user confirmation for the exact tuple `(request_id, request_sha256, authorization_id, authorization_sha256, APPROVE|REJECT)` and returns an opaque, process-local verifier result. Its recorded provenance means only “the configured host confirmation boundary acknowledged this exact challenge”; it does not mean the person's real-world identity was cryptographically verified. If the host cannot provide a direct confirmation interaction that an agent/skill cannot synthesize as ordinary input, the provider reports unavailable and correction activation is blocked. A CLI flag, TTY check, prompt transcript, or JSON file alone does not satisfy this boundary.

The provider must be a narrow host capability, callable only through the correction review/activation workflow. It validates the exact request and authorization artifact digests itself, displays the operation and full proposed effective content/diff, captures APPROVE or REJECT, and returns a `VerifiedCorrectionDecision` bound to those exact digests and a provider-issued interaction identifier. REJECT is evidence and cannot activate a correction. Ordinary skills and agents may prepare and present a correction request; they cannot manufacture the provider result or convert gate responses into one. If Phase 9 cannot implement and adversarially demonstrate that isolation using host capabilities available at implementation time, it must ship with correction activation disabled and report the missing capability rather than provide a weaker provider under the same name.

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

### 3.1 Single effective-history API

Add one production `EffectiveHistoryStore` / resolver facade (final names may follow code conventions) above the existing schemas, store, and pure resolver. Its only public operation for production reads returns a typed immutable `EffectiveHistorySnapshot` containing:

- ordered sparse chapter entries, each with the validated immutable base commit, base digest, effective status, effective extraction (or null for retracted), effective content digest, effective revision ID, and applied correction IDs;
- a deterministic `base_set_digest` over all validated commit identities;
- a deterministic `correction_lineage_digest` over all relevant request/authorization/correction artifact identities and verifier evidence identities;
- `snapshot_id` / `effective_history_digest`, project-data schema, build time, and diagnostics;
- a fail-closed status. No consumer receives a partially resolved snapshot as usable history.

The facade discovers the entire sparse commit set once, rejects any malformed commit before consumers run, enumerates every exact base-bound correction namespace, obtains verifier evidence from the trusted provider/verifier service, and delegates semantic interpretation to `canon_correction_resolver.resolve_effective_history`. Only that resolver owns AMEND/RETRACT/SUPERSEDE, parent, sibling, and lineage semantics. Other layers consume its result and must not reparse artifacts or duplicate operations.

For chapters without correction artifacts, effective entries equal the validated base commit payloads byte-for-byte in Canon-relevant fields. For a chapter with any staged correction/request/authorization namespace, the facade must validate the complete namespace; it may not silently ignore invalid, rejected, unverified, or conflicting staged lineage and return base history as if no correction existed. In particular, stale/missing authorization, verifier unavailable, sibling branch, corrupt lineage, or invalid artifact gives an unusable snapshot with stable diagnostics. That prevents one reader seeing a correction while another silently falls back to base.

### 3.2 Effective projection input without forged commits

Introduce a typed `EffectiveProjectionInput` constructed only by the snapshot facade. It contains the unchanged validated base commit and the corresponding `EffectiveHistoryEntry`, plus snapshot/generation identity. `require_durable_commit_match` remains the base-integrity check; a new validator verifies:

1. base payload canonically matches the immutable disk commit;
2. the effective entry's base digest, chapter, snapshot digest, and applied correction chain match the facade-produced snapshot;
3. effective extraction conforms to `ExtractionResult`, and status/digest/revision recompute exactly;
4. an unforgeable-in-process capability/constructor boundary prevents arbitrary dict callers from labeling a payload “effective”.

Projection writers receive this typed input or a narrow projection payload derived from it. They never persist a modified base commit and never accept a bare corrected dictionary. This adapts the provenance boundary while retaining strict verification; it does not permit a correction to masquerade as an accepted commit.

### 3.3 Runtime consumption

All Canon-bearing runtime/context builders must acquire one `EffectiveHistorySnapshot` and use it for the operation. Canon facts, recent chapter material, event retrieval, and correction-derived content use effective entries. Planning/Craft inputs remain on their existing ownership path and are not promoted by the facade. If snapshot resolution fails, runtime returns a structured blocked/recovery state and does not mix base commits with correction-aware projections. A feature flag cannot switch individual consumers independently.

## 4. Trusted decision and staging protocol

1. **Prepare:** Agent/skill may create a schema-valid immutable request that names the exact current effective parent revision/content digest and proposed full effective content. This is a proposal, not approval.
2. **Review:** The host-owned provider displays exact request/auth IDs and SHA-256 digests, operation, base/effective parent, changed paths and full resulting extraction; it receives explicit APPROVE or REJECT through a human-only interaction boundary. It records provider name/version, interaction ID, capture time, and declared identity/provenance at the strength the host actually supports. No free-form provenance string can substitute.
3. **Verify:** A provider/verifier validates that request and authorization digests are exact, decision is explicit, current parent remains exact, and provider interaction evidence is valid. It returns the transient `VerifiedCorrectionDecision` bound to request ID/digest, authorization ID/digest, decision, identity/provenance, and verifier evidence digest. Stale requests must be re-reviewed; no reuse across requests or parent revisions.
4. **Stage:** `append_correction` appends an immutable correction artifact only after verification and full resolver validation. It remains staged, not live.
5. **Build candidate:** The single effective-history facade resolves the candidate lineage. A projection coordinator builds a complete new immutable projection generation from the complete candidate history, validates it, and holds publication while verifying that the correction-lineage digest has not changed during build.
6. **Publish:** Under a project activation lock, recheck candidate snapshot and current active generation. Atomically replace one small activation pointer (write/fsync temporary file, rename, fsync parent) to point at the validated generation manifest. This pointer is the sole transition from staged to live effective Canon. Readers pin the pointer/generation at operation start. A reader already pinned to the previous generation may finish against it; a new reader sees the new generation. No reader combines generations.
7. **Verify/recover:** Reopen the published pointer and validate all listed outputs/generation digests. If publication fails before rename, prior activation stays live. If a crash occurs after rename, startup validates the new immutable generation; it either uses the complete generation or marks the project blocked and restores the prior pointer as an operational rollback, never by removing correction artifacts.

The pointer is not a feature flag. It names a fully built snapshot and projection set. Base-only projects with no activation manifest retain existing behavior through a compatibility reader that still constructs a base-only effective snapshot; when the first correction is activated, all active Canon readers must use the generation resolver. No correction-aware reader may be enabled before all readers and writers in the manifest have migrated.

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

Each build uses a unique `.story-system/projections/generations/<generation-id>.staging/` directory, outside live projection paths. Every writer targets only that generation (including a generation-local SQLite DB and vector/BM25 artifacts), consumes typed effective inputs, and records per-chapter/per-writer completion against the snapshot ID. The coordinator fsyncs files and manifest, validates output content and provenance for the full set, then atomically renames staging to immutable `generations/<generation-id>/`. A generation is not eligible for activation until validation succeeds for every manifest writer.

The activation pointer stores the project activation schema, generation ID, snapshot ID, base-set digest, correction-lineage digest/tip, projection-manifest digest, and previous generation ID. Generation metadata stores a manifest for each output's digest, writer/schema version, effective revision coverage, and required/optional status. Missing optional retrieval data may be explicitly unavailable; it cannot be represented as healthy. The runtime loads and pins a pointer once, verifies the named manifest and required outputs, and then reads only from that generation.

Build journal states are `prepared -> building -> validated -> published` (or `failed/abandoned`), stored separately from immutable correction artifacts. On restart, an incomplete staging generation is never read by runtime; it may be resumed only if snapshot and all completed-output digests revalidate, otherwise it is abandoned and rebuilt. A published pointer whose generation is missing or corrupt makes runtime unavailable for Canon reads; it must not silently fall back to base commits. Recovery may atomically point back to the last complete generation after verifying it, while marking correction activation pending. It never edits history.

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

## 6. Existing-project migration contract

### 6.1 Preflight and report

`migrate preflight` is read-only and returns a deterministic report plus digest. It scans, without repair or rewrite:

- every sparse durable commit and full schema/filename/base validity;
- all correction namespaces, requests, authorizations, decisions, sibling branches and lineage validity;
- event JSON, SQLite story-event mirror and projection-log consistency;
- state, index, summaries, memory, vectors and intent diagnostics against current base-only/effective history;
- `.story-system` contract/schema marker, `.webnovel` files, plugin/project format indicators and supported schema versions;
- ownership and provenance of legacy/mixed data, including Craft/planning fields and user-authored state/memory rows;
- any active activation pointer and referenced generation.

Report categories are `READY_NOOP`, `READY_ACTIVATE`, `READY_REBUILD`, `LEGACY_OFFER`, `MIXED_BLOCKED`, `CORRECTION_UNVERIFIED`, `CORRECTION_CONFLICT`, `CORRUPT_CANON`, `PROJECTION_DRIFT`, and `UNSUPPORTED_SCHEMA`, with exact file evidence, hashes, conflicts, and recommended next action. It does not choose a sibling, import Craft as Canon, delete data, or write migration state.

### 6.2 Backup and dry run

Before any migration that changes project data or publishes an activation pointer, create a dated backup containing the complete `.story-system` correction/commit/contract trees, `.webnovel` state/index/memory/summaries/event-related files, vector DB and its sidecars, relevant project configuration, and any exact legacy sources the migration intends to read. Preserve file metadata where supported and include a content manifest with relative path, file type, size, and SHA-256. A backup counts as successful only after the manifest is reread, all files/hash entries verify, SQLite files pass integrity checks, and a restore-to-temporary-location verification passes. If disk space or verification fails, stop before mutation.

Dry run computes the candidate snapshot, exact generation output set and digests, files to create/replace in the new generation, retained legacy/non-Canon data, unsupported/conflicting items, required user decisions, backup location estimate, and rollback target. It writes only to an explicitly requested report destination outside the project data tree, or prints the report; default is read-only. The user reviews conflicts before execution. Dry run is not approval to migrate.

### 6.3 Migration execution and rollback

Execution revalidates the preflight report digest and unchanged source hashes, makes and verifies backup, builds a complete staged generation, validates every projection, then atomically publishes the activation pointer. Legacy source files remain intact and readable through compatibility mode unless a separately reviewed retirement phase removes them. Migration never overwrites an unowned value; a conflicting source remains preserved and blocks any mapping that would replace it.

Rollback classes are distinct:

- **Projection rollback/recovery:** repoint atomically to a verified prior complete generation or rebuild from the same effective history. This changes operational read-model selection only.
- **Filesystem migration rollback:** after validating the backup, restore the project's prior activation pointer/project files as a single reviewed recovery procedure. It does not delete correction artifacts. If pointer restoration is unsafe or partial, block reads and use recovery tooling.
- **Semantic Canon change:** issue a new exact correction request and trusted human decision. There is no “undo” that deletes a correction artifact; a later AMEND/SUPERSEDE correction may restore earlier content as a new append-only event.

No automated rollback may overwrite post-backup human changes. Compare current hashes to the backup manifest and report conflicts before restoring any path.

### 6.4 Compatibility matrix

| Project state | Expected Phase 9 behavior |
|---|---|
| Clean Story System, no corrections | Base-only effective snapshot; behavior unchanged. Preflight `READY_NOOP`; no data migration. |
| Valid corrections with trusted decisions | Preflight `READY_ACTIVATE`; build complete generation, validate, then atomic activation. |
| Staged but unverified corrections | No live activation or silent base fallback; `CORRECTION_UNVERIFIED`; require trusted review/provider availability. |
| Sibling/conflicted/corrupt correction lineage | `CORRECTION_CONFLICT`; block activation, preserve every artifact, require human-led new resolution design. |
| Valid history with stale projections | `READY_REBUILD` / `PROJECTION_DRIFT`; backup, dry-run, rebuild generation, publish only after validation. |
| Legacy project with no Story System commits | Continue supported legacy behavior; `LEGACY_OFFER`; explicit opt-in migration only. |
| Mixed/partial project | `MIXED_BLOCKED`; produce conflict report, preserve both ownership domains, no automatic conversion. |
| Invalid durable commit / unsupported schema | `CORRUPT_CANON` / `UNSUPPORTED_SCHEMA`; fail closed and report exact file; do not repair or delete. |

## 7. Failure and recovery matrix

| Failure | Canon history | Projection/pointer | Runtime | Human action | Retry/recovery |
|---|---|---|---|---|---|
| Verifier/provider unavailable | Unchanged; staged artifacts remain staged | No candidate publication | Existing verified active generation only; if none, block correction-aware reads | Required to restore supported provider or defer activation | Re-run preflight/review; never accept caller JSON fallback |
| Authorization conflict or stale/missing auth | Unchanged | No build publication | Continue prior generation only if valid; otherwise block | Review exact request/current parent and issue a new request/auth | Append-only new artifacts; do not mutate old auth |
| Sibling correction | Both artifacts preserved; no winner | Candidate generation rejected | Prior verified active generation only; if sibling appeared under an active namespace, mark activation stale and block new snapshots | Explicit human-led semantic repair outside Phase 9 | New corrective design/lineage; no auto-merge |
| Invalid correction artifact/corrupt lineage | Unchanged | No publication | Fail closed for correction namespace; no base fallback pretending no correction exists | Inspect and preserve evidence | Repair only by separately authorized append-only protocol; no in-place edit |
| Corrupt base commit | Base file unchanged | No build/publication | Block Story System Canon reads and recovery claims | Human repairs source under a separately reviewed procedure | Re-run full validation before any reset/build |
| Rebuild writer failure | Correction artifacts unchanged | Staging only; previous pointer intact | Continue prior pointer if valid | Usually none; report if source conflict needs decision | Resume only after validating staging outputs or abandon and rebuild |
| Process crash during build, before pointer rename | Unchanged | Incomplete staging, pointer remains old | Prior verified generation | None unless staging cannot validate | Startup validates journal/output digests; resume or abandon staging |
| Disk write/fsync failure | Unchanged | No pointer switch; incomplete staging retained for diagnosis | Prior verified generation; if it fails integrity, block | Free/repair storage as indicated | Revalidate all artifacts then rebuild; never mark healthy from logs |
| Partial staged projection / missing writer | Unchanged | Staging invalid and ineligible | Prior verified generation only | None unless missing source/config needs correction | Rebuild missing/whole generation; set-level validation required |
| Migration conflict or unowned legacy data | Unchanged | No migration activation | Existing supported mode if internally valid; mixed Canon reads block | Human maps/retains conflict explicitly | Update report after reviewed decision; rerun dry run and backup |
| Projection rollback | Unchanged | Atomic pointer to verified prior generation or fresh rebuild | Pinned readers finish; new readers use the chosen valid generation | Needed if choosing a prior semantic revision; explain effect | Verify all generation hashes before repoint |
| Filesystem rollback | Never delete or overwrite correction artifacts created after backup; preserve/quarantine newer artifacts and flag the project for preflight | Restore only verified, conflict-free paths after post-backup hash check | Block during restore, then verify old pointer/generation | Required if conflicts or later human files exist | Preserve newer artifacts, restore only approved paths, rerun preflight; do not claim clean rollback while conflicts remain |
| Correction added while rebuild runs | New correction is append-only; candidate snapshot remains immutable | Final lineage digest recheck fails, so candidate is not published | Continue prior valid generation | Human approval only for new request; rebuild itself needs none | Re-resolve latest history and build a new generation |
| Pointer published but startup validation fails | History unchanged | New pointer is invalid; prior generation retained | Block Canon reads until verified pointer recovery | Operator notified; human needed if prior generation is also invalid | Atomically repoint to verified prior generation or rebuild from full validated history |

“Continue prior generation” is allowed only while its activation pointer, manifest, lineage digest, and required output digests still validate. Any newly discovered invalid artifact that conflicts with the active correction namespace marks that generation stale and blocks new runtime snapshots rather than silently downgrading.

## 8. Version and compatibility decision

Phase 9 introduces a separate project activation/data marker, proposed schema `story-system-effective-history/v1`, and generation manifest schema `story-system-projection-generation/v1`. It does not alter `story-system/v1` accepted commit schema. The marker records minimum reader capability and current generation; older plugin runtimes that do not understand an activation pointer must refuse correction-aware project reads with an actionable unsupported-project-activation error. They must not treat corrected projection files as base-only projections.

Keep these version identities separate:

1. Git/source-tree identity and commit SHA;
2. canonical plugin package version (`.claude/plugins/zhanghui/.claude-plugin/plugin.json`);
3. marketplace catalog version (`.claude-plugin/marketplace.json`);
4. installed host/plugin version, observable only from that host;
5. project data schemas (`story-system/v1`, correction schemas, activation/generation schemas, and individual SQLite/file schemas).

Current source/marketplace versions both read `6.4.0`; this design does not prescribe a version bump. Implementation must check release policy. Project activation schema is created only when opted into or required for first correction activation; plugin installation alone never mutates user project data. Existing base-only projects use a no-op compatibility path. `6.4.0/**` remains untouched and is not a second implementation target.

## 9. Ownership, non-goals, and Phase 10 handoff

Update the active ownership inventory and drift guard for the effective-history reader, trusted decision provider, activation pointer, generation manifest, and migration surfaces. Record writers, readers, migration paths, authority claims, modes/fallbacks, and evidence separately. Planning/Craft and legacy writers remain under their owners; they cannot write correction artifacts or be elevated into Canon by migration.

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

1. Arbitrary dicts, dataclass construction, agent output, ordinary skills, CLI flags, and GateDecisionStore responses cannot create trusted correction approval.
2. Trusted provider binds exact request ID/hash and authorization ID/hash, exact current parent, APPROVE/REJECT, provider interaction evidence, and provenance; stale or cross-request evidence fails.
3. Base-only projects preserve Phase 8 pre-activation behavior and project files; no package update performs project migration.
4. Valid AMEND, RETRACT, and SUPERSEDE produce correct live effective history; correction artifacts and base commit remain byte-identical.
5. Unverified correction, unavailable verifier, sibling branch, corrupt artifact/lineage, authorization conflict, and corrupt base fail closed.
6. Every runtime/context/recovery/projection reader is routed through one snapshot and consumes the same effective revision.
7. Correction at N produces the designed per-chapter replacement plus full replay where no verified suffix checkpoint exists; test changed N+1 cumulative state, memory lifecycle, intent links and shared stores.
8. Event JSON, SQLite story-event mirror, state, index, summary, memory, vector/BM25, and intent diagnostics match the same effective snapshot and generation manifest.
9. Crash/retry before and after each build/publication boundary never marks mixed outputs healthy; pinned old readers and new readers remain generation-consistent.
10. Projection staging is isolated, all required outputs validate before atomic pointer publication, and a partial generation is never runtime-visible.
11. Migration preflight is read-only and deterministic; dry run records exact impacts/conflicts and cannot mutate source data.
12. Backup manifest hashes, SQLite integrity, restore verification, filesystem rollback conflict detection, and projection rollback are tested.
13. Legacy, clean Story System, staged correction, stale projection, mixed, corrupt and unsupported-schema compatibility matrix cases are exercised.
14. Historical accepted commit bytes and all correction artifact bytes remain unchanged through activation, rebuild, failure, retry, and rollback.
15. Ownership inventory and drift guard cover new producers/readers/migrations and exclude noncanonical/versioned paths.
16. Ordinary planning/Craft writers cannot write to or be routed into the correction/effective-history system.
17. `.claude/plugins/zhanghui/6.4.0/**` is unchanged.
18. Phase 8 schema/store/resolver/preview regression and existing architecture/projection/rebuild regression pass.

## 11. Design self-check

- The production verifier is an explicit host capability; current repository code cannot authenticate a human. If the host does not supply an unsynthesizable human interaction boundary, activation remains disabled. No stronger identity claim is made.
- All correction semantics stay in the existing resolver behind one facade; consumers do not implement a second AMEND/RETRACT/SUPERSEDE interpreter.
- Activation is a generation pointer rename after whole-generation validation; no consumer-by-consumer feature-flag window exists.
- Projections are derived and disposable, never Canon authority. Their freshness is set-wide and digest-bound.
- Chapter N can alter cumulative state and cross-chapter memory/intent. First release uses a full rebuild because there is no proven checkpoint; chapter-only replay is reserved for demonstrably independent outputs.
- Migration preflight, verified backup, dry run, preserved originals, and conflict checks prevent silent data loss or Craft-to-Canon promotion.
- Phase 10 remains separate; release versions and `6.4.0/**` remain untouched absent independent policy.
