## What this is

A held-out validation of the five literary-editing principles from PR #66.
The principles are frozen; the six chapters here did not participate in deriving them.
This PR does **not** modify the production chain, Canon, Data Agent, reconciliation,
Step 2B, Step 4, or add any agent.

Question: do the PR #66 principles still improve literary quality on unseen chapters
without damaging content?

## Design

- Test set, fixed before generation: ch01, ch02, ch06, ch07, ch09, ch10.
- Five principles copied verbatim from PR #66.
- Three guards added, each from a real PR #66 failure:
  1. protect next-step / direction / time-place constraints / chapter-end hooks;
  2. protect "number/object/evidence → key conclusion" inference links;
  3. hard 90% length floor (`EDITOR_REJECT_LENGTH`, no padding, no rerun).
- A = Zhanghui final; B = one frozen editor pass.
- Jarvis text is never in the editor input or the A/B.
- Blind: two judge families, two passes per chapter, forced position reversal,
  six dimensions.

## Result

- **72/72 stable verdicts point to B; 0 SPLIT, 0 TIE, 0 A wins.**
  Both judge families, both positions, all six dimensions.
- Chapter-level `OVERALL_PREFERENCE`: **6/6 strict B** (both judges B on every chapter).
- `READING_APPEAL` and `LOW_AUTHOR_EXPLANATION`: **12/12 B each**.
- `SENTENCE_NATURALNESS` and `SCENE_IMMERSION`: **12/12 B each** (no A wins).
- All six chapters passed the 90% floor on the first call (92.50%–98.02%);
  no retries, no truncation, no `EDITOR_REJECT_LENGTH`.

## Content

- **0 HARD losses.** No event outcome, knowledge state, item ownership, number/date/ID,
  or terminology change; no unique next-step action, investigation direction, or
  time/place constraint deleted.
- **SOFT losses are real and locatable**, despite the blind result:
  - ch02: the standalone chapter-end hook "明天。" was deleted (the next-day information
    remains in dialogue, but the final beat is gone);
  - ch06: "不是问。" and the emotional settlement sentence "他换到的，比交出去的少。"
    were deleted;
  - ch09: the only closing sensory-memory sentence was deleted;
  - ch07: the negotiation action "乔宁的手没把它推回来" was deleted.
- The three guards eliminated the PR #66-style HARD losses, but did not protect
  chapter-end hooks / emotional settlement / closing sensory carrying.
- Blind judges sometimes praised exactly these deletions as gains (e.g. ch06's
  "他换到的，比交出去的少。"), so the blind score cannot substitute for content review.

## Verdict

**PARTIAL.**

Literary generalization is strong and stable (6/6 chapters, 72/72 judgements, no SN/SI
decline). Fact/function-level content is intact and no length guard was violated.
But three locatable SOFT losses — especially ch02's chapter-end hook — mean the
pre-registered "no content damage" condition is not fully met. Not FAIL: no HARD
content loss and no systematic naturalness/immersion decline.

Next round would need only one narrow guard: preserve standalone chapter-end hooks
and emotional/sensory closing beats. No new architecture, agents, or semantic gate.


## Artifacts

- `SAMPLE_SELECTION.md`, `ANALYSIS_PLAN.md`, `FREEZE.json`
- `prompts/editor_zh_heldout.md`
- `inputs/` — source, outline, hard limits, next-chapter opening, provenance
- `outputs/` — B, run records, diff, deterministic checks
- `blind/` — prompts, raw judgements, evidence, aggregate
- `analysis/` — manual content review
- `report/REPORT.md` — full report

🤖 Generated with [Claude Code](https://claude.com/claude-code)
