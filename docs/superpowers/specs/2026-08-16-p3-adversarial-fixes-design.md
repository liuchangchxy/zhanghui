# P3 Adversarial Fixes — Mini Cycle

**Date:** 2026-08-16
**Status:** Proposed
**Source:** Final adversarial review (opus) after P3 declared done. 5 Critical + 3 Important + 1 Minor found.

## Critical (5)

### C1. `rejection_contract.VALID_CATEGORIES` rejects `do_not_copy_violation` — silent revision flow breaker

- **File:** `scripts/rejection_contract.py:20-22`
- **Bug:** A second whitelist (sister to `review_schema.py`'s VALID_CATEGORIES) doesn't include the new P3 category. `revise_chapter.py:264` `validate_contract()` rejects it → EXIT_INVALID → chapter never auto-revised.
- **Fix:** Add `"do_not_copy_violation"` to `VALID_CATEGORIES`.
- **Test:** `test_rejection_contract_accepts_do_not_copy_violation` — build contract with the category, validate, assert no exception.

### C2. `reference_research_injector.py` has no `__main__` — write-side injection silently produces empty stdout

- **File:** `scripts/data_modules/reference_research_injector.py` (no `if __name__ == "__main__":` block)
- **Bug:** `python3 reference_research_injector.py build-step1-summary --project-root /tmp/proj` exits 0 with empty stdout. SKILL.md "若返回空串 → 跳过" silently no-ops the entire write-side injection.
- **Fix:** Add `__main__` block with argparse. Use subcommand names matching SKILL.md strings:
  - `build-step1-summary` → calls `build_step1_summary(project_root)`
  - `build-step2a-section` → calls `build_step2a_prompt_section(project_root)`
  - `build-do-not-copy-check-data` → calls `build_do_not_copy_check_data(project_root, chapter_text)` (chapter_text from stdin or `--chapter-file`)
- **Test:** `test_cli_build_step1_summary` — subprocess.run with `["python3", "reference_research_injector.py", "build-step1-summary", "--project-root", tmp_path]` asserts stdout non-empty (or "skip\n" if no trees).

### C3. CJK matcher over-matches — false positives on innocent text

- **File:** `scripts/data_modules/reference_research_injector.py:170-197`
- **Bug:** `_CLASSIFIER_SUFFIXES` splits `韩立人设` to `["韩立"]` (2-char). Substring match triggers on innocent text like `韩立群` (common unrelated given name).
- **Fix:** Require minimum token length of 3 CJK chars. Tokens shorter than 3 → skip from matching (still reported in `item` field for reference but don't match).
- **Test:** `test_do_not_copy_check_skips_subtoken_false_positive` — chapter text `韩立群上山` + do_not_copy=`韩立人设` → 0 violations.

### C4. CJK matcher under-matches colon-form items

- **File:** `scripts/data_modules/reference_research_injector.py:170-197`
- **Bug:** Most common storage format `"原作人物名: 韩立"` doesn't contain any `_CLASSIFIER_SUFFIXES`, so tokens = full string. Matcher requires exact full-string match → never hits.
- **Fix:** Split colon-prefix items. Add `:` to split delimiters. For items matching `^([^:]+):\s*(.+)$`, use the value side as the match target. The original item stays in the violation's `item` field.
- **Test:** `test_do_not_copy_check_matches_colon_form_value` — chapter `韩立出场了` + do_not_copy=`原作人物名: 韩立` → 1 violation.

### C5. `build_step1_summary` violates its documented ≤ 200-token budget — actually 800 chars (~1200 tokens)

- **File:** `scripts/data_modules/reference_research_injector.py:102-122`
- **Bug:** `max_tokens` parameter is unused in function body. Hardcoded 800 chars ≈ 1200-1360 tokens for CJK.
- **Fix:** Either (a) implement real token counting via `tiktoken` (if available), or (b) update the SKILL.md / context-agent.md / helper docstrings to say "≤ 800 chars (~1200 CJK tokens)" and remove the `max_tokens` parameter from the signature. Pick option (b) for simplicity unless tiktoken is already a dep.
- **Decision:** Option (b) — update docstrings + SKILL.md to match actual behavior. If users need true token control later, add tiktoken.
- **Test:** `test_step1_summary_docstring_matches_actual_cap` — assert the function's docstring contains "≤ 800 chars".

## Important (3)

### I1. Tests don't cover dangerous failure modes

- **File:** `scripts/data_modules/tests/test_reference_research_injector.py`
- **Bug:** No tests for C3/C4/C5, no CLI invocation test (C2), no rejection_contract integration test (C1).
- **Fix:** Add tests:
  - `test_cli_build_step1_summary` (C2)
  - `test_do_not_copy_check_skips_subtoken_false_positive` (C3)
  - `test_do_not_copy_check_matches_colon_form_value` (C4)
  - `test_rejection_contract_accepts_do_not_copy_violation` (C1)
  - `test_step1_summary_docstring_mentions_char_cap` (C5)

### I2. reviewer.md declares 8 dimensions but document silently passes when check.json missing

- **File:** `agents/reviewer.md:124, 199`
- **Bug:** When `do_not_copy_check.json` is missing or malformed, the dimension is silently `pass` — false confidence.
- **Fix:** In reviewer.md around line 199, replace silent `pass` with `error` dimension conclusion when check.json is missing/invalid. Add explicit error message: "do_not_copy check unavailable; please re-run /webnovel-review after ensuring reference_research/ has trees".
- **Test:** Manual smoke verification (no easy unit test for agent prompt).

### I3. Subcommand name mismatch

- **File:** Same as C2 (the `__main__` block in C2 must use exact names `build-step1-summary`, `build-step2a-section`, `build-do-not-copy-check-data`).
- **Bug:** SKILL.md uses hyphenated names. Function names use underscores.
- **Fix:** Solved by C2's `__main__` block using hyphenated subcommand names matching SKILL.md.

## Minor (1)

### M1. Pinyin slug substring collision

- **File:** `scripts/data_modules/reference_research_injector.py:37-66`
- **Bug:** Substring fallback for `_primary_tree_path` could match wrong tree for similar pinyin names.
- **Fix:** Require `==` or use exact match against `sanitize_book_title(reference_title)`. Drop the substring fallback.
- **Test:** `test_primary_tree_path_requires_exact_match` (covered by C4/I1 test additions).

## File modifications

| File | Bugs |
|---|---|
| `scripts/rejection_contract.py` | C1 |
| `scripts/data_modules/reference_research_injector.py` | C2, C3, C4, C5 |
| `agents/reviewer.md` | I2 |
| `scripts/data_modules/tests/test_reference_research_injector.py` | I1 (new tests) |
| `scripts/data_modules/tests/test_rejection_contract.py` (or similar) | C1 test |

## Acceptance Criteria

- [ ] C1: `rejection_contract` accepts `do_not_copy_violation`
- [ ] C2: CLI invocations work end-to-end (3 subcommands)
- [ ] C3: `韩立群` does NOT trigger violation on `韩立人设`
- [ ] C4: `原作人物名: 韩立` matches `韩立出场了`
- [ ] C5: docstring matches actual behavior (800 chars cap documented)
- [ ] I1: All 5 new tests pass + no regression on prior 12
- [ ] I2: reviewer.md `do_not_copy` dimension shows error when check.json missing
- [ ] I3: subcommand names match SKILL.md invocations
- [ ] All P0-Full + P1+P2 + 14-fix + P3 tests still pass
- [ ] Final adversarial review pass: no new Critical bugs