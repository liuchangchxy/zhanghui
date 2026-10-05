# Phase 6A — Shared Gate Findings and Deterministic Severity Policy

## Status and intent

This is the Phase 6A architecture design for replacing split review/fulfillment/disambiguation veto interpretation with one shared finding envelope and deterministic severity policy. The approved direction is **Option B: shared finding envelope + deterministic severity policy + compatibility adapters**. This phase does not create a unified `GateService`.

The purpose is to make a chapter's final commit decision reproducible and explainable. The durable chapter commit boundary remains owned by `ChapterCommitService`; policy output is persisted as workflow/infrastructure audit data and is recomputed by the commit service from structured findings.

## Existing contracts and verified boundaries

- `.story-system/MASTER_SETTING.json`, chapter JSON, volume JSON and review JSON are already addressed by `StoryContractPaths` in `scripts/data_modules/story_contracts.py`.
- Contract layering currently exposes `locked`, `append_only` and `override_allowed`; the JSON payloads allow node-level metadata to be extended without a separate global constraint registry. Phase 6A should add an optional, versioned `metadata` object to an existing contract node when the node is a user-authored constraint. Its fields are `constraint_id`, `authority: USER_EXPLICIT`, `explicitness`, and `source_ref`. The existing contract's identity and scope remain authoritative. No new global `UserConstraint` registry is introduced.
- `ChapterCommitService.build_commit()` currently validates typed review, fulfillment and disambiguation artifacts, then rejects based on `review.blocking_count`, missed fulfillment nodes, and pending disambiguation. The shared policy replaces these independent veto interpretations at this boundary.
- `ReviewResult` currently requires only `blocking_count`; fulfillment has planned/covered/missed/extra arrays; disambiguation has `pending`. This is the legacy surface to be adapted, not the target finding model.
- Canon facts and chapter decision ownership remain governed by the architecture constitution: rejected decisions are workflow records, accepted facts enter Canon only through a durable chapter commit.

## Core data model

### Controlled dimensions

`category` describes the kind of issue. It is a closed enum and is distinct from `authority`, which describes provenance and standing. The Phase 6A category set is:

| Category | Meaning |
| --- | --- |
| `INTEGRITY` | Invalid, stale, mismatched, or unverifiable inputs/artifacts that compromise safe processing |
| `CANON_CONTRADICTION` | A proposed fact contradicts established Canon under deterministic evidence |
| `USER_CONSTRAINT` | A violation of an explicit user-authored contract constraint |
| `DISAMBIGUATION` | An unresolved entity, identity, or referent needed for safe acceptance |
| `INTENT_FULFILLMENT` | A required planned node or declared goal was not fulfilled |
| `CRAFT` | Craft, pacing, structure, or heuristic quality finding |
| `STYLE` | Voice/style conformity finding |
| `PROJECTION_HEALTH` | Projection/recovery state that affects the ability to safely proceed |
| `WORKFLOW` | Missing or invalid workflow prerequisite or approval |

`authority` is a separate closed enum: `SYSTEM_INTEGRITY`, `ACCEPTED_CANON`, `USER_EXPLICIT`, `AUTHOR_PLAN`, `PLANNER_GENERATED`, `CRAFT_HEURISTIC`, `LLM_REVIEW`, `LEGACY_UNKNOWN`. Unknown values are rejected by schema validation; adapters must explicitly map known legacy sources to one of these values.

`explicitness` is `EXPLICIT`, `IMPLICIT`, or `UNKNOWN`. It is not a severity and does not imply user authority by itself.

### DetectedFinding

`DetectedFinding` is a source-neutral record of what a checker observed. Minimum fields:

```text
finding_id
gate_id
category
authority
explicitness
subject_id (optional)
constraint_id (optional)
scope (project/chapter/workflow scope)
evidence[] (typed, structured references and observed values)
source_ref (optional)
checker_id / checker_version
suggested_severity (optional hint; never authority)
detected_at
```

Evidence is structured (for example contract node ID, canonical event ID, artifact path plus content digest, chapter span, expected/observed value). A prose `message` may be carried for display, but policy and identity must never classify findings from its contents. `finding_id` is stable across retries and rewrites according to the contract below.

### GateDecision

`GateSeverityPolicy.evaluate(findings, policy_version, scope)` deterministically emits a `GateDecision` for each finding plus an aggregate workflow action. Each persisted decision includes:

```text
finding_id
effective_severity
effective_action
policy_version
policy_reason
rule_id
decision_scope
evaluated_at
evidence_fingerprint
input_fingerprint
```

`GateDecision` is Workflow / Infrastructure audit data, not Canon. The **sole authoritative owner** is a versioned per-attempt workflow decision artifact adjacent to the review/commit artifacts (under `.story-system/reviews/` through `StoryContractPaths`). It is append-only per attempt; a retry adds a new artifact and does not rewrite the previous explanation. `CHAPTER_COMMIT` contains only a reference to this record and its binding fields (`gate_decision_ref`, `input_fingerprint`, `policy_version`, `final_action`). It never duplicates the full effective decisions and is not a second GateDecision owner. The original checker findings remain separately available as `DetectedFinding` input records.

Changing the active policy version affects new evaluations only. Historical `GateDecision` records remain interpretable under the exact saved `policy_version`, `rule_id`, input fingerprint and reason; replaying a newer policy creates a new decision attempt rather than silently redefining an old one.

## Severity and action policy

Severity is a deterministic policy output, not a checker declaration:

```text
category + authority + explicitness + structured evidence
    → effective severity + effective action + rule_id + reason
```

`effective_severity` is one of `HARD_INTEGRITY`, `HARD_CANON`, `HARD_USER`, `HUMAN_DECISION`, `RECOVERABLE`, `ADVISORY`, or `SCORE`. `SCORE` carries a numeric value and score kind (for example pacing, hook, style, or satisfaction); it is a continuous quality signal and never a veto by itself. The aggregate action is one of `REJECT`, `REQUIRE_HUMAN`, `RECOVER`, or `ALLOW_WITH_ADVISORY`.

Policy rules, in precedence order:

1. Invalid/stale/mismatched artifacts or unsafe identity/evidence bindings with deterministic proof are `HARD_INTEGRITY` / `REJECT`.
2. `HARD_CANON` requires all of: category `CANON_CONTRADICTION`; authority `ACCEPTED_CANON`; deterministic linkage to accepted Canon identity; and deterministic contradiction evidence produced by a trusted validator. `LLM_REVIEW` alone can never produce `HARD_CANON`, even if it supplies category, evidence text, or suggested severity. Without a deterministic contradiction validator, an LLM candidate is `HUMAN_DECISION` when it is material and unresolved, otherwise `ADVISORY`.
3. `USER_CONSTRAINT` can produce `HARD_USER` / `REJECT` only when `USER_EXPLICIT`, `EXPLICIT`, and evidence points to an existing contract node carrying a stable `constraint_id` and `source_ref`. Implicit or unproven user standing cannot create a hard veto.
4. Unresolved disambiguation with a stable subject/evidence reference is `HUMAN_DECISION` / `REQUIRE_HUMAN`; a completed resolution removes it from the current finding set.
5. `INTENT_FULFILLMENT` with `AUTHOR_PLAN` or `PLANNER_GENERATED` authority always maps to `ADVISORY` or `SCORE`. Ordinary intent misses can never produce `REJECT`, `HARD_USER`, or `HUMAN_DECISION`. A missed node may be treated as a `USER_CONSTRAINT` finding with `HARD_USER` only when deterministic linkage proves all of: `authority=USER_EXPLICIT`, `explicitness=EXPLICIT`, stable `constraint_id`, and present `source_ref`. A field name such as `must_cover_nodes` does not grant authority; planner-generated “must” remains planner Intent.
6. Craft/style findings default to `ADVISORY`; numeric pacing, hook, style, and satisfaction assessments may be `SCORE`. Legacy pacing blockers map to `ADVISORY`. LLM suggested severity cannot raise either result to a hard severity.
7. A recoverable integrity/projection condition starts at `RECOVERABLE` / `RECOVER`. Transition is explicit: `RECOVERABLE → run existing recovery → verify → resolved`. If recovery fails, re-evaluate the failure evidence and classify it as `HARD_INTEGRITY` when safe processing is demonstrably compromised, or `HUMAN_DECISION` when the evidence is ambiguous and requires an accountable choice. It cannot remain indefinitely `RECOVERABLE` after a failed attempt.
8. There is no `HARD_WORKFLOW` catch-all. A workflow condition that compromises artifact or transaction integrity maps to `HARD_INTEGRITY`; an unresolved choice requiring an accountable person maps to `HUMAN_DECISION`; otherwise it is `ADVISORY` or `SCORE`. Craft, Style, and ordinary Intent cannot use workflow labeling to gain veto power.
9. Unknown or unsupported combinations are handled by an explicit conservative rule table; they do not inherit checker severity or blocker flags.

The policy is a pure function over normalized inputs and a pinned policy version. Same inputs and version produce byte-equivalent decisions apart from operational timestamp; timestamps are excluded from the decision fingerprint.

## Stable finding identity

`finding_id` identifies the logical problem, not a particular observation of its evidence. It is deterministic and independent of message wording, evidence excerpts, artifact digests, source spans, list order, timestamps, and random UUIDs. The canonical identity tuple is:

```text
identity_version
+ gate_id
+ stable subject_id or constraint_id
+ chapter/workflow scope
```

The tuple is serialized with canonical JSON (sorted keys, normalized strings, explicit nulls) and hashed with SHA-256; the public ID is `gf1_` plus the full lowercase hex digest. Authority/category are policy attributes, not identity dimensions, so policy reclassification does not fork logical identity. `evidence_fingerprint` represents the evidence state for this observation and may include artifact digests, source spans, expected/observed values, and typed evidence pointers. `input_fingerprint` binds the entire normalized policy input set for a decision attempt. These fingerprints can change after a rewrite while `finding_id` remains stable.

The same gate/subject/scope recurring after a rewrite retains the same ID even when evidence changes. Policy-version changes do not change the finding ID. Override, retry, repeated-finding suppression and rewrite-loop counters reference `finding_id` and maintain evidence/attempt history; suppression never removes a hard finding from `ChapterCommitService` evaluation. If a checker cannot produce a stable logical subject identity or checker-defined stable subject key, it may emit only a non-deduplicable diagnostic. Such a diagnostic cannot drive a hard veto, override identity, or rewrite-loop identity.

## Legacy compatibility adapters

Adapters normalize known legacy structures into `DetectedFinding` before policy evaluation. They are source- and gate-specific deterministic mappings. They must not inspect message/description text.

| Legacy source identity / structured condition | Normalized category | Authority | Explicitness | Default policy result |
| --- | --- | --- | --- | --- |
| Reviewer `pacing` gate issue with legacy blocker flag | `CRAFT` | `LEGACY_UNKNOWN` | `UNKNOWN` | `ADVISORY` |
| Existing structured reviewer categories `setting`, `timeline`, `continuity`, `character`, `logic` | `CANON_CONTRADICTION` only when deterministic Canon linkage and validator evidence exist; otherwise `CRAFT` or `WORKFLOW` per gate registry | `LLM_REVIEW` | `UNKNOWN` | `HUMAN_DECISION` for material unsupported Canon claim; otherwise `ADVISORY` |
| Existing artifact type `disambiguation_result.pending[]` | `DISAMBIGUATION` | `SYSTEM_INTEGRITY` for machine-detected unresolved identity, preserving the original gate identity | `EXPLICIT` | `HUMAN_DECISION` |
| Fulfillment artifact `missed_nodes[]` linked to planned node IDs | `INTENT_FULFILLMENT` | `AUTHOR_PLAN` when authored in chapter/volume contract; `PLANNER_GENERATED` when generated | As recorded by source contract | Policy table based on plan requirement and evidence |
| Legacy review artifact with only `blocking_count` and no structured issue rows | `WORKFLOW` diagnostic for missing detail; count itself is never expanded into invented findings | `LEGACY_UNKNOWN` | `UNKNOWN` | Recompute from other available structured sources; if the old hard-veto path's artifact type identifies a material integrity/Canon risk but cannot disambiguate it, `HUMAN_DECISION`; otherwise follow the registered legacy gate default. No blanket human fallback. |

The gate registry is keyed by stable checker/gate identity and artifact type. It records the mapping, evidence extractor, default authority/category, and policy rule. Unknown gate IDs become an audit diagnostic with `LEGACY_UNKNOWN`; they do not become human decisions just because their prose sounds severe. Only a registered legacy gate whose known function can affect Canon or transaction integrity and whose structured data is insufficient to decide receives conservative `HUMAN_DECISION`.

Phase 6A provides the P1–P7 consistency mapping contract and adapter table. It migrates only consistency paths that currently feed review/commit veto. It does not rewrite the consistency CLI, every patch output format, or every skill consumer.

## Canonical commit veto and flow

The single rejection authority is `ChapterCommitService`. Its new path is:

```text
Checker
    ↓
DetectedFinding
    ↓
Compatibility Adapter (legacy inputs only)
    ↓
GateSeverityPolicy.evaluate(...)
    ↓
GateDecision
    ↓
Workflow action
    ↓
ChapterCommitService final veto
```

`ChapterCommitService` receives the structured source artifacts, normalizes them through canonical adapters, and invokes the shared deterministic policy itself before writing a commit. It rejects on the policy's effective hard decisions and does not delegate final authority to reviewer output or a prior artifact. The service validates any submitted/cached GateDecision against its own recomputation and records an inconsistency diagnostic if values differ.

It never trusts LLM `blocking`, `blocking_count`, checker strings, an external `effective_hard_count`, or any precomputed severity as an independent veto. `effective_hard_count` may be saved as a cache/audit summary, but the service recomputes it from findings and policy and rejects the artifact as inconsistent when it disagrees. Missing decision artifact is regenerated from inputs within the commit attempt; missing source findings needed to prove a legacy blocker are handled through the registered adapter mapping, not by trusting the count.

The aggregate workflow action is derived from recomputed GateDecisions. `REJECT` creates a durable `CHAPTER_COMMIT` with `meta.status=rejected`, preserving the current Phase 0/1 rejection boundary. That record is an immutable workflow audit of the attempted chapter decision; it contains no accepted Canon facts and triggers no accepted event/state/index/summary/memory/vector projections (the existing projection path marks these skipped for rejected commits). Introducing GateDecision does not remove or replace this rejected commit record.

`REQUIRE_HUMAN` also creates a durable `CHAPTER_COMMIT` with `meta.status=rejected`, plus the pending human-action state in workflow metadata. This follows the existing chapter-level decision contract: an unresolved disambiguation currently rejects the attempt, and there must be one durable chapter outcome without implying accepted history. It does not write accepted Canon facts or accepted story-fact projections; the existing rejection-status projection may still record `chapter_rejected`. Under the current immutable one-commit-per-chapter boundary, resolving the pending item does not rewrite or replace that rejected commit. Any later accepted outcome for the same chapter requires a separately designed amend/supersede or retry identity protocol and is outside Phase 6A. The prior rejected audit remains unchanged.

`RECOVER` runs only the existing recovery mechanism, verifies the result, and then reevaluates; a failed recovery is reclassified before the chapter outcome is persisted. `ALLOW_WITH_ADVISORY` may proceed to the existing reconciliation and durable accepted commit sequence. Existing reconciliation authority remains unchanged and independently required. Before a `CHAPTER_COMMIT` is persisted, the authoritative per-attempt GateDecision artifact must be durable; the commit stores only its reference and binding fields.

## Phase boundary

### Phase 6A

- Define and version the shared finding envelope, controlled category/authority enums, deterministic policy, decision audit artifact, stable logical finding identity, and separate evidence/input fingerprints.
- Add contract-node metadata for explicit user constraints after validation that current master/chapter/volume/review contracts can carry it.
- Add P1–P7 structured consistency mapping contracts and deterministic adapters.
- Migrate the current review, fulfillment, disambiguation, and highest-risk consistency paths that feed chapter review/commit veto.
- Make `ChapterCommitService` the sole final veto, recomputing the canonical policy from normalized findings.
- Persist immutable per-attempt GateDecision audit data as its sole authoritative owner, with effective severity/action, policy version, reason/rule ID, scope, evidence fingerprint and input fingerprint. A chapter commit stores only the decision reference and binding fields.
- Keep compatibility input support while making legacy values non-authoritative.

### Phase 6B

- Migrate all consistency producers to native shared findings.
- Converge consistency CLI exit behavior and all skill consumers.
- Retire legacy `Blocker` compatibility after consumers migrate.
- Complete conversion of remaining consistency patch output formats.

Explicit non-goals for 6A: a unified GateService; a complete deterministic Canon contradiction engine; a rewrite of the consistency CLI; universal patch-format migration; all skill-consumer migrations; a global UserConstraint registry; policy decisions stored as Canon; allowing an LLM or artifact summary to veto independently.

## Acceptance criteria

1. Category and authority are distinct validated enums; policy inputs include category, authority, explicitness, structured evidence and pinned policy version.
2. Same normalized findings under the same policy version produce the same effective severity/action/rule/reason and fingerprints.
3. Every actual commit decision has a durable per-attempt GateDecision record with effective severity, effective action, policy version, reason/rule ID and input fingerprint.
4. Historical GateDecision records remain unchanged and retain their original policy explanation after policy upgrades; CHAPTER_COMMIT references them without duplicating their effective decisions.
5. `ChapterCommitService` recomputes policy from structured findings and is the only rejection authority; a false external hard count cannot pass, and a misleading high count cannot independently reject.
6. LLM `CANON_CONTRADICTION` cannot yield `HARD_CANON`; hard Canon requires accepted Canon provenance, deterministic identity/linkage and deterministic contradiction evidence.
7. User hard veto requires an explicit existing contract node with stable constraint identity and source reference.
8. Stable finding IDs survive repeated detection after rewrite even when evidence changes; evidence/input fingerprints record the changing observation separately. IDs do not depend on prose messages, ordering, time, or random identifiers.
9. Legacy pacing blockers map deterministically to advisory; known unresolved disambiguation maps to human decision; no mapping uses message text.
10. Unknown legacy blockers do not all become human decisions. Only identified material Canon/integrity risk with insufficient structured evidence gets conservative human review.
11. Recovery has an explicit run/verify/resolve transition; failed recovery is reclassified and cannot remain stuck in `RECOVERABLE`.
12. Phase 6A defines all P1–P7 mappings but migrates only veto-relevant current paths; full producer, CLI, skill and Blocker retirement work remains in 6B.
13. Existing story contracts carry user constraint metadata without introducing a global registry; if a particular existing contract node cannot be extended safely, the smallest Workflow-owned artifact is scoped to that contract and justified by the incompatibility.

## Self-review

- **Placeholder scan:** no TODO/TBD placeholders remain.
- **Dimension separation:** `category`, `authority`, `explicitness`, evidence and suggested severity are separate fields; messages are display-only.
- **Rejected outcomes:** both `REJECT` and `REQUIRE_HUMAN` preserve a durable `meta.status=rejected` CHAPTER_COMMIT audit with no accepted Canon facts or accepted story-fact projections; the existing rejection-status projection remains allowed, and human pending status remains workflow metadata.
- **Audit ownership:** the per-attempt GateDecision artifact is the only authoritative full decision record; commits hold only reference and binding fields.
- **Veto authority:** the service recomputes from normalized findings, checks cached decisions, and does not treat any external count as authority.
- **Canon safety:** LLM review cannot self-assert `HARD_CANON`; deterministic validator evidence and accepted Canon linkage are explicit prerequisites.
- **Audit semantics:** GateDecision is workflow/infrastructure data, stored per attempt with a pinned policy version and preserved historical record.
- **Identity:** logical identity uses stable gate/subject/scope; changing evidence is captured by separate evidence/input fingerprints.
- **Legacy fallback:** mappings are keyed by gate/artifact identity; no prose classification or blanket `LEGACY_UNKNOWN → HUMAN_DECISION` rule exists.
- **Scope consistency:** P1–P7 mapping contract is included in 6A while full consistency producer, CLI, skills and Blocker retirement remain 6B.
- **User constraints:** existing Story System contracts are the primary carrier; no global registry is proposed.
- **Recovery:** successful and failed recovery transitions terminate in resolved, hard integrity, or human decision states.
- **Severity taxonomy:** no `HARD_WORKFLOW` catch-all remains; `SCORE` models continuous craft/style/satisfaction results without veto authority.
- **Intent boundary:** ordinary planner/author Intent miss is only Advisory/Score; only explicitly linked `USER_EXPLICIT` constraints may map to `HARD_USER`.
- **Question 9:** no Phase 6A architecture question remains undecided. Same-chapter acceptance after a rejected immutable commit remains unsupported by the existing one-commit-per-chapter boundary; changing that requires a separate amend/supersede or retry-identity design and is explicitly outside this phase.
- **Scope:** one coherent architecture slice: shared finding/policy and final commit veto, with broader producer/consumer convergence deferred to 6B.
