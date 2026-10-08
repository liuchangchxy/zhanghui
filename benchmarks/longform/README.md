# Zhanghui Long-Form Effectiveness Benchmark

This directory is the implementation boundary for Issue #13.

The benchmark exists to answer a product question, not to prove the current architecture correct:

> Does Zhanghui's Story Truth system improve long-form writing enough to justify its complexity compared with simpler memory designs?

## Experimental tracks

### Primary: memory/truth architecture comparison

All arms use the same story seed, master outline, per-chapter author Intent, target length, common prose instructions, and model/runtime configuration available to the executor.

Only long-term context and memory differ:

- **A / minimal** — static story setup + current chapter Intent + previous two chapters. No persistent Story Bible, long-term RAG, structured Canon ledger, or Zhanghui truth machinery.
- **B / lightweight** — A plus one compact mutable Story Bible and simple retrieval over prior prose/summaries. It must remain intentionally simpler than Zhanghui.
- **C / zhanghui** — current governed Zhanghui Canon / Intent / Craft / Reference context and Story Truth machinery.

This is the primary track because it can attribute differences mainly to the memory/truth design.

### Secondary: product workflow comparison

Only after the primary harness is accepted, a separate report may compare practical end-to-end workflows, including the real current `/webnovel-write` flow for C.

Do not mix primary and secondary results.

## Stages

| Stage | Scope | Purpose |
| --- | --- | --- |
| 0 | 1 scenario × 3 arms × 3 chapters | Harness smoke only |
| 1 | 1 scenario × 3 arms × 10 chapters | Pilot and evaluator audit |
| 2 | ≥3 scenarios × 3 arms × 30 chapters | Formal comparison |
| 3 | 50–100 chapters if justified | Long-horizon confirmation |

No architecture conclusion may be drawn from Stage 0.

## Required measurements

Narrative consistency:
- Canon contradiction rate
- temporal contradiction rate
- character-state contradiction rate
- open-loop / promise lifecycle error rate

Extraction:
- Data Agent extraction precision
- Data Agent extraction recall

Operational:
- accountable/human interventions
- elapsed time
- retry/failure count
- token usage only when reliably measured; otherwise record `unavailable`

Output:
- blinded prose-quality ratings kept separate from consistency scores

## Evaluation rules

1. Zhanghui projections are never ground truth for judging Zhanghui.
2. Findings must cite prose-grounded evidence.
3. Arm identity should be hidden from evaluators where practical.
4. Ambiguous or low-confidence findings remain unresolved.
5. Evaluator versions are immutable for a compared run set; changing an evaluator requires rerunning all affected arms.
6. Generation and evaluation are separate phases. The harness must ingest externally generated chapters.
7. Hidden evaluator/oracle material must not enter generation context.
8. Existing pytest/behavior-eval pass counts are not narrative-effectiveness evidence.

## Contradiction taxonomy

At minimum:
- `FACTUAL_ENTITY`
- `CHARACTER_STATE`
- `RELATIONSHIP`
- `WORLD_RULE`
- `TEMPORAL`
- `LOCATION`
- `OBJECT_OWNERSHIP`
- `EPISTEMIC`
- `OPEN_LOOP`

An `EPISTEMIC` error includes incorrectly promoting a character statement, rumor, belief, prediction, dream, or allegation into objective world truth.

## Existing repository facilities

- `.claude/plugins/zhanghui/scripts/run_behavior_evals.py` remains a deterministic package/behavior contract suite. It is not this benchmark.
- `.webnovel/observability/data_agent_timing.jsonl` may provide one measured timing source for arm C but is not sufficient as experiment telemetry.

## Directory contract

The implementation should converge on:

```text
benchmarks/longform/
  README.md
  protocol/
  scenarios/
  schemas/
  capture/
  evaluators/
  reports/
  tests/
```

The checked-in protocol and schemas are the contract. Runtime code must not silently reinterpret them.

## Scope boundary

This benchmark must not modify production Story Truth behavior merely to improve C's score. Production changes discovered by the benchmark belong in separate Issues after the evidence is reviewed.

Refs: #13
