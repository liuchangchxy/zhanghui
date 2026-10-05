# Phase 7 — Legacy Ownership, Documentation & Compatibility Closure

旧路径 Ownership、文档与兼容闭环

Status: design for review; no implementation included.
Design baseline: `origin/main` at `e9156f57fe79da63731cbc69c1e5f716c4feb577`.

## 1. Purpose and corrected audit finding

Phase 7 closes the ownership and compatibility gap left after the durable chapter-commit boundary, Context provenance, intent identity, and Phase 6 gate convergence. It makes the active canonical plugin's data owners machine-readable and testable, aligns active instructions with those owners, and makes the remaining legacy and CHANGES contracts explicit enough to migrate safely later.

The active `webnovel-write` main path already says that Data Agent creates temporary extraction artifacts, `chapter-commit` persists Canon, and projection writers refresh read models from the durable commit. Phase 7 must preserve that path. The verified drift is narrower:

- `webnovel-review/SKILL.md` still names Data Agent as the unique writer of state/index/summary/memory/vector projections.
- `webnovel-write/SKILL.md` contains an older completion gate saying Step 5 “has written back” state/index/summary. Projection completion is a legitimate postcondition; the actor wording is stale. Replace it with a requirement to verify the commit-backed projection result (or a successful retry), without deleting projection verification.
- `webnovel-resume/references/system-data-flow.md` is a redirect file whose quick reference still calls `state.json` authoritative and Data Agent a writer. The redirect target under init is current, so the duplicate quick reference must be corrected or reduced to an unambiguous redirect.
- Other loaded guidance still contains legacy direct-write claims. Examples include `references/shared/core-constraints.md`, query tag-format guidance, and old-flow sections inside `webnovel-query/references/system-data-flow.md`. Each must be checked in context: explicitly historical material may remain if it is clearly labeled and does not describe the active workflow as using that path.

No finding in this design assumes that all direct `state.json` writes are Canon writes or that all projection files must be written only by one API in every project mode.

## 2. Goals

1. Define a versioned, machine-readable ownership inventory and schema for the requested story-data domains and their write paths.
2. Add two distinct drift guards: a runtime writer-coverage guard and an active-document ownership guard.
3. Classify existing write APIs by data domain and Story System/legacy behavior, preserving valid Intent, Craft, Workflow, setup, and migration operations.
4. Converge the canonical active plugin documentation while preserving accurate projection-success checks and historically useful compatibility instructions.
5. Define a read-only CHANGES shadow-measurement protocol and evidence gates for a future decision to discuss retirement.
6. Define the canonical plugin/version and existing-project upgrade contract without editing or synchronizing the historical `6.4.0` snapshot.
7. Produce Phase 7 acceptance evidence using a non-self-referential implementation-commit / record-commit sequence.

## 3. Authority model and inventory contract

### 3.1 Inventory files and record types

Use these canonical files, under the active plugin's architecture documentation:

- `.claude/plugins/zhanghui/docs/ownership-inventory.schema.json`
- `.claude/plugins/zhanghui/docs/ownership-inventory.json`

The JSON Schema is Draft 2020-12. The inventory has required `schema_version`, `baseline`, `writers`, `readers`, and `migrations` arrays. Keep these arrays separate: writer, read-authority, and migration records answer different questions and should not be forced into one generic edge object. Shared evidence and lifecycle vocabulary is validated by the inventory tests.

Every writer record has:

| Field | Required meaning |
|---|---|
| `writer_id` | Stable unique ID for this write capability, not a display name. |
| `implementation` | Canonical repo-relative module/path plus API symbol, CLI command/selector, or migration entrypoint. At least one exact callable coordinate is required. |
| `data_domains` | One or more controlled values: `CANON_COMMIT`, `EVENTS`, `STATE_JSON`, `INDEX_DB`, `SUMMARIES`, `MEMORY`, `VECTORS`, `INTENT`, `CRAFT`, `WORKFLOW_METADATA`, `MIGRATION`, `COMPATIBILITY`. |
| `owner` | The authority that may accept/write this data, e.g. `ChapterCommitService`, planning/author, review workflow, migration command, or named projection writer. |
| `story_system_mode` | `allowed`, `guarded`, `rejected`, `projection_only`, or `not_applicable`, plus a short behavior description. |
| `legacy_mode` | Same shape, stating the supported old-project behavior. |
| `lifecycle_status` | `allowed`, `guarded`, `deprecated`, or `compatibility_only`. This is a policy label, separate from runtime mode behavior. |
| `active_consumers` | Active skills, commands, runtime services, or projection/recovery coordinators that invoke this writer. |
| `replacement` | Exact replacement writer/API, or `null` when still current. |
| `retirement_criterion` | Observable evidence required before changing this writer's lifecycle status. “When no longer needed” is invalid. |
| `evidence` | Source path and symbol/section anchors supporting the entry. |

Every reader record has:

| Field | Required meaning |
|---|---|
| `reader_id` | Stable unique ID for the read capability. |
| `implementation` | Exact canonical repo-relative module/API/CLI or active consumer section. |
| `read_edges` | One record per logical resource/read channel, including `data_domain`, resource/path/table, and mode-specific source details. |
| per-mode source details | For each of Story System and legacy mode: `primary_source`, `authority_claim`, `condition`, and `fallback` (source plus authority, or explicit `null`). Allowed claims are `CANON_AUTHORITY`, `VERIFIED_PROJECTION`, `LEGACY_COMPATIBILITY`, `INTENT`, `CRAFT`, `WORKFLOW`, `REFERENCE`, `PRESERVE_ONLY`, or `UNKNOWN`. The claim describes how the reader treats a value, not a policy grant. |
| `active_consumers` | Skills, agents, commands, or services receiving the read result. |
| `replacement`, `retirement_criterion`, `evidence` | Same observable replacement, retirement, and source-evidence rules as writer records. |

Every migration record has a stable `migration_id`, exact implementation coordinate, source and target format/domain, supported project modes, preflight, backup, idempotency, postcondition, rollback behavior, ambiguity handling, lifecycle status, consumers, replacement/retirement criterion, and source evidence. A migration that has not yet been implemented is recorded as required/planned only when the compatibility matrix makes it mandatory; it is not represented as an active writer.

`authority_claim` values are precise: only a schema-validated accepted durable chapter commit may claim `CANON_AUTHORITY`; a projection may claim `VERIFIED_PROJECTION` only after matching that commit; legacy stores may claim `LEGACY_COMPATIBILITY` in legacy mode and may not silently promote that value to Story System Canon. `PRESERVE_ONLY` means a read-modify-write path preserves fields it does not own and does not treat them as current story truth.

Schema and inventory tests use only standard-library JSON parsing and repository-owned validation helpers; no new runtime dependency is required. The schema remains the normative field/type/enum contract. Tests validate schema well-formedness, every record in all three arrays, enum values, unique IDs, resolvable implementation coordinates, evidence references, per-mode source/authority/fallback, and required lifecycle/retirement fields.

### 3.2 Inventory scope and owner distinctions

`writers`, `readers`, and `migrations` are independent inventories: `writer.active_consumers` is a caller list, not reader coverage. Reader records identify each consumer's mode-specific source, authority claim, condition, and compatibility fallback. Required reader families are Context/runtime source assembly; query and resume; write/plan/review consumers; state/index/summary/memory/vector readers; Story System commit and projection readers; and legacy fallback readers. A family may have multiple records where sources or authority differ.

This inventory is an architecture-governance and test artifact only. Production runtime must not load it or use it to decide write permission, Canon authority, gate severity, or ChapterCommit acceptance. Runtime authority remains defined by actual services, guards, and contracts. Add a test rejecting production imports/reads of the inventory and runtime decisions derived from it.

One file or database may contain several domains. The inventory records the write capability and its domains, not merely the file extension. In particular:

- `CHAPTER_COMMIT` is Canon authority; its accepted fact payload is immutable through ordinary chapter writes.
- Event JSON and `index.db.story_events` are event projections from a matching durable accepted commit. `EventLogStore.write_events()` is a guarded projection API, not a free-standing history owner.
- `state.json`, story/entity/index tables, summaries, memory, and vectors are projections where written by commit projection services. The same physical files may also hold explicit Intent, Craft, Workflow, or legacy data under different APIs; these require separate inventory records and field/table boundaries.
- `StoryCraftField` and `VolumeStateManager` manage future-facing planning/Craft state. Their writes are not automatically Canon bypasses; their overlap with event-linked obligations is a later field-reconciliation issue.
- Review metrics, chapter drafted/reviewed status, run ledgers/logs, caches, and disambiguation workflow records are operational metadata, not chapter facts.
- Setup and migration writers are inventoried even if they do not run during normal writing. They must not fabricate accepted chapter facts.

### 3.3 Initial writer classification to encode and verify

This is the implementation baseline for the inventory, subject to Phase 7's call-site audit and tests:

| Writer/API family | Domain and current classification |
|---|---|
| `ChapterCommitService` / `chapter-commit` | `CANON_COMMIT`; allowed owner for new accepted/rejected chapter decisions. Existing commit replacement is rejected. |
| `EventLogStore.write_events` and `EventProjectionRouter` | `EVENTS`, event mirror tables; guarded/projection-only. Require a matching durable commit; direct-call status does not make the store authoritative. |
| `StateProjectionWriter`, `IndexProjectionWriter`, `SummaryProjectionWriter`, `MemoryProjectionWriter`, `VectorProjectionWriter` | Commit-derived domains; allowed only for validated durable commit projection/rebuild flows. Record each writer and owning coordinator separately. |
| `StateManager` fact mutators and `save_state`/SQLite pending sync | `STATE_JSON`/`INDEX_DB` Canon fields; guarded in Story System mode and retained for legacy compatibility. Review/disambiguation/workflow metadata remains allowed when isolated from Canon buffers. |
| `IndexManager` and `SQLStateManager` chapter/entity/relationship APIs | Canon-like index tables; guarded in Story System mode except the authorized projection-write scope; legacy writes remain compatibility-only pending caller migration. Operational/review tables must be separately classified. |
| `update_state.py` | The CLI rejects its current `canon_mutation_requested` option set in Story System mode and retains legacy behavior; inventory each option separately because the set includes foreshadowing/strand operations whose semantic owner may be Intent/Craft. Explicit planning/review metadata options have separate behavior. |
| `story_craft.py` and `webnovel.py story-craft` | `CRAFT` and some future-facing planning fields stored in `state.json`; currently direct mutable writers. Allowed by domain, but field lifecycle/ownership and overlapping payoff status require reconciliation before retirement. |
| `VolumeStateManager` / `PromiseLedger` | `INTENT` planning state (`volumes`, `planning_horizon`, `project_info.promise_ledger`); user/planner-owned and directly mutable. Canon promise projection does not create or status-mutate these entries. |
| `ConsistencyRunner.apply_all` | In Story System mode, P1–P6 state mutations are skipped and P7 may rebuild filesystem derived views; in legacy mode patch-owned Intent/Craft state may still be saved. Classify mode-specific behavior rather than globally banning `apply`. |
| `init_project.py` and Story Craft initialization | `MIGRATION`/setup/configuration; allowed for new project setup and explicitly scoped defaults, never a substitute for chapter commit. |
| `migrate_story_craft.py` | `MIGRATION` for old Craft shape; it backs up state and inserts defaults when `story_craft` is missing, but also replaces a malformed non-object `story_craft` value with defaults. Inventory this behavior, require preflight/reporting and a preservation test before treating it as a safe upgrade for Story System projects. |
| CHANGES parsing and `changes_gate.py` | Validation of `INTENT`/ProposedChanges and legacy protocol, not a persistent Canon writer. Preserve until evidence and an explicit later decision satisfy retirement criteria. |

The inventory will also include writers for Workflow metadata and non-story compatibility paths found by scanning all production call sites, not just this seed list.

## 4. Drift-guard design

### 4.1 Runtime writer coverage guard

Implement a repository test helper, proposed as `scripts/tests/architecture/ownership_inventory_guard.py`, with three checks:

1. **Entry integrity:** every inventoried `implementation` coordinate resolves to the expected module/API/CLI selector and has a testable source anchor.
2. **Candidate write coverage:** scan the canonical active plugin's production modules for writes to protected story stores and known write boundaries: calls to the state atomic-write helper targeting `.webnovel/state.json`; mutating `index.db` SQL/API calls; event-store writes; commit/projection writer entrypoints; summary/memory/vector write APIs; and migration entrypoints touching those stores. Resolve constant and simple local-variable aliases for protected targets; unresolved writes in a protected module are reported for explicit classification, not silently ignored. Compare discovered candidates to inventory coordinates. An unregistered candidate fails with the path and symbol so it can be classified before merge.
3. **Inventory runtime isolation:** fail if production imports, opens, or parses either inventory file, or derives runtime authorization, authority, severity, or acceptance from inventory fields. Inventory tests may read these files; shipped runtime modules may not.

The scanner is scoped to the listed protected stores and their known helper APIs; it does not claim whole-program proof for arbitrary dynamically constructed filesystem writes. It enumerates all calls to protected persistence sinks under the canonical production source tree, not only currently inventoried modules. Writes routed through wrappers must expose their protected target at the wrapper boundary; a dynamic/unresolved target requires an explicit, reason-coded inventory exception and test. A small exception list covers non-story artifacts such as observability logs, RAG caches, plugin-owned templates, and test fixtures. Each exception identifies the exact target, domain, and owner; broad directory exclusions are disallowed. Tests add synthetic new writers that use the existing sink APIs and prove each fails until inventoried, then passes after an explicit inventory record. A synthetic unresolved target fails pending classification. Tests also prove migration/setup, workflow, and projection writers are not misclassified as Canon bypasses.

### 4.2 Reader coverage and authority drift guard

Maintain a required-family manifest in architecture tests, independent of `active_consumers`. Discover read candidates from protected-source adapters and known APIs for commits/events, state/index, summaries, memory, vectors, Intent/Craft, and workflow metadata; scan active skills/agents/references for declared source and authority claims. Every discovered candidate must resolve to a reader record, and every required family must have a mode-aware record. Unknown or dynamically selected sources fail pending explicit classification. Include a regression where a synthetic reader reads legacy `state.json` and labels it `CANON_AUTHORITY`: validation rejects it; in Story System mode a divergent legacy sentinel must never be returned as Canon. A legacy-mode fixture may return that sentinel only while declaring legacy compatibility. Reader coverage is reported separately from writer coverage and document drift.

### 4.3 Active-document ownership guard

Implement an architecture test over an explicit active-path manifest generated from the marketplace-selected plugin root. It checks:

- current positive contract statements exist: Data Agent emits temporary extraction artifacts; ChapterCommitService owns canonical commit creation; projection writers consume durable commits;
- forbidden active assertions do not appear unqualified, including “Data Agent is the unique writer of projections” and “state.json is the story truth”;
- actor-ambiguous completion language (“Step 5 wrote back state/index/summary”) is replaced with a postcondition describing successful, commit-backed projection verification;
- historical compatibility text is accepted only when it is explicitly marked historical/legacy and names its supported mode. It must not be presented as the active write workflow.

The active set includes write/plan/review/init/query/resume skills, Context/Data Agent instructions, active `system-data-flow` and architecture references, and loaded shared references such as `references/shared/core-constraints.md` and query `tag-specification.md`. It excludes nested `.claude/plugins/zhanghui/6.4.0/**` by source selection, not by copying or patching that snapshot. A mutation test adds a misleading assertion to a synthetic active document and expects failure; a historical labeled example passes.

Runtime coverage and document drift remain separate tests and reports. A documentation correction cannot be counted as proof that a live writer is guarded; a runtime guard cannot be counted as documentation convergence.

## 5. Active-document convergence decisions

| Active surface | Phase 7 disposition |
|---|---|
| `skills/webnovel-write/SKILL.md` | Preserve Data Agent extraction → reconciliation → `chapter-commit` → projection writers. Correct the stale duplicate Step 5 sufficiency phrase. Retain and strengthen postcondition checks: expected projection set is current for the accepted commit or retry succeeds; missing/stale projection remains a visible failure. Do not ask Data Agent to write projections. |
| `skills/webnovel-review/SKILL.md` | Replace the false Data Agent projection-owner statement. Retain the distinct review-result artifact/review-pipeline ownership rule. |
| `skills/webnovel-plan/SKILL.md` | Label direct Story Craft/Volume/Promise Ledger operations as Intent/Craft writes; do not state they establish past Canon. Preserve legitimate author planning operations. |
| `skills/webnovel-init/SKILL.md` | Identify project setup/config writes separately from chapter facts; initialize Story System contracts and defaults without describing `.webnovel/state.json` as Canon. |
| `skills/webnovel-query/SKILL.md` and loaded references | Use governed Context/commit/projection terminology. Mark legacy query/write examples as compatibility-only; correct active entity/tag guidance that says Data Agent writes the index. |
| `skills/webnovel-resume/SKILL.md` and `references/workflow-resume.md` | Resume from workflow metadata and durable commit/projection state. Keep author-selected prose rollback distinct from Canon/projection recovery; do not imply that Git rollback repairs commits or projections. |
| `agents/context-agent.md` | Preserve the Canon/Intent/Craft/Reference distinctions and state that projections are evidence only when validated against accepted commits. |
| `agents/data-agent.md` | Already states temporary artifacts only; keep as positive contract and cover it in drift tests. |
| `skills/webnovel-init/references/system-data-flow.md`, `skills/webnovel-query/references/system-data-flow.md`, `skills/webnovel-resume/references/system-data-flow.md`, and architecture docs | Keep one canonical data-flow explanation and clear historical labels; init and resume redirect documents must not reintroduce competing quick-reference facts. Update active references rather than rewriting project-history records or Phase acceptance evidence. |

## 6. Direct-writer verification and runtime-guard policy

Phase 7 implementation first lands the inventory and its failing coverage tests. It then verifies actual CLI/API call chains for every Issue #1 writer family. For each path it records its target fields/tables, project-mode predicate, caller set, owning semantic domain, and current regression test.

If a suspected Canon bypass is found, implementation must include a real reproduction against a Story System project with a valid contract marker, invoke the actual production API/CLI, and demonstrate that Canon-owned bytes or rows change without a matching durable commit. Only after the reproduction fails for the intended reason may the plan add a runtime guard and integration regression. A synthetic direct filesystem mutation alone is not a sufficient bypass reproduction. If all actual paths are already blocked, add guard regression coverage and make no production guard change.

Expected classifications are the table in §3.3. The call-site audit may split APIs that write mixed fields/tables. Do not “fix” coverage by forbidding all direct `state.json` writes: explicit Intent, Craft, Workflow, setup, and migration writes retain their distinct owner and mode behavior. Any guard must reject only the unowned Canon mutation and run before the first durable side effect.

## 7. CHANGES compatibility and retirement evidence

### 7.1 Current responsibility and known v1 boundary

Keep `<chapter_changes>` and `changes_gate.py`. CHANGES is `ProposedChanges`: it records the writer's declaration and is checked for protocol/schema and existing ledger integrity. Data Agent receives prose-only input and yields `ObservedChanges`; ChapterCommitService recomputes reconciliation and derives accepted facts.

Reconciliation v1 deterministically maps character-state proposals to `state_deltas`, explicit realm changes in entity deltas, and explicit realm values in `power_breakthrough` events. Other categories and opaque events remain visible but not semantically reconciled. `passed` therefore means no conflict within the implemented deterministic mappings, not complete chapter-change parity.

### 7.2 Shadow measurement

Add an opt-in, read-only shadow report tool/mode. It consumes existing final chapter text, parsed ProposedChanges, extraction artifacts, and reconciliation output; it never changes the chapter, blocks a commit, updates ledgers, or writes Canon. Reports are project-local under a diagnostics/shadow directory or explicitly exported by the operator; no telemetry or prose upload is introduced. Bind each row to schema/policy version and hashes, and store category-level counts rather than unnecessary full prose.

Pilot sample: target at least 60 completed chapters across at least three opted-in projects, including Story System and legacy projects, multiple genres, short/long chapters, explicit and implicit changes, and each currently supported CHANGES category. If fewer than 60 chapters or three projects are available, or a required mode/category cell is absent, status is explicitly `INSUFFICIENT`; analyze all available material but do not claim population-level adoption evidence or pass the adoption discussion gate. Adjudicate every deterministic conflict candidate, review a stratified random 20% of matched and one-sided rows per category, and include an author-reviewed selection of opaque/unmapped categories.

Freeze categories and parsing rules before sampling. Use separate denominators: all schema-valid atomic ProposedChanges claims and all schema-valid atomic ObservedChanges facts in sampled chapters; publish both and their combined total. Unknown, opaque, unsupported, and unmappable items stay in their denominator and count as uncovered. Do not narrow the denominator by redefining “in scope.” Missing, invalid, stale artifacts and extraction failures are separately reported infrastructure failures and make evidence `INSUFFICIENT`, rather than silently dropping affected chapters. Report these measures per category and project mode:

- **mapping coverage:** deterministically comparable items divided by the frozen proposal-claim and observation-fact denominators, reported separately and combined; opaque/unscorable/unsupported items remain uncovered denominator entries, never excluded;
- **match and disagreement:** matched, proposed-only, observed-only, proposal/observation conflict, observed-internal conflict, and opaque counts/rates;
- **hard-conflict precision:** author-confirmed true conflicts divided by adjudicated hard-conflict candidates; include false-block and unresolved counts;
- **artifact health:** missing, invalid, stale/hash-mismatch, and extractor failure counts, separate from semantic disagreement;
- **migration/compatibility:** share of sampled chapters/projects that can be parsed under the current and supported legacy formats without loss.

### 7.3 Gate to discuss a future retirement decision

Retirement may only be put up for discussion (not enacted automatically) when all of these are met:

1. The pilot sample and category/mode matrix above is complete, versioned, reproducible, and reviewed by the project owner.
2. The complete target cohort is present, and every category proposed for a changed policy has at least 95% mapping coverage using the frozen denominator above. Opaque/unmapped items remain denominator misses and are listed with a named owner/path; 95% only permits a separately reviewed retirement discussion and never automatically retires a gate or file.
3. Every proposed hard conflict in the pilot is adjudicated; no unresolved candidate is silently converted into a hard block, and the reviewed hard-conflict set has no known false block. Any observed false block resets the affected category's adoption decision until the rule or evidence is corrected and remeasured.
4. The chosen replacement preserves proposal auditability and provides a project migration report, backup, and tested rollback. Existing commits and CHANGES are not rewritten or deleted.
5. A release/cohort policy says which installed plugin/project versions remain supported and how many migrations have completed. Repository fixtures alone cannot establish installed-user adoption.

Only then can a separate design decide whether to retire any portion of the independent CHANGES gate. If a new gate or reconciliation path produces stale/missing artifacts, the current behavior remains fail-closed and the operator can restore the pre-decision policy/version; no automatic fallback may accept un-reconciled extraction.

## 8. Plugin and existing-project compatibility

- **Canonical source:** `.claude/plugins/zhanghui/`; `.claude-plugin/marketplace.json` selects `./.claude/plugins/zhanghui` and currently declares version `6.4.0`.
- **Version axes:** keep distinct (1) canonical source-tree identity/path and Git commit, (2) source-tree plugin package version in `.claude/plugins/zhanghui/.claude-plugin/plugin.json`, (3) marketplace catalog version in `.claude-plugin/marketplace.json`, (4) version installed on a user's host, and (5) project data schema version. These answer different questions and must not be conflated. The two repository manifests currently declare `6.4.0`. During implementation, read the existing release/version policy first; do not guess a version. If policy requires a bump, change only those two manifests. If no unambiguous policy exists, record the unresolved release decision instead of inventing a number. A Git/source update does not update an installed plugin or project schema.
- **Nested snapshot:** `.claude/plugins/zhanghui/6.4.0/` is a historical/versioned snapshot, not a second active plugin source. Phase 7 does not copy active changes there. The drift guard derives the active root from the marketplace manifest and proves the nested snapshot is excluded.
- **Installed plugin upgrade:** repository metadata cannot prove what a user's already-installed plugin runs. Document an explicit host/plugin update procedure, active plugin version/source check, restart/reload requirement where applicable, and a support matrix; never infer adoption from a Git checkout alone.
- **Existing project modes:**
  - new Story System projects use canonical commit and projection writers;
  - existing Story System projects retain immutable commits and use additive, idempotent migrations only;
  - legacy `.webnovel` projects continue supported compatibility behavior until a separate migration is approved;
  - mixed/partially initialized projects are detected explicitly and must fail safe or enter a named compatibility mode, not select an owner implicitly.
- **Migrations that must exist:** plugin source/version update alone must not edit user project data. Existing Story System projects need a version/schema preflight and a no-op path when no on-disk format change is required; no migration may rewrite CHAPTER_COMMIT. A legacy project needs no automatic migration while it remains in supported legacy mode. If a user later opts it into Story System, a separate explicit migration must exist with dry-run conflict report, backup, preserved legacy data, contract/bootstrap step, post-migration provenance check, and rollback. Mixed/partial projects need an explicit diagnostic/repair path before they can switch modes. Unsupported durable commit schema versions must fail with an actionable compatibility error rather than be rewritten by a plugin update.
- **Migration record:** any future migration has a stable ID, source/target schema, mode predicate, preflight result, backup reference, idempotency rule, postcondition, rollback path, and a report that lists ambiguous/unmigrated data without selecting a winner silently. Phase 7 defines this contract but performs no project-data migration.
- **Compatibility retirement evidence:** exact active-source verification; inventory shows no supported caller for the old API; migration tests pass across each supported mode/format; an opt-in cohort report records zero data-loss incidents and no unresolved migrated fields; backup/restore rehearsal succeeds; maintainer explicitly ends the support window. A version folder's existence/removal alone is not retirement evidence.

## 9. Phase 7 implementation boundary and acceptance

Phase 7 may add only the inventory/schema, drift scanners/tests, CHANGES shadow analysis/report path, documentation convergence, and runtime guards justified by reproduced bypasses. It does not rewrite stored project data. A production-code guard change is allowed only under §6's real reproduction rule; absence of a reproduction means no production guard change.

Phase 7 acceptance requires:

1. Every required data domain has at least one justified owner record, and each discovered writer/call path is inventoried or has a narrow reason-coded exclusion.
2. Synthetic new-writer and wrong-owner-doc mutations fail their respective drift tests; repaired inventory/docs pass. Historical-only text is recognized as historical.
3. Runtime-writer tests and active-document tests run independently and report independently.
4. Each direct writer listed in Issue #1 has a mode-aware classification and integration evidence; valid non-Canon writers still work in their supported modes.
5. Active docs agree with the canonical inventory. Projection completion remains required as a verified outcome, not attributed to Data Agent.
6. CHANGES remains enabled. The shadow report is read-only, freshness-bound, separates opaque coverage and infrastructure failures, and meets the specified cohort protocol or records why the available corpus is insufficient. No retirement is claimed without the §7.3 evidence.
7. Marketplace source resolution selects the canonical root; the nested snapshot remains untouched; compatibility and migration contracts are documented and tested with fixtures.
8. No chapter commit schema/major version, existing commit bytes, or user project state is changed by Phase 7.
9. Acceptance uses a non-self-referential two-commit binding. First commit all implementation, tests, docs, inventory, and a manifest template without results as immutable implementation commit H1. Run acceptance on H1 and collect exact commands, node IDs, corpus limits, and reviewer evidence. Then create record-only H2 updating `docs/superpowers/acceptance/2026-10-06-phase-7-final-acceptance.md` with `tested_implementation_head: H1`. Verify H2 changes only the acceptance record and its production/runtime tree is identical to H1. Record H2 or a later PR/merge SHA through a Git note or Issue/PR completion record, with any required final-head verification; no tracked manifest may claim to contain its own commit SHA.
10. Reader-family coverage passes for all required families; a synthetic legacy-reader-as-Canon mutation fails; production code does not load or consult the inventory for runtime decisions.

## 10. Non-goals

Phase 7 does not:

- merge Promise, Open Loop, Foreshadow, and Timed Lock models or create a universal `NarrativeObligation`;
- perform a historical full rebuild or broad existing-project data migration;
- implement Canon amendment, retraction, or supersede semantics;
- delete CHANGES, `changes_gate.py`, old project support, or the nested historical `6.4.0` snapshot;
- change the ChapterCommit major contract;
- route all planning/Craft writes through ChapterCommitService;
- make a destructive or silent project-data choice;
- change production writer behavior absent a reproduced Story System Canon bypass.

## 11. Revised post-Phase-7 dependency graph

The remaining work is not safely represented as an automatic “Phase 8 + Phase 9” pair. Phase 7 supplies ownership coordinates and compatible migration constraints. Three dependent phases remain likely, with a closure review after them:

```text
Phase 7 Ownership / docs / compatibility contract
  ├── Phase 8 Canon correction contract: amendment, retraction, supersede, lineage
  │     └── Phase 9 Projection recovery + historical rebuild + existing-project migration
  │              └── Phase 10 Intent/Craft field reconciliation + selective migration/retirement
  └── CHANGES shadow measurement continues alongside 8–10;
      any CHANGES retirement decision is separately reviewed after its evidence gate.
```

Why this order: an all-history rebuild must know which Canon records remain effective after a correction, so it needs accepted append-only correction/lineage semantics first. Project migration then needs deterministic recovery/reset/backups and a tested rollback contract. Intent/Craft field retirement depends on both the Phase 7 owner map and the proven migration/rebuild machinery to round-trip legacy fields without data loss. CHANGES measurement can run in parallel, but deciding to retire an authority is a separate policy decision. Phase 8–10 are design dependencies, not approved scopes; each needs its own reviewed design and acceptance boundary. Issue #1 closes only when those accepted obligations and the CHANGES/version retirement decisions are either completed or explicitly retained as supported compatibility with owners and criteria.
