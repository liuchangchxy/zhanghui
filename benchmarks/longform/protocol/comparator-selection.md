# Comparator Selection Audit

Issue: #13  
Audit date: 2026-10-08

## Decision

The current controlled Track A benchmark set is:

1. `ynnyh/jarvis-write`
2. `YILING0013/AI_NovelGenerator`
3. `liuchangchxy/zhanghui`

`Xiaoyangy/novel-studio` remains a mature comparator, but is assigned to Track B under the current Antigravity-only runtime because its native `agentcore` loop requires caller-owned structured tool-calling transport that Antigravity's headless interface does not expose.

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

## Selected: AI_NovelGenerator

Repository: https://github.com/YILING0013/AI_NovelGenerator

Frozen Track A SHA:

`f9aefef90b1493c579d7f72547efb4a3d8a0da25`

Why it qualifies:

- mature modular V1.4.x production line with multiple public releases;
- multi-stage architecture generation and chapter-blueprint generation;
- a simple production LLM seam, `BaseLLMAdapter.invoke(prompt) -> str`, that can be connected to Antigravity through a thin text transport without rebuilding the system;
- native chapter-context assembly that combines architecture, chapter blueprint, character state, historical summary and vector-retrieved memory;
- native finalization that updates global summary and character state;
- native Chroma vector memory;
- production-supported `MLStudioEmbeddingAdapter`, qualified locally with LM Studio and Nomic Embed Text without new paid API access;
- consistency-review workflow;
- external prose can enter the normal chapter/finalization path without controller-authored state synthesis.

Why it is useful against Zhanghui:

```text
AI_NovelGenerator:
multi-stage architecture + chapter blueprint
-> assemble text/vector memory
-> draft chapter
-> finalize summary + character state
-> persist semantic vector memory
-> optional consistency review

Zhanghui:
governed Canon / Intent / Craft
-> draft/review
-> extract observed changes
-> reconcile
-> durable ChapterCommit
-> rebuild projections
```

This compares a conventional hierarchical-text-plus-vector-memory architecture against Zhanghui's governed truth/acceptance model.

## Track B: Xiaoyangy/novel-studio

Repository: https://github.com/Xiaoyangy/novel-studio

Frozen audited SHA:

`ed04a106f665f456246af3c4414ba62992a2a1d1`

Why it remains important:

- complete local-first production engine;
- explicit world/character simulation, sealed render packets, review/actual-match/acceptance lifecycle and recoverable state;
- architecturally valuable contrast with Zhanghui.

Why it is not current Track A:

The Stage 0 transport audit found that its production `agentcore.ChatModel` path requires caller-owned structured tool definitions, interceptable tool calls and tool-result continuation. Antigravity's current headless/programmatic surface keeps its own host tool loop internal and does not expose that wire boundary. A controller-side emulation would reimplement novel-studio's agent loop, violating the thin-adapter rule.

It therefore remains a native product/workflow comparator in Track B rather than being replaced by a benchmark-authored imitation.

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

If an external project fails that test, do not replace it with a benchmark-authored imitation. Promote a mature reserve only after its own compatibility audit, or keep the incompatible system in the native product track. The novel-studio -> AI_NovelGenerator Track A substitution followed exactly this rule.
