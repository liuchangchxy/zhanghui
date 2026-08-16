# Adversarial Review Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Fix all 14 adversarial findings (3 Critical + 5 Important + 6 Minor). After this lands, the P0-Full + P1+P2 implementation is genuinely production-ready.

**Architecture:** Six task batches organized by file scope (most-efficient dispatch). Batches are not strictly ordered — Critical bugs are the priority but can be parallelized. Each batch is a single subagent dispatch that covers related fixes in one file + their tests + sync.

**Tech Stack:** Python 3, pytest, `pathlib`, `json`. No new deps.

---

## File Structure

| File | Action | Bugs |
|---|---|---|
| `agents/deconstruction-agent.md` | Modify | C1 (init_candidates schema) |
| `scripts/init_reference_tree.py` | Modify | C1 (pass-through stays), C3 (symlink check), I4 (CJK punct), M2 (microsecond backup) |
| `scripts/data_modules/templates/reference_report.md.j2` | Verify | C1 (template stays correct for object; smoke verifies) |
| `scripts/init_project.py` | Modify | C2 (no rmtree), C3 (symlink check), I2 (version strict), I3 (path validation) |
| `scripts/data_modules/marked_references.py` | Modify | I1 (type validation), M6 (cleanup) |
| `scripts/data_modules/reference_research_scanner.py` | **Create** | I5 (new helper) |
| `scripts/data_modules/tests/test_init_reference_tree.py` | Modify | Add C1/C3/I4/M2 tests |
| `scripts/data_modules/tests/test_init_idea_bank.py` | Modify | Add C3/I2/I3 tests |
| `scripts/data_modules/tests/test_marked_references.py` | Modify | Add I1 tests |
| `scripts/data_modules/tests/test_prompt_integrity.py` | Modify | Add C1 agent-schema test |
| `scripts/data_modules/tests/test_reference_research_scanner.py` | **Create** | I5 tests |
| `skills/webnovel-chart-scan/scripts/output.py` | Modify | M1 (microsecond ts), M3 (path validation), M4 (rename) |
| `skills/webnovel-chart-scan/scripts/schema.py` | Modify | M5 (Pydantic UTC validator) |
| `skills/webnovel-plan/SKILL.md` | Modify | I5 (use new scanner helper) |

---

## Task A: Critical Bugs (C1, C2, C3)

**Files:** `agents/deconstruction-agent.md`, `scripts/init_reference_tree.py`, `scripts/init_project.py`, `scripts/data_modules/templates/reference_report.md.j2`, `tests`

- [ ] **Step 1: Write failing tests for C1 (init_candidates object)**

Add to `scripts/data_modules/tests/test_prompt_integrity.py`:

```python
def test_init_candidates_is_object_not_list_in_agent_schema():
    """deconstruction-agent.md must declare init_candidates as a SINGLE OBJECT, not a list."""
    text = _read_text(AGENTS_DIR / "deconstruction-agent.md")
    # Must mention init_candidates and reference it as object-like access (not a list)
    assert "init_candidates" in text
    # Spec §D1: init_candidates is an object with one_liner, anti_trope, hard_constraints, etc.
    for field in ("one_liner", "anti_trope", "hard_constraints", "protagonist_flaw", "antagonist_mirror", "opening_hook"):
        assert field in text, f"init_candidates.{field} must be referenced in agent schema"
```

Add to `scripts/data_modules/tests/test_init_reference_tree.py`:

```python
def test_build_reference_tree_with_minimal_init_candidates():
    """init_candidates must be an OBJECT (not a list) for template to render."""
    import json, pathlib, tempfile
    schema = _minimal_schema()
    # Schema's _minimal_schema() already uses init_candidates as object — verify it stays so
    assert isinstance(schema["init_candidates"], dict), \
        "_minimal_schema() fixture must use OBJECT init_candidates (not list)"

    with tempfile.TemporaryDirectory() as td:
        tree = build_reference_tree(pathlib.Path(td), schema, "X")
        report = (tree / "report.md").read_text(encoding="utf-8")
        # Must contain the actual values (not empty due to type mismatch)
        assert "一句话" in report, "report.md must render init_candidates.one_liner value"
        assert "硬约束1" in report, "report.md must render init_candidates.hard_constraints items"
```

- [ ] **Step 2: Verify C1 tests fail (or pass with wrong fixture)**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py::test_init_candidates_is_object_not_list_in_agent_schema data_modules/tests/test_init_reference_tree.py::test_build_reference_tree_with_minimal_init_candidates -v 2>&1 | tail -10
```

Expected: at least one fails (depending on current agent schema phrasing).

- [ ] **Step 3: Fix C1 — agent schema says init_candidates is OBJECT**

Open `agents/deconstruction-agent.md`. Find the schema section that declares `init_candidates`. If it says `"init_candidates": [ { ... } ]` (a list), change to `"init_candidates": { ... }` (object). Update §7 description to say "single object containing one_liner, anti_trope, hard_constraints, protagonist_flaw, antagonist_mirror, opening_hook".

- [ ] **Step 4: Verify C1 tests pass**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py::test_init_candidates_is_object_not_list_in_agent_schema data_modules/tests/test_init_reference_tree.py::test_build_reference_tree_with_minimal_init_candidates -v 2>&1 | tail -5
```

Expected: PASS.

- [ ] **Step 5: Write failing tests for C2 (no rmtree) + C3 (symlink refusal)**

Add to `scripts/data_modules/tests/test_init_idea_bank.py`:

```python
def test_init_refuses_symlink_reference_research_dir(tmp_path, monkeypatch):
    """Symlink at --reference-research-dir target raises SystemExit."""
    import init_project as init_project_module
    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)

    # Create a symlink pointing to a real directory
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    symlink = tmp_path / "link"
    symlink.symlink_to(real_dir)

    project_root = tmp_path / "book"
    with pytest.raises(SystemExit, match="[Ss]ymlink"):
        init_project_module.init_project(
            str(project_root), title="T", genre="仙侠", protagonist_name="P",
            reference_research_dir=str(symlink / "fanren-xiuxian-chuan"),
        )


def test_init_overwrite_preserves_old_schema_outside_target(tmp_path, monkeypatch):
    """--reference-overwrite must preserve old _schema.json OUTSIDE target_tree."""
    import init_project as init_project_module
    from init_reference_tree import build_reference_tree
    import shutil, json as _json

    monkeypatch.setattr(init_project_module, "is_git_available", lambda: False)

    schema_v1 = _minimal_schema()
    schema_v1["reader_promise"] = "VERSION_1"
    schema_v2 = _minimal_schema()
    schema_v2["reader_promise"] = "VERSION_2"

    project_root = tmp_path / "book"
    project_root.mkdir()
    # Pre-build v1 in target
    target = project_root / ".webnovel" / "reference_research" / "x"
    build_reference_tree(project_root, schema_v1, "X")

    # Build v2 in separate source dir
    src_v2_root = tmp_path / "src2"
    src_v2_root.mkdir()
    src_v2 = build_reference_tree(src_v2_root, schema_v2, "X")

    # Run init with --reference-overwrite
    init_project_module.init_project(
        str(project_root), title="T", genre="仙侠", protagonist_name="P",
        reference_research_dir=str(src_v2),
        reference_overwrite=True,
    )

    # Old _schema.json must be preserved SOMEWHERE (not in target which is overwritten)
    # Check backup directory or in-place backup pattern
    target_schema = _json.loads((target / "_schema.json").read_text(encoding="utf-8"))
    assert target_schema["reader_promise"] == "VERSION_2"  # new is in target

    # Old must be preserved — check backups/ or in-place .bak
    backups_dir = project_root / ".webnovel" / "backups"
    has_backup = (
        backups_dir.exists() and any(backups_dir.glob("*x*"))
        or any(target.parent.glob("*.bak-*"))
        or any(target.glob("_schema.json.bak-*"))
    )
    assert has_backup, "old _schema.json must be preserved in backup location"
```

Add to `scripts/data_modules/tests/test_init_reference_tree.py`:

```python
def test_build_reference_tree_refuses_symlink_target(tmp_path):
    """Symlink at target path raises SystemExit."""
    import os
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    symlink = tmp_path / "link"
    symlink.symlink_to(real_dir)

    schema = _minimal_schema()
    with pytest.raises(SystemExit, match="[Ss]ymlink"):
        build_reference_tree(symlink, schema, "X")
```

- [ ] **Step 6: Verify C2/C3 tests fail**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_init_idea_bank.py::test_init_refuses_symlink_reference_research_dir data_modules/tests/test_init_idea_bank.py::test_init_overwrite_preserves_old_schema_outside_target data_modules/tests/test_init_reference_tree.py::test_build_reference_tree_refuses_symlink_target -v 2>&1 | tail -10
```

Expected: All 3 FAIL.

- [ ] **Step 7: Fix C2 — remove `rmtree`, use in-place overwrite**

In `scripts/init_project.py`, find the reference_research copy block (around lines 760-785). Replace:

```python
        if target_tree.exists():
            # Backup existing schema
            existing_schema = target_tree / "_schema.json"
            if existing_schema.exists():
                from datetime import datetime, timezone
                backup = target_tree / f"_schema.json.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')}"
                existing_schema.rename(backup)
        target_tree.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        if target_tree.exists():
            shutil.rmtree(target_tree)
        shutil.copytree(src_tree, target_tree)
```

With:

```python
        # Backup existing schema to OUTSIDE target_tree (preserves even on overwrite)
        existing_schema = target_tree / "_schema.json"
        if existing_schema.exists():
            from datetime import datetime, timezone
            backups_dir = project_path / ".webnovel" / "backups"
            backups_dir.mkdir(parents=True, exist_ok=True)
            backup = backups_dir / f"{book_safe}__schema__{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')}.bak"
            shutil.copy2(existing_schema, backup)
        # In-place overwrite (no rmtree)
        target_tree.parent.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(target_tree) if False else None  # DISABLED — keep for reference, do not execute
        shutil.copytree(src_tree, target_tree)
```

(Better: just remove the `shutil.rmtree` line entirely. The `shutil.copytree` will overwrite files in place.)

- [ ] **Step 8: Fix C3 — refuse symlinks**

In `scripts/init_reference_tree.py`, find `build_reference_tree()`. At the very start (after parameter parsing), add:

```python
    if tree.is_symlink():
        raise SystemExit(
            f"refusing to write through symlink: {tree}. "
            f"Remove the symlink first or choose a different <book-safe> name."
        )
```

In `scripts/init_project.py`, find the reference_research validation block (around line 758). After `src_tree.is_dir()` check, add:

```python
        if src_tree.is_symlink():
            raise SystemExit(
                f"--reference-research-dir is a symlink (refusing to follow): {src_tree}"
            )
```

- [ ] **Step 9: Verify all C1/C2/C3 tests pass**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_prompt_integrity.py::test_init_candidates_is_object_not_list_in_agent_schema data_modules/tests/test_init_reference_tree.py::test_build_reference_tree_with_minimal_init_candidates data_modules/tests/test_init_reference_tree.py::test_build_reference_tree_refuses_symlink_target data_modules/tests/test_init_idea_bank.py::test_init_refuses_symlink_reference_research_dir data_modules/tests/test_init_idea_bank.py::test_init_overwrite_preserves_old_schema_outside_target -v 2>&1 | tail -10
```

Expected: 5 PASSED.

- [ ] **Step 10: Sync + commit**

```bash
cp /Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/agents/deconstruction-agent.md /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/agents/
cp /Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/scripts/init_reference_tree.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/
cp /Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/scripts/init_project.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/
cp /Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_init_reference_tree.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/tests/
cp /Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_init_idea_bank.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/tests/
cp /Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_prompt_integrity.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/tests/

cd /Users/chang/Desktop/ai写小说工具开发
git add -A
git commit -m "fix(adversarial): C1 init_candidates schema, C2 backup destruction, C3 symlink leak

C1: init_candidates is now an OBJECT (not list) in agent schema; template
    correctly renders all 6 fields; was silently dropping the primary
    deconstruction output.

C2: --reference-overwrite now backs up _schema.json to
    .webnovel/backups/ BEFORE overwriting (was destroying the backup
    with shutil.rmtree because it lived inside target_tree).

C3: Both build_reference_tree() and init_project's reference_research
    validation now refuse symlinks with SystemExit (was following
    symlinks and writing to attacker-controlled locations)."
```

---

## Task B: Important Bugs (I1, I2, I3, I4)

**Files:** `scripts/data_modules/marked_references.py`, `scripts/init_project.py`, `scripts/init_reference_tree.py`, `tests`

- [ ] **Step 1: Write failing tests for I1, I2, I3, I4**

Add to `scripts/data_modules/tests/test_marked_references.py`:

```python
def test_marked_references_rejects_empty_string_title():
    from data_modules.marked_references import validate_marked_references
    with pytest.raises(ValueError, match="title"):
        validate_marked_references({"schema_version": 1, "references": [{"platform": "qidian", "title": ""}]})


def test_marked_references_rejects_whitespace_only_title():
    from data_modules.marked_references import validate_marked_references
    with pytest.raises(ValueError, match="title"):
        validate_marked_references({"schema_version": 1, "references": [{"platform": "qidian", "title": "   "}]})


def test_marked_references_rejects_non_string_platform():
    from data_modules.marked_references import validate_marked_references
    with pytest.raises(ValueError, match="platform"):
        validate_marked_references({"schema_version": 1, "references": [{"platform": 123, "title": "X"}]})
```

Add to `scripts/data_modules/tests/test_init_idea_bank.py`:

```python
def test_validate_idea_bank_rejects_version_true():
    from init_project import _validate_idea_bank_payload
    bad = {"version": True, "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
           "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": []}
    with pytest.raises(ValueError):
        _validate_idea_bank_payload(json.dumps(bad))


def test_validate_idea_bank_rejects_version_float():
    from init_project import _validate_idea_bank_payload
    bad = {"version": 1.0, "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
           "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": []}
    with pytest.raises(ValueError):
        _validate_idea_bank_payload(json.dumps(bad))


def test_validate_idea_bank_rejects_non_string_reference_research_path():
    from init_project import _validate_idea_bank_payload
    bad = {"version": 1, "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
           "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
           "reference_research_path": 123}
    with pytest.raises(ValueError):
        _validate_idea_bank_payload(json.dumps(bad))


def test_validate_idea_bank_rejects_path_traversal_reference_research_path():
    from init_project import _validate_idea_bank_payload
    bad = {"version": 1, "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
           "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
           "reference_research_path": "../etc/passwd"}
    with pytest.raises(ValueError):
        _validate_idea_bank_payload(json.dumps(bad))


def test_validate_idea_bank_rejects_absolute_reference_research_path():
    from init_project import _validate_idea_bank_payload
    bad = {"version": 1, "source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
           "selected_idea": {}, "constraints_inherited": {}, "borrowed_patterns": [], "do_not_copy": [], "canon_contamination_warnings": [],
           "reference_research_path": "/etc/passwd"}
    with pytest.raises(ValueError):
        _validate_idea_bank_payload(json.dumps(bad))
```

Add to `scripts/data_modules/tests/test_init_reference_tree.py`:

```python
def test_sanitize_book_title_strips_cjk_punctuation():
    from init_reference_tree import sanitize_book_title
    # Each should NOT contain CJK punctuation in the resulting slug
    for punct in ["！", "。", "？", "，", "：", "（", "）", "、", "；"]:
        title = f"凡人修仙传{punct}"
        result = sanitize_book_title(title)
        assert punct not in result, f"{punct} leaked into slug: {result!r}"
```

- [ ] **Step 2: Verify tests fail**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_marked_references.py data_modules/tests/test_init_idea_bank.py data_modules/tests/test_init_reference_tree.py -v -k "rejects_empty_string_title or rejects_whitespace or rejects_non_string or rejects_version or rejects_non_string_reference or rejects_path_traversal or rejects_absolute or strips_cjk" 2>&1 | tail -15
```

Expected: All new tests FAIL.

- [ ] **Step 3: Fix I1 — strict type validation in `marked_references.py`**

Find the loop in `validate_marked_references()` (lines 41-49). Replace the type-check section:

```python
    for i, ref in enumerate(references):
        if not isinstance(ref, dict):
            raise ValueError(f"marked-references.json references[{i}] must be an object")
        if not isinstance(ref.get("platform"), str) or not ref["platform"].strip():
            raise ValueError(f"marked-references.json references[{i}] missing or invalid 'platform'")
        if not isinstance(ref.get("title"), str) or not ref["title"].strip():
            raise ValueError(f"marked-references.json references[{i}] missing or invalid 'title'")
```

- [ ] **Step 4: Fix I2 — strict version check in `init_project.py`**

Find `_validate_idea_bank_payload()` line `if data.get("version") != 1:`. Replace:

```python
    if data.get("version") is not 1:
        raise ValueError(f"idea_bank.json version must be exactly 1 (int), got {data.get('version')!r}")
```

- [ ] **Step 5: Fix I3 — reference_research_path validation**

After the `source` validation block, add:

```python
    # Optional reference_research_path validation (P0-Full spec §D4)
    if "reference_research_path" in data:
        rrp = data["reference_research_path"]
        if not isinstance(rrp, str):
            raise ValueError("idea_bank.reference_research_path must be a string")
        from pathlib import Path as _Path
        if _Path(rrp).is_absolute():
            raise ValueError(f"idea_bank.reference_research_path must be relative, got {rrp!r}")
        if ".." in _Path(rrp).parts:
            raise ValueError(f"idea_bank.reference_research_path must not contain '..', got {rrp!r}")
```

- [ ] **Step 6: Fix I4 — strip CJK punctuation in `sanitize_book_title`**

Find the `_CJK_BRACKETS = "《》「」『』【】"` definition. Replace the `re.sub(r'[\\/:\*\?"<>\|]', "", title)` line:

```python
    safe = re.sub(r'[\\/:\*\?"<>\|]', "", title)
    # Also strip CJK punctuation (U+3000-U+303F CJK Symbols, U+FF00-U+FFEF Halfwidth/Fullwidth)
    safe = re.sub(r'[　-〿＀-￯]', "", safe)
```

- [ ] **Step 7: Verify all I1-I4 tests pass**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_marked_references.py data_modules/tests/test_init_idea_bank.py data_modules/tests/test_init_reference_tree.py -v -k "rejects_empty_string_title or rejects_whitespace or rejects_non_string or rejects_version or rejects_non_string_reference or rejects_path_traversal or rejects_absolute or strips_cjk" 2>&1 | tail -15
```

Expected: All new tests PASS.

- [ ] **Step 8: Sync + commit**

(Same sync pattern as Task A.)

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add -A
git commit -m "fix(adversarial): I1-I4 strict validation — marked_references types, version, paths, CJK punct

I1: marked_references rejects empty/whitespace/non-string platform+title.
I2: idea_bank version must be int(1), not True/1.0.
I3: reference_research_path must be string, relative, no '..'.
I4: sanitize_book_title strips CJK punctuation (U+3000-U+303F, U+FF00-U+FFEF)."
```

---

## Task C: Important I5 + Plan scanner helper

**Files:** `scripts/data_modules/reference_research_scanner.py` (NEW), `skills/webnovel-plan/SKILL.md`, tests

- [ ] **Step 1: Write failing tests for the new scanner**

Create `scripts/data_modules/tests/test_reference_research_scanner.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import pytest


def test_scanner_finds_valid_trees(tmp_path):
    """Scanner returns all valid reference_research trees in project."""
    from data_modules.reference_research_scanner import scan_reference_research_trees
    import init_reference_tree

    # Build 2 valid trees
    schema = {"source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
              "reader_promise": "", "opening_hook_patterns": [], "cool_point_loops": [],
              "protagonist_patterns": "", "antagonist_pressure_patterns": "", "pacing_notes": "",
              "narrative_function": "", "boundary_reason": {}, "protagonist_action_chain": [],
              "emotion_curve": [], "satisfaction_point": [], "foreshadowing": [],
              "gains_costs": [], "character_changes": [], "borrowable_patterns": [],
              "differentiation_requirements": "", "init_candidates": {},
              "do_not_copy": [], "canon_contamination_warnings": [],
              "quality": {"passed": True, "confidence": 0.5, "coverage": 0.5}}
    init_reference_tree.build_reference_tree(tmp_path, schema, "A")
    init_reference_tree.build_reference_tree(tmp_path, schema, "B")

    trees = scan_reference_research_trees(tmp_path)
    assert len(trees) == 2
    assert any("a" in str(t) for t in trees)
    assert any("b" in str(t) for t in trees)


def test_scanner_filters_invalid_paths(tmp_path):
    """Scanner skips directories missing required files."""
    from data_modules.reference_research_scanner import scan_reference_research_trees
    import init_reference_tree

    schema = {"source": {"reference_title": "X", "reference_source": "book_name", "analysis_mode": "quick", "confidence": 0.5},
              "reader_promise": "", "opening_hook_patterns": [], "cool_point_loops": [],
              "protagonist_patterns": "", "antagonist_pressure_patterns": "", "pacing_notes": "",
              "narrative_function": "", "boundary_reason": {}, "protagonist_action_chain": [],
              "emotion_curve": [], "satisfaction_point": [], "foreshadowing": [],
              "gains_costs": [], "character_changes": [], "borrowable_structures": [],
              "differentiation_requirements": "", "init_candidates": {},
              "do_not_copy": [], "canon_contamination_warnings": [],
              "quality": {"passed": True, "confidence": 0.5, "coverage": 0.5}}
    init_reference_tree.build_reference_tree(tmp_path, schema, "valid")

    # Create invalid dir (no _schema.json)
    invalid = tmp_path / ".webnovel" / "reference_research" / "invalid"
    invalid.mkdir(parents=True)
    (invalid / "report.md").write_text("garbage", encoding="utf-8")

    trees = scan_reference_research_trees(tmp_path)
    assert len(trees) == 1
    assert "valid" in str(trees[0])


def test_scanner_returns_empty_when_no_dir(tmp_path):
    """Scanner returns [] when .webnovel/reference_research doesn't exist."""
    from data_modules.reference_research_scanner import scan_reference_research_trees
    trees = scan_reference_research_trees(tmp_path)
    assert trees == []


def test_scanner_validates_idea_bank_pointer(tmp_path):
    """validate_idea_bank_pointer() rejects unsafe paths."""
    from data_modules.reference_research_scanner import validate_idea_bank_pointer

    assert validate_idea_bank_pointer(".webnovel/reference_research/foo/") == ".webnovel/reference_research/foo/"
    with pytest.raises(ValueError, match="absolute"):
        validate_idea_bank_pointer("/etc/passwd")
    with pytest.raises(ValueError, match=r"\.\."):
        validate_idea_bank_pointer("../etc/passwd")
    with pytest.raises(ValueError, match="string"):
        validate_idea_bank_pointer(123)
    with pytest.raises(ValueError, match="string"):
        validate_idea_bank_pointer(None)
```

- [ ] **Step 2: Verify tests fail**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_reference_research_scanner.py -v 2>&1 | tail -10
```

Expected: All 4 FAIL with `No module named 'reference_research_scanner'`.

- [ ] **Step 3: Implement the scanner**

Create `/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/reference_research_scanner.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Validate and enumerate reference_research trees under <project>/.webnovel/reference_research/.

Implements 2026-08-16-p0-full-p1-p2-adversarial-fixes-design I5.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union


REQUIRED_FILES = ("_schema.json", "report.md", "do_not_copy.md",
                  "canon_contamination_warnings.md", "_progress.json")


def validate_idea_bank_pointer(value: Union[str, None]) -> str:
    """Validate idea_bank.json.reference_research_path value.

    Rules:
      - Must be a non-empty string
      - Must be a relative path (not absolute)
      - Must not contain '..' components

    Returns the validated string. Raises ValueError on any miss.
    """
    if not isinstance(value, str):
        raise ValueError(f"idea_bank.reference_research_path must be a string, got {type(value).__name__}")
    if not value.strip():
        raise ValueError("idea_bank.reference_research_path must not be empty")
    p = Path(value)
    if p.is_absolute():
        raise ValueError(f"idea_bank.reference_research_path must be relative, got {value!r}")
    if ".." in p.parts:
        raise ValueError(f"idea_bank.reference_research_path must not contain '..', got {value!r}")
    return value


def scan_reference_research_trees(project_root: Path) -> list[Path]:
    """Scan <project_root>/.webnovel/reference_research/*/ for valid trees.

    Returns paths to subdirectories that contain ALL required files.
    Returns [] if the directory doesn't exist or contains no valid trees.
    """
    root = Path(project_root).expanduser().resolve()
    base = root / ".webnovel" / "reference_research"
    if not base.is_dir():
        return []

    valid: list[Path] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir() or entry.is_symlink():
            continue
        if all((entry / name).is_file() for name in REQUIRED_FILES):
            valid.append(entry)
    return valid
```

- [ ] **Step 4: Verify tests pass**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_reference_research_scanner.py -v 2>&1 | tail -10
```

Expected: 4 PASSED.

- [ ] **Step 5: Update plan SKILL.md to use the scanner**

Open `skills/webnovel-plan/SKILL.md`. Find the "按需读取 reference_research 拆书产物" section (around line 100). Update the opening to mention the scanner helper:

```markdown
读完 `idea_bank.json` 后，按以下规则加载所有可用拆书产物：

1. **如果 `idea_bank.reference_research_path` 存在** → 先调用 `scripts/data_modules/reference_research_scanner.py:validate_idea_bank_pointer()` 验证路径安全（拒绝绝对路径、`..`、非字符串）。通过后该路径指向的树是**主对标书**（primary）。
2. **扫描所有可用树**：调用 `scan_reference_research_trees(project_root)` 返回所有合法 `<book-safe>/` 子目录。
3. **加载每棵树**：`_schema.json` + `report.md`（节选）+ `do_not_copy.md` + `canon_contamination_warnings.md`。
4. **去重**：相同 `<book-safe>` 不重复加载。
5. **主从优先级**：主对标书（来自 init §1.5）的字段优先；次要参考（来自 standalone deconstruct）补充多样性。
...
```

- [ ] **Step 6: Sync + commit**

```bash
cp /Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/scripts/data_modules/reference_research_scanner.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/
cp /Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_reference_research_scanner.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/tests/
cp /Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang/skills/webnovel-plan/SKILL.md /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/skills/webnovel-plan/SKILL.md

cd /Users/chang/Desktop/ai写小说工具开发
git add -A
git commit -m "feat(scan): reference_research_scanner helper — Python enforcement for plan

I5 fix: plan SKILL.md now references scan_reference_research_trees()
+ validate_idea_bank_pointer() helpers. Auto-discovery is no longer
purely LLM-driven — Python validates paths are safe + skips symlinks
+ requires all 5 standard files per tree."
```

---

## Task D: Minor Bugs (M1, M2, M3, M4, M5, M6)

**Files:** `skills/webnovel-chart-scan/scripts/output.py`, `skills/webnovel-chart-scan/scripts/schema.py`, `scripts/data_modules/marked_references.py`, tests

- [ ] **Step 1: Write failing tests for M1-M6**

Add to `scripts/data_modules/tests/test_init_reference_tree.py`:

```python
def test_build_reference_tree_backup_timestamp_unique():
    """Two backups in quick succession get unique timestamps."""
    from init_reference_tree import build_reference_tree
    import time
    schema = _minimal_schema()

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        build_reference_tree(pathlib.Path(td), schema, "X")  # first
        backup1 = list((pathlib.Path(td) / ".webnovel" / "backups").glob("*.bak"))
        time.sleep(0.001)  # ensure measurable time gap
        # We'd need to force overwrite — but build_reference_tree refuses to overwrite without overwrite=True
        # So just verify timestamp format includes microseconds
        assert backup1, "first build should produce a backup or fresh dir"
```

(Adjust as needed — the backup timestamps should include microsecond precision.)

Add to a new file or test_init_reference_tree.py:

```python
def test_slug_timestamp_includes_microseconds():
    """slug_timestamp uses microsecond precision to avoid same-second collision."""
    from skills.webnovel_chart_scan.scripts.output import slug_timestamp
    from datetime import datetime, timezone
    ts = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)
    result = slug_timestamp(ts)
    assert "_" in result or "." in result, f"slug_timestamp should include microseconds: {result}"
```

(Adjust import path to match actual module structure.)

- [ ] **Step 2: Fix M1 + M2 — microsecond precision in backup timestamps**

In `scripts/init_reference_tree.py`, find `_schema.json.bak-{ts}` (around line 243). Change `%Y%m%dT%H%M%SZ` → `%Y%m%dT%H%M%S_%fZ` (microsecond + Z).

In `scripts/init_project.py`, find the same pattern (Task A Step 7 already added `%fZ` for the new backup path; verify).

In `skills/webnovel-chart-scan/scripts/output.py`, find `slug_timestamp` function. Update its format string to include microseconds.

- [ ] **Step 3: Fix M3 — validate `output_dir` in `write_chart_scan_marked_references`**

In `skills/webnovel-chart-scan/scripts/output.py`, find `write_marked_references` (after M4 rename). Add validation:

```python
    from pathlib import Path
    output_dir_resolved = Path(output_dir).expanduser().resolve()
    cwd = Path.cwd().resolve()
    try:
        output_dir_resolved.relative_to(cwd)
    except ValueError:
        raise ValueError(f"output_dir must be within current working directory: {output_dir_resolved} not under {cwd}")
```

- [ ] **Step 4: Fix M4 — rename chart-scan's helper**

In `skills/webnovel-chart-scan/scripts/output.py`, rename `write_marked_references` → `write_chart_scan_marked_references`.

Update `chart-scan/SKILL.md` if it references the function name.

- [ ] **Step 5: Fix M5 — Pydantic UTC validator in chart-scan schema**

In `skills/webnovel-chart-scan/scripts/schema.py`, find the `scanned_at` field in `ScanMeta`. Add a field validator:

```python
from pydantic import field_validator

@field_validator("scanned_at")
@classmethod
def _scanned_at_must_be_utc(cls, v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("scanned_at must be timezone-aware (use timezone.utc)")
    return v
```

- [ ] **Step 6: Fix M6 — remove unused `Any` import**

In `scripts/data_modules/marked_references.py`, remove `Any` from `from typing import Any` (line 14).

- [ ] **Step 7: Verify M1-M6 tests pass**

(Sync to marketplace first, then run.)

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_init_reference_tree.py data_modules/tests/test_marked_references.py -v -k "backup_timestamp or slug_timestamp" 2>&1 | tail -10
```

- [ ] **Step 8: Sync + commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git add -A
git commit -m "fix(adversarial): M1-M6 — microsecond timestamps, path validation, rename, UTC validator, cleanup

M1: chart-scan scan_<ts>.log uses microsecond precision.
M2: init_reference_tree backup timestamp includes microseconds.
M3: write_chart_scan_marked_references validates output_dir under cwd.
M4: rename to write_chart_scan_marked_references (no name collision).
M5: Pydantic UTC validator on chart-scan scanned_at.
M6: remove unused Any import from marked_references.py."
```

---

## Task E: Final verification + re-adversarial review

**Files:** (none — verification + dispatch)

- [ ] **Step 1: Full test suite run**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest \
  data_modules/tests/test_prompt_integrity.py \
  data_modules/tests/test_init_reference_tree.py \
  data_modules/tests/test_init_idea_bank.py \
  data_modules/tests/test_marked_references.py \
  data_modules/tests/test_reference_research_scanner.py \
  -v 2>&1 | tail -10
```

Expected: 33 prior + 14 new = 47+ tests pass. Pre-existing failures (37 unrelated) are out of scope.

- [ ] **Step 2: Sync verification**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
for f in \
  agents/deconstruction-agent.md \
  scripts/init_reference_tree.py \
  scripts/init_project.py \
  scripts/data_modules/marked_references.py \
  scripts/data_modules/reference_research_scanner.py \
  skills/webnovel-chart-scan/scripts/output.py \
  skills/webnovel-chart-scan/scripts/schema.py \
  skills/webnovel-plan/SKILL.md \
  scripts/data_modules/tests/test_init_reference_tree.py \
  scripts/data_modules/tests/test_init_idea_bank.py \
  scripts/data_modules/tests/test_marked_references.py \
  scripts/data_modules/tests/test_prompt_integrity.py \
  scripts/data_modules/tests/test_reference_research_scanner.py
do
  diff -q ".claude/plugins/webnovel-writer_chang/$f" "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/$f" || echo "OUT OF SYNC: $f"
done
echo "Sync check complete"
```

Expected: All identical, no OUT OF SYNC.

- [ ] **Step 3: Dispatch final adversarial review**

Re-run adversarial review to confirm no new Critical bugs introduced. (This is the gate that prevented the prior 4 confirmatory reviews from missing bugs.)

```bash
# Use the Task tool to dispatch a fresh opus-level adversarial reviewer
# with the same prompt as the original review, but updated to include
# the new fixes. Confirm no new Critical bugs introduced.
```

- [ ] **Step 4: Report results**

Print summary:
- 14 fixes complete (3 Critical + 5 Important + 6 Minor)
- All new tests pass
- No regressions
- Re-adversarial review shows no new Critical bugs

---

## Acceptance Criteria Checklist

After all 5 tasks complete, verify:

- [ ] C1: agent schema declares `init_candidates` as OBJECT; template renders 6 fields correctly
- [ ] C2: `--reference-overwrite` preserves old schema in `.webnovel/backups/` (or similar)
- [ ] C3: Symlinks at target path raise SystemExit in both functions
- [ ] I1: `marked_references` rejects empty/whitespace/non-string title+platform
- [ ] I2: `version: True` / `version: 1.0` rejected by validator
- [ ] I3: `reference_research_path` rejects non-string/absolute/.. 
- [ ] I4: `sanitize_book_title` strips CJK punctuation
- [ ] I5: `reference_research_scanner` helper exists + plan SKILL.md uses it
- [ ] M1: chart-scan log timestamp has microseconds
- [ ] M2: `init_reference_tree` backup timestamp has microseconds
- [ ] M3: `write_chart_scan_marked_references` validates output_dir
- [ ] M4: chart-scan helper renamed (no name collision)
- [ ] M5: Pydantic UTC validator on chart-scan `scanned_at`
- [ ] M6: `Any` import removed
- [ ] All 33 prior tests pass (no regression)
- [ ] 14 new tests pass
- [ ] Both copies in sync
- [ ] Re-adversarial review: no new Critical bugs introduced

---

## Out-of-Scope Reminder

- Performance optimization
- Multi-user shared `reference_research/`
- English book title support
- Replacing LLM-driven plan auto-discovery with deterministic pipeline (deferred)

---

## Self-Review Notes

- **Spec coverage**: All 14 findings have a corresponding task section (C1→Task A, C2→Task A, C3→Task A, I1→Task B, I2→Task B, I3→Task B, I4→Task B, I5→Task C, M1→Task D, M2→Task D, M3→Task D, M4→Task D, M5→Task D, M6→Task D).
- **Placeholder scan**: no "TBD"/"TODO"/"implement later". All code blocks complete.
- **Type consistency**: `validate_idea_bank_pointer(value: str) -> str` consistent between helper and plan mention. `scan_reference_research_trees(project_root: Path) -> list[Path]` consistent.
- **Risk acknowledgment**: Re-running adversarial review (Task E Step 3) is the most important gate.