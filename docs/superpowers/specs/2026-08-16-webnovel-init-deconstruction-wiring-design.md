# Init ↔ Deconstruction-Agent Wiring (P0)

**Date:** 2026-08-16
**Status:** Proposed (awaits user review)
**Scope:** P0 of the deconstruction-feature decision matrix (see background below)

## Background (one paragraph)

The plugin ships a fully-implemented `deconstruction-agent` (Read/Grep/Bash-only subagent) that returns a structured `init_reference_research` JSON describing reusable patterns from a reference novel. The agent and its tests are green, but two integration gaps make it dead code in practice:

1. `skills/webnovel-init/SKILL.md` does not call the agent (no Step 1.5). The test `test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate` currently fails.
2. `scripts/init_project.py` never writes `.webnovel/idea_bank.json`, even though `webnovel-init/SKILL.md §"写入 idea_bank.json"` says it should, and `webnovel-plan/SKILL.md:98` reads it.

This spec fixes only those two gaps. Standalone `/webnovel-deconstruct` and `chart-scan → deconstruct` linkage (P1/P2) are explicitly out of scope.

## Goal

When a user runs `/webnovel-init` and voluntarily provides a reference novel, the agent's structured analysis flows into a single confirmed, transformed entry in `.webnovel/idea_bank.json` that `webnovel-plan` already knows how to read.

When the user does **not** provide a reference novel, the init flow is unchanged and `idea_bank.json` is **not** created (matches current behavior).

## Non-Goals

- No standalone `/webnovel-deconstruct` command.
- No `/webnovel-chart-scan --auto-deconstruct` linkage.
- No `webnovel-write` / `webnovel-review` consumption of `idea_bank.json` (out of scope; current consumers are only `init` and `plan`).
- No retroactive patching of pre-existing projects (only the `init` flow writes it).
- No changes to `deconstruction-agent.md` itself.

## Design

### D1. Add Step 1.5 to `webnovel-init/SKILL.md`

Insert a new section **between Step 1 and Step 2** titled `### Step 1.5：灵感来源询问`. It must:

1. Open with: "进入故事核采集前，先问用户灵感来源——**不要默认拆书**。"
2. Ask the user exactly one prompt containing the substring "你这本书的灵感来源想从哪里开始" (test-asserted literal). Acceptable answer categories:
   - **A) 原创 / 无参考** → record `reference_source = "none"`, skip the agent, do not create `idea_bank.json`.
   - **B) 有参考书名 + 平台线索**（如 "起点《XX》"）→ enter `quick` mode; warn user that without text, `quality.passed=false` and patterns may be sparse.
   - **C) 有参考书名 + 本地正文路径**（`reference_text_path`）→ enter `deep` mode if file readable, else degrade to `quick` with excerpt.
   - **D) 有参考书名 + 仅摘录**（`reference_text_excerpt` 粘进对话）→ enter `quick` mode.
3. After (B)(C)(D) answer, invoke the agent with the literal phrase (test-asserted):
   ```
   Use the Agent tool to run `webnovel-writer:deconstruction-agent`
   ```
   with fields per `deconstruction-agent.md §2`. **No `subagent_type:` field** (test forbids it).
4. Inspect returned `init_reference_research.quality` — checking the literal fields `` `quality` `` and `` `quality.passed=false` `` from the JSON (test-asserted):
   - If `quality.passed=false` or `confidence < 0.85` (test-asserted literal `` `confidence < 0.85` ``): show the user the gaps, ask whether to (i) re-run with more text, (ii) proceed with sparse patterns, or (iii) abandon reference. Default = (iii).
   - Otherwise, show the user **only the transformed, book-agnostic patterns** (read from `init_candidates`, `borrowable_structures`, `differentiation_requirements`) — never raw fields like `reader_promise` that may carry canon contamination risk (the agent's `canon_contamination_warnings` must be surfaced verbatim).
5. The text "用户确认前" must appear in the section (test-asserted), and the literal phrase "Step 2-6 只能使用用户确认过、并已变形为本书差异化表达的模式" (test-asserted) must appear before Step 2. The phrase "init_reference_research JSON 对象" (test-asserted) must also appear, referring to the object received from the agent.
6. The phrase "汇总 Step 1.5 已确认的灵感来源" (test-asserted literal) must appear in Step 6 ("一致性复述与最终确认"), summarizing reference attribution for the final confirmation.

Forbidden in the new section (test-asserted):
- Any of the 6 forbidden path substrings: `idea_bank.json`, `.story-system`, `设定集`, `大纲`, `正文`, `.webnovel/state.json`. (Reason: agent itself must not write them; main flow must not preempt the agent's job.)
- The phrase "不写任何文件" must appear (test-asserted) — clarifying the agent itself does not persist.
- The phrase "不得由 init 主流程口头替代拆解结果" (test-asserted) — clarifying main flow cannot summarize away the structured JSON.
- The substring `.webnovel/tmp/reference_analyses/<safe-title>/` and `project_root=${PROJECT_ROOT` must NOT appear (test-asserted anti-patterns — these were earlier, rejected draft phrasings).

### D2. Persist `idea_bank.json` from `init_project.py`

Update `scripts/init_project.py` so that after writing `设定集/*` and `大纲/总纲.md`, it also writes `.webnovel/idea_bank.json` **only when** the init caller (main flow) explicitly passes a `idea-bank` payload.

Payload schema (camelCase-free, matches `deconstruction-agent.md` field names where applicable):

```json
{
  "version": 1,
  "created_at": "<ISO8601>",
  "source": {
    "reference_title": "",
    "reference_source": "none|book_name|local_text|excerpt",
    "analysis_mode": "quick|deep",
    "confidence": 0.0
  },
  "selected_idea": {
    "title": "",
    "one_liner": "",
    "anti_trope": "",
    "hard_constraints": []
  },
  "constraints_inherited": {
    "anti_trope": "",
    "hard_constraints": [],
    "protagonist_flaw": "",
    "antagonist_mirror": "",
    "opening_hook": ""
  },
  "borrowed_patterns": [],   // from borrowable_structures, user-confirmed subset
  "do_not_copy": [],         // from do_not_copy, verbatim
  "canon_contamination_warnings": []  // from agent, verbatim
}
```

`init_project.py` rules:
- New CLI flag (init subcommand only): `--idea-bank-file <path>` (init main flow writes the JSON to a tempfile after user confirms in Step 1.5, then passes the path; this avoids serializing through argv).
- If the flag is absent → no `idea_bank.json` written (current behavior preserved).
- If the flag is present and file is missing/unreadable → hard error before generating other files (avoid half-init state).
- Three-state overwrite behavior on `idea_bank.json` at the target project:
  - **Absent** → create from payload (first-run case).
  - **Present, content matches payload semantically** (title/one_liner/anti_trope/hard_constraints/opening_hook all equal) → skip with notice; idempotent re-run.
  - **Present, content differs** → refuse to silently overwrite. Init main flow surfaces a "patch" prompt asking the user to either (i) abort, (ii) accept an auto-merge preserving user's local edits to `do_not_copy` and `canon_contamination_warnings`, or (iii) explicit overwrite via `--idea-bank-force` flag (fail-closed by default). This aligns with the existing invariant "约束启用但 idea_bank.json 缺失或内容不一致 → 只重写该文件" — the script only rewrites the specific file, never silently.
- Schema validation: the payload must parse as JSON, contain `version: 1`, and have all top-level keys (`source`, `selected_idea`, `constraints_inherited`, `borrowed_patterns`, `do_not_copy`, `canon_contamination_warnings`). Otherwise refuse with field-level error.

### D3. Init main flow contract

The init main flow (Claude, in chat) is responsible for:

1. Running Step 1.5 conversation.
2. Calling the agent (per D1.3).
3. Showing the user the transformed, book-agnostic summary + `canon_contamination_warnings`.
4. Collecting user confirmation before any write.
5. On confirmation: build `idea_bank.json` JSON per D2 schema, write to tempfile, then pass `--idea-bank-file` to `webnovel.py init`.
6. In Step 6 (final confirmation), include the line "汇总 Step 1.5 已确认的灵感来源" with: reference title, mode, confidence, hard_constraints count, anti_trope.

The init main flow does **not** paraphrase away the structured fields — that violates "不得由 init 主流程口头替代拆解结果". If the user wants prose, the user asks; otherwise the JSON travels through.

### D4. Files modified

| File | Change |
|---|---|
| `skills/webnovel-init/SKILL.md` | Insert `### Step 1.5：灵感来源询问` between Step 1 and Step 2. Add 3 mandatory literal strings to Step 6. Add `用户确认前` / `Step 2-6 只能使用...` strings to Step 2 preamble. |
| `scripts/init_project.py` | Add `--idea-bank-file` flag + write block. Add idempotency check (refuse overwrite). |
| `scripts/init_project.py` | New unit test: missing flag ⇒ no `idea_bank.json`; valid flag ⇒ file matches schema; existing file ⇒ refuse. |

No new files. No new skill. No new command.

### D5. Out-of-scope confirmations (intentional)

- `webnovel-plan/SKILL.md:98` already reads `idea_bank.json`; nothing changes there. Once D2 lands, plan starts actually receiving data — verified by manual smoke (run init with a reference, then plan, confirm plan's constraint usage is non-empty).
- `webnovel-write` / `webnovel-review` are not modified. `idea_bank.json` consumption by write is a future task.
- `deconstruction-agent.md` is not modified — its current prompt already returns the schema init needs.

## Testing Strategy

### T1. Test red→green

`scripts/data_modules/tests/test_prompt_integrity.py::test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate` is currently failing. After D1 lands, it must pass. CI gate: `pytest -k test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate`.

### T2. New tests in `init_project.py`

- `test_init_project_no_idea_bank_when_flag_absent` — runs init, asserts no `.webnovel/idea_bank.json`.
- `test_init_project_writes_idea_bank_from_file` — runs init with `--idea-bank-file <valid JSON>`, asserts file exists and matches schema (version, source.reference_title, constraints_inherited.opening_hook).
- `test_init_project_refuses_overwrite_existing_idea_bank` — pre-creates `idea_bank.json` with sentinel, runs init with flag, asserts sentinel unchanged + nonzero exit.
- `test_init_project_errors_on_unreadable_idea_bank_file` — passes a nonexistent path, asserts hard error.

### T3. Manual smoke (one-time)

1. `/webnovel-init` with a reference novel (e.g. "《XX》, 我把第一章贴在下面: <text>").
2. Step 1.5 fires → agent returns JSON → user confirms transformed patterns.
3. `idea_bank.json` exists at project root, contains expected fields.
4. `/webnovel-plan` reads it (verify by adding a one-shot print in plan, or by running plan and confirming the constraint references are non-empty in chapter outline).
5. Without reference: Step 1.5 still asks once, user picks (A), `idea_bank.json` is **not** created, everything else unchanged.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| User confirmation gate is verbal — agent JSON could be paraphrased away | Test asserts literal phrase "不得由 init 主流程口头替代拆解结果" in SKILL.md; main flow review step in T3 |
| `idea_bank.json` overwrite could destroy user edits | Refuse-overwrite in init_project.py (T2) |
| Reference novel's `canon_contamination_warnings` ignored | Surfaced verbatim to user in Step 1.5 (D1.4); written verbatim to `idea_bank.json` field (D2 schema) |
| Agent may return low-quality output for poorly-known titles | Quality gate: `confidence < 0.85` literal in SKILL.md triggers re-run/abandon (D1.4); user never auto-proceeds past bad output |
| Test assertions lock in awkward phrasing | All literals are reviewed in this spec; future rewording requires updating the test (intentional — changes the contract) |

## Acceptance Criteria

- [ ] `test_prompt_integrity.py::test_webnovel_init_deconstruction_wiring_keeps_confirmation_gate` passes
- [ ] `webnovel-init/SKILL.md` contains all 9 handoff field names + 6 forbidden path substrings + the mandatory literal phrases: `Use the Agent tool to run \`webnovel-writer:deconstruction-agent\`` / `Step 1.5：灵感来源询问` / `进入故事核采集前` / `不要默认拆书` / `你这本书的灵感来源想从哪里开始` / `init_reference_research` / `init_reference_research JSON 对象` / `不写任何文件` / `不得由 init 主流程口头替代拆解结果` / `` `quality` `` / `` `quality.passed=false` `` / `` `confidence < 0.85` `` / `用户确认前` / `Step 2-6 只能使用用户确认过、并已变形为本书差异化表达的模式` / `汇总 Step 1.5 已确认的灵感来源`
- [ ] `init_project.py` has `--idea-bank-file` flag with three-state overwrite behavior; schema validation rejects malformed payloads
- [ ] 4 new unit tests pass (T2 list)
- [ ] Manual smoke (T3) succeeds end-to-end with and without a reference novel
- [ ] No new skill, command, or agent created

## Out of Spec (deferred)

- **P1:** `/webnovel-chart-scan --auto-deconstruct <book>` — chain scan output to agent input. Separate spec when chart-scan v0.3 lands.
- **P2:** Standalone `/webnovel-deconstruct` — **not recommended**. If a future need arises (e.g. "纯学习不创作"), it requires redesigning the agent's output (not `init_candidates`) and a separate product decision.