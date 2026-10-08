# Zhanghui Long-Form Architecture Benchmark

This directory implements Issue #13.

The benchmark exists to answer a design question:

> Is Zhanghui's Story Truth architecture a better long-form fiction design tradeoff than other mature, independently implemented systems?

It must not be used to "prove" Zhanghui correct by comparing it only with benchmark-authored toy baselines.

## Current protocol

Authoritative protocol for new work:

- `protocol/v2.json`
- `protocol/comparator-selection.md`
- `schemas/run-manifest-v2.schema.json`
- `protocol/antigravity-runtime-qualification.md`
- `protocol/stage0-harness-contract.md`
- `schemas/writer-package-v1.schema.json`
- `protocol/stage1-evaluation-protocol.md`
- `schemas/stage1-evaluator-report-v1.schema.json`
- `schemas/evaluator-runtime-lock-v1.schema.json`
- `schemas/stage1-dataset-manifest-v1.schema.json`

`protocol/v1.json` and `run-manifest.schema.json` are preserved as historical artifacts from the superseded toy-baseline design and must not be used for new runs.

## Primary systems

### jarvis-write

Repository: https://github.com/ynnyh/jarvis-write

Design philosophy:

> temporal Story Bible + explicit foreshadowing lifecycle + cascading outline updates + consistency checking.

Important distinction from Zhanghui:

- facts are represented as chapter-valid intervals rather than through Zhanghui's ChapterCommit/projection authority model;
- foreshadowing and outline change management are first-class author-facing control surfaces;
- state extraction and consistency review are organized around a temporal Story Bible rather than an event-sourced Canon transaction boundary.

### AI_NovelGenerator

Repository: https://github.com/YILING0013/AI_NovelGenerator

Design philosophy:

> multi-stage story architecture + chapter blueprint + hierarchical text state + semantic vector memory + consistency review.

Important distinction from Zhanghui:

- story structure is produced through staged architecture and chapter-blueprint generation rather than Canon / Intent / Craft authority layers;
- long-term continuity combines `global_summary.txt`, `character_state.txt`, recent chapters and Chroma semantic retrieval;
- chapter finalization updates text-ledger state and vector memory directly rather than producing a durable ChapterCommit transaction and rebuildable projections;
- its production LLM boundary is text-in/text-out, enabling a thin Antigravity transport without reimplementing the system.

### Zhanghui

Repository: `liuchangchxy/zhanghui`

Design philosophy:

> governed Canon / Intent / Craft separation + durable ChapterCommit acceptance + rebuildable projections + correction lineage + governed context retrieval.

## Track B / reserve systems

- `Xiaoyangy/novel-studio`: mature product-level comparator with world/character simulation, sealed render packets and an acceptance/state lifecycle. It is excluded from the current Antigravity-only Track A because its native `agentcore` requires caller-owned structured tool-calling transport that the current headless Antigravity interface does not expose without reimplementing the agent loop.
- `iLearn-Lab/NovelClaw`: serious product-level reserve comparator with persistent sessions, storyboards, memory banks, inspectable runs and provider configuration. Its public architecture is more workspace/session centric, so a clean controlled writer comparison is less direct.

## What Minimal / Lightweight mean now

A no-memory or hand-built Story Bible run may be retained only as a **lower-bound sanity check**.

They are not mature competitors and must not be used to claim:

- Zhanghui's complexity is justified;
- Zhanghui has measured marginal benefit over a mature alternative;
- mature Story Bible architectures are inferior.

## Benchmark tracks

### Track A — Mature architecture comparison (primary)

Compare:

1. jarvis-write
2. AI_NovelGenerator
3. Zhanghui

Hold constant where practical:

- story seed;
- author-level plot requirements;
- current chapter objective;
- target length;
- language;
- writer model/runtime;
- evaluation protocol.

Do not force the three systems into one fake internal representation. Their actual planning, memory and context mechanisms are part of the comparison.

### Track B — Product workflow comparison (secondary)

Run each system through its documented end-to-end workflow with minimal benchmark interference.

This measures the complete user-facing tradeoff, including:

- prose quality;
- consistency;
- human intervention;
- setup/maintenance burden;
- elapsed time;
- resource/token usage where measurable;
- recoverability;
- diagnosis/repair ergonomics.

Track B may contain more uncontrolled variables and must be reported separately.

## Stage -1: comparator compatibility audit

No prose benchmark may start until a local executor has inspected the three primary repositories at frozen SHAs.

For each system record:

1. exact tested commit SHA;
2. install/runtime requirements;
3. license;
4. chapter-generation entrypoint;
5. context/prompt assembly boundary;
6. memory/state update boundary;
7. model-provider boundary;
8. whether the same Gemini writer can be used without changing architecture semantics;
9. whether externally generated prose can be ingested without bypassing core behavior;
10. whether post-chapter state updates require additional model calls;
11. adapter size and invasiveness.

If making a system fit the benchmark would require reimplementing it, it is not eligible for controlled Track A. It can remain in Track B.

## Fixed writer policy

The intended common writer is Gemini through the user's existing Gemini Pro / Antigravity or another already-entitled execution path.

- Never invent an exact Gemini model ID.
- If Gemini 3.8 Flash is explicitly available and can be invoked in isolated sessions without incremental API charges, prefer it.
- All controlled systems must use the same exact writer runtime.
- No new paid API top-up is allowed.
- If a common writer cannot be connected without materially changing a mature system, record that limitation rather than faking control.

## Physical isolation contract

Source repositories and story runtime data must be separate.

Recommended layout:

```text
<benchmark-root>/
  sources/
    zhanghui/
    jarvis-write/
    AI_NovelGenerator/

  runs/
    pilot-tide-archive-001/
      run-001/
        jarvis-write/
        ai-novel-generator/
        zhanghui/
        _controller/
```

Rules:

- source repositories are read from their frozen commits;
- novel runtime data lives outside source Git working trees;
- each story project has its own runtime root;
- one system may not read another system's runtime state;
- `_controller/` owns blind mappings and evaluation artifacts;
- generated manuscripts/databases do not enter Zhanghui's source repository.

## Model-session isolation contract

Directory isolation is not enough.

For a controlled writer comparison:

- every prose-mutating writer call uses a fresh isolated invocation/session; a native chapter pipeline may make multiple such calls (draft/finalize/rework/etc.);
- the writer sees only the package produced by that system for that chapter;
- no Antigravity session may write one system and then another while retaining hidden chat history;
- future chapter objectives are hidden;
- evaluator findings and oracle material are hidden;
- another system's prose, memory or state is hidden.

If the executor cannot guarantee this, stop at prepared generation packages.

## Scenario

The checked-in `pilot-tide-archive-001.public.json` remains the first pilot scenario.

It intentionally stresses:

- character-state changes;
- relationship changes;
- object ownership;
- delayed payoff;
- world rules;
- story-time/flashback handling;
- allegation vs objective truth;
- intentionally unresolved facts.

Each mature system receives the same author-level requirements, not another system's internal schema.

## Evaluation principles

1. No participant's memory/state store is used as the ground truth for grading that participant.
2. Findings require prose-grounded evidence.
3. System identity is blinded from prose evaluators where practical.
4. Ambiguity may remain `UNRESOLVED`.
5. Evaluation versions are fixed across compared outputs.
6. Prose quality is reported separately from consistency.
7. System-specific mechanism audits are allowed, but do not force all systems into Zhanghui's schema.

Core contradiction taxonomy:

- `FACTUAL_ENTITY`
- `CHARACTER_STATE`
- `RELATIONSHIP`
- `WORLD_RULE`
- `TEMPORAL`
- `LOCATION`
- `OBJECT_OWNERSHIP`
- `EPISTEMIC`
- `OPEN_LOOP`

## Stages

| Stage | Purpose |
| --- | --- |
| -1 | Freeze comparator SHAs, prove local runability and fair adapter feasibility |
| 0 | 3-chapter smoke; validate isolation/capture/blinding only |
| 1 | 10-chapter pilot; validate metrics and evaluator credibility |
| 2 | Multi-scenario >=30-chapter formal comparison |
| 3 | 50-100 chapter long-horizon confirmation only if justified |

No architecture conclusion may be drawn from Stage 0.

## Stage 1 evaluator gate

Stage 1 does not immediately regenerate ten chapters from scratch.

The accepted Formal Stage 0 chapters 1-3 are hash-locked and reused. Stage 1 continues each native system from its accepted chapter-3 state and generates only chapters 4-10, producing 21 new chapters and three complete 10-chapter manuscripts.

Before any chapter-4 generation:

1. freeze the evaluator runtime and prompt hashes;
2. run the checked-in evaluator calibration cases without exposing calibration gold;
3. satisfy the thresholds in `protocol/stage1-evaluation-protocol.md`;
4. validate an `evaluator-runtime-lock-v1` artifact.

Consistency grading uses only immutable seed + generated prose as story truth. Chapter intent is scored separately for instruction compliance and may never be promoted into Canon merely because it was planned.

Stage 1 reports a metric vector rather than one weighted winner score and does not authorize architectural superiority claims.

## Existing Zhanghui facilities

- `.claude/plugins/zhanghui/scripts/run_behavior_evals.py` remains a deterministic package/behavior contract suite. It is not this benchmark.
- `.webnovel/observability/data_agent_timing.jsonl` may be used as one Zhanghui timing source but is not the benchmark's universal telemetry format.

## Scope boundary

- No Phase 11.
- No production Story Truth changes merely to improve Zhanghui's score.
- No production changes to comparator repositories merely to make them easier to grade.
- No benchmark-authored fake competitor presented as mature.
- No new paid model requirement.
- No automatic 100-chapter run.

Refs: #13