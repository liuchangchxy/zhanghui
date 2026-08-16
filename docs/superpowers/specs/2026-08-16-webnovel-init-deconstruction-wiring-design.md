# Init ↔ Deconstruction-Agent Wiring (P0-Full)

**Date:** 2026-08-16
**Status:** Proposed (supersedes `-lite` version, archived 2026-08-16)
**Scope:** P0-Full of the deconstruction-feature decision matrix
**Supersedes:** `2026-08-16-webnovel-init-deconstruction-wiring-lite-design.md`

## Background

The plugin ships a `deconstruction-agent` (Read/Grep/Bash-only subagent) that returns a structured `init_reference_research` JSON. The agent is implemented but never invoked because:

1. `skills/webnovel-init/SKILL.md` does not call the agent (no Step 1.5). `test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate` currently fails.
2. `scripts/init_project.py` never writes `.webnovel/idea_bank.json`, even though `webnovel-init/SKILL.md §"写入 idea_bank.json"` says it should, and `webnovel-plan/SKILL.md:98` reads it.

### Why P0-Full, not P0-Lite

Prior art research (2026-08-16) on `oh-story-claudecode` (Claude Code skill pack, MIT) and `harnessNovel` (Python AI agent, GPL-3.0) revealed:

- Both ship **standalone** deconstruction features (not init sub-steps).
- Both produce **multi-file output trees** (`拆文库/<书>/` with `拆文报告.md` + `剧情/` + `角色/` + `设定/` + `章节/` in oh; `reference/chapter_cards/*.json` + `reference/outlines/vol_*/story_arcs/` in harnessNovel).
- Both expose richer dimension schemas (8-10 dimensions) than our 9-field JSON.
- Both downstream consumers (`write` / `outline` / `arcs`) consume deconstruction output via **path convention**, not optional grep.
- Both treat deconstruction as the **persistent reference archive**, not as transient init input.

The original P0-Lite spec (single JSON → `.webnovel/idea_bank.json`) would fix the broken wiring but leave the plugin materially weaker than both competitors. P0-Full aligns with the industry-standard artifact shape while keeping the change scoped to the init wiring path.

### Differentiation we preserve

- **state.json + SQLite RAG** — recoverable state + semantic retrieval beats competitors' pure file-path conventions.
- **Dual-engine deslop** (deterministic + LLM-judge) — beats competitors' single-pass humanize post-processing.
- **Three-phase pipeline** (init → plan → write) — gives users the "no reference" path competitors lack.
- **`webnovel-resume` skill** — already gives us incremental continuation; competitors hand-roll it per project.

## Goal

When a user runs `/webnovel-init` and voluntarily provides a reference novel:

1. The agent is invoked from Step 1.5 with an **extended schema** (chapter_rhythm, highlights, foreshadowing, gains_costs, emotion_curve, boundary_reason, narrative_function, protagonist_action_chain, satisfaction_point, character_changes — added to existing 9 fields).
2. The agent's output is persisted to a **multi-file product tree** at `.webnovel/reference_research/<book-safe>/`, not just a single JSON.
3. `idea_bank.json` is written as before, but now **references the path** of the product tree.
4. `webnovel-plan` SKILL.md is updated to read specific files from the product tree via **path convention** (not optional grep).
5. Re-running init on the same reference reuses the existing product tree (no full re-extraction) via `webnovel-resume` mechanism.

When the user does **not** provide a reference novel, the init flow is unchanged and `reference_research/` is **not** created.

## Non-Goals

- No standalone `/webnovel-deconstruct` command (deferred to a separate spec; P2 in decision matrix).
- No `/webnovel-chart-scan --auto-deconstruct` linkage (deferred; P1).
- No `webnovel-write` / `webnovel-review` consumption of `reference_research/` (separate spec; the write phase's "对标召回" is a larger feature).
- No retroactive patching of pre-existing projects.
- No changes to `deconstruction-agent.md` schema that would break the existing prompt-integrity test (we ADD fields, do not remove or rename existing 9).
- No new skill or command in this PR — `deconstruction-agent` remains the sole invocation surface.

## Design

### D1. Extend `deconstruction-agent` output schema (additive, non-breaking)

The agent's top-level `init_reference_research` JSON grows from 9 fields to ~16 fields. **All 9 existing fields (`reader_promise`, `opening_hook_patterns`, `cool_point_loops`, `protagonist_patterns`, `antagonist_pressure_patterns`, `pacing_notes`, `borrowable_structures`, `differentiation_requirements`, `init_candidates`) keep their names and meanings.** New fields:

| New field | Type | Meaning | Why |
|---|---|---|---|
| `chapter_rhythm` | object: `{ core_content, emotion_tone, beat_detail }` × N | Per-chapter rhythm triplet for the first 1-3 chapters (golden three) | harnessNovel forces this; without it plan has no chapter-level rhythm anchor |
| `narrative_function` | string | Overall plot function archetype (升级流 / 复仇线 / 多线交织 / 单元剧 etc.) | oh-story-claudecode uses this in Stage 3; needed for plan's volume_outline alignment |
| `boundary_reason` | object: `{ first_arc_start, first_arc_end, reason }` | Natural narrative boundary in opening chapters | harnessNovel forces this; needed for plan to map arc boundaries |
| `protagonist_action_chain` | array of `{ trigger, action, result }` | Trigger→action→result chains in golden three | harnessNovel forces this; needed for chapter-level hook design |
| `emotion_curve` | array of `{ chapter, intensity, label }` | Emotion intensity curve across chapters 1-3 (label ∈ {紧张, 热血, 爽, 甜, 温馨, 压抑, 悲伤, 轻松, 恐怖, 其他}) | oh has "全书情绪节奏" / harnessNovel has `emotion_rhythm`; without it plan writes blind to pacing |
| `satisfaction_point` | array of strings | 1-6 single-line "highlight" beats in golden three (金句/梗/爆点) | harnessNovel forces this; needed for chapter writer's tone anchoring |
| `foreshadowing` | array of `{ setup_chapter, payoff_chapter_estimate, content }` | Foreshadow map within golden three | harnessNovel forces this; foundation for plan's cross-chapter tracking |
| `gains_costs` | array of `{ chapter, gain, cost, category }` (category ∈ {物质, 实力, 关系, 认知}) | Per-chapter gains/costs | harnessNovel forces this; needed for protagonist_flaw payoff tracking |
| `character_changes` | array of `{ chapter, character, before, after }` | Per-chapter character delta | harnessNovel forces this; needed for chapter-level consistency |

The agent prompt is updated with a new section listing the 9 new fields and their meaning. **The existing tool-whitelist test (`test_agent_write_ownership_matches_tools_frontmatter`) and the existing schema-field assertions remain untouched.**

### D2. Step 1.5 in `webnovel-init/SKILL.md`

Same shape as P0-Lite spec D1, with two changes:

- The literal "Use the Agent tool to run `webnovel-writer:deconstruction-agent`" still triggers the agent.
- After agent returns, the main flow **builds the multi-file tree** (D3), not a single JSON.
- The forbidden path list now includes `.webnovel/reference_research/`-adjacent phrases being forbidden for the agent itself (still cannot Write), but the main flow's responsibility to write there is **explicit and required**.

### D3. Multi-file product落点

Agent returns a single `init_reference_research` JSON. Main flow **splits** it into a multi-file tree under `.webnovel/reference_research/<book-safe>/`:

```
.webnovel/reference_research/<book-safe>/
├── _schema.json                  # Full init_reference_research (machine-readable)
├── report.md                     # 人类可读综合报告 (rendered from schema)
├── do_not_copy.md                # 仅含 do_not_copy 字段，独立成文方便 review/revise 引用
├── canon_contamination_warnings.md  # 同上，独立成文
├── opening_chapters/             # 仅当有原文摘录时生成
│   ├── chapter_001_深度拆解.md   # 含 chapter_rhythm + emotion_curve + highlights
│   ├── chapter_002_深度拆解.md
│   └── chapter_003_深度拆解.md
└── _progress.json                # 续跑状态（see D6）
```

`<book-safe>` = reference title sanitized: strip path-illegal chars, replace spaces with `-`, lowercase, max 64 chars. **Refuse to create a second tree for a book with the same safe name without explicit `--reference-overwrite` flag.**

`_schema.json` is the verbatim agent output (no transformation). `report.md` is rendered from schema using a Jinja-style template embedded in `webnovel-init/SKILL.md` (so the agent itself doesn't render). `do_not_copy.md` and `canon_contamination_warnings.md` are verbatim field extracts with section headers.

If `opening_chapters/` cannot be generated (no local text available — quick mode), skip that subdir but keep the others.

### D4. `idea_bank.json` references the tree

The `idea_bank.json` schema from P0-Lite is extended with one new top-level field:

```json
{
  "version": 1,
  ... existing fields ...
  "reference_research_path": ".webnovel/reference_research/<book-safe>/"
}
```

When `webnovel-plan` reads `idea_bank.json`, it now follows the pointer to the tree (D5). When the tree is missing or empty, plan surfaces a "reference_research missing" notice (not a hard error — plan still runs).

### D5. `webnovel-plan` consumes the tree

`webnovel-plan/SKILL.md` is updated:

1. After reading `idea_bank.json`, if `reference_research_path` is set, plan loads:
   - `_schema.json` (entire schema, full injection — file is small)
   - `report.md` (excerpted sections only: "可复现模块" + "反套路" + "硬约束", max ~500 lines)
   - `do_not_copy.md` (full — short)
   - `canon_contamination_warnings.md` (full — short)
2. Plan uses these for:
   - `narrative_function` + `boundary_reason` → volume-level structure alignment
   - `emotion_curve` + `satisfaction_point` → per-chapter pacing reference
   - `foreshadowing` → cross-chapter continuity constraints
   - `gains_costs` + `character_changes` → protagonist_flaw payoff reminders
3. Path-convention consumption: plan grep-finds `设定/题材定位.md` and `设定/对标定位.md` if they exist; if they exist and reference a different tree, plan follows that tree instead of idea_bank's pointer.

No new CLI flags or scripts for plan — this is purely a SKILL.md doc change.

### D6. Incremental continuation via `webnovel-resume`

If init is re-run with the same reference (same `<book-safe>`):

1. Main flow checks for `.webnovel/reference_research/<book-safe>/_schema.json` existence.
2. If exists and `created_at` is within 7 days AND no `quality.passed=false` flag → main flow offers three options: (a) reuse, (b) re-run with more text (deep mode), (c) abandon.
3. If user picks (a): copy the existing tree to a backup (`_schema.json.bak-<timestamp>`), reuse as-is, refresh `idea_bank.json` pointer only.
4. If (b): call agent in deep mode, write `_progress.json` with new schema_version, mark old fields as `superseded`.
5. The `webnovel-resume` skill's state.json mechanism handles the rest (no new code in resume).

`_progress.json` schema:

```json
{
  "schema_version": 1,
  "reference_title": "...",
  "created_at": "ISO8601",
  "last_updated": "ISO8601",
  "superseded_versions": [],
  "quality_flags": { "passed": true, "confidence": 0.88, "issues": [] }
}
```

### D7. Files modified

| File | Change |
|---|---|
| `agents/deconstruction-agent.md` | Add new section listing the 9 new fields (additive; existing 9 untouched). Extend tool whitelist assertion test only if needed (it shouldn't be). |
| `skills/webnovel-init/SKILL.md` | Insert `### Step 1.5：灵感来源询问` between Step 1 and Step 2 (P0-Lite wording + new "build multi-file tree" responsibility). Add `用户确认前` / `Step 2-6 只能使用用户确认过...` strings to Step 2 preamble. Add `汇总 Step 1.5 已确认的灵感来源` to Step 6. |
| `skills/webnovel-plan/SKILL.md` | New section after the existing "按需读取设定集" line: load reference_research tree if `idea_bank.json.reference_research_path` is set. |
| `scripts/init_project.py` | Add `--reference-research-dir <path>` flag (used by init main flow to specify pre-built tree). Add `--reference-overwrite` flag. Tree creation lives in **main flow**, not init_project.py — to avoid re-rendering the report.md template. init_project.py only validates the tree exists if the flag is set. |
| `scripts/data_modules/tests/test_init_idea_bank.py` | Add tests for reference_research tree validation in init_project.py. |
| `scripts/data_modules/tests/test_prompt_integrity.py` | Existing test continues to pass; add assertions for new literals if needed. |

No new files except test additions. No new skill. No new command.

### D8. Out-of-scope confirmations (intentional)

- `webnovel-write` / `webnovel-review` are not modified. Reference召回 in write is a larger feature with its own RAG + prompt-injection design — separate spec.
- `deconstruction-agent.md` field additions are **additive only** — no field is renamed or removed. Backward compatibility preserved for any external code reading the 9 existing fields.
- `_meta.json`-style numbering for short-form deconstruction (oh-style) is **not** introduced; long-form only.

## Testing Strategy

### T1. Test red→green (P0-Lite invariant)

`test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate` must continue to pass after D2 changes (all 9 existing handoff fields + 6 forbidden paths + literal phrases preserved).

### T2. New agent schema assertions

Add to `scripts/data_modules/tests/test_prompt_integrity.py` (new test function):

- `test_deconstruction_agent_schema_extension` — assert `deconstruction-agent.md` mentions all 9 new field names: `chapter_rhythm`, `narrative_function`, `boundary_reason`, `protagonist_action_chain`, `emotion_curve`, `satisfaction_point`, `foreshadowing`, `gains_costs`, `character_changes`. Assert none of the 9 existing field names are removed or renamed (greppable: each old field name still appears in the agent prompt).

### T3. New init tests

Add to `scripts/data_modules/tests/test_init_idea_bank.py`:

- `test_init_validates_reference_research_dir_when_flag_present` — pre-create a minimal valid tree, run init with `--reference-research-dir <path>`, assert success.
- `test_init_refuses_missing_reference_research_dir` — pass a nonexistent path, assert hard error.
- `test_init_refuses_overwrite_existing_reference_research_without_force` — pre-create a tree, run init without `--reference-overwrite`, assert SystemExit + tree unchanged.
- `test_init_overwrites_with_explicit_force_flag` — same setup with `--reference-overwrite`, assert overwrite.

### T4. Plan consumption smoke

Add to `scripts/data_modules/tests/test_prompt_integrity.py`:

- `test_plan_reads_reference_research_when_pointer_set` — assert `webnovel-plan/SKILL.md` contains the literal `reference_research_path` and a path-convention consumer pattern (e.g., `read_text\(.*reference_research.*_schema\.json`).

### T5. Manual smoke (T3 from prior lite spec, expanded)

1. Run init with reference "《凡人修仙传》" + 3-chapter excerpt → Step 1.5 fires → agent returns extended JSON → main flow builds tree.
2. Tree exists at `.webnovel/reference_research/fanren-xiuxian-chuan/` with all 5 files + `opening_chapters/` populated.
3. `idea_bank.json` has `reference_research_path` pointing to the tree.
4. Run `/webnovel-plan` → confirm plan reads tree (one-shot print in plan, or verify chapter outline references emotion_curve or foreshadowing).
5. Re-run init with same reference → main flow offers reuse/re-run/abandon (default reuse).
6. Without reference: Step 1.5 still asks once, user picks "原创", `reference_research/` NOT created, `idea_bank.json` NOT created, everything else unchanged.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Adding 9 fields to agent schema is a big prompt change → regressions in agent quality | Field additions are additive; existing 9 fields keep their semantics; agent quality validated via T5 manual smoke (golden three demo) |
| Multi-file tree creation lives in main flow (Claude), not init_project.py → less testable | Tree creation is pure file IO + Jinja-style template; the Jinja template is the only testable artifact (assert template renders valid Markdown given minimal schema) |
| `idea_bank.json.reference_research_path` could be a stale pointer if tree is deleted | Plan surfaces "reference_research missing" notice; not a hard error; user can manually edit idea_bank.json or run init again |
| Plan consuming tree may double-load data (idea_bank + tree) | Plan reads tree ONLY if pointer is set; idea_bank still reads; tree data wins for overlapping fields |
| Sanitization `<book-safe>` collisions (e.g., two books both normalize to same name) | `--reference-overwrite` flag required for same-name re-extraction; default is refuse |
| `_progress.json` schema_version drift over time | Version field is monotonic; old versions retained in `superseded_versions[]` |
| Existing integrity test breakage due to schema extension | All existing literals preserved (T1 invariant); new literals additive (T2) |

## Acceptance Criteria

- [ ] `test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate` still passes (no regression)
- [ ] `test_deconstruction_agent_schema_extension` passes (new)
- [ ] `test_plan_reads_reference_research_when_pointer_set` passes (new)
- [ ] `test_init_idea_bank.py` has 4 new tests passing (T3 list)
- [ ] `deconstruction-agent.md` mentions all 9 new field names; existing 9 field names still present
- [ ] `webnovel-init/SKILL.md` Step 1.5 instructs main flow to build multi-file tree
- [ ] `webnovel-plan/SKILL.md` consumes tree via path convention when `idea_bank.reference_research_path` is set
- [ ] `init_project.py` has `--reference-research-dir` + `--reference-overwrite` flags
- [ ] Manual smoke (T5) succeeds end-to-end with and without reference novel
- [ ] Re-init on same reference offers reuse/re-run/abandon (not silent overwrite)
- [ ] No new skill, command, or agent created
- [ ] Tree structure under `.webnovel/reference_research/<book-safe>/` matches D3 layout

## Out of Spec (deferred to separate specs)

- **P1:** `/webnovel-chart-scan --auto-deconstruct <book>` — manual user flow already exists in oh/harnessNovel; our chart-scan v0.3 will add the auto-link.
- **P2:** Standalone `/webnovel-deconstruct` skill — explicitly recommended per industry consensus; needs its own spec for the "随时随地拆书" use case (multi-book storage, learning notes output variant).
- **P3:** `webnovel-write` / `webnovel-review` consumption of reference_research — needs prompt-injection design + RAG integration; larger feature.
- **P4:** Agent schema extension to "全本结构" (chapters 4-N, not just 1-3) — oh/harnessNovel cover this; our agent currently only handles opening excerpt.

---

## Migration Note

If a project already has `.webnovel/idea_bank.json` from a prior (manually written or future lite-version) init, the new `reference_research_path` field is simply missing. Plan treats this as "no pointer" and runs in the old mode (no tree consumption). This preserves backward compatibility with any pre-existing projects.