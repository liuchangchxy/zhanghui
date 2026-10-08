# Comparator Selection Audit

Issue: #13  
Audit date: 2026-10-08

## Decision

The first primary benchmark set is:

1. `ynnyh/jarvis-write`
2. `Xiaoyangy/novel-studio`
3. `liuchangchxy/zhanghui`

The previous benchmark-authored Minimal/Lightweight pair is no longer a primary comparison set. A minimal run may remain only as a lower-bound sanity check.

## Selection criteria

A primary comparator must be:

- an independently implemented long-form fiction system;
- complete enough to run as a real project rather than a prompt/demo;
- explicit about persistent story state / memory / planning;
- architecturally different enough to represent a genuine alternative;
- inspectable enough to identify prompt/context/state boundaries;
- locally runnable or self-hostable;
- adaptable to a common writer only through a thin transport/adapter boundary, not by rebuilding its architecture;
- usable without requiring a new paid service solely for the benchmark.

Popularity alone is not a selection criterion.

## Selected: jarvis-write

Repository: https://github.com/ynnyh/jarvis-write

Observed remote SHA during selection:

`efc5e1030b33f4bb19fc9509a6f28dafefa59848`

Why it qualifies:

- complete backend/frontend system rather than a benchmark fixture;
- hundreds of repository commits and an active 2026 changelog/release line;
- Docker, local development and desktop packaging paths;
- explicit Gemini / DeepSeek / OpenAI / compatible-provider model layer;
- temporal Story Bible with chapter-valid facts;
- post-chapter entity/fact/foreshadowing/knowledge extraction;
- explicit foreshadowing lifecycle;
- cascading outline updates;
- consistency checking and user-visible resolution;
- deliberately removed vector-memory dependency in favor of temporal Story Bible + rolling summaries + recent chapters.

Why it is useful against Zhanghui:

Zhanghui and jarvis-write attack many of the same long-form failures but make materially different architectural choices.

```text
jarvis-write:
temporal Story Bible
+ outline cascade
+ explicit foreshadowing scheduler
+ consistency review
+ author-facing temporal state

Zhanghui:
Canon / Intent / Craft authority separation
+ ChapterCommit acceptance
+ event history
+ rebuildable projections
+ correction lineage
+ governed retrieval
```

This is a legitimate alternative design, not a deliberately weaker baseline.

## Selected: Xiaoyangy/novel-studio

Repository: https://github.com/Xiaoyangy/novel-studio

Observed remote SHA during selection:

`ed04a106f665f456246af3c4414ba62992a2a1d1`

Why it qualifies:

- complete local-first CLI/production engine;
- stable release path plus current-source execution;
- repository includes architecture, lifecycle, observability, evaluation and operations documentation;
- role-specific model routing with Gemini support;
- RAG and source-receipt design;
- explicit world/character simulation;
- arc-level planning and sealed rendering bundles;
- chapter draft/review/rewrite/commit lifecycle;
- recoverable checkpoints;
- accepted prose and observed outcomes become formal state.

Why it is useful against Zhanghui:

Its central idea is not merely better retrieval. It shifts control earlier:

```text
novel-studio:
simulate world and characters
-> seal causal/POV plan
-> render prose
-> review/accept
-> update recoverable state

Zhanghui:
assemble governed context
-> draft/review
-> extract observed changes
-> reconcile
-> accept ChapterCommit
-> rebuild projections
```

This tests whether consistency is better achieved through pre-generation causal simulation/sealing or through post-generation truth acceptance and governance.

## Reserve: NovelClaw

Repository: https://github.com/iLearn-Lab/NovelClaw

Observed remote SHA:

`226d50d3ec284c9cc037c47eb14af39505f9ed74`

Why it remains important:

- substantial public usage signal;
- complete local Docker/Windows workflow;
- provider/model API;
- persistent sessions, storyboards, manuscript views and editable memory banks;
- inspectable run logs and chapter artifacts.

Why it is not first-line Track A:

Its public design is intentionally workspace/session centric. Persistent conversation itself is part of the product philosophy, which makes "same isolated writer invocation" harder to impose without changing the behavior being tested. It remains a strong Track B / product-level comparator and can be promoted after Stage -1 if a clean adapter boundary is found.

## Reserve: AI_NovelGenerator

Repository: https://github.com/YILING0013/AI_NovelGenerator

Observed remote SHA:

`f9aefef90b1493c579d7f72547efb4a3d8a0da25`

Why it remains important:

- long-running public project with a large user/fork base and multiple releases;
- multi-stage novel generation;
- state tracking;
- semantic retrieval;
- continuity/proofreading flow;
- configurable model routing including Gemini.

Why it is not first-line Track A:

The project is simultaneously carrying a mature older line and an active refactor/newer line. That is useful for product benchmarking but creates ambiguity over which architecture should be treated as the clean current philosophical baseline.

## Research implementations not selected as mature product comparators

Systems such as DOME and ConWriter remain relevant research references, especially for:

- dynamic hierarchical planning;
- temporal knowledge graphs;
- lightweight symbolic transition/state constraints.

They may inspire later targeted mechanism experiments, but research code does not automatically satisfy the current requirement for a mature alternative product/system.

## Required local validation

This document selects candidates based on their current public repositories and documentation. It does **not** claim that a controlled common-Gemini benchmark is already feasible.

Stage -1 must prove that for each selected project:

- the pinned checkout actually runs;
- its true writer context can be captured without rewriting it;
- the same writer runtime can be substituted through a thin boundary;
- state updates can continue after externally supplied prose if the controlled track uses external Gemini;
- no hidden cross-system context is introduced.

If either external project fails that test, do not replace it with a benchmark-authored imitation. Promote a reserve mature system or run it only in the native product track.
