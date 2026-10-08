# Stage 1 Evaluation Protocol v1

Issue: #13

Status: frozen before any Stage 1 chapter 4-10 generation.

## Purpose

Stage 1 is a **10-chapter pilot and evaluator-validation stage**.

It answers:

1. Can the validated Track A pipelines continue from chapter 3 through chapter 10 without losing isolation or native state behavior?
2. Can a blinded evaluator reliably detect long-form continuity failures, epistemic mistakes, temporal mistakes, missed intent, and prose-quality differences?
3. Can system-native memory/state mechanisms be audited against prose-grounded evidence without forcing all systems into one internal schema?

Stage 1 **does not authorize an architecture winner**. One scenario is not enough for a general superiority claim.

## Track A systems

1. `ynnyh/jarvis-write`
2. `YILING0013/AI_NovelGenerator`
3. `liuchangchxy/zhanghui`

`Xiaoyangy/novel-studio` remains Track B under the current Antigravity-only runtime.

## Stage 1 continuation policy

Stage 1 reuses the already validated Formal Stage 0 chapters 1-3 from:

`runs/pilot-tide-archive-001/run-002-track-a/`

The Stage 0 prose itself has not been substantively scored and may therefore become the first three chapters of the Stage 1 pilot after this evaluation protocol is frozen.

Do **not** regenerate chapters 1-3.

Instead:

1. hash-lock all Stage 0 chapter 1-3 prose, manifests, receipts, and native runtime-state snapshots;
2. copy each system's chapter-3 native runtime state into a new Stage 1 continuation root;
3. verify the copied state against the frozen snapshot;
4. generate only chapters 4-10;
5. construct the final Stage 1 manuscript from frozen chapters 1-3 plus newly generated chapters 4-10.

This produces:

- 21 new accepted chapter outputs;
- 30 total chapter outputs in the Stage 1 pilot dataset;
- 10 chapters per system.

If any chapter-3 state snapshot cannot be reproduced exactly enough to continue the native pipeline, stop rather than silently rebuilding it.

## Generation protocol lock

Stage 1 generation must preserve the already validated Track A rules:

- same author-level scenario;
- same Antigravity prose runtime;
- every prose-mutating call uses a fresh isolated session;
- system-native context is preserved;
- benchmark future-oracle injection is forbidden;
- comparator production source is not modified;
- controller synthetic state writes remain zero;
- AI_NovelGenerator vector memory uses the qualified production `MLStudioEmbeddingAdapter` + local LM Studio path;
- no new paid API is introduced.

The participant execution SHAs remain those used by the accepted Stage 0 continuation unless a separate compatibility re-audit explicitly authorizes a change.

The benchmark protocol revision may advance independently from the participant execution SHA.

## Evaluation surfaces

Evaluation is split into three blinded modes. Do not collapse them into one score.

### A. Consistency / truth evaluation

Input:

- opaque blind sample ID;
- immutable seed only;
- full generated manuscript chapters 1-10;
- contradiction taxonomy and evaluator instructions.

Hidden from this mode:

- system identity;
- repository/runtime metadata;
- chapter intents;
- master outline;
- system memory/state;
- adapter details;
- evaluator-only expected answers.

Reason: chapter intent is author intent, not story truth. A consistency evaluator must not treat an intended event as if it happened.

### B. Intent-compliance evaluation

Input:

- opaque blind sample ID;
- chapter-by-chapter author intent;
- full generated manuscript.

This mode evaluates whether the requested chapter objective, intended changes, open developments, and explicit stress constraints were actually followed.

It does **not** decide the prose truth ledger for later chapters.

### C. Prose-quality evaluation

Input:

- opaque blind sample ID;
- genre/language;
- manuscript only.

No system identity, architecture metadata, or native state is visible.

This mode scores writing quality separately from consistency.

## Prose-grounded truth ledger

Each blind manuscript gets its own independent truth ledger.

The ledger starts only from the scenario's `immutable_seed`.

Then process generated prose in chapter order.

### May enter objective story truth

- explicit narrator-level events presented as having occurred;
- explicit state transitions shown in prose;
- object transfers actually narrated;
- direct observations where the narration presents the observation itself as reliable;
- explicit corrections that explain why an earlier apparently objective belief was wrong.

### Must not be automatically promoted to objective truth

- dialogue assertions;
- accusations;
- rumors;
- hypotheses;
- dreams;
- hallucinations;
- subjective beliefs;
- reconstructed memories with limited observation;
- chapter intent;
- master outline;
- evaluator stress-point notes;
- a system's own memory database.

These remain attributed or `UNRESOLVED` unless later prose establishes them.

### Time-scoping rule

Flashbacks, archive reconstructions, and memories are recorded at their story-time.

Historical state must not overwrite current state unless the prose explicitly establishes a transition that affects the present.

### State-transition rule

A changed value is not a contradiction if the prose narrates a plausible transition.

Examples:

- key owner A -> B after an explicit handoff: valid transition;
- injured -> recovering after elapsed time and recovery evidence: valid transition;
- accusation -> disproved: valid epistemic development.

### Correction rule

Later prose may correct an earlier attributed belief without creating a contradiction.

Later prose that simply conflicts with an earlier objective narrator-level fact, with no correction/reveal mechanism, is a candidate continuity violation.

## Contradiction taxonomy

Use the protocol-v2 categories:

- `FACTUAL_ENTITY`
- `CHARACTER_STATE`
- `RELATIONSHIP`
- `WORLD_RULE`
- `TEMPORAL`
- `LOCATION`
- `OBJECT_OWNERSHIP`
- `EPISTEMIC`
- `OPEN_LOOP`

A finding may have one primary category and optional secondary categories.

## Finding severity

### MATERIAL

A contradiction or unsupported certainty that changes meaningful story truth, current state, object ownership, world rules, temporal interpretation, relationship state, or the status of an important unresolved question.

MATERIAL findings form the primary consistency metric.

### MINOR

A local continuity mismatch with limited downstream consequence.

### ADVISORY

Plausibility, taste, style, convenience, or weak exposition concerns that are not contradictions.

ADVISORY findings are excluded from consistency error counts and belong primarily in prose-quality commentary.

## Evidence rule

No consistency finding is valid without prose evidence.

Every asserted finding must provide:

1. the proposition judged inconsistent;
2. evidence for the current proposition;
3. the conflicting prior prose or immutable invariant;
4. chapter references;
5. epistemic status;
6. a short rationale.

If evidence is ambiguous, use `UNRESOLVED`.

A rater may never confirm a finding because "the outline said otherwise."

## Intent-compliance statuses

For each chapter:

- `SATISFIED`
- `PARTIAL`
- `MISSED`
- `CONTRADICTED`
- `AMBIGUOUS`

Also score individually where present:

- requested objective;
- intended changes;
- open-development preservation;
- continuity/epistemic/temporal stress constraints;
- explicit payoff requirement.

The chapter intent is evaluated as instruction-following only. It does not enter the truth ledger.

## Prose-quality rubric

Each chapter receives 1-5 ratings on:

- `clarity`: readability and comprehensibility;
- `scene_coherence`: whether events within the chapter connect coherently;
- `characterization`: credible and differentiated character behavior/voice;
- `pacing`: scene progression and allocation of attention;
- `language_quality`: fluency, naturalness, repetition control, and sentence-level craft.

The evaluator also gives a 1-5 `overall_reader_quality` rating.

Do not penalize a system twice for a continuity error here. Consistency is reported separately.

## Deterministic metrics

The controller computes without an LLM:

- Chinese character count per chapter;
- chapters within the frozen 1800-2600 target range;
- absolute and relative length deviation;
- model-call counts;
- input/output tokens where measurable;
- elapsed time;
- retry/intervention counts;
- prose-mutating vs non-prose call counts.

These are not evaluator judgments.

## Primary Stage 1 outcome vector

Do not create a single weighted "winner score".

Report each system as a vector:

1. confirmed MATERIAL consistency findings, raw count;
2. MATERIAL findings per 10,000 Chinese characters;
3. MATERIAL findings by taxonomy;
4. confirmed MINOR findings;
5. UNRESOLVED findings;
6. intent-compliance distribution;
7. prose-quality medians and dispersion by axis;
8. chapter-length adherence;
9. model-call/token/time overhead;
10. native-state audit precision/recall where meaningful.

Any later composite metric requires a separate pre-registered protocol revision.

## Native mechanism audit

Mechanism audits are secondary and must not become participant ground truth.

Checkpoints:

- after chapter 3;
- after chapter 6;
- after chapter 10.

At each checkpoint derive a prose-grounded material-state ledger first.

Then audit native state surfaces:

### jarvis-write

Audit factual Story Bible / knowledge / ownership/state assertions that are intended to inform later generation.

### AI_NovelGenerator

Audit `global_summary.txt` and `character_state.txt` for factual support and material-change coverage.

Vector memory is additionally tested with fixed retrieval probes, but raw vector contents are not forced into the same schema.

### Zhanghui

Audit accepted events/current projections and Data Agent extraction against prose-grounded material changes.

Report:

- supported native assertions / audited native assertions = state precision;
- represented material prose changes / adjudicated material prose changes = material recall;
- unsupported state assertions;
- missed material changes;
- stale current-state assertions.

Do not punish a system for not storing information outside the purpose of its native state surface.

## Blinding

Blind IDs are random and contain no architecture hint.

Evaluators must not receive:

- system name;
- source repository;
- source SHA;
- native database/file paths;
- adapter name;
- model-call telemetry;
- state implementation details.

Blind mappings remain controller-only until all reports and adjudication are frozen.

## Evaluator independence

For each blind 10-chapter manuscript:

- run 3 fresh consistency-evaluator sessions;
- run 3 fresh intent/prose-quality evaluator sessions, using the frozen prompt/schema;
- no evaluator session may evaluate more than one blind manuscript while retaining conversation memory;
- all evaluator runtimes and prompt/template hashes are recorded.

The evaluator runtime does not have to equal the writer runtime, but it must be frozen before Stage 1 chapter 4 generation and identical across systems for a given evaluator role.

## Finding normalization and adjudication

Equivalent findings may differ in wording.

Normalize by:

- chapter;
- primary taxonomy;
- proposition/conflict target;
- evidence locations.

A finding becomes `CONFIRMED` if:

- at least 2 of 3 independent consistency raters assert the same material conflict with valid evidence; or
- a blinded adjudicator confirms a disputed finding after seeing the evidence and relevant manuscript context.

A finding is `REJECTED` if the alleged conflict is actually:

- a narrated state transition;
- a character claim rather than objective truth;
- a correctly scoped flashback;
- an explicit correction/reveal;
- unsupported by the cited prose.

Use `UNRESOLVED` when the evidence does not support a confident decision.

Majority vote never overrides the evidence rule.

## Frozen evaluator prompt artifacts

Stage 1 evaluator behavior is defined by checked-in, hashable prompt artifacts:

- consistency: `evaluators/consistency-evaluator-v1.md`
- intent + prose quality: `evaluators/intent-quality-evaluator-v1.md`
- blinded adjudication: `evaluators/adjudicator-v1.md`

The first runtime candidate is the already-entitled Antigravity `Gemini 3.8 Flash (Medium)` runtime with machine label `MODEL_PLACEHOLDER_M322`. This is a candidate only until calibration passes. A failed calibration does not authorize prompt tuning after seeing participant outputs; prompt/runtime changes must be versioned and re-calibrated before chapter 4 generation.

## Evaluator calibration gate

Before Stage 1 chapter 4 generation, the chosen evaluator runtime must pass the checked-in calibration fixtures without access to calibration gold.

Minimum gate:

- schema-valid reports: 100%;
- MATERIAL contradiction detection recall >= 0.85;
- MATERIAL contradiction precision >= 0.85;
- taxonomy macro-F1 >= 0.80;
- false-confirm rate on explicit ambiguity/non-violation controls <= 0.10;
- no system-identity inference requirement;
- no filesystem/repository access required.

Failure blocks Stage 1 generation until the evaluator prompt/runtime is revised and versioned.

## Inter-rater validation on Stage 1

After all blind reports exist, measure:

- material-finding presence agreement by chapter;
- normalized finding-set pairwise Jaccard;
- intent-status agreement;
- prose-quality rating dispersion.

Stage 1 evaluator validation passes if:

- material finding presence agreement is substantial enough to support adjudication (target kappa >= 0.60 where computable);
- median normalized finding-set Jaccard >= 0.60;
- intent status exact agreement >= 0.75 before adjudication;
- at least 80% of prose-quality axis ratings differ by no more than 1 point across raters.

If these are missed, report evaluator instability and revise before Stage 2. Do not tune the evaluator to favor one participant.

## Evaluator-only scenario annotations

`scenarios/pilot-tide-archive-001.evaluator.json` lists known stress points from the authored scenario.

Those annotations:

- may guide calibration and adjudication;
- may support intent-compliance evaluation;
- may identify where to inspect for likely continuity failures;
- must never be treated as proof that an intended event happened in generated prose;
- must never enter generation packages.

## Stage 1 statistical policy

Stage 1 uses one scenario.

Therefore:

- report descriptive statistics;
- report within-scenario paired chapter patterns;
- report effect candidates;
- do not claim population-level significance;
- do not declare architectural superiority;
- do not use p-values as evidence of generality.

Formal architecture comparison begins only in Stage 2 with multiple scenarios.

## Stage 1 acceptance criteria

Stage 1 is valid only if:

- evaluator calibration passed before chapter 4 generation;
- Stage 0 chapter 1-3 artifacts and state snapshots were hash-locked;
- 21 new accepted chapter outputs exist;
- 30 total pilot chapter outputs are assembled;
- all new prose-mutating calls satisfy the common-writer isolation rule;
- source trees remain frozen/clean;
- native pipelines complete or preserve failure evidence;
- all blind packages are identity-free;
- all evaluator reports pass schema validation;
- adjudication is completed without unblinding;
- evaluator agreement metrics are computed;
- no architecture winner is declared.

## Stage 1 stop conditions

Stop if:

- evaluator calibration fails;
- a participant requires production-code modification;
- chapter-3 continuation state cannot be reproduced;
- source SHA drifts;
- blind identity leaks into evaluator material;
- an evaluator uses chapter intent as story truth;
- controller synthetic state is introduced;
- a new paid model/API is required.

## Stage 1 outputs

Required:

- Stage 1 dataset manifest linking Stage 0 chapters 1-3 and Stage 1 chapters 4-10;
- 3 identity-free 10-chapter manuscript packages;
- consistency evaluator reports;
- intent/prose-quality evaluator reports;
- adjudicated finding set;
- prose-grounded truth ledgers;
- native mechanism-audit reports at chapters 3/6/10;
- evaluator calibration result;
- inter-rater agreement report;
- descriptive metric table.

## Explicit non-goals

- no architecture winner;
- no production fix to improve a score;
- no Stage 2 generation;
- no new comparator;
- no post-hoc metric weighting;
- no use of participant state as grading ground truth.

Refs: #13
