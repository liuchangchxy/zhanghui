# P3 Adversarial Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Fix all 5 Critical + 3 Important + 1 Minor bugs from P3 adversarial review.

**Architecture:** Three batched fix dispatches (by file scope). Each batch is a single subagent that fixes related bugs in one file + tests.

**Tech Stack:** Python 3, pytest, argparse. No new deps.

---

## Task A: rejection_contract fix + test (C1 + new test)

**Files:**
- Modify: `scripts/rejection_contract.py:20-22`
- Modify: tests (add C1 test — find or create test file)

- [ ] **Step 1: Write failing test**

Find/create `scripts/data_modules/tests/test_rejection_contract.py`. Add:

```python
def test_rejection_contract_accepts_do_not_copy_violation():
    from rejection_contract import build_contract_from_reviewer_output, validate_contract
    contract = build_contract_from_reviewer_output({
        "chapter": 1,
        "issues": [{
            "severity": "critical",
            "category": "do_not_copy_violation",
            "location": "第2段",
            "description": "出现禁用元素",
            "fix_hint": "改写",
            "blocking": True,
        }]
    })
    validate_contract(contract)  # MUST NOT raise
```

(Adjust the import path if the helper function signature differs — read `rejection_contract.py` first.)

- [ ] **Step 2: Verify test fails**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_rejection_contract.py::test_rejection_contract_accepts_do_not_copy_violation -v 2>&1 | tail -10
```

Expected: FAIL.

- [ ] **Step 3: Add `do_not_copy_violation` to `VALID_CATEGORIES`**

Open `/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/scripts/rejection_contract.py`. Find the `VALID_CATEGORIES` definition. Add `"do_not_copy_violation"`.

- [ ] **Step 4: Verify test passes**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_rejection_contract.py::test_rejection_contract_accepts_do_not_copy_violation -v 2>&1 | tail -8
```

Expected: PASS.

- [ ] **Step 5: Sync + commit**

```bash
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/scripts/rejection_contract.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/

cd /Users/chang/Desktop/zhanghui
git add -A
git commit -m "fix(p3-adversarial): C1 — rejection_contract accepts do_not_copy_violation

VALID_CATEGORIES whitelist now includes the new P3 category. Without
this, revise_chapter.py:264 validate_contract() rejects every Step 4
revision triggered by do_not_copy_violation → EXIT_INVALID → chapter
never auto-revises (silent flow breakage)."
```

---

## Task B: reference_research_injector fixes (C2 + C3 + C4 + C5 + I1 tests)

**Files:**
- Modify: `scripts/data_modules/reference_research_injector.py`
- Modify: `scripts/data_modules/tests/test_reference_research_injector.py`

- [ ] **Step 1: Write failing tests for C2, C3, C4, C5**

Add to `scripts/data_modules/tests/test_reference_research_injector.py`:

```python
def test_cli_build_step1_summary(tmp_path):
    """CLI invocation produces non-empty output when trees exist."""
    import subprocess
    import sys
    _build_minimal_tree(tmp_path, borrowable=["宗门升级"])
    helper = "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/reference_research_injector.py"
    result = subprocess.run(
        [sys.executable, helper, "build-step1-summary", "--project-root", str(tmp_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"CLI failed: stderr={result.stderr}"
    assert result.stdout.strip(), "CLI produced empty output"


def test_cli_build_step2a_section(tmp_path):
    import subprocess, sys
    _build_minimal_tree(tmp_path, do_not_copy=["韩立人设"])
    helper = "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/reference_research_injector.py"
    result = subprocess.run(
        [sys.executable, helper, "build-step2a-section", "--project-root", str(tmp_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "对标书红黑名单" in result.stdout


def test_cli_build_do_not_copy_check_data(tmp_path):
    import subprocess, sys, json
    _build_minimal_tree(tmp_path, do_not_copy=["韩立人设"])
    helper = "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/reference_research_injector.py"
    chapter_text = "韩立出场了\n"
    result = subprocess.run(
        [sys.executable, helper, "build-do-not-copy-check-data",
         "--project-root", str(tmp_path),
         "--chapter-text", chapter_text],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert len(data) >= 1


def test_do_not_copy_check_skips_subtoken_false_positive(tmp_path):
    """Sub-3-char tokens must NOT trigger violations (avoids false positives like 韩立群 on 韩立人设)."""
    from data_modules.reference_research_injector import build_do_not_copy_check_data
    _build_minimal_tree(tmp_path, do_not_copy=["韩立人设"])
    chapter_text = "李明与韩立群一同走进山谷。"
    violations = build_do_not_copy_check_data(tmp_path, chapter_text)
    # 韩立 alone is 2 chars; tokens < 3 must not match
    assert violations == [], f"false positive: {violations}"


def test_do_not_copy_check_matches_colon_form_value(tmp_path):
    """Colon-prefix items like '原作人物名: 韩立' should match the value '韩立'."""
    from data_modules.reference_research_injector import build_do_not_copy_check_data
    _build_minimal_tree(tmp_path, do_not_copy=["原作人物名: 韩立"])
    chapter_text = "第一章：韩立出场。"
    violations = build_do_not_copy_check_data(tmp_path, chapter_text)
    assert len(violations) >= 1
    assert violations[0]["item"] == "原作人物名: 韩立"
    assert "韩立" in violations[0]["matched_text"]


def test_step1_summary_docstring_mentions_char_cap():
    """Docstring must document actual 800-char cap (not the lying 200-token claim)."""
    import inspect
    from data_modules.reference_research_injector import build_step1_summary
    doc = inspect.getdoc(build_step1_summary) or ""
    assert "800" in doc or "char" in doc.lower(), f"docstring misleading: {doc}"
```

- [ ] **Step 2: Verify tests fail**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_reference_research_injector.py -v -k "cli_build or skips_subtoken or matches_colon_form or docstring_mentions_char_cap" 2>&1 | tail -15
```

Expected: 6 FAIL.

- [ ] **Step 3: Fix C2 — add `__main__` block with argparse**

Open `/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/scripts/data_modules/reference_research_injector.py`. Append at the end:

```python

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="reference_research_injector — build prompt sections for write/review")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("build-step1-summary")
    p1.add_argument("--project-root", required=True)
    p1.set_defaults(fn=lambda a: print(build_step1_summary(Path(a.project_root))))

    p2 = sub.add_parser("build-step2a-section")
    p2.add_argument("--project-root", required=True)
    p2.set_defaults(fn=lambda a: print(build_step2a_prompt_section(Path(a.project_root))))

    p3 = sub.add_parser("build-do-not-copy-check-data")
    p3.add_argument("--project-root", required=True)
    p3.add_argument("--chapter-text", default="")
    p3.add_argument("--chapter-file", default=None,
                     help="Read chapter text from this file (alternative to --chapter-text)")
    p3.set_defaults(fn=lambda a: print(json.dumps(
        build_do_not_copy_check_data(Path(a.project_root),
                                    a.chapter_text if a.chapter_text
                                    else Path(a.chapter_file).read_text(encoding="utf-8") if a.chapter_file
                                    else ""),
        ensure_ascii=False)))

    args = parser.parse_args()
    args.fn(args)
```

- [ ] **Step 4: Fix C3 — minimum token length 3**

Find `_do_not_copy_match_tokens()` (or whatever the tokenization function is named — look for `_CLASSIFIER_SUFFIXES` usage). Add a min-length filter:

```python
def _do_not_copy_match_tokens(item: str) -> list[str]:
    """Split colon-prefix and CJK classifier-suffix items into match tokens.

    Rules:
      - Colon-prefix ('原作人物名: 韩立') → use value side ('韩立')
      - Split on classifier suffixes
      - Drop tokens shorter than 3 CJK chars (avoids false positives)
    """
    # Strip colon-prefix
    if ":" in item:
        parts = item.split(":", 1)
        item = parts[1].strip()
    # Split on classifier suffixes
    pattern = "|".join(re.escape(s) for s in _CLASSIFIER_SUFFIXES)
    tokens = [t for t in re.split(f"({pattern})", item) if t and not re.fullmatch(pattern, t)]
    # Filter to tokens ≥ 3 chars
    return [t for t in tokens if len(t) >= 3]
```

(Adjust based on actual existing function structure.)

- [ ] **Step 5: Fix C4 — handled by C3's colon-stripping**

Verify: `test_do_not_copy_check_matches_colon_form_value` passes after C3 fix.

- [ ] **Step 6: Fix C5 — docstring + remove unused `max_tokens` parameter**

Update the `build_step1_summary()` docstring to say "≤ 800 chars (~1200 CJK tokens)". Remove `max_tokens: int = 200` parameter (unused). Also update `write/SKILL.md` and `context-agent.md` if they say "≤ 200 tokens" to say "≤ 800 chars (~1200 CJK tokens)".

- [ ] **Step 7: Verify all new tests pass + no regression**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest data_modules/tests/test_reference_research_injector.py -v 2>&1 | tail -25
```

Expected: All 18 tests pass (12 original + 6 new).

- [ ] **Step 8: Sync + commit**

```bash
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/scripts/data_modules/reference_research_injector.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/scripts/data_modules/tests/test_reference_research_injector.py /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/tests/
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/skills/webnovel-write/SKILL.md
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/agents/context-agent.md /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/agents/

cd /Users/chang/Desktop/zhanghui
git add -A
git commit -m "fix(p3-adversarial): C2+C3+C4+C5 — CLI main, CJK matcher fixes, doc accuracy

C2: reference_research_injector now has __main__ with argparse; CLI
    invocations from SKILL.md (build-step1-summary, build-step2a-section,
    build-do-not-copy-check-data) work end-to-end.

C3: CJK matcher requires min 3-char tokens; '韩立人设' no longer splits
    to ['韩立'] (2-char false positive on innocent text like '韩立群').

C4: colon-prefix stripping: '原作人物名: 韩立' now matches the value
    side '韩立' (the actual most common storage format).

C5: build_step1_summary docstring now says '≤ 800 chars (~1200 CJK tokens)'
    matching actual hardcoded 800-char cap. Removed unused max_tokens param.

6 new tests added (CLI x3, false positive, colon-form, docstring)."
```

---

## Task C: reviewer.md silent-pass fix (I2)

**Files:**
- Modify: `agents/reviewer.md`

- [ ] **Step 1: Read current reviewer.md**

Open `/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/agents/reviewer.md`. Find the section around line 199 that handles `do_not_copy_check.json`.

- [ ] **Step 2: Update silent-pass to error**

Find the section that says something like "`do_not_copy_check.json` 不存在或不是合法 JSON → 对标书禁抄合规性结论写 `pass`，不产出 issue、不报错". Replace with:

```markdown
"do_not_copy_check.json" 不存在或不是合法 JSON → 对标书禁抄合规性维度结论写 `error` 并产出 1 个 `category: "do_not_copy_violation"` issue（severity: high）：

{
  "severity": "high",
  "category": "do_not_copy_violation",
  "location": "全章",
  "description": "无法读取 do_not_copy_check.json（文件不存在或格式错误）。请确认 .webnovel/reference_research/<book>/ 存在并重跑 /webnovel-review。",
  "evidence": "do_not_copy_check.json missing or invalid JSON",
  "fix_hint": "确认 reference_research 树存在；review 主流程重跑",
  "blocking": false
}
```

- [ ] **Step 3: Sync + commit**

```bash
cp /Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/agents/reviewer.md /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/agents/

cd /Users/chang/Desktop/zhanghui
git add -A
git commit -m "fix(p3-adversarial): I2 — do_not_copy dimension silent-pass replaced with error

reviewer.md no longer silently passes the do_not_copy dimension when
check.json is missing or malformed. Now emits an explicit high-severity
issue directing the user to re-run /webnovel-review after confirming
reference_research/ exists."
```

---

## Task D: Final verification + re-adversarial

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts
python3 -m pytest \
  data_modules/tests/test_prompt_integrity.py \
  data_modules/tests/test_init_reference_tree.py \
  data_modules/tests/test_init_idea_bank.py \
  data_modules/tests/test_marked_references.py \
  data_modules/tests/test_reference_research_scanner.py \
  data_modules/tests/test_reference_research_injector.py \
  data_modules/tests/test_rejection_contract.py \
  -v 2>&1 | tail -10
```

Expected: All prior 157 + new tests passing.

- [ ] **Step 2: Re-adversarial spot-check**

```bash
cd /Users/chang/Desktop/zhanghui
# Verify C1 fix
python3 -c "
import sys
sys.path.insert(0, '.claude/plugins/webnovel-writer_chang/scripts')
from rejection_contract import build_contract_from_reviewer_output, validate_contract
contract = build_contract_from_reviewer_output({'chapter': 1, 'issues': [{'severity': 'critical', 'category': 'do_not_copy_violation', 'location': '第1段', 'description': 'x', 'fix_hint': 'y', 'blocking': True}]})
validate_contract(contract)
print('C1 OK')
"

# Verify C2 fix (CLI)
python3 /Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/scripts/data_modules/reference_research_injector.py build-step1-summary --project-root /tmp/nonexistent 2>&1 | head -3

# Verify C3 fix (false positive)
python3 -c "
import sys, pathlib, tempfile
sys.path.insert(0, '.claude/plugins/webnovel-writer_chang/scripts')
from data_modules.init_reference_tree import build_reference_tree
from data_modules.reference_research_injector import build_do_not_copy_check_data
with tempfile.TemporaryDirectory() as td:
    proj = pathlib.Path(td)
    schema = {'source': {'reference_title': 'X', 'reference_source': 'book_name', 'analysis_mode': 'quick', 'confidence': 0.9},
              'reader_promise': '', 'opening_hook_patterns': [], 'cool_point_loops': [],
              'protagonist_patterns': '', 'antagonist_pressure_patterns': '', 'pacing_notes': '',
              'narrative_function': '', 'boundary_reason': {}, 'protagonist_action_chain': [],
              'emotion_curve': [], 'satisfaction_point': [], 'foreshadowing': [], 'gains_costs': [], 'character_changes': [],
              'borrowable_structures': [], 'differentiation_requirements': '', 'init_candidates': {},
              'do_not_copy': ['韩立人设'], 'canon_contamination_warnings': [],
              'quality': {'passed': True, 'confidence': 0.9, 'coverage': 0.9}}
    build_reference_tree(proj, schema, 'X')
    v = build_do_not_copy_check_data(proj, '李明与韩立群走进山谷')
    assert v == [], f'C3 FAIL: {v}'
    print('C3 OK: subtoken false positive avoided')
"

# Verify C4 fix (colon-form)
python3 -c "
import sys, pathlib, tempfile
sys.path.insert(0, '.claude/plugins/webnovel-writer_chang/scripts')
from data_modules.init_reference_tree import build_reference_tree
from data_modules.reference_research_injector import build_do_not_copy_check_data
with tempfile.TemporaryDirectory() as td:
    proj = pathlib.Path(td)
    schema = {'source': {'reference_title': 'X', 'reference_source': 'book_name', 'analysis_mode': 'quick', 'confidence': 0.9},
              'reader_promise': '', 'opening_hook_patterns': [], 'cool_point_loops': [],
              'protagonist_patterns': '', 'antagonist_pressure_patterns': '', 'pacing_notes': '',
              'narrative_function': '', 'boundary_reason': {}, 'protagonist_action_chain': [],
              'emotion_curve': [], 'satisfaction_point': [], 'foreshadowing': [], 'gains_costs': [], 'character_changes': [],
              'borrowable_structures': [], 'differentiation_requirements': '', 'init_candidates': {},
              'do_not_copy': ['原作人物名: 韩立'], 'canon_contamination_warnings': [],
              'quality': {'passed': True, 'confidence': 0.9, 'coverage': 0.9}}
    build_reference_tree(proj, schema, 'X')
    v = build_do_not_copy_check_data(proj, '韩立出场了')
    assert len(v) >= 1, f'C4 FAIL: {v}'
    print('C4 OK: colon-form matched')
"
```

---

## Acceptance Criteria

- [ ] C1: `rejection_contract` accepts `do_not_copy_violation`
- [ ] C2: CLI subcommands `build-step1-summary`, `build-step2a-section`, `build-do-not-copy-check-data` all work end-to-end
- [ ] C3: `韩立群` doesn't false-positive on `韩立人设`
- [ ] C4: `原作人物名: 韩立` matches `韩立出场了`
- [ ] C5: docstring reflects actual 800-char cap
- [ ] I1: 6 new tests pass + 12 original = 18 injector tests
- [ ] I2: reviewer.md emits error issue when check.json missing
- [ ] I3: subcommand names match SKILL.md invocations
- [ ] All P0-Full + P1+P2 + 14-fix + P3 tests still pass (157+)
- [ ] 4 adversarial probes confirm fixes correct