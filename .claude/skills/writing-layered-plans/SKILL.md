---
name: writing-layered-plans
description: Use when creating detailed implementation plans with bite-sized tasks (2-5min), mandatory TDD verification, and integration with three-layer document system (Master/Phase/Step with YAML Frontmatter). Triggers: clear requirements, multi-file changes, need structured verification, or auto-called by interactive-planning.
---

# Writing Layered Plans

**Announce:** "Using writing-layered-plans for detailed TDD implementation plan."

**Context:** Plan Mode, clear requirements → detailed execution plan

---

## Communication Guidelines

**Be concise**: Use tables/lists. Details only when asked.

**Plain language**: Explain like to a junior developer. No jargon.

---

## When to Use

**Triggers:**
- Requirements already clear
- Need detailed plan (2-5min tasks, mandatory TDD)
- Multi-file/multi-module changes
- Auto-called by `interactive-planning` after architecture

**NOT for:**
- Unclear requirements (use `interactive-planning` first)
- Simple single-file tasks

---

## Core Pattern

### 1. Explore Phase (Understand Code)

**Up to 3 Explore agents in parallel:**

| Agent | Focus | Output |
|-------|-------|--------|
| 1 | Existing implementations | File paths, patterns |
| 2 | Related components | Dependencies, interfaces |
| 3 | Test patterns | Test structure |

**Combine** → Complete context

### 2. Design Phase (Plan Approach)

**Plan agent:**
1. Gap analysis (requirements vs code)
2. Implementation approach
3. Key technical points
4. Detailed plan

### 3. Task Breakdown & TDD

**Architecture:**
- ≤5 tasks, ≤2hrs → Single
- 6-20 tasks, 2-8hrs → Two (master + phase)
- >20 tasks OR >8hrs → Three (master + phase + step)

**Granularity:**
- **Phase**: 1-2hr (multiple steps)
- **Step**: 2-5min (one action)

### 4. Mandatory TDD

**Every Step MUST follow:**

```markdown
### Step N: [Name]
**Files:** Create/Modify/Test paths

**1. RED (failing test)**
[Code]

**2. Run → verify FAIL**
Run: `command`
Expected: FAIL

**3. GREEN (implement)**
[Code]

**4. Run → verify PASS**
Run: `command`
Expected: PASS

**5. REFACTOR** (if needed)
**6. COMMIT** `git add/commit`
```

### 5. Frontmatter & Script

**Use:** `pwsh -File .claude/scripts/new-plan.ps1 -Type [type] -Title "[title]" -Parent "[parent]"`

**Manual fallback:**
```yaml
---
title: "[Title]"
type: "[master-plan|phase-plan|step-plan]"
status: "🟢 待开始"
created: "[YYYY-MM-DD]"
parent: "[path]"
children: []
tags: ["keyword1"]
---
```

### 5.5. Plan Document Header (REQUIRED)

**Every plan MUST include this header after Frontmatter:**

> **重要说明**：Plan Header 与 Frontmatter 互补
> - **Frontmatter (YAML)**：机器解析，用于跨会话上下文重建
> - **Plan Header (文本)**：人类可读，快速理解计划核心

```markdown
# [Feature Name] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---
```

**Purpose**:
- **Goal**: One-sentence objective for quick reference
- **Architecture**: High-level technical approach
- **Tech Stack**: Key dependencies and tools

---

## Quick Reference

| Decision | Criteria |
|----------|----------|
| Use this skill | Clear requirements, detailed plan needed, or auto-called by interactive-planning |
| Plan architecture | ≤5 tasks/≤2hrs (single), 6-20/2-8hrs (two-layer), >20/>8hrs (three-layer) |
| Task granularity | Phase: 1-2hr; Step: 2-5min |
| TDD | Mandatory RED→GREEN→REFACTOR for every step |
| Frontmatter | new-plan.ps1 script or manual YAML |
| Execution | Subagent-Driven (this session) |

---

## Common Mistakes

| Error | Fix |
|-------|-----|
| Skip Explore | Always launch agents first |
| Phase too large | Split into Steps |
| Incomplete TDD | Must have RED→GREEN→REFACTOR |
| No full code | Provide complete code |
| No Frontmatter | Always generate YAML |
| Technical jargon | Use plain language (explain to junior dev) |
| Long explanations | Use tables/lists, one-line summaries |

---

## Integration

**Parent:** `superpowers:interactive-planning` (auto-calls)
**System:** atomic-foraging-cat (three-layer + Frontmatter)
**Executors:**
- `superpowers:subagent-driven-development` (this session)
- `superpowers:executing-plans` (parallel session)
**Script:** `.claude/scripts/new-plan.ps1`
**Memory:** `.claude/MEMORY.md`

**Replaces:** `superpowers:writing-plans` (功能更全面：三层文档系统、Frontmatter 跨会话支持、双执行选项)

---

## Execution Handoff

**Plan saved. Two execution options:**

1. **Subagent-Driven (this session)**
   - Fresh subagent per task, review between tasks, fast iteration
   - **Best for**: Small tasks (<10 steps), need frequent review, quick iteration

2. **Parallel Session (separate)**
   - Open new session with executing-plans, batch execution with checkpoints
   - **Best for**: Large projects (>20 steps), batch processing, interruptible work

**Which approach?**

If Subagent-Driven chosen:
- **REQUIRED:** superpowers:subagent-driven-development
- Stay in this session
- Ready to start?

If Parallel Session chosen:
- Guide user to open new session in worktree
- **REQUIRED:** New session uses superpowers:executing-plans
- Plan file will be loaded automatically
