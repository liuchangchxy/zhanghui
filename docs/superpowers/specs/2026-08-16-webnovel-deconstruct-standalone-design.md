# P1+P2: Standalone Deconstruction Skill + Chart-Scan Marked-References

**Date:** 2026-08-16
**Status:** Proposed (awaits user review)
**Scope:** P1 (chart-scan → deconstruct linkage) + P2 (standalone `/webnovel-deconstruct` skill)
**Builds on:** P0-Full (`2026-08-16-webnovel-init-deconstruction-wiring-design.md`) — reuses `deconstruction-agent`, `init_reference_tree.py`, `build_reference_tree()`, `validate_reference_tree()`.

## Background

P0-Full wired `webnovel-init` Step 1.5 to call `deconstruction-agent` and persist results as a multi-file tree. That work is complete. Two user-facing gaps remain:

1. **Users can't deconstruct a reference book OUTSIDE of `/webnovel-init`** — they have no way to "explore deconstruction" mid-writing, before committing to a new book, or to deconstruct multiple references for a single project.
2. **Chart-scan output has no handoff to deconstruction** — after scanning, users manually pick titles from `report.md` and re-type them into `/webnovel-init`. There's no "I marked these as 对标书, now deconstruct them" workflow.

Both are industry-standard features (oh-story-claudecode, harnessNovel, 笔灵, 星火 all have them as standalone, not init-bound).

## Goal

After this lands, users can:
1. Run `/webnovel-deconstruct <书名|路径|摘录>` at any time to deconstruct a reference into the project's `reference_research/` library
2. Run `/webnovel-chart-scan` → mark favorite titles → run `/webnovel-deconstruct --from-scan` to batch-deconstruct marked titles
3. Run `/webnovel-plan` and have it auto-discover **all** books in `.webnovel/reference_research/`, regardless of whether they came from init or standalone deconstruct

The standalone skill does NOT touch `idea_bank.json` — it's a reference library, not a project init input. P0-Full's init wiring is unchanged.

## Non-Goals

- No `webnovel.py deconstruct` CLI subcommand (slash command + plan auto-discovery is sufficient)
- No consumption by `webnovel-write` / `webnovel-review` (separate P3 spec)
- No full-text deconstruction beyond opening chapters (separate P4 spec; only golden-three analysis from P0-Full is reused)
- No English book title support (Chinese only for v1)
- No multi-user / team-shared `reference_research/` (single-user local)
- No retroactive migration of pre-existing projects

## Design Decisions (confirmed in brainstorming)

| Decision | Choice |
|---|---|
| P1 link strength | Pure manual + minimal `marked-references.json` manifest |
| P2 input forms | All three: book name (+platform hint), local file path, in-conversation excerpt |
| P2 output location | `<project>/.webnovel/reference_research/<book-safe>/` (same as init) |
| Multi-book per project | ✅ Multi-book via separate `<book-safe>/` directories |
| Re-deconstruct same book | Default **overwrite** with backup (different from init's default-refuse; standalone use is more exploratory) |
| Touches `idea_bank.json` | **No** — standalone library, plan auto-discovers |
| Quality gate | Same as init §1.5: `quality.passed=false` or `confidence < 0.85` → user picks (re-run/sparse/drop) |
| Plan discovery | Auto-scan `.webnovel/reference_research/*/` + use `idea_bank.reference_research_path` if set |

## Design

### D1. New command wrapper

Create `commands/deconstruct.md`:

```markdown
---
description: 独立拆解参考书到 .webnovel/reference_research/ 库（多书并存，不动 idea_bank）
---
Use the Skill tool to invoke the `webnovel-deconstruct` skill
```

### D2. New skill `webnovel-deconstruct`

Create `skills/webnovel-deconstruct/SKILL.md`. Sections:

1. **Goal** — Deconstruct a reference book into `<project>/.webnovel/reference_research/<book-safe>/`. Multi-book per project. No init coupling.

2. **Invocation**:
   - `/webnovel-deconstruct "起点《凡人修仙传》"` — quick mode (name only)
   - `/webnovel-deconstruct --text-path /path/to/chapter1.txt` — deep mode if readable
   - `/webnovel-deconstruct --excerpt "<paste in chat>"` — quick mode
   - `/webnovel-deconstruct --from-scan` — read `chart-scan/marked-references.json`, batch process

3. **Input collection**: One AskUserQuestion per ambiguity. Don't repeat init §1.5 verbatim — keep concise.

4. **Quality gate** (same as init §1.5):
   - Check `quality.passed` AND `confidence >= 0.85`
   - If failed: present 3 options (re-run with more text / sparse mode / drop)
   - User-confirm gate before any file write

5. **Execution**:
   - Call `deconstruction-agent` via Agent tool (subagent_type: webnovel-writer:deconstruction-agent)
   - Display `do_not_copy` + `canon_contamination_warnings` raw
   - On user confirm: `from init_reference_tree import build_reference_tree; build_reference_tree(project_path, schema, reference_title)` — note `overwrite=True` always (default for P2)
   - **Never** write to `idea_bank.json`, `.webnovel/state.json`, `设定集/`, `大纲/`, `正文/`, `.story-system/`
   - **Never** call `init_project.py`

6. **Output**: `<project>/.webnovel/reference_research/<book-safe>/` with the standard 5 files (P0-Full D3 layout):
   - `_schema.json`, `report.md`, `do_not_copy.md`, `canon_contamination_warnings.md`, `_progress.json`

7. **Backward compat**: Default overwrite. If `<book-safe>/` exists, backup `_schema.json` to `_schema.json.bak-<ts>` before overwrite. Do NOT ask user unless they passed `--strict`.

### D3. Unlock `deconstruction-agent` for multi-caller

Modify `agents/deconstruction-agent.md` frontmatter `description` field:

From:
```
description: /webnovel-init 的参考书拆解子代理。
```

To:
```
description: 从参考书抽取可迁移的创作模式。可被 /webnovel-init（Step 1.5）和 /webnovel-deconstruct（独立）调用。
```

Body of agent prompt unchanged (still Read/Grep/Bash-only, still returns `init_reference_research` JSON). Caller is responsible for persistence.

### D4. Chart-scan marked-references manifest

#### D4.1 New file: `chart-scan/marked-references.json`

Written by chart-scan (or by Claude on user request after viewing `report.md`). Schema:

```json
{
  "schema_version": 1,
  "marked_at": "2026-08-16T12:34:56Z",
  "from_scan": "./chart-scan/books.json",
  "references": [
    {
      "platform": "qidian",
      "title": "凡人修仙传",
      "author": "忘语",
      "category": "仙侠"
    }
  ]
}
```

#### D4.2 Update `skills/webnovel-chart-scan/SKILL.md`

Add a new section at the end of "使用案例":

```markdown
### 标记对标书（联动 /webnovel-deconstruct）

读完 `report.md` 后，可以告诉 Claude "标记对标：《A》《B》《C》"（书名列表）。
Claude 会把标记清单写到 `./chart-scan/marked-references.json`。

之后运行 `/webnovel-deconstruct --from-scan` 会读取这个清单，批量拆解所有标记的书。

查看当前标记清单：直接读 `./chart-scan/marked-references.json`（如果有）。
```

#### D4.3 Update `skills/webnovel-chart-scan/scripts/output.py` (optional helper)

Add a `write_marked_references(references: list[dict], output_dir: str) -> Path` helper that writes `marked-references.json` with the schema above. The helper is callable from chart-scan SKILL.md flow but does NOT run automatically (chart-scan stays hermetic — no auto-write of marked-references.json).

### D5. Update `webnovel-plan` for auto-discovery

Modify `skills/webnovel-plan/SKILL.md` lines 100-117 (the P0-Full "按需读取 reference_research 拆书产物" section) to:

1. After reading `idea_bank.json`, scan `.webnovel/reference_research/` for all `<book-safe>/` subdirectories.
2. For each, load `_schema.json` + `report.md` (excerpts) + `do_not_copy.md` + `canon_contamination_warnings.md`.
3. Deduplicate (same `<book-safe>` only once).
4. If `idea_bank.reference_research_path` is set, that tree is the **primary**; other trees are **secondary references**.
5. Plan uses primary tree for "对标" alignment, secondary trees for "参考" diversity.

The existing path-convention consumption stays valid — backward compatible.

### D6. Files modified / created

| File | Action | Purpose |
|---|---|---|
| `commands/deconstruct.md` | **Create** | Slash command wrapper |
| `skills/webnovel-deconstruct/SKILL.md` | **Create** | Main skill (~120 lines) |
| `agents/deconstruction-agent.md` | **Modify** | Unlock description to allow multi-caller |
| `skills/webnovel-chart-scan/SKILL.md` | **Modify** | Add "标记对标书" section (~30 lines added) |
| `skills/webnovel-chart-scan/scripts/output.py` | **Modify** | Add `write_marked_references()` helper (~25 lines) |
| `skills/webnovel-plan/SKILL.md` | **Modify** | Auto-discover `.webnovel/reference_research/*/` |
| `scripts/data_modules/marked_references.py` | **Create** | Schema + read/write helpers (~60 lines) |
| `scripts/data_modules/tests/test_deconstruction_agent_multi_caller.py` | **Create** | Test agent description unlocked (1 test) |
| `scripts/data_modules/tests/test_marked_references.py` | **Create** | Schema + read/write tests (5 tests) |
| `scripts/data_modules/tests/test_prompt_integrity.py` | **Modify** | Add 2 new tests: `test_plan_auto_discovers_reference_research`, `test_chart_scan_skill_mentions_marked_references` |

No new skill registration needed (skills dir resolution is automatic via `plugin.json`).

### D7. Out-of-scope confirmations

- **P3**: `webnovel-write` / `webnovel-review` consumption of `reference_research` is a separate spec. Plan's auto-discovery already handles this for plan; write/review are next.
- **P4**: Full-text deconstruction beyond golden-three chapters — separate spec.
- **Option C content**: `webnovel.py deconstruct` CLI subcommand — explicitly deferred.
- **English book titles**: Chinese-only for v1. Agent already accepts CJK characters; English titles would need additional slug handling (currently `sanitize_book_title` only handles CJK range).

## Testing Strategy

### T1. New agent description test

Add `test_deconstruction_agent_multi_caller` to `test_prompt_integrity.py`:

```python
def test_deconstruction_agent_is_not_init_only():
    """Agent description must allow multiple callers (init Step 1.5 + standalone deconstruct)."""
    text = _read_text(REPO_ROOT / "agents" / "deconstruction-agent.md")
    assert "/webnovel-deconstruct" in text, "agent must mention deconstruct skill as caller"
    assert "/webnovel-init" in text, "agent must still mention init Step 1.5 as caller"
```

### T2. marked_references module tests

Create `test_marked_references.py` with 5 tests:

1. `test_schema_version_required` — payload missing `schema_version` raises ValueError
2. `test_minimal_valid_payload` — minimal `{schema_version: 1, references: []}` validates
3. `test_reference_must_have_platform_and_title` — payload with reference missing `platform` fails
4. `test_roundtrip_via_disk` — write → read → equal (using tmp_path)
5. `test_load_returns_empty_if_file_missing` — `load_marked_references(path)` returns `None` (not error) when file absent

### T3. Plan auto-discovery test

Add `test_plan_auto_discovers_reference_research` to `test_prompt_integrity.py`:

```python
def test_plan_auto_discovers_reference_research():
    """plan SKILL.md must scan .webnovel/reference_research/*/ for ALL trees, not just idea_bank pointer."""
    text = _read_text(SKILLS_DIR / "webnovel-plan" / "SKILL.md")
    assert ".webnovel/reference_research/" in text
    # Must mention scanning the directory (multi-tree support)
    assert "scan" in text.lower() or "扫描" in text or "glob" in text or "*" in text
```

### T4. Chart-scan marked-references mention test

Add `test_chart_scan_skill_mentions_marked_references`:

```python
def test_chart_scan_skill_mentions_marked_references():
    """chart-scan SKILL.md must mention marked-references.json + /webnovel-deconstruct --from-scan."""
    text = _read_text(SKILLS_DIR / "webnovel-chart-scan" / "SKILL.md")
    assert "marked-references" in text or "marked_references" in text
    assert "/webnovel-deconstruct" in text or "webnovel-deconstruct" in text
```

### T5. Manual smoke

1. Run `chart-scan` → verify `report.md` shows TOP books
2. Tell Claude "标记对标：《凡人修仙传》《完美世界》" → verify `./chart-scan/marked-references.json` exists
3. Run `/webnovel-deconstruct --from-scan` → verify two trees at `.webnovel/reference_research/{fanren-xiuxian-chuan,wanmei-shijie}/`
4. Verify `idea_bank.json` was NOT created (P2 doesn't touch it)
5. Re-run `/webnovel-deconstruct --from-scan` → verify trees are overwritten (not refused), with `.bak-<ts>` backups
6. Run `/webnovel-plan` on a project where init never ran (only P2 ran) → verify plan finds the trees and uses them
7. Verify plan reads both `idea_bank.reference_research_path` (if set) AND any number of `reference_research/*/` trees

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| P2 conflicts with P0-Full init wiring (same output dir, different overwrite semantics) | Default-overwrite in P2 vs default-refuse in init is intentional — P2 is exploratory, init is committed. Document difference in SKILL.md and command help text. |
| Multi-book in `.webnovel/reference_research/` creates naming collisions | `sanitize_book_title()` (P0-Full) handles slug uniqueness; collisions on different titles produce different safe names; collisions on same title default to overwrite |
| `marked-references.json` may reference books that agent can't recognize | Surface `quality.passed=false` per book; user can `drop` per item or batch |
| Plan auto-discovery loads too many trees and blows context | Add max-trees guard (e.g., load max 5 trees; warn if more). Document as future work. |
| Agent description change breaks existing init §1.5 tests | New test in T1 explicitly verifies both callers mentioned |
| P2 users may accidentally init via this path (overlapping concerns) | SKILL.md clearly states "P2 never writes idea_bank.json"; init is a separate command |

## Acceptance Criteria

- [ ] `commands/deconstruct.md` exists and is a valid slash command wrapper
- [ ] `skills/webnovel-deconstruct/SKILL.md` exists with all 7 sections (Goal, Invocation, Input, Quality Gate, Execution, Output, Backward compat)
- [ ] `deconstruction-agent.md` description mentions BOTH `/webnovel-init` and `/webnovel-deconstruct` as callers
- [ ] `skills/webnovel-chart-scan/SKILL.md` mentions `marked-references.json` + `/webnovel-deconstruct`
- [ ] `scripts/data_modules/marked_references.py` exists with read/write + schema validation
- [ ] `webnovel-plan/SKILL.md` mentions scanning `.webnovel/reference_research/*/`
- [ ] T1 (1 test), T2 (5 tests), T3 (1 test), T4 (1 test) all pass
- [ ] All P0-Full tests still pass (no regression)
- [ ] Manual smoke T5 succeeds end-to-end
- [ ] No new command in `webnovel.py` CLI (per non-goal)
- [ ] `idea_bank.json` is NOT touched by P2 (verified by smoke)
- [ ] `deconstruction-agent` body is unchanged (only frontmatter description)

## Out of Spec (deferred)

- **P3**: `webnovel-write` / `webnovel-review` consumption of `reference_research`
- **P4**: Full-text deconstruction beyond opening chapters
- **English book titles**: separate spec if needed
- **`webnovel.py deconstruct` CLI subcommand**: explicitly deferred per non-goal
- **Multi-user shared `reference_research/`**: separate spec if needed
- **Plan auto-discovery cap (max 5 trees)**: future enhancement

---

## Migration Note

Existing projects (with `idea_bank.json.reference_research_path` set from P0-Full init) are unaffected by this spec — the plan's existing path-convention reading still works. The new auto-discovery simply adds **additional** trees from standalone deconstructs. No migration required.