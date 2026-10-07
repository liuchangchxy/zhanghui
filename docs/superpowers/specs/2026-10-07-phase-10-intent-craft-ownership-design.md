# Phase 10 — Intent / Craft Ownership Reconciliation (Design R0)

> Status: design candidate for independent review. Production implementation: NOT_STARTED.
> Baseline: main at `6f04925a321a01f72c6d00b127d6ab2d2e8ce7aa`.
> Issue: https://github.com/liuchangchxy/zhanghui/issues/1 (OPEN at audit time).

## 1. Problem statement

The repository already distinguishes CANON, INTENT, CRAFT, and REFERENCE when assembling writer context, and Phase 9 provides a mutable owner overlay for activation-managed projects. The remaining problem is that the same future-facing idea can be authored or projected through several paths, while field classification still follows container boundaries in some readers and migrations. Story Craft is especially mixed: some rows express author decisions with deadlines, some are craft methods or metrics, and some record claims about events that only accepted Canon can establish.

Phase 10 must reconcile semantic ownership and mutation paths without changing Canon authority, collapsing different lifecycles, or creating a second registry. This document records current paths, proposes one owner per semantic field, and defines a migration and implementation candidate. It does not authorize or perform production changes.

## 2. Design constraints and decisions

These constraints are ratified for R0:

1. Accepted durable CHAPTER_COMMIT and its effective correction lineage remain the authority for past story facts. A plan never becomes a past fact by being copied, fulfilled, or placed in a contract.
2. No unified NarrativeObligation authority or shared lifecycle is introduced. Canon-derived obligations, planner obligations, foreshadow, timed locks, and craft recommendations keep distinct authority and transition rules. A Context-only shared envelope is permitted for display and diagnostics; it cannot persist, write, or resolve any source item.
3. Canon-derived lifecycle is determined only by effective accepted Canon events. Planner fields such as deadline, priority, defer, or cancel belong to planner Intent and cannot change a Canon-derived resolved/fulfilled state. Explicit cross-reference is allowed; automatic bidirectional synchronization is prohibited.
4. Reuse Phase 9 OwnedStateStore and state-overlay.json for mutable state fields where activation-managed persistence applies. No new intent/craft registry or database is proposed. Existing Story System contract files remain the current authored contract artifacts; they are not copied into a second store by this design.
5. Classify fields, not JSON roots. Intent wins when an explicit author decision conflicts with a Craft recommendation. Craft, style, and quality heuristics default to advisory or score.
6. Unknown and ambiguous legacy values remain preserved and non-authoritative until explicit mapping. Migration may use exact schema/field identity, never prose similarity, timestamps, ordering, or guessed meaning.
7. Context is a composition boundary. Each composed item carries its semantic class, owner reference, source reference, provenance status, and stable identity when available. Duplicate or conflicting sources produce diagnostics; composition does not silently merge or create authority.
8. The approved `/根源牌序` option B remains unchanged: chapter 1/2 are legacy/reference only, not Canon; `_rerun_at` remains `UNKNOWN / PRESERVED / NOT IMPORTED`.
9. `.claude/plugins/zhanghui/6.4.0/**` is immutable. Stash `pre-phase7-preserve-untracked-2026-10-06` is preserved.

### Options considered

| Option | Result | Reason |
|---|---|---|
| One NarrativeObligation model and lifecycle | Rejected | Event-derived resolution, planner defer/deadline, authored foreshadow payoff, and craft advice have different authority and legal transitions. A shared lifecycle would either grant planners Canon power or erase planning semantics. |
| Shared envelope with distinct variants and owners | Allowed only in Context | It can standardize display identity/provenance without persisting or mutating the records. R0 does not require a persistent shared schema. |
| Distinct owners composed by Context | Recommended | Matches existing ownership boundaries, avoids another registry, and preserves type-specific lifecycle. |

## 3. Current implementation map: writer → persistence → reader → runtime

### 3.1 Planner and project configuration

| Path | Writer and persistence | Readers and runtime behavior |
|---|---|---|
| `init_project.py` | Initializes and updates `.webnovel/state.json`; writes `project_info`, volume skeletons through VolumeStateManager, outlines, and optional cross-volume artifacts. | `VolumeStateManager`, init/plan/write skills, chapter-to-volume helpers, and legacy state readers. |
| `volume_state.py` | VolumeStateManager owns `state.json.volumes[]` and planning-horizon values in `project_info`; confirms human/AI draft state and mutates planner Promise Ledger nested in `project_info`. Caller persists the state. | Plan skill reads volumes to decide V+1 outline writeback; write skill reads Promise Ledger deadlines; runtime/context may read project info through state. |
| `promise_ledger.py` | Creates ForeshadowEntry rows with type, depth, planted/payoff chapters and volumes, status, timestamps, and audit log. Persisted at `project_info.promise_ledger`. | VolumeStateManager queries overdue/cross-volume entries; write skill passes overdue entries to chunked-write gate. |
| `webnovel-plan/SKILL.md`, `update_state.py`, `update_master_outline.py` | Plan workflow writes markdown outlines/timeline/beat artifacts, updates state progress, and writes back confirmed V+1 volume fields into master outline. Optional all-volumes flow writes `project_info.cross_volume_beat_map`. | Planning and init workflows, chapter outline loader, Story System contract builder, write gates. |
| `story_system.py`, `story_contracts.py`, RuntimeContractBuilder | Writes `.story-system/MASTER_SETTING.json`, volume JSON, chapter JSON, and review JSON; marked Markdown is a rendered companion with generated blocks. | `story_runtime_sources.load_runtime_sources`, ContextManager, prewrite validation, commit artifact creation. |

The planning formats are not interchangeable: state volume records establish confirmed/deferred volume decisions; outlines carry authored plot plans; Story System contracts package selected plans and constraints for a chapter. R0 retains those existing artifacts while naming one writer family for each field. Where the same field appears in more than one artifact, its source relationship must be declared; a rendered or runtime copy is not a second authority.

### 3.2 Story Craft and chapter metadata

| Path | Writer and persistence | Readers and runtime behavior |
|---|---|---|
| `story_craft.py` | Mutates `state.json.story_craft` and `chapter_meta` in memory. Exposes add/payoff foreshadow, add/fulfill timed lock, rhythm, character arc, thematic echo, chapter metadata, volume beat initialization/fill/check APIs. | `webnovel.py` CLI, plan/write/review skills, `review_pipeline.py`, consistency patches, Context. |
| `webnovel.py::cmd_story_craft` | Loads legacy `.webnovel/state.json`, calls Story Craft functions, then writes the whole state directly with `_save_state_via_atomic`. This path does not route through OwnedStateStore when project activation is present. | CLI check and update commands; for activation-managed projects direct legacy-file writes can diverge from the pinned owner overlay that Context reads. |
| `migrate_story_craft.py` | Adds the default Story Craft object if absent or malformed and backs up state; it does not semantically migrate or classify existing fields. | Plan skill invokes it before planning. |
| `review_pipeline.py` | Reads volume beats, rhythm thresholds, timed-lock deadlines, Scene-Sequel and hook metadata; emits blocking/warning issue rows. | Review artifacts flow into commit gate policy; the write skill also reacts to critical/blocking prose. |
| `consistency/runner.py` and patches P1–P7 | Reads Story Craft, patches may update foreshadow DAG, volume anchors, event matrix, pacing tracker, reader contract and derived views. CLI offers check/apply. | Consistency CLI and plan/write skills. These mutation paths need owner routing and severity review in Phase 10. |
| `state_manager.py` | Legacy process-chapter path stores `chapter_meta` as pending state writes and persists in base-only mode. For activated projects `_save_activation_owner_overlay` writes approved owner roots but excludes `chapter_meta`. | State consumers/status/context; Phase 9 migration currently labels the whole `chapter_meta` root as Canon state. This root-level classification conflicts with its mixed content and legacy writers. |

### 3.3 Canon events and derived obligations

| Path | Writer and persistence | Readers and runtime behavior |
|---|---|---|
| `ChapterCommitService` | Persists accepted/rejected commit artifacts and effective extraction result; accepted events include promise/open-loop create and resolution events. Phase 9 effective history/correction resolution selects effective accepted input. | Canon Context reader and projection rebuild use validated accepted commits/effective history. |
| `intent_reconciliation.py` | Pure deterministic reconciliation from ordered events. Creates event-ID keyed open-loop and reader-promise rows; closes by explicit IDs or exact-unique legacy content; emits unlinked/ambiguous diagnostics. It does not mutate source events. | Called by `MemoryWriter.apply_commit_projection`; lifecycle is persisted into memory projection, which is rebuildable and not planner authority. |
| `MemoryWriter` / memory projection | Derives `open_loop` and `reader_promise` memory rows from accepted commit event lifecycle and stores them in memory projection/scratchpad. | `MemoryContractAdapter.get_open_loops`, Context memory pack, writer prompt. Existing Context categorizes these memory rows as INTENT with generic `unverified_plan`, losing the important Canon-derived provenance distinction. |
| `context_provenance.py` | Reads accepted commit facts separately from state projections, contracts, outline, memory, and retrieval. It emits CANON/INTENT/CRAFT/REFERENCE groups and diagnostics for fact conflicts. | `ContextManager` and `MemoryContractAdapter` output governed context to Writer and other consumers. |

The accepted event is a past fact (CANON). An active or resolved obligation derived from that event is a CANON_DERIVED_OBLIGATION presented within the INTENT section, explicitly labeled with that origin. The projection must remain reproducible from effective Canon; planner metadata may link to it but cannot change its lifecycle.

### 3.4 Context and contracts

`ContextManager` pins an active `OwnedProjectView` and reads owner state from its overlay-backed view when enrolled; otherwise it reads `state.json`. It reads Story System contracts and outlines from their existing files. `build_governed_context` currently classifies entire outline and contract payloads as INTENT; `project_info.promise_ledger`, `story_craft.timed_locks`, and `story_craft.foreshadow_chain` as INTENT; and the remaining nonempty `story_craft` fields as one CRAFT item. That container-level fallback misclassifies mixed fields such as character arc, thematic echo, volume beats, and reader contract. ContextItem has semantic/source role and source reference but no explicit owner field today.

Context's existing duplicate resolver handles keyed factual projections against commits and emits diagnostics; it does not perform equivalent identity/provenance/conflict resolution for every Intent and Craft source. Multiple sources without a stable shared identity currently pass through as separate items, which avoids some destructive merging but does not consistently surface duplicates.

### 3.5 Existing ownership overlay and migration

`owned_project_view.py` defines owner roots including `story_craft`, `planning`, `promise_ledger`, `review_checkpoints`, `workflow`, `craft`, `intent`, `project_info`, and `volumes`, and writes them into `.webnovel/state-overlay.json`. `StateManager` routes a selected set of these roots there for activation-managed projects. The overlay is a persistence boundary, not a semantic classifier: it currently stores whole roots and does not validate the internal semantic field owner.

`project_migration.py::_owner_inventory` classifies known project_info fields but leaves any unlisted field as an explicit conflict; actual nested `project_info.promise_ledger` is not in its enumerated intent field set. It labels whole `chapter_meta` as Canon, although that root contains planned targets and craft annotations alongside commit-produced/factual metadata. Unknown and ambiguous paths are preserved with conflicts. Phase 10 should extend that inventory deterministically; it must not weaken fail-closed behavior.

The repository also already has a Phase 7 governance-only ownership inventory at scripts/tests/architecture with docs/ownership-inventory.json, its schema, and AST writer/reader coverage tests. Phase 10 should extend those existing record families and guard tests; the inventory remains test/governance evidence and must never become runtime authority or a second mutable registry.

## 4. Authoritative field-level semantic inventory

The class cell in each row contains exactly one allowed semantic class. Where a legacy value is mixed or lacks provenance, the row class is UNKNOWN and the recognized future/commit-backed field is listed separately.

| Field / Artifact | Current writer | Current storage | Current readers | Proposed semantic class | Authority | Mutability | Lifecycle | Canon interaction | Target owner | Compatibility status |
|---|---|---|---|---|---|---|---|---|---|---|
| Accepted StoryEvent including promise/open-loop create and close | ChapterCommitService from accepted extraction | Durable chapter commit and generation event projection | Canon Context, event projection, MemoryWriter | CANON | Accepted commit and effective correction lineage | Append/effective correction only | Accepted or corrected | Defines past event | Canon commit service | Retain; guard standalone legacy event writers |
| Canon-derived Open Loop lifecycle | intent_reconciliation via MemoryWriter | Rebuildable Canon memory projection | memory adapter, Context, Writer | CANON_DERIVED_OBLIGATION | Effective accepted source/close events | Not planner mutable; recomputed | active to resolved; correction recomputes | Derived from Canon; not itself a past event | Canon-derived projection; displayed under INTENT with origin | Preserve; make provenance explicit |
| Canon-derived reader Promise lifecycle | intent_reconciliation via MemoryWriter | Same derived projection | memory adapter, Context, Writer | CANON_DERIVED_OBLIGATION | Effective promise event lineage | Not planner mutable | active to paid_off; correction recomputes | Distinct from planner deadline | Canon-derived projection; displayed under INTENT with origin | No automatic ledger sync |
| Planner Promise Ledger identity, type, and content | VolumeStateManager and plan workflow | state.json.project_info.promise_ledger; overlay after routing | VolumeStateManager, write skill, Context | INTENT | Author/planner | Explicit upsert/edit | Existing pending/advanced/paid_off/overdue | Optional exact event link; cannot determine Canon payoff | project_info owner root | Exact known schema only; no text matching |
| Planner Promise Ledger payoff chapter, volume, and deadline | VolumeStateManager and PromiseLedger | Same | overdue/cross-volume queries, write precondition | INTENT | Author/planner | Planner edit/defer/cancel | Planner lifecycle; exact enum remains open | Deadline is schedule, not payoff evidence | project_info owner root | No inferred migration from other ledgers |
| volumes[].title, range, conflict, climax, cool points, characters, foreshadowing | VolumeStateManager, init/plan | state.json.volumes[]; overlay after routing | plan writeback, volume resolver, runtime | INTENT | Author-confirmed planner | Explicit edit; confirmed records protected from AI overwrite | Draft ephemeral; persisted confirmed/deferred | Prospective plan only | volumes owner root | Preserve exact fields; ambiguous records block |
| volumes[].status and source | VolumeStateManager | Same | init, plan, status | INTENT | Author decision; AI cannot overwrite confirmed state | Explicit confirm/defer | draft/confirmed/deferred | Not Canon status | volumes owner root | Unknown enum preserved and conflicted |
| project_info.title | project init/author edit | state.json.project_info.title; overlay | status and plan prompts | PROJECT_CONFIG | User/project setup | Explicit config edit | Project lifetime | None | project_info owner root | Exact config field |
| project_info.genre, genre_label, genre_tags, tags | project init/author edit | Same | planning templates, Story Craft CLI, Context | PROJECT_CONFIG | User-selected project profile | Explicit config edit | Versioned selection | No Canon authority | project_info owner root | Separate from reference genre profile |
| project_info.author, language, output_dir, project_id, platform, created_at | project init/setup | Same | init/runtime/reporting | PROJECT_CONFIG | User/setup | Config operation; created_at stable after setup | Project lifetime | None | project_info owner root | Preserve recognized values |
| project_info.core_selling_points, target_reader, target_words, target_chapters | project init/planner edit | Same | init, plan, progress/runtime helpers | INTENT | Author/planner | Explicit revision | Project-level plan | Not a past fact | project_info owner root | Map exact field names |
| project_info.story_pitch, story_premise, theme, outline | project init/plan | Same; outline also appears in 大纲 files | plan, Context, Story System seed | INTENT | Author | Explicit author edit | Plan may become stale | Never proof of occurrence | project_info Intent and authored outline file | Cross-copy disagreement diagnostic |
| project_info.characters, world_setting, golden_finger fields, protagonist/heroine/co-protagonist/antagonist structure, world_scale, factions, power/currency/sect/cultivation/social/resource fields | init/author plan | Same | Story System seed, plan, Context | PROJECT_CONFIG | Author-selected story baseline | Explicit revision | Project setup/configuration | Grounds later Canon; does not establish chapter events | project_info owner root | Exact allowlist; unknown nested fields conflict |
| project_info.later_volumes_status and expected_total_volumes | VolumeStateManager/init | Same | planning horizon and plan workflow | INTENT | Author/planner | Explicit status/target edit | deferred/unknown/planned | None | project_info owner root | expected_total_volumes currently omitted from Phase 9 field allowlist |
| project_info.confirmed_through_volume | VolumeStateManager recomputation | Same cache | plan/init | DERIVED_REFERENCE | Derived from volumes status | Recomputed | Mirrors max confirmed index | None | Derived view of volumes | Not independent authority |
| project_info.cross_volume_beat_map | init_project all-volumes flow | project_info and outline artifacts | planning validation | DERIVED_REFERENCE | Derived from confirmed-volume adjacency | Rebuilt | Rebuild after source change | None | Derived from confirmed volumes | Compare source and diagnose drift |
| Nested project_info.promise_ledger migration disposition | project_migration inventory currently treats it as unmapped | Original state file; project_info overlay root is supported | Context and write precondition | UNKNOWN | No migration authority until explicit field mapping | Preserve | Unresolved mapping | No promotion or deletion | Existing project_info owner after explicit mapping | Fail closed until deterministic mapping is added |
| planning state root | No active production writer found in audited paths | Overlay-supported root; possible legacy state | No canonical reader found | UNKNOWN | Undetermined | Preserve | Unknown | None | None assigned | Do not auto-migrate or infer meaning |
| progress.volumes_planned, current_volume, total_volumes, volumes_completed, last_updated | init/update-state/plan workflow | state.json.progress; overlay paths where supported | plan, status, runtime | WORKFLOW | Workflow progress service | Workflow transition | Operational progress | Does not imply Canon | Existing workflow progress owner | Keep separate from volume plan |
| progress.current_chapter and total_words | Canon projection and legacy StateManager compatibility path | Canon generation when enrolled; legacy state projection otherwise | status, gates, dashboard | DERIVED_REFERENCE | Accepted commit projection | Recomputed | Progress projection | Never creates Canon | Canon generation | Preserve Phase 9 projection boundary |
| progress.chapter_status | Commit projection for committed status; workflow service for draft/review/reject | Canon generation and workflow metadata | status, gates, dashboard | WORKFLOW | Workflow transition except committed projection | Workflow transition | Draft/review/reject/committed | Status alone never creates Canon | Existing workflow path | Keep status authority explicit |
| MASTER_SETTING authored setting/world baseline | init/story seed/author plan | .story-system/MASTER_SETTING.json and marked Markdown rendering | Runtime sources, Context, validation | PROJECT_CONFIG | Author-approved project setup | Explicit author edit | Project lifetime/versioned by file history | May ground later Canon; not proof events occurred | Existing Story System contract artifact | JSON source; marked Markdown is rendered companion |
| MASTER_SETTING explicit locked/append-only/override constraints | Story seed and author/planner | Same contract JSON | contract merge, prewrite, Context, gate binding | INTENT | Explicit author contract node | Explicit revision with provenance | Proposed/active/superseded | Only exact user-bound constraint may hard gate | Contract node owner | Do not infer hard status from key name |
| VOLUME_BRIEF conflict, climax, and target beats | RuntimeContractBuilder and plan | .story-system/volumes/volume_NNN.json | Runtime sources, Context, prewrite/review | INTENT | Author/planner | Author revise/defer | Plan lifecycle | Plan deviation is not Canon contradiction | Volume contract owner | Diagnose duplicate state-volume values |
| CHAPTER_BRIEF goal, must-cover, forbidden, planned time/characters | RuntimeContractBuilder and plan | .story-system/chapters/chapter_NNN.json and outline | Context, prewrite validator, fulfillment review | INTENT | Author/planner; explicit user constraint only with binding | Author revision | Proposed/active/stale/satisfied candidate | Canon may inform satisfaction; never deletes plan | Chapter plan contract owner | Exact source identity required |
| Review contract quality/method rules | RuntimeContractBuilder/review flow | .story-system/reviews/chapter_NNN.review.json | prewrite, review, commit gates | CRAFT | Reviewer method unless separately user-bound | Versioned advisory config | active/superseded | Cannot imply Canon truth | Review/craft contract owner | Keep constraint binding separate |
| Master/volume/chapter outline prose | Plan authoring and writeback | 大纲 Markdown/JSON planning artifacts | plan, outline loader, Context | INTENT | Author/planner | Author edit; generated fragments replace marked sections only | Proposed/active/stale/satisfied | Plan remains plan | Plan artifact writer | Preserve author-edited regions |
| story_craft.foreshadow_chain planned setup/payoff fields | plan skill, story_craft.py, webnovel CLI | state.json.story_craft.foreshadow_chain; overlay after routing | CLI, review, P1/P7 consistency, Context | INTENT | Author/planner | Explicit add/amend/payoff/defer/cancel | Existing active/paid_off; additional transitions remain open | Planned target only; occurrence requires accepted event | story_craft Intent subfields | Exact known schema; auto placeholders remain unconfirmed |
| Legacy foreshadow payoff/burial chapter claims without accepted event identity | Story Craft and consistency legacy writers | story_craft.foreshadow_chain | review, Context | UNKNOWN | Canon owns occurrence | Preserve annotation | Unverified | Does not prove Canon event | Legacy reference pending link | No migration by text/chapter match |
| Foreshadow payoff/burial quality evaluation | Craft/review workflow | story_craft.foreshadow_chain fields | review and Context | CRAFT | Reviewer/craft method | Advisory annotation | Re-evaluable | No factual authority | story_craft Craft subfields | Exact field mapping |
| story_craft.timed_locks description, trigger, deadline | plan skill/CLI | state.json.story_craft.timed_locks; overlay after routing | CLI, review pipeline, chunked gate, Context | INTENT | Author/planner; generated template is proposal | Edit/defer/cancel | Existing active/fulfilled | Deadline miss is plan deviation | story_craft Intent subfields | Auto-generated lock not user-hard by default |
| Legacy timed_locks.fulfilled_chapter without commit reference | Story Craft CLI | Same | review/Context | UNKNOWN | Canon owns occurrence | Preserve | Unverified | No factual fulfillment | Legacy reference pending link | No promotion |
| Commit-linked timed-lock occurrence reference | Accepted event projection | Existing Canon projection | Context | DERIVED_REFERENCE | Accepted Canon source event | Rebuildable | Rebuild with history | Planner record remains separate | Canon-linked reference | No planner write |
| story_craft.rhythm_curve thresholds and history | Craft APIs/review | state.json.story_craft.rhythm_curve | CLI, review pipeline, Context | CRAFT | Craft measurement/recommendation | Mutable/recomputable | ok/warning/block is recommendation only | No Canon interaction | story_craft Craft fields | Existing threshold cannot reject commit |
| story_craft.volume_beat and volume_beats | Craft APIs/plan | state.json.story_craft plus 大纲 beat files | CLI, review, plan/write, Context | CRAFT | Craft framework/author annotation | Editable recommendation | Proposed/filled/advisory | Filled marker is not Canon proof | story_craft Craft fields | Keep V1/V2 schemas; exact map only |
| character_arc desired transformation, end state, explicit milestone | Plan skill/API | state.json.story_craft.character_arc | Context, plan/review | INTENT | Author | Author edit | Proposed/active/stale/satisfied candidate | Canon may diagnose; does not delete plan | story_craft Intent subfields | Legacy nested mapping must be exact |
| character_arc structural quality and evaluation | Plan/review/craft method | Same | review and Context | CRAFT | Craft evaluator/reviewer | Advisory edit | Recommendation/score | No story fact authority | story_craft Craft subfields | Unknown nested values preserved |
| thematic_echoes premise or desired motif | Plan skill/API | state.json.story_craft.thematic_echoes | Context/review | INTENT | Author | Explicit edit | Planned motif | Does not prove occurrence | story_craft Intent subfield | Duplicate target diagnostics |
| Legacy thematic echo chapter/manifestation note | add_thematic_echo and planning | Same | Context/review | UNKNOWN | Canon owns occurrence | Preserve | Unverified | No Canon claim | Legacy reference pending event link | Not bulk promoted |
| Commit-linked thematic echo occurrence | Accepted event reference | Existing Canon projection | Context/review | DERIVED_REFERENCE | Accepted event owns occurrence | Rebuildable link | Rebuild with effective history | Commit remains fact authority | Canon-linked reference | Legacy note remains separate |
| reader_contract expectation debt, causal credits, swap debt | Consistency P6/review | story_craft.reader_contract | consistency, review, Context | CRAFT | Checker/reviewer | Recompute/advisory | Finding lifecycle | No story fact authority | story_craft Craft subfields | No hard gate by default |
| Legacy reader_contract.endgame_reserves without author provenance | Reader-contract patch or legacy plan | Same | Context/plan/review | UNKNOWN | No proven author authority | Preserve | Unverified | No Canon interaction | Legacy reference | No authority inferred from field name |
| Explicitly authored endgame reserve or reveal target | Author plan writer with source identity | Existing story_craft owner path or contract | Context and plan | INTENT | Author | Explicit edit | Plan lifecycle | Canon may inform stale/satisfied status | Intent owner | Exact provenance required |
| Consistency P1–P7 heuristic findings | Consistency patches/runner | Review result and existing craft fields | consistency CLI, review, plan/write | CRAFT | Checker/pipeline | Rerunnable | Finding lifecycle | No Canon authority | Existing Craft/check owner | Phase 10 aligns local severity |
| Consistency generated views | P7 derived-view writer | .webnovel/views and current projection path | consistency CLI and Context | DERIVED_REFERENCE | Source owner projection | Rebuildable | Rebuilt from source | No independent authority | Existing derived-view path | Retain source link |
| Consistency run/apply workflow metadata | consistency CLI/runner | Existing state/workflow result path | plan/write/review | WORKFLOW | Workflow service | Explicit run/apply operation | Per-run | Semantic changes need field owner | Existing workflow owner | Separate from finding |
| chapter_meta hook_type, beat_position, Scene-Sequel fields | Story Craft setter/CLI, review | Legacy state and current review metadata | review, Context, status/dashboard | CRAFT | Author/reviewer craft assessment | Advisory/editable | Per-chapter annotation | Storage does not prove fact | Craft owner/projection | Split mixed root |
| chapter_meta must_cover, forbidden, CBN/CPNs/CEN, planned time/strand/villain targets | Plan/artifact generation and Story Craft setter | Outline/contract; legacy state duplicate | prewrite/fulfillment, Context | INTENT | Author/planner | Editable until accepted/revised plan | Proposed/active/stale/satisfied candidate | Canon may inform satisfaction | Chapter plan owner | Exact source link required |
| Legacy chapter_meta hook/foreshadow occurrence values without commit identity | Legacy state/process-chapter | state.json.chapter_meta | review, memory writer, Context | UNKNOWN | No Canon proof | Preserve | Unverified | Cannot promote to Canon | Legacy reference | Phase 9 root-level Canon label must be split |
| Accepted-commit chapter_meta hook/foreshadow occurrence fields | ChapterCommitService extraction | Accepted commit and generation index | Canon Context, review, memory | CANON | Accepted commit/correction | Effective correction only | Historical event | Defines accepted story event | Canon commit/projection | Legacy values stay UNKNOWN |
| review_checkpoints, run ledger, gate decision events | Review/run workflow | Existing owner overlay and review artifacts | resume/review/write | WORKFLOW | Workflow service | Workflow update/append | Started/completed/resumable | No story fact authority | Existing workflow owner | Do not merge with plan or craft |
| writing_guidance, author style patterns, style contract, reader metrics | Author/config/review systems | Existing config/context sources | Context, review, Writer | CRAFT | Craft source/reviewer | Configurable; heuristic results advisory | Active/superseded/score | Never fact evidence | Existing Craft/config owner | Keep provenance |
| Author preferences | Author config | Existing preference source | Context and Writer | PROJECT_CONFIG | User | Explicit configuration edit | Project lifetime/versioned | No Canon authority | Existing config owner | Separate from generated recommendations |
| Selected project genre and tags | Project init/config | project_info and Context source sections | planning/templates/Context | PROJECT_CONFIG | User selection | Explicit config edit | Project configuration | No Canon authority | project_info owner | Separate reference profile |
| Reference genre/craft profile advice | Reference profile source/Context builder | Read-only reference files and Context projection | plan and Context | CRAFT | Craft reference | Read-only source; advisory presentation | Advisory | No Canon authority | Existing reference source | User selection remains separate |
| progress.current_chapter and progress.total_words | Canon projection and legacy StateManager compatibility path | Canon generation when enrolled; legacy state projection otherwise | status, gates, dashboard | DERIVED_REFERENCE | Accepted commit projection | Recomputed | Progress projection | Never creates Canon | Canon generation | Preserve Phase 9 boundary |
| progress.chapter_status | Commit projection for committed status; workflow service for draft/review/reject | Canon generation and workflow metadata | status, gates, dashboard | WORKFLOW | Workflow transition except committed projection | Workflow transition | Draft/review/reject/committed | Status alone never creates Canon | Existing workflow path | Preserve field-level Phase 9 split |
| Unknown state roots and unrecognized nested fields | Legacy writers/migrations | Original state/contract files | Compatibility readers | UNKNOWN | None assigned | Preserve only | Unknown | No Canon authority | Legacy/reference quarantine | Fail closed; never bulk move/delete |

## 5. Current duplicate ownership graph

~~~mermaid
flowchart TD
  E[Accepted StoryEvent in CHAPTER_COMMIT] --> R[intent_reconciliation]
  R --> M[Canon-derived memory projection]
  M --> C[Context INTENT today, generic provenance]
  P[Planner Promise Ledger in project_info] --> C
  F[story_craft.foreshadow_chain] --> C
  T[story_craft.timed_locks] --> C
  V[state.json volumes and horizon] --> O[Outline files]
  O --> S[Story System contracts]
  S --> C
  B[story_craft volume beats] --> Q[Plan/review/CLI checks]
  BM[Outline beat files] --> Q
  CM[legacy chapter_meta] -->|mixed root| C
  CC[accepted commit chapter_meta] --> G[Canon generation/index]
  CM --> G
  G --> C
  SC[story_craft whole root] --> X[state-overlay.json when routed]
  SC --> L[legacy state.json direct CLI write]
  X --> C
  L -. activation view may ignore .-> C
~~~

### Duplicate/conflict pairs requiring explicit identity and diagnostics

| Sources | Current overlap | R0 rule |
|---|---|---|
| Canon-derived Promise/Open Loop projection ↔ planner Promise Ledger | Both contain promise/loop content, status, and payoff concepts. | Distinct IDs and lifecycles; explicit cross-reference only. Never text-match or synchronize. Conflict diagnostic reports both owners and values. |
| Promise Ledger ↔ story_craft.foreshadow_chain | Both model planted/payoff chapters, status, and type. | Keep types distinct. Legacy row-to-row linking requires explicit IDs; no merging by content/chapter. |
| Foreshadow chain ↔ timed locks | Both are future-facing and reviewed for deadline. | Keep separate: payoff chain vs deadline constraint. A lock may refer to a foreshadow ID but does not own its payoff state. |
| `volumes[]` ↔ outline volume rows ↔ VOLUME_BRIEF | Conflict/climax/targets can repeat. | Confirmed volume record owns volume-level summary decision; outline/brief reference it or carry an explicitly authored scoped expansion. Mismatch diagnostic, no silent winner except source-qualified derived rendering. |
| CHAPTER_BRIEF ↔ chapter outline ↔ chapter_meta plan fields | Chapter goals and required nodes repeat. | Chapter plan contract/outline owns explicit plan; chapter_meta duplicate is compatibility projection unless it has exact source identity. Conflict is Intent vs Intent, requiring planner resolution. |
| Story Craft volume beats ↔ beat markdown files | Same method/beat positions in JSON and files. | Existing explicit source-of-writeback must be documented; rendered copy is derived. Author-edited unmarked content is preserved and conflicts block automated overwrite. |
| chapter_meta state root ↔ commit extraction chapter_meta ↔ generation index | Same root mixes plan, Craft and actual chapter metadata; Phase 9 inventory treats root as Canon. | Split by field and provenance. Only commit-backed fields are CANON; plans remain INTENT and method annotations CRAFT. Legacy unlinked state values are UNKNOWN. |
| Thematic echo chapter notes ↔ accepted story events | Notes can claim a theme appeared in a chapter. | Note remains reference until linked to a validated accepted event; never promotes Canon. |
| `project_info.confirmed_through_volume` ↔ volume statuses | Cached derived value duplicates max confirmed status. | Volume record is source; horizon is recomputed derived reference. |
| `cross_volume_beat_map` ↔ adjacent confirmed volume plans | Generated map repeats volume relationships. | Derived reference with source digest/identity; rebuild or diagnose drift. |
| Consistency finding ↔ Craft field ↔ generated view | P1/P7 can inspect or update both state and view. | Finding is advisory evidence; view is derived; semantic state mutation must go through declared owner API. |

## 6. Intent taxonomy and lifecycle candidate

Intent records author/planner choices about future story content. Distinguish: project-level decisions; volume/chapter plans; explicit user constraints; planner-owned obligations; and authored foreshadow/timed-lock plans. These remain separate variants with explicit owner and source identity.

R0 lifecycle proposal: do not impose one enum. Keep existing exact per-model status where valid. Add only the minimum distinctions needed by implementations: a planner item may be proposed/confirmed/active/deferred/cancelled/satisfied/stale; satisfaction is an assessment, not deletion, and only an explicit planner action may cancel or alter a deadline. Exact enum and transition table remain an implementation-review item because existing Promise Ledger and Story Craft statuses differ. Existing items are not bulk-renamed in R0.

`character_arc` desired change and `thematic_echoes.premise` are Intent only when explicitly authored as target. Evaluations, echo quality, or notes that a chapter manifested something are Craft/UNKNOWN unless linked to Canon evidence. A source's JSON location never decides semantic class.

## 7. Craft taxonomy and lifecycle candidate

Craft is advice, methodology, craft structure, evaluation, or quality score. It includes rhythm curves, generated 15-beat sheets, Scene-Sequel checks, hook variety/type advice, quality/style heuristics, reader expectation debt, and unverified craft observations. These may be accepted, rejected, scored, superseded, or recomputed by their own UI/workflow, but do not acquire an obligation lifecycle or fact-blocking severity from their storage field.

The following do not become factual blockers solely through a legacy BLOCKER label: missing/unfilled Save-the-Cat beats, rhythm thresholds, overdue timed locks, Scene-Sequel checklist omissions, hook_type missing, foreshadow-depth counts, style/anti-AI/quality heuristic results. Explicit user constraints can still be hard only when the existing stable contract-binding path proves user authority. A plan-stage workflow may pause for a missing required artifact or unresolved decision as WORKFLOW; it must state the artifact/process reason rather than claim Canon inconsistency.

## 8. Canon-derived obligation model

Keep `intent_reconciliation.py` as deterministic event-to-lifecycle derivation, not as a mutable owner. Inputs must be the effective accepted event stream in canonical order. Creation and resolution identity remains explicit event/loop/promise IDs; exact-unique historical matching remains compatibility-only. Ambiguity, orphan close, duplicate resolution, or missing source identity remains diagnostic and does not select a winner.

The durable authority is the accepted commit/effective correction lineage. The lifecycle projection is rebuildable and may be physically stored in the existing Canon projection generation or current memory read model; R0 does not add a database. Context must label the item as CANON_DERIVED_OBLIGATION, identify the source event(s), and expose it under INTENT without representing it as a new past event. Correction replay recomputes it. Planner actions cannot resolve it.

## 9. Planner-owned obligation model

The planner Promise Ledger stays at its current owner boundary pending exact Phase 10 writer routing. Author/planner may edit its expected payoff/deadline, priority if present, defer/cancel, and planner lifecycle. A canonical cross-reference is an opaque exact event/obligation ID, optional and non-authoritative in the planner record. It cannot change Canon lifecycle.

If Canon reports a payoff while a planner ledger stays active/overdue, Context emits an Intent-vs-Canon-derived-obligation diagnostic and may report the planner row as stale/satisfied candidate. It does not auto-pay off or delete the planner row. If the planner changes its deadline while Canon remains active, only planner presentation changes. If cross-references disagree or resolve ambiguously, preserve both and show an unresolved link diagnostic.

## 10. Promise, Open Loop, Foreshadow, and Timed Lock decisions

| Type | Creation authority | Target/deadline | Resolve/fulfill authority | Cancellation/defer | Canon linkage | Model decision |
|---|---|---|---|---|---|---|
| Story promise event | Accepted chapter commit | Optional event payload target; not a planner schedule | Accepted promise_paid_off event; correction changes effective history | Not planner-controlled | Intrinsic source event ID | CANON event |
| Canon-derived reader promise | Event reconciliation | Event target is descriptive; not automatically a deadline | Derived from accepted payoff event | Only effective Canon correction can invalidate the event-derived lifecycle | Required source event and resolution event IDs | Distinct rebuildable projection |
| Planner Promise Ledger | Author/planner | Explicit expected payoff chapter/volume | Planner records plan state; only Canon evidence may label factual outcome | Planner-owned explicit action | Optional exact cross-reference | Distinct Intent record |
| Canon open-loop event/projection | Accepted event and reconciliation | Optional target chapter/urgency | Accepted close event | Canon correction only | Required source IDs; exact-unique historical linking stays compatibility-only | Canon event plus derived projection |
| Story Craft foreshadow chain | Author/planner | Optional expected payoff chapter; depth/type | Planner annotation today; factual payoff requires accepted Canon reference | Explicit planner choice; no inferred cancellation | Optional explicit link | Intent plan, not same as Canon loop |
| Timed lock | Author/planner or an unconfirmed template generator | Explicit deadline chapter; may be based on craft beat | Planner may close planning item; claim of story occurrence needs accepted event | Planner defer/cancel; missed deadline is advisory deviation | Optional explicit Canon event link | Intent constraint; template rows are unconfirmed proposal |
| Volume/chapter target | Author/planner | Scoped target in contract/outline | Plan fulfillment assessment against accepted commit | Author revise/defer | Plan source path and commit evidence on satisfaction | Intent |
| Rhythm/beat/style recommendation | Craft framework/checker | Recommendation window/score threshold | Recompute/review/dismiss | Dismiss/supersede as craft advice | No required Canon link | Craft, advisory/score |

Therefore R0 selects distinct owners composed by Context. There is no common NarrativeObligation authority, shared persistence, common status enum, or automatic linkage.

## 11. Story Craft field-by-field split

| Field path | R0 class | Owner / authority | Gate and migration rule |
|---|---|---|---|
| foreshadow_chain planned setup/payoff fields | INTENT | Author/planner | Exact recognized schema only; generated placeholders remain unconfirmed |
| Legacy foreshadow payoff/burial chapter claim without accepted event identity | UNKNOWN | Canon owns occurrence | Preserve; no content/chapter matching |
| Foreshadow payoff/burial quality evaluation | CRAFT | Reviewer/craft method | Advisory annotation |
| timed_locks description, trigger, and deadline | INTENT | Author/planner | Deadline miss is advisory; generated template is a proposal |
| Legacy timed_locks fulfilled_chapter without commit reference | UNKNOWN | Canon owns occurrence | Preserve; no factual promotion |
| Commit-linked timed-lock occurrence reference | DERIVED_REFERENCE | Accepted Canon source event | Rebuildable; planner record remains separate |
| rhythm_curve fields and history | CRAFT | Craft measurement/reviewer | Advisory/score; threshold cannot reject Canon commit |
| volume_beat and volume_beats fields | CRAFT | Craft framework and author annotation | Advisory; explicit required story beat is a separate Intent contract node |
| character_arc desired transformation, end state, milestones | INTENT | Author | Canon may diagnose stale/satisfied; keep plan |
| character_arc structural quality/evaluation | CRAFT | Reviewer/craft method | Advisory; unknown nested values preserved |
| thematic_echoes premise or desired motif | INTENT | Author | Future target only |
| Legacy thematic_echoes chapter/manifestation note | UNKNOWN | Canon owns occurrence | Preserve; no import as Canon |
| Commit-linked thematic echo occurrence | DERIVED_REFERENCE | Accepted event identity | Rebuildable link; source event remains authority |
| reader_contract expectation_debt, causal credits, swap debt | CRAFT | Checker/reviewer | Advisory or score |
| Legacy endgame_reserves without author provenance | UNKNOWN | No proven author authority | No authority inferred from field name |
| Explicitly authored endgame reserve/reveal target | INTENT | Author | Exact source identity required |
| volume_anchors, event-matrix recommendations, pacing history | CRAFT | Patch/checker | Advisory; explicit authored targets are separate Intent fields |
| chapter_meta hook_type, beat_position, Scene-Sequel fields | CRAFT | Author/reviewer | Missing heuristic field cannot hard block |
| chapter_meta must_cover, forbidden, CBN/CPNs/CEN, planned time/strand/villain targets | INTENT | Plan owner | Source reference required when copied from contract |
| Legacy chapter_meta hook/foreshadow occurrence values without commit identity | UNKNOWN | No Canon proof | Preserve as reference |
| Accepted-commit chapter_meta hook/foreshadow occurrence fields | CANON | ChapterCommitService | Effective correction only; legacy root cannot promote |
| Other story_craft keys or unknown nested fields | UNKNOWN | Unassigned | Preserve and diagnose; do not inherit root class |

Mixed-container policy: migration and Context split by explicit subfield identity. If a legacy object does not match a recognized schema, retain the original object as REFERENCE/UNKNOWN and require an explicit decision. Do not divide nested content by keyword or guess from prose.

## 12. Persistence target and writer ownership

No new store is proposed. Canon stays in accepted chapter commits and effective correction history; Canon-derived obligation rows remain a rebuildable projection; mutable state fields use the existing owner overlay on enrolled projects; existing contract JSON/outline artifacts remain their established authored paths; operational lifecycle stays in existing workflow records.

| Semantic data | Authoritative writer family after Phase 10 | Existing target path |
|---|---|---|
| Canon event/factual chapter metadata | ChapterCommitService and authorized correction resolver | `.story-system/commits/` and effective generation |
| Canon-derived obligation | Deterministic effective-event reconciler/projection builder only | Existing generation/memory projection; no planner write API |
| Planner Promise Ledger, volume decisions, story_craft Intent fields | Typed planner owner operations, routed to OwnedStateStore when enrolled | Existing `project_info`, `volumes`, `story_craft` overlay roots; legacy state source retained for base-only compatibility |
| Story System contracts/outlines | Existing plan/contract writer family | `.story-system/*.json` and `大纲/` authored files |
| Craft values/findings | Craft API/checker writer family | Existing craft owner path and review artifacts |
| Workflow checkpoints/review decisions | Existing workflow/review services | Existing workflow owner and review artifacts |
| Derived volume horizon/cross-volume map | Existing deterministic rebuild from volumes | Current project_info cache/artifact path, explicitly marked derived |

`webnovel.py::cmd_story_craft` currently writes the legacy state file directly. Phase 10 implementation must route it through the active owner view and reject writes that bypass an enrolled overlay. Volume planning/initialization callers and consistency apply need equivalent routing or explicit base-only compatibility guards. No semantic field should be dual-written to overlay and state.json. `OwnedStateStore` remains the physical persistence boundary, not the policy engine; domain-specific writer families continue to own transitions.

## 13. Context target model and conflict semantics

Context output remains a read-only composition. Candidate envelope fields are: semantic class, stable item identity when known, owner reference, source reference(s), provenance status, chapter/scope, and display payload. For derived obligation rows, semantic class is CANON_DERIVED_OBLIGATION while presentation section is INTENT. This is Context metadata only and does not create an obligation registry.

| Section | Content | Authority treatment |
|---|---|---|
| CANON | Accepted effective history and exact Canon-backed facts/events | Only accepted commit/correction lineage establishes past fact. |
| INTENT | Explicit planner decisions, contracts, outlines, active planner obligations, and Canon-derived obligations with origin labels | Multiple sources remain separate. Intent never overwrites Canon; Canon does not silently delete plan. |
| CRAFT | Rhythm, structure, style, reader signals, methodology, and quality advice | Advisory/score unless a separate exact user-constraint binding proves elevation. |
| REFERENCE | Legacy/unknown items, summaries, retrieval hits, compatibility copies | Useful with labels; no authority inferred from similarity, location, or recency. |

Conflict rules:

- Canon vs Intent: retain both; report whether Intent is stale, possibly satisfied, or contradictory; do not alter Canon or delete plan.
- Intent vs Intent: exact identity plus different payload emits `intent_conflict`; require planner resolution. Never select by path order, newest timestamp, or last write.
- Intent vs Craft: explicit Intent wins; keep the Craft item as advisory and report the disagreement when useful.
- Canon-derived obligation vs planner ledger: keep separate; explicit links show cross-owner mismatch, never synchronize.
- Duplicate rows with same exact owner and same stable identity/value may be presentation-deduplicated only while retaining all provenance refs. Different owner or unknown identity is not silently merged.
- Missing owner/provenance or malformed source yields UNKNOWN/REFERENCE and diagnostic; it cannot be treated as an authoritative hard constraint.

## 14. Lifecycle, writer API, and failure behavior

R0 does not mandate one lifecycle enum. Each model retains its existing valid lifecycle until its writer and reader transition matrix is ratified in implementation review. Required invariants:

- Planner deadline/defer/cancel affects only planner record.
- Canon-derived fulfilled/resolved is reconstructed only from effective Canon events and corrections.
- Craft recommendation lifecycle never implies story obligation.
- Workflow status never implies story fact.
- Semantic changes use one owner writer family and carry actor/source/identity evidence appropriate to that owner.
- Missing overlay, stale pinned view, invalid owner path, or conflicting copy fails closed for mutation; readers preserve the source and surface diagnostics.
- Partial migration never deletes the legacy source. Rollback restores the pre-migration source/overlay manifest and leaves accepted commits/correction history untouched.

### Required owner API behavior (candidate, not a frozen signature)

Planner operations should be typed by existing domain (volume, Promise Ledger, Story Craft Intent), validate stable IDs and allowed transitions, and commit only to that domain's current owner root. Craft operations may edit Craft-owned fields but cannot change Intent lifecycle or Canon. Projection generation may write derived rows but cannot accept owner commands. Generic owner-root writes remain guarded by field inventory/ownership checks at the service boundary.

## 15. Migration strategy and compatibility window

Migration is design-only in R0. Proposed stages:

1. **Inventory/preflight:** hash inputs and record exact JSON paths, types, recognized schema versions, owner mapping, reader/writer evidence, and conflicts. No writes on dry-run.
2. **Deterministic mapping:** map only enumerated field paths and exact known schemas. Extend Phase 9 inventory for nested `project_info.promise_ledger`, split `chapter_meta` by exact subfield/provenance, and map recognized Story Craft fields separately. Preserve every unrecognized value as UNKNOWN/reference.
3. **Ambiguity review:** require explicit author decisions for duplicate Promise/Foreshadow items, unlinked echo/payoff claims, malformed/unknown Story Craft shapes, mismatched volume/outline/contract plans, mixed memory evidence, and chapter_meta values with no commit/source identity.
4. **Backup and apply:** use existing Phase 9 backup/activation/rollback machinery; preserve source bytes and hashes; write to overlay/owner target once; retain legacy source as read-only compatibility evidence. Do not delete or normalize old values during the first migration.
5. **Parity/read audit:** compare source identities and rendered Context sections; conflicts stay visible and block authority promotion, not necessarily reading.
6. **Retire legacy writers only after adoption:** guard direct writes for enrolled projects, retain base-only compatibility until migration coverage and rollback criteria pass.

Project classes:

| Project state | R0 handling |
|---|---|
| Base-only project | Continue exact existing files; add compatibility adapters/diagnostics in implementation. Do not force Phase 9 enrollment as Phase 10 prerequisite. |
| Phase 9 enrolled project | Overlay is owner-state write target; do not let state.json-only Story Craft CLI appear successful. Preserve the immutable pinned Canon generation. |
| Old state.json | Keep byte/hash-preserved; exact known field mapping only; unknown root/nested paths become explicit conflicts. |
| Existing Promise Ledger | Map only exact ForeshadowEntry schema and known legal statuses. Do not link to event promises by matching wording. |
| Existing volumes/project_info | Map recognized field paths. Derive horizon fields from source volumes; flag duplicate plan facts instead of picking a copy. |
| Existing story_craft | Split exact known fields. Unknown or mixed nested shape remains preserved reference and requires human selection. |
| Old Open Loop projection/memory | Rebuild Canon-derived items from accepted commits/effective corrections; owner-only legacy rows remain reference unless exact source identity confirms lineage. |
| Unknown fields | Preserve source; no mutation, deletion, or authoritative Context promotion. |

The compatibility window ends per path only after all production writers/readers use the assigned owner, migration has zero unresolved conflicts for that path, round-trip/parity checks pass, rollback has been exercised, and no supported installed skill invokes the old writer. R0 does not set dates or delete files.

## 16. Gates and skill prose findings

### Shared GateSeverityPolicy paths already handled

`gate_finding_adapters.py` registers Story Craft heuristic, volume beat, rhythm, timed lock, Scene-Sequel, and hook-type findings as CRAFT. `GateSeverityPolicy` makes CRAFT/STYLE advisory or score and makes ordinary planner misses non-blocking. Valid explicitly bound user constraints and deterministic Canon contradictions retain their separate severity routes. This is the desired policy boundary; Phase 10 should preserve it.

### Local craft blocks that remain outside or bypass that policy

| Path | Current behavior | Phase 10 disposition |
|---|---|---|
| `review_pipeline.py` | Emits `blockers` for beat coverage, rhythm threshold, overdue timed lock, missing Scene-Sequel fields and hook type. Adapter maps the structured rows to CRAFT, but downstream skill prose also treats critical/blocking as rewrite. | Phase 10 implementation: align output and write skill interpretation so these are advisory unless an exact user hard constraint is bound. Do not restructure all gate infrastructure. |
| `webnovel.py story-craft check-volume` | Returns exit code 1 for craft blockers, including deep-foreshadow count and missing generated outline artifacts. | Phase 10 implementation: craft heuristics return advisory/score; missing required plan artifact may remain a WORKFLOW precondition with distinct code/reason. |
| `webnovel-write/SKILL.md` Step 0.5 | Chunked-write gate exits before writing when planner foreshadows are overdue. | Phase 10 implementation: make default advisory/author choice; permit blocking only for explicit user-bound Intent constraint. |
| `webnovel-write/SKILL.md` review steps | Says critical/blocking from tools triggers whole chapter rewrite, including mixed craft/style outputs. | Phase 10 implementation: interpret canonical/user/integrity blockers separately; Craft/style stays advisory. |
| `webnovel-plan/SKILL.md` beat/foreshadow quantity requirements | Plan steps enforce method-specific quantities and pause for author adjudication; prose says not GateSeverityPolicy. | Keep user-selected planning workflow checks as WORKFLOW prompts; do not treat counts as Canon or chapter-commit hard blockers. Later cleanup may rationalize style methodology. |
| `webnovel-plan/SKILL.md` missing plan artifacts / unresolved plan decisions | Hard-fails planning task when required files are absent or an explicit planning decision is unresolved. | Keep scoped WORKFLOW integrity/precondition gates; clarify these do not assert story fact or general Craft quality. |
| `consistency/cli.py apply` and P1–P7 | Can mutate state Craft fields and derived files. | Phase 10 implementation: route through field owner; permit derived refresh, require owner-specific explicit path for semantic change. Broader patch/test reorganization is later cleanup. |
| `prewrite_validator.py` | Blocks missing contracts, placeholders, and high-priority disambiguation. | Retain contract/integrity/user-decision reasons as distinct classes; do not relabel as Craft. Scope changes only where a heuristic has been folded into these conditions. |

Gate normalization beyond these direct Intent/Craft ownership leaks is explicitly outside Phase 10. Full shared severity redesign and unrelated anti-AI/style pipeline cleanup remain later Issue #1 work.

## 17. Failure and recovery behavior

- Invalid or unknown field schema: preserve source and return explicit migration conflict; do not partially reinterpret that container.
- Conflicting copies with known same identity: expose both owner references and conflict; block automated selection or overwrite.
- Missing explicit cross-reference: keep records separate; no text matching.
- Owner overlay write failure: no success response; keep pending source and allow retry under existing atomic write/backup semantics.
- Activation-managed direct legacy state write: fail or clearly report compatibility-only/no effective mutation; never report persisted success if active Context will ignore the write.
- Canon correction: regenerate affected derived obligation projections from effective history; planner values and source artifacts remain unchanged.
- Derived projection unavailable/stale: expose recovery diagnostic; do not downgrade Canon or mutate planner lifecycle.
- Rollback: restore backed-up overlay/source bytes; do not reverse accepted commits/corrections or rewrite their history.

## 18. Proposed implementation slices

1. Extend ownership inventory and schema catalog with field-level Intent/Craft/Workflow/config/derived mappings; add fail-closed diagnostics for unknown fields.
2. Define planner obligation and Canon-derived obligation reference fields separately; preserve lifecycle-specific writers and prohibit synchronization.
3. Add explicit Canon-derived obligation provenance in projection and Context; correction replay rebuilds only the derived projection.
4. Route planner Promise Ledger, volume and Story Craft Intent mutations through the correct active owner path; reject direct legacy writes for enrolled projects.
5. Split Story Craft field ownership and mixed chapter_meta classification; migrate only exact known schemas, preserve unknowns.
6. Add Context owner/provenance identity, deterministic duplicate/conflict diagnostics for Intent/Craft, and Intent-over-Craft presentation precedence.
7. Align direct craft blockers in review/CLI/skill prose with existing GateSeverityPolicy; retain distinct workflow/integrity preconditions.
8. Add base-only/enrolled migration dry-run, backup, parity, rollback and compatibility-retirement criteria; update only directly affected architecture instructions.

These are candidate slices; sequence and exact APIs require independent review. No implementation is started by this spec.

## 19. Acceptance tests for implementation

1. Accepted promise/open-loop create and close events yield the correct derived lifecycle; rejected/draft events yield none.
2. A correction that changes/removes a create/close event deterministically rebuilds only Canon-derived lifecycle and leaves planner ledger bytes unchanged.
3. Planner deadline/defer/cancel operations do not alter event-derived resolved status; Canon payoff does not silently alter planner status/deadline.
4. Explicit cross-reference is preserved; missing, ambiguous, stale, or conflicting links emit diagnostics without content-match fallback.
5. Story Craft Intent and Craft field writes target their own owner paths; unknown fields are rejected or preserved as non-authoritative, never misclassified by root.
6. `chapter_meta` plan, craft and factual fields are separated; legacy unlinked rows do not enter Canon; accepted commit-backed facts remain Canon.
7. Intent-vs-Intent conflicts are visible; Context does not select by time/order. Intent wins over Craft recommendations without discarding either source.
8. Duplicate same-identity/same-value rows may be display-deduplicated only with every provenance reference retained.
9. Craft/style/quality threshold findings cannot reject a chapter commit or trigger mandatory rewrite by default; explicit user constraint remains hard only with stable contract evidence.
10. Missing plan artifacts and disambiguation integrity remain distinctly classified WORKFLOW/integrity checks.
11. Base-only migration and Phase 9 enrolled migration both preserve original bytes, report unknown values, and support verified rollback.
12. `/根源牌序` chapter 1/2 remains REFERENCE-only and `_rerun_at` remains `UNKNOWN / PRESERVED / NOT IMPORTED`.
13. Phase 9 activation writes become visible from pinned overlay reads; old state.json-only mutation is rejected/guarded rather than falsely succeeding.

## 20. Explicit non-goals

- No production code, schema, lifecycle enum, migration, or gate behavior is changed in R0.
- No unified NarrativeObligation authority, shared obligation status, or new Intent/Craft registry/store/database.
- No Issue #1 edit, PR, merge, release, broad docs rewrite, or cleanup of legacy paths.
- No change to Canon correction architecture, Phase 9 immutable generation/publication/recovery, accepted commit boundary, or `/根源牌序` option B.
- No comprehensive GateSeverityPolicy refactor; only direct craft ownership leaks are listed for Phase 10 implementation.
- No deletion of legacy state, Story Craft paths, outline artifacts, or installed skill compatibility.

## 21. Open design questions for independent review

1. Should planner-only `fulfilled` be renamed to `satisfied_by_plan` or retained as an annotation distinct from Canon-derived `resolved`? Exact status vocabulary is intentionally not frozen.
2. What minimum stable ID and source reference must be required for existing planner Promise Ledger rows that currently have IDs but no Canon cross-reference?
3. Which exact recognized Story Craft schema versions exist in supported user projects, beyond fields found in current source/tests? Unknown shapes must remain fail-closed.
4. Should ContextItem gain an explicit owner field, or should a typed owner reference be added through a Context-only envelope while preserving the public Context v3 shape during a compatibility window?
5. Should `.story-system` authored contract files be versioned with content digests/source identities to diagnose duplicate state/outline values, or is existing file provenance sufficient for R0 implementation?
6. Which existing project_info fields are live and user-authored versus compatibility cache fields? `_owner_inventory` currently recognizes only a subset and deliberately conflicts on unknown values.
7. Can chapter_meta be split without altering compatibility consumers that expect one root, and which exact fields are projected from accepted commits in every production path?
8. What compatibility period and measurable adoption threshold should precede retirement of direct state.json Story Craft writers and legacy plan adapters?

## 22. Audit scope and evidence paths

Primary production paths inspected on baseline main (all active-source paths, excluding immutable 6.4.0 snapshot):

- `scripts/data_modules/{volume_state.py,promise_ledger.py,intent_reconciliation.py,state_manager.py,webnovel.py,owned_project_view.py,project_migration.py}`
- `scripts/{story_craft.py,migrate_story_craft.py,init_project.py,update_master_outline.py,update_state.py,story_system.py}`
- `scripts/data_modules/{story_contracts.py,story_runtime_sources.py,context_provenance.py,context_manager.py,memory_contract_adapter.py,memory/writer.py,gate_severity_policy.py,gate_finding_adapters.py,prewrite_validator.py,write_gates/*}`
- `scripts/{review_pipeline.py,consistency/cli.py,consistency/core/runner.py,consistency/patches/p1_foreshadow_dag.py,p2_volume_anchor.py,p3_event_matrix.py,p4_pacing_tracker.py,p5_state_revision.py,p6_reader_contract.py,p7_derived_views.py}`
- `skills/webnovel-{init,plan,write,review,resume}/SKILL.md`, `agents/context-agent.md`, chapter outline/runtime callers, and Issue #1.

Tests were not run; this is a read-only architecture audit. No implementation claim is made.
