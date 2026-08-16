# P3: Write / Review Consume reference_research

**Date:** 2026-08-16
**Status:** Proposed
**Scope:** P3 (write + review consume `reference_research/` produced by P0-Full + P1+P2)
**Builds on:** P0-Full (deconstruction wiring), P1+P2 (standalone deconstruct), 14 adversarial fixes (already shipped).

## Background

P0-Full wired `/webnovel-init` Step 1.5 to call `deconstruction-agent` and persist results as a multi-file tree under `<project>/.webnovel/reference_research/<book-safe>/`. P1+P2 added a standalone `/webnovel-deconstruct` skill that creates the same trees independently of init. **Both flows end with the same artifact on disk.**

The remaining gap: `webnovel-write` (chapter drafting) and `webnovel-review` (multi-dim review) have **zero awareness** of `reference_research/`. The deconstruction output — `do_not_copy.md`, `canon_contamination_warnings.md`, `borrowable_structures`, `satisfaction_point`, `emotion_curve`, `foreshadowing`, `gains_costs`, `character_changes` — is never read by the writing pipeline.

This spec closes that gap by:
1. **write**: injecting a small (≤ 200 token) summary into Step 1's taskbook + a longer "对标红黑名单" section into Step 2A's drafting prompt.
2. **review**: scanning the chapter against `do_not_copy.md`; each violation becomes a critical issue with evidence.

## Goal

After this lands:
- A user who has run `/webnovel-init` (or standalone `/webnovel-deconstruct`) sees the deconstruction output actively shape what they write.
- A chapter that lifts a forbidden character name, plot device, or canon element is flagged by review with line-level evidence.
- The plugin becomes self-reinforcing: deconstruct → consume → flag violations → author adjusts.

## Non-Goals

- No fix for the 39 pre-existing prompt_integrity failures (separate cycle).
- No P4 (full-text deconstruction beyond golden-three chapters).
- No review of `canon_contamination_warnings` (separate enhancement).
- No review of `borrowable_structures` "must use" enforcement.
- No English / multi-language book title support.
- No multi-user shared `reference_research/`.
- No automatic chart-scan → deconstruct flow (P1+P2 manual handoff stays).
- No new artifact writing contract changes (reviewer's 7 categories stays at 7 + 1 new; write's data-agent stays single writer).

## Design Decisions (confirmed in brainstorming)

| Decision | Choice |
|---|---|
| P3 scope | Narrow — only add `reference_research` consumption. 39 pre-existing failures stay for separate follow-up. |
| Write injection depth | **Two points**: Step 1 taskbook (≤ 200 token summary) + Step 2A drafting prompt (longer 红黑名单 section). |
| Review detection scope | **`do_not_copy.md` only**. Violations = `critical` issues with evidence. `canon_contamination_warnings` not checked in this cycle. |
| Multi-book priority | idea_bank.reference_research_path → primary; others → secondary. |
| Empty state | Graceful fallback — no `reference_research/` tree → no injection, no error. |
| Reviewer category | New 8th category: `do_not_copy_violation`. |

## Design

### D1. New helper: `reference_research_injector.py`

Create `scripts/data_modules/reference_research_injector.py`. Two public functions:

```python
def build_step1_summary(project_root: Path, max_tokens: int = 200) -> str:
    """Build a ≤ max_token summary for Step 1 taskbook injection.

    Format:
      ## 对标参考（来自 reference_research/）
      主对标书：《凡人修仙传》 题材：升级流
      可借鉴：宗门阶梯式升级结构
      规避：韩立人设、神秘小瓶机制

    Returns "" if no valid reference_research trees exist.
    Reuses reference_research_scanner.scan_reference_research_trees().
    """

def build_step2a_prompt_section(project_root: Path) -> str:
    """Build a longer '对标书红黑名单' section for Step 2A prompt injection.

    Format:
      ## 对标书红黑名单（必读）

      ### 不可照搬（do_not_copy）
      - 韩立人设（来自《凡人修仙传》）
      - 神秘小瓶机制

      ### 必须规避的角色名/地名（canon_contamination_warnings）
      - 原作人物名: 韩立
      - 原作地名: 落云宗

      ### 可借鉴的结构（borrowable_structures，3-5条）
      - 宗门阶梯式升级结构

      ### 反转 hooks（satisfaction_point，1-2条）
      - 灵根检测反转

    Returns "" if no valid trees exist. Reuses reference_research_scanner.
    """

def build_do_not_copy_check_data(project_root: Path, chapter_text: str) -> list[dict]:
    """Scan chapter text against do_not_copy items, return violation list.

    Each violation is a dict:
      {
        "item": "韩立人设",
        "source_book": "凡人修仙传",
        "chapter_line": 12,
        "matched_text": "韩立...",
        "severity": "critical",
        "category": "do_not_copy_violation"
      }

    Empty list if no violations or no reference_research trees exist.
    """
```

Use `reference_research_scanner.scan_reference_research_trees()` to enumerate trees. The function reads `_schema.json` (for reference_title), `do_not_copy.md` (line by line), and `canon_contamination_warnings.md`. The primary tree is the one whose `<book-safe>/` name matches `idea_bank.json.reference_research_path`'s `<book-safe>` component (verified via `validate_idea_bank_pointer`).

### D2. `webnovel-write` SKILL.md changes

#### D2.1 Step 0 — reference_research 检测

Find the existing "个人语料检测" (L157–161) and "写作宪法加载" (L162–166) blocks. Add a sibling section immediately after them:

```markdown
**对标参考检测（reference_research）**：
- 调用 `python3 ${SCRIPTS_DIR}/data_modules/reference_research_injector.py build-step1-summary --project-root ${PROJECT_ROOT}`，得到 ≤ 200 token 摘要字符串
- 无 `reference_research/` 树 → 跳过（不报错）
- 摘要非空 → 注入到 Step 1 任务书的 "对标参考（来自 reference_research/）" 段
```

#### D2.2 Step 1 — context-agent 扩展

Find the section describing the context-agent invocation. Add to the guidance for what context-agent should include in its taskbook §4:

```markdown
context-agent 的 load-context base pack 增加字段 `reference_research_summary`（来自 build_step1_summary）。
任务书 §4 "怎么写更顺" 段，以"对标参考（来自 reference_research/）"为子标题插入。
不要把字段名 / 路径 / 系统术语暴露到任务书里——必须改写为自然语言。
```

#### D2.3 Step 2A — 起草前注入红黑名单

Find the `cat core-constraints.md` line in Step 2A. Insert **before** it:

```markdown
调用 `python3 ${SCRIPTS_DIR}/data_modules/reference_research_injector.py build-step2a-section --project-root ${PROJECT_ROOT}`，
把"对标书红黑名单"段（可能为空）**追加到章节起草提示词的"约束"段，作为 L1 注入**。
主流程**不口头重写或简化**该段；原样作为约束素材传下去。
若返回空串（无 reference_research 树）→ 跳过此注入。
```

### D3. `webnovel-review` SKILL.md changes

#### D3.1 Step 3 — 新增 do_not_copy 检查

Find the "并行 Task 调用" paragraph in Step 3. Add immediately after:

```markdown
**do_not_copy 检查（reviewer.md Step 1 之后执行）**：

1. 调用 `python3 ${SCRIPTS_DIR}/data_modules/reference_research_injector.py build-do-not-copy-check-data --project-root ${PROJECT_ROOT} --chapter-text "$(cat .webnovel/tmp/chapter_text.txt)"`
2. 检查返回的 violations 列表
3. 对每个 violation → 写入 `.webnovel/tmp/do_not_copy_check.json`，并把每个 item 加入 reviewer 任务的 evidence
4. 无 violations → 写空文件 `{"violations": []}`
```

#### D3.2 New artifact: `.webnovel/tmp/do_not_copy_check.json`

Schema:
```json
{
  "violations": [
    {
      "item": "韩立人设",
      "source_book": "凡人修仙传",
      "chapter_line": 12,
      "matched_text": "韩立微微一笑...",
      "severity": "critical",
      "category": "do_not_copy_violation"
    }
  ]
}
```

Reviewer reads this artifact and incorporates violations into its `issues` array.

### D4. `agents/reviewer.md` changes

#### D4.1 New category

Find the section enumerating issue categories. Add `do_not_copy_violation` to the list. Update the wording in §5 / §6 / §7 accordingly.

#### D4.2 Reading do_not_copy_check.json

Add a step in the reviewer's process: read `.webnovel/tmp/do_not_copy_check.json` and convert each violation into an `issue` entry:

```json
{
  "severity": "critical",
  "category": "do_not_copy_violation",
  "location": "ch{NNN}:line{MM}",
  "description": "出现 do_not_copy.md 中禁止的元素：<item>（来自《<source_book>》）",
  "evidence": "<matched_text>（do_not_copy.md 第 X 行）",
  "fix_hint": "删除或改写该元素。可借鉴 borrowable_structures 中的对应结构。",
  "blocking": true
}
```

### D5. `agents/context-agent.md` changes

Find the section listing the `load-context` base pack fields. Add:

```markdown
| `reference_research_summary` | string | ≤ 200 token | `reference_research_injector.build_step1_summary()` |
```

Add to the §4 taskbook template:

```markdown
## 怎么写更顺（cont'd）
### 对标参考（来自 reference_research/）
<reference_research_summary 内容，自然语言改写，不暴露字段名>
```

### D6. Files modified / created

| File | Action | Purpose |
|---|---|---|
| `scripts/data_modules/reference_research_injector.py` | **Create** | Two `build_*` functions + `build_do_not_copy_check_data()` |
| `scripts/data_modules/tests/test_reference_research_injector.py` | **Create** | Unit tests (10+) |
| `skills/webnovel-write/SKILL.md` | Modify | Step 0 + Step 1 + Step 2A wiring |
| `skills/webnovel-review/SKILL.md` | Modify | Step 3 do_not_copy check |
| `agents/context-agent.md` | Modify | load-context pack + taskbook §4 |
| `agents/reviewer.md` | Modify | New category + read do_not_copy_check.json |
| `scripts/data_modules/tests/test_prompt_integrity.py` | Modify | 3 new tests asserting wiring |
| `scripts/data_modules/reference_research_scanner.py` | Modify (light) | Expose `validate_idea_bank_pointer` for injector use (already exists) |

No new skill, command, or agent.

### D7. Out-of-scope confirmations

- **39 pre-existing prompt_integrity failures** (separate follow-up cycle). They will continue to fail; P3 does not introduce new ones.
- **P4 (full-text deconstruction)** separate.
- **Review of `canon_contamination_warnings`** could be added later — `build_step2a_prompt_section()` already surfaces these to the writer, but review doesn't currently check them.

## Testing Strategy

### T1. Injector unit tests (10+)

Create `scripts/data_modules/tests/test_reference_research_injector.py`:

1. `test_build_step1_summary_with_no_trees` → returns `""`.
2. `test_build_step1_summary_with_one_tree` → returns formatted summary ≤ 200 tokens.
3. `test_build_step1_summary_with_multiple_trees_primary_first` → primary tree (from `idea_bank.reference_research_path`) is listed first.
4. `test_build_step1_summary_includes_narrative_function` → primary tree's `narrative_function` is included.
5. `test_build_step1_summary_token_limit` → output ≤ 200 tokens (use `len(summary)` / 4 heuristic OR tiktoken).
6. `test_build_step2a_section_with_no_trees` → returns `""`.
7. `test_build_step2a_section_includes_do_not_copy` → items from `do_not_copy.md` appear.
8. `test_build_step2a_section_includes_canon_contamination_warnings` → items appear.
9. `test_build_step2a_section_borrowable_structures_limited_to_5` → ≤ 5 borrowable structures shown.
10. `test_build_do_not_copy_check_data_finds_violation` → chapter text containing forbidden item → violation dict returned.
11. `test_build_do_not_copy_check_data_no_violation` → clean chapter → empty list.
12. `test_build_do_not_copy_check_data_with_multiple_trees` → scans all trees' do_not_copy files.

### T2. Prompt integrity tests (3)

Add to `scripts/data_modules/tests/test_prompt_integrity.py`:

```python
def test_write_skill_references_reference_research_injector():
    """webnovel-write SKILL.md must call reference_research_injector at Step 0 + Step 2A."""
    text = _read_text(SKILLS_DIR / "webnovel-write" / "SKILL.md")
    assert "reference_research_injector" in text, "write SKILL must inject reference_research"
    assert "build-step1-summary" in text or "build_step1_summary" in text
    assert "build-step2a-section" in text or "build_step2a_prompt_section" in text


def test_review_skill_references_do_not_copy_check():
    """webnovel-review SKILL.md must perform do_not_copy check in Step 3."""
    text = _read_text(SKILLS_DIR / "webnovel-review" / "SKILL.md")
    assert "do_not_copy" in text, "review SKILL must check do_not_copy"
    assert "do_not_copy_check.json" in text, "review must read new artifact"


def test_reviewer_agent_supports_do_not_copy_violation_category():
    """agents/reviewer.md must declare do_not_copy_violation as a valid issue category."""
    text = _read_text(AGENTS_DIR / "reviewer.md")
    assert "do_not_copy_violation" in text
```

### T3. Manual smoke

1. Build a reference_research tree (use existing P0-Full helper) at `/tmp/p3_smoke/.webnovel/reference_research/fanren-xiuxian-chuan/`
2. Write a chapter that contains the forbidden name "韩立" in a sentence
3. Run `/webnovel-write` for that chapter — verify the Step 2A prompt contains the 红黑名单 section
4. Run `/webnovel-review` — verify `do_not_copy_check.json` has 1+ violations, and reviewer's `issues` array contains `do_not_copy_violation` entries
5. Verify Step 1 taskbook contains the summary (check via context-agent output)

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Token budget exceeded by Step 1 summary | Explicit `max_tokens=200` parameter + test asserts |
| Reviewer might report too many false positives (substring matches in non-problematic contexts) | `build_do_not_copy_check_data()` accepts a `--min-length` filter (default 2 chars); future enhancement can add word-boundary matching |
| Injector fails on malformed do_not_copy.md | Wrap with try/except, log to stderr, return empty string (graceful fallback) |
| context-agent's `reference_research_summary` field leaked into taskbook verbatim (violating §6 of agent prompt) | Test that the field is properly transformed to natural language by mocking context-agent and inspecting output |
| Step 2A's 红黑名单 section breaks chapter drafting (too restrictive) | Length cap on section (~ 1500 chars); user can manually skip with explicit `WEB_NOVEL_NO_REF_RESEARCH=1` env var |
| Reviewer's new category may break existing review_pipeline consumers | `do_not_copy_violation` is additive; no existing consumer filters on the 7-category enum |

## Acceptance Criteria

- [ ] `scripts/data_modules/reference_research_injector.py` exists with all 3 public functions
- [ ] `build_step1_summary()` returns ≤ 200 token summary OR empty string
- [ ] `build_step2a_prompt_section()` includes do_not_copy + canon_contamination_warnings + 3-5 borrowable_structures + 1-2 satisfaction_points
- [ ] `build_do_not_copy_check_data()` correctly identifies violations with line numbers + matched text
- [ ] All 12+ injector unit tests pass
- [ ] `webnovel-write/SKILL.md` calls injector at Step 0 + Step 2A (test T2.1)
- [ ] `webnovel-review/SKILL.md` does do_not_copy check (test T2.2)
- [ ] `agents/reviewer.md` declares `do_not_copy_violation` category (test T2.3)
- [ ] `agents/context-agent.md` lists `reference_research_summary` in load-context pack
- [ ] All P0-Full + P1+P2 + 14-fix tests still pass (no regression)
- [ ] Manual smoke T3 succeeds: violation detected, evidence in reviewer's `issues` array
- [ ] No new prompt_integrity failures introduced (39 pre-existing stay)
- [ ] Adversarial review pass: no new Critical bugs introduced

## Out of Spec (deferred to separate cycles)

- **Cleanup cycle**: Fix 39 pre-existing prompt_integrity failures (webnovel-init/-write/-review author-friendly contracts, agent_tool_name refactor, write-gate/prewrite/precommit/postcommit stages, chapter-commit replacement of state process-chapter, etc.)
- **P4**: Full-text deconstruction beyond golden-three chapters
- **Review of `canon_contamination_warnings`** — could be added in v2 if needed
- **Review of `borrowable_structures` enforcement** — separate
- **English / multi-language** — separate spec
- **Multi-user shared `reference_research/`** — separate spec
- **Auto chart-scan → deconstruct flow** — separate (P1+P2 manual handoff stays)

## "Formally Done" Definition

After P0-Full + P1+P2 + 14 adversarial fixes + P3 lands, the plugin is **feature-complete for the v1 spec**. Remaining follow-up cycles (cleanup, P4) are quality-of-life improvements, not blockers.

"Formally done" criteria for the writer/review pipeline:
1. ✅ Reference research is produced (P0-Full + P1+P2)
2. ✅ Reference research is consumed by write (P3)
3. ✅ Reference research violations are caught by review (P3)
4. ⏳ Cleanup cycle for prompt_integrity contracts (separate)
5. ⏳ P4 full-text deconstruction (separate, optional)