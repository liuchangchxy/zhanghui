# P0-Full + P1+P2 Adversarial Review Fixes (Bug-Fix Batch)

**Date:** 2026-08-16
**Status:** Proposed
**Source:** Adversarial review (opus) after P0-Full + P1+P2 declared done. Caught 3 Critical + 5 Important + 6 Minor bugs that 4 prior confirmatory reviews missed.

## Why this spec exists

A prior incident in this project: 4 confirmatory "GO" reviews approved work containing 14 Critical/Important bugs. A single adversarial review caught them all. This spec records those bugs and the fixes.

## Findings & Fix Strategy

### Critical (3 — blocking)

#### C1. `init_candidates` schema mismatch — primary output silently dropped
- **File:** `agents/deconstruction-agent.md:104` + `scripts/init_reference_tree.py:178` + `scripts/data_modules/templates/reference_report.md.j2:89-97`
- **Bug:** Agent returns `init_candidates` as a LIST, but template + builder expect an OBJECT. Jinja2 returns empty string for `Undefined`, so report.md's "Init 候选" section is empty.
- **Root cause:** Agent schema (§7 of deconstruction-agent.md) declares `"init_candidates": [ { ... } ]` but template uses `{{ init_candidates.one_liner }}` (object access).
- **Fix:**
  - **Agent (preferred):** Change schema to declare `init_candidates` as a SINGLE OBJECT, not a list. Update §7 description.
  - **Template:** Keep `{{ init_candidates.one_liner }}` etc. as-is (already correct for object).
  - **Builder:** No code change — pass-through is correct.
  - **Test fix:** `test_init_reference_tree.py:_minimal_schema()` already uses object shape — keep. Add new test asserting schema field name present in agent.md.
- **Test:** `test_init_candidates_is_object_in_agent_schema` (new) + `test_build_reference_tree_with_empty_init_candidates` (new) + existing report sections test still passes.

#### C2. Backup destroyed by `rmtree` — silent data loss
- **File:** `scripts/init_project.py:774-783`
- **Bug:** `--reference-overwrite` flag's promise of "preserve old `_schema.json`" is broken because the backup is created INSIDE `target_tree`, then `shutil.rmtree(target_tree)` wipes the entire directory including the backup.
- **Fix:** Move backup OUTSIDE `target_tree` to `project_path / ".webnovel" / "backups" / f"{book_safe}__schema__{ts}.bak"`. OR: skip `rmtree` entirely; only overwrite changed files in place.
- **Decision:** Skip `rmtree` — overwrite in place. The init_reference_tree already does this correctly (line 235-246). Use the same pattern for init_project.py.
- **Test:** `test_init_overwrite_preserves_old_schema_outside_target` (new) — run with `--reference-overwrite`, assert old schema exists in `.webnovel/backups/` OR at least one of: previous `_schema.json.bak-<ts>` exists somewhere NOT inside target_tree.

#### C3. Symlink overwrite leak
- **File:** `scripts/init_reference_tree.py:235-246` + `scripts/init_project.py:774-783`
- **Bug:** Symlink at target path can redirect writes to attacker-controlled location.
- **Fix:** Add `if tree.is_symlink(): raise SystemExit(f"refusing to write through symlink: {tree}")` in both functions, BEFORE any file operations.
- **Test:** `test_build_reference_tree_refuses_symlink_target` + `test_init_refuses_symlink_reference_research_dir`.

### Important (5)

#### I1. `marked_references` accepts non-string title/platform
- **File:** `scripts/data_modules/marked_references.py:41-49`
- **Bug:** Only checks key presence, not type. `{"platform": 123, "title": ""}` passes.
- **Fix:** Add `isinstance(ref["platform"], str) and ref["platform"].strip()` and same for `title`.
- **Test:** `test_marked_references_rejects_empty_title`, `test_marked_references_rejects_non_string_platform`, `test_marked_references_rejects_whitespace_only_title`.

#### I2. `version: True` passes `_validate_idea_bank_payload`
- **File:** `scripts/init_project.py:254-255`
- **Bug:** `True == 1` → True passes validation. Float `1.0` also passes.
- **Fix:** Change to `if data.get("version") is not 1:`.
- **Test:** `test_validate_idea_bank_rejects_version_true` + `test_validate_idea_bank_rejects_version_float`.

#### I3. `reference_research_path` has no type/path validation
- **File:** `scripts/init_project.py:265-266`
- **Bug:** Integer, dict, absolute paths, `..` all pass.
- **Fix:** After validating `source` etc., add:
  ```python
  if "reference_research_path" in data:
      rrp = data["reference_research_path"]
      if not isinstance(rrp, str):
          raise ValueError("idea_bank.reference_research_path must be a string")
      if ".." in Path(rrp).parts:
          raise ValueError("idea_bank.reference_research_path must not contain '..'")
      if Path(rrp).is_absolute():
          raise ValueError("idea_bank.reference_research_path must be relative")
  ```
- **Test:** `test_validate_idea_bank_rejects_non_string_path`, `test_validate_idea_bank_rejects_path_traversal`, `test_validate_idea_bank_rejects_absolute_path`.

#### I4. `sanitize_book_title` doesn't strip CJK punctuation
- **File:** `scripts/init_reference_tree.py:39, 120`
- **Bug:** `_CJK_BRACKETS` only strips 6 fullwidth brackets. `！。？，` etc. leak into filesystem paths.
- **Fix:** Strip CJK punctuation Unicode range (U+3000-U+303F, U+FF00-U+FFEF for fullwidth forms).
- **Test:** `test_sanitize_book_title_strips_cjk_punctuation` + parameterized tests for `！`, `。`, `？`, `，`, `：`, `（`, `）`.

#### I5. Plan SKILL.md describes auto-discovery but no Python enforces it
- **File:** `skills/webnovel-plan/SKILL.md:100-121`
- **Bug:** Plan's auto-discovery is entirely LLM-driven; no Python precheck validates `reference_research_path` is under `.webnovel/`.
- **Fix:** Add a Python helper `scripts/data_modules/reference_research_scanner.py` that:
  - Validates `idea_bank.json.reference_research_path` is a string, relative, under `.webnovel/`, contains `_schema.json`
  - Scans `.webnovel/reference_research/*/` for valid trees (each must have `_schema.json`)
  - Returns a list of validated tree paths
  - Plan SKILL.md then just calls this helper and iterates the result
- **Test:** `test_reference_research_scanner_filters_invalid_paths`, `test_reference_research_scanner_returns_empty_when_no_trees`.

### Minor (6)

#### M1. `scan_<ts>.log` 1-second precision → same-second collision
- **File:** `skills/webnovel-chart-scan/scripts/output.py:8-16, 40`
- **Fix:** Add microsecond precision: `%Y%m%dT%H%M%S_%fZ`.
- **Test:** `test_slug_timestamp_includes_microseconds`.

#### M2. `init_reference_tree` backup 1-second precision
- **File:** `scripts/init_reference_tree.py:243`
- **Fix:** Same as M1 — microsecond precision in `_schema.json.bak-<ts>`.
- **Test:** `test_build_reference_tree_backup_timestamp_unique`.

#### M3. `write_marked_references` (chart-scan/output.py) can write to any directory
- **File:** `skills/webnovel-chart-scan/scripts/output.py:79`
- **Fix:** Validate `output_dir` is within current working directory or its subdirs (no `..`, not absolute).
- **Test:** `test_chart_scan_write_marked_references_rejects_unsafe_path`.

#### M4. Two `write_marked_references` functions with same name in different modules
- **File:** `skills/webnovel-chart-scan/scripts/output.py:56-88` + `scripts/data_modules/marked_references.py:66-78`
- **Fix:** Rename chart-scan's wrapper to `write_chart_scan_marked_references`.
- **Test:** `test_chart_scan_helper_renamed`.

#### M5. `slug_timestamp` defensive check is runtime-only
- **File:** `skills/webnovel-chart-scan/scripts/output.py:8-16`
- **Fix:** Add Pydantic validator in `schema.py` to enforce `tzinfo=timezone.utc`.
- **Test:** `test_chart_scan_schema_enforces_utc_timestamp`.

#### M6. Unused `Any` import in `marked_references.py`
- **File:** `scripts/data_modules/marked_references.py:14`
- **Fix:** Remove `Any` from typing import.
- **Test:** N/A (cleanup).

## File modifications

| File | Bugs fixed |
|---|---|
| `agents/deconstruction-agent.md` | C1 |
| `scripts/init_reference_tree.py` | C1 (pass-through), C3 (symlink), I4 (CJK punct), M2 (timestamp) |
| `scripts/data_modules/templates/reference_report.md.j2` | C1 (template already correct; verify) |
| `scripts/init_project.py` | C2 (rmtree), C3 (symlink), I2 (version), I3 (path validation) |
| `scripts/data_modules/marked_references.py` | I1 (type validation), M4 (rename — actually only chart-scan needs rename), M6 (cleanup) |
| `scripts/data_modules/tests/test_init_reference_tree.py` | C1, C3, I4, M2 new tests |
| `scripts/data_modules/tests/test_init_idea_bank.py` | C3, I2, I3 new tests |
| `scripts/data_modules/tests/test_marked_references.py` | I1 new tests |
| `scripts/data_modules/tests/test_prompt_integrity.py` | C1 new test (agent schema) |
| `skills/webnovel-chart-scan/scripts/output.py` | M1 (timestamp), M3 (path), M4 (rename), M5 (schema) |
| `skills/webnovel-chart-scan/scripts/schema.py` | M5 (Pydantic validator) |
| `skills/webnovel-plan/SKILL.md` | I5 (use new helper) |
| `scripts/data_modules/reference_research_scanner.py` (NEW) | I5 |
| `scripts/data_modules/tests/test_reference_research_scanner.py` (NEW) | I5 |

## Acceptance Criteria

- [ ] All 14 findings have corresponding fix + test
- [ ] C1: `init_candidates` is an OBJECT in agent schema; template renders correct values; new tests pass
- [ ] C2: `--reference-overwrite` preserves old schema in `.webnovel/backups/` (or in place); rmtree not used
- [ ] C3: Symlinks at target path raise SystemExit; new tests pass
- [ ] I1-I5: All have new tests + the fix lands
- [ ] M1-M6: All addressed (renames, defensive checks)
- [ ] All prior 33 tests still pass (no regression)
- [ ] New tests for all 14 fixes pass
- [ ] Re-run adversarial review → no new Critical bugs introduced

## Out of Scope

- Performance optimization (separate spec)
- Multi-user shared `reference_research/` (separate spec)
- English book title support (separate spec)
- Replacing LLM-driven plan auto-discovery with deterministic pipeline (deferred)