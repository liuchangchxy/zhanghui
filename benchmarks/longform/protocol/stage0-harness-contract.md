# Stage 0 Harness Contract

Issue: #13

This contract applies after Stage -1 comparator compatibility and Antigravity runtime qualification.

Status before implementation:

`STAGE_MINUS_1_COMPLETE_COMMON_WRITER_QUALIFIED`

## Purpose

Stage 0 validates that three mature systems can be compared through one common writer runtime without cross-system leakage or production-code rewrites.

It does **not** establish architectural superiority.

Primary systems:

1. `ynnyh/jarvis-write`
2. `Xiaoyangy/novel-studio`
3. `liuchangchxy/zhanghui`

Writer runtime:

- Antigravity consumer entitlement;
- UI-selected runtime: Gemini 3.8 Flash (Medium);
- machine metadata label observed: `MODEL_PLACEHOLDER_M322`;
- backend exact model ID is only partially verifiable and must not be invented.

## Frozen Stage 0 scope

Scenario:

`pilot-tide-archive-001`

Chapters:

- jarvis-write: 1-3
- novel-studio: 1-3
- Zhanghui: 1-3

Total prose outputs: 9.

No Stage 1 work is allowed in the Stage 0 implementation PR.

## Controller responsibility

The benchmark controller is the only component allowed to:

- read the three source repositories;
- inspect system runtime state;
- prepare chapter-level writer packages;
- create ephemeral writer directories;
- invoke Antigravity;
- ingest returned prose into the corresponding system boundary;
- run each system's post-write workflow;
- collect telemetry;
- create blind mappings;
- prepare evaluator packages.

The prose writer invocation must not inspect repositories or decide benchmark control flow.

## Physical layout

Source and runtime roots remain separate:

```text
<benchmark-root>/
  sources/
    zhanghui/
    jarvis-write/
    novel-studio/

  runs/
    pilot-tide-archive-001/
      run-001/
        jarvis-write/
        novel-studio/
        zhanghui/
        _controller/

  writer-invocations/
    <invocation-id>/
      writer-package.txt
      writer-package.json
      output.txt
      runtime-metadata.json
```

`writer-invocations/<invocation-id>/` is ephemeral and must contain only the current chapter's serialized writer package plus its own output/metadata.

It must not contain symlinks or copied files from another system.

## Writer isolation

Filesystem isolation is only soft in the current Antigravity host.

Therefore every controlled writer invocation must satisfy all of the following:

1. fresh Antigravity conversation/session;
2. fresh invocation ID and brain directory;
3. invocation working directory is the per-call ephemeral directory, not `<benchmark-root>`;
4. input is self-contained serialized text;
5. no absolute paths to any source repository or run root;
6. no sibling-system content;
7. no controller blind mapping;
8. no evaluator findings;
9. no future chapter objectives;
10. no instruction to inspect the filesystem, repository, shell, network, or tools;
11. output is prose-only;
12. controller performs all repository/state reads before invocation and all ingestion after invocation.

A Stage 0 manifest is invalid if isolation evidence is absent.

## Writer-package boundary

Each adapter must produce one normalized outer package containing:

- protocol version;
- scenario ID;
- system ID;
- chapter number;
- frozen source SHA;
- runtime label;
- system-owned writer instructions;
- system-owned chapter context;
- author-level current chapter objective;
- target length;
- output rule: prose only;
- hashes of all serialized inputs.

The normalized wrapper must not rewrite or summarize away system-owned context.

System-specific prompt/context must be preserved verbatim where possible.

## Common-writer rule

Controlled prose generation must use the same Antigravity runtime for all three systems.

Record both:

- human-visible selected runtime;
- machine-reported runtime/model label.

Do not claim an exact backend Gemini model ID beyond evidence actually exposed by Antigravity.

## Adapter contracts

### jarvis-write

Allowed adapter behavior:

1. invoke its real chapter-context preparation;
2. obtain the real Composer draft/finalize prompt boundary;
3. serialize the actual system-owned writer prompt;
4. call common Antigravity writer;
5. return prose through the existing `precomputed=(draft, final)` path or another equally thin native short-circuit;
6. continue the real review/rework/finalize/Story-Bible maintenance pipeline.

The adapter must not independently recreate the temporal Story Bible, rolling summary, hard constraints, foreshadow scheduler, resource ledger, style directives, or context assembly.

### novel-studio

Allowed adapter behavior:

1. run the real planning/world/character simulation required by the system;
2. obtain the real primed/sealed Drafter message envelope;
3. serialize the exact Drafter-visible prose context;
4. call common Antigravity writer;
5. wrap returned prose through a thin transport bridge equivalent to the expected `draft_chapter(chapter=N, mode="write", content=...)` tool call;
6. continue the native review / actual-match / acceptance / state pipeline.

The adapter must not bypass or reconstruct sealed render packets, character activation state, causal simulation, source receipts, or transaction guards.

### Zhanghui

Allowed adapter behavior:

1. use current governed context generation;
2. obtain the real Step 2A writing execution package;
3. serialize the exact writer-visible package;
4. call common Antigravity writer;
5. write returned prose into the current chapter draft boundary;
6. continue the real review / changes refresh / Data Agent / reconciliation / ChapterCommit / projection pipeline.

The adapter must not reconstruct Canon, Intent, Craft, projections, or ChapterCommit semantics.

## Model-call accounting

The benchmark must distinguish:

- common prose-writer calls;
- system-native planning calls;
- system-native review calls;
- system-native extraction/state-update calls.

Do not report only the common writer cost.

For every model call that can be measured, record provider/runtime label and token usage.

If a system-native call cannot use the already-entitled runtime without new API billing, Stage 0 must stop and report the exact blocker rather than purchasing access.

## Fairness rule

Track A holds the prose writer constant, not every model call in each architecture.

System-specific planner/reviewer/extractor calls are part of the architecture under test and must not be deleted merely to make call counts equal.

However, their model/runtime and cost must be recorded separately so the result can distinguish:

- prose quality from the common writer;
- architectural overhead from extra calls;
- consistency benefit from the system's own machinery.

## Blind evaluation package

After all 9 outputs exist:

- controller maps each output to a random blind sample ID;
- evaluator package contains prose and the common author-level scenario evidence required for grading;
- package contains no system name, source path, runtime database path, or adapter name;
- mapping remains only in `_controller/`.

No prose evaluator may see which system produced a chapter.

## Stage 0 success criteria

Stage 0 is valid only if:

- all three source SHAs remain frozen;
- production source trees remain unchanged;
- 9 fresh writer invocations are recorded;
- all 9 manifests contain isolation evidence;
- no cross-system prompt leakage is detected;
- each prose output is ingested through the system's real native boundary;
- system-native post-write pipelines complete or fail with preserved evidence;
- blind evaluator packages can be generated;
- deterministic harness tests pass;
- no new paid API access is required.

## Stop conditions

Stop and return evidence if:

- an adapter must reimplement a comparator architecture;
- Antigravity writer invocation cannot remain fresh/self-contained;
- one system requires a new paid API credential for an essential Stage 0 step;
- a production repository must be modified to continue;
- a system cannot ingest external prose without bypassing its core state lifecycle;
- source SHA drifts during the run.

## Non-goals

- no Stage 1;
- no 10-chapter run;
- no architecture winner;
- no production fixes;
- no comparator forks;
- no Phase 11;
- no model benchmark.

Refs: #13
