# PR: experiment — minimal literary editor on Zhanghui finals

## What this is

A self-contained experiment under `experiments/jarvis-literary-gain-20261107/`.
It does **not** modify the production chain, Canon, Data Agent, reconciliation,
Step 2B, Step 4, or add any agent.

Question: can Zhanghui's final drafts gain Jarvis-like reading appeal and
lower author explanation without losing their naturalness / immersion?

## Design

- A = Zhanghui final (`e2e/zhanghui/chNN/published.md`, fingerprint stripped)
- B = A after one pass of a five-principle literary editor
- Jarvis final is used for analysis only; it is never in the editor prompt or the A/B.
- Frozen sample: ch03, ch04, ch05, ch08 (see `SAMPLE_SELECTION.md`, `FREEZE.json`)
- Blind: two judge families, two passes each, forced position reversal,
  six dimensions (overall, reading appeal, low author explanation,
  sentence naturalness, scene immersion, subtext).

## Result

- Two judge families (`codex/gpt-6.1-terra` and Gemini 3.8 Flash), two passes per chapter
  with forced position reversal, six dimensions.
- **48/48 stable verdicts point to B (edited); 0 SPLIT, 0 TIE, 0 A wins.**
  This includes `READING_APPEAL`, `LOW_AUTHOR_EXPLANATION`, `SENTENCE_NATURALNESS`,
  `SCENE_IMMERSION`, `SUBTEXT`, and `OVERALL_PREFERENCE`.
- Deterministic checks: no number/date/term/event changes, no terminology substitutions.
- Manual review found two real content side effects:
  - ch04 deleted the 19/7 → door/valve/post-change inference link and
    "原值班室他进不去。第二张单子也不会有。"
  - ch05 deleted the chapter-end "交接班登记簿" propulsion and compressed to 87.7%
    (below the editor's own 90% floor).

## Verdict

**PARTIAL** — clear, stable literary gain; two locatable content losses and one length-floor
violation. Not a production integration. Next round needs two narrow guards (protect the
chapter-end next action / hard constraint; protect number→conclusion inference sentences)
and a hard 90% floor, not a new architecture.

Full report: `report/REPORT.md`.

## Artifacts

- `analysis/ANALYSIS.md` — text-level attribution from actual prose
- `analysis/MANUAL_REVIEW.md` — content-loss / term / event checks
- `report/REPORT.md` — full report
- `blind/` — prompts, raw judgements, aggregate
- `outputs/` — A inputs, B outputs, diffs, deterministic checks
