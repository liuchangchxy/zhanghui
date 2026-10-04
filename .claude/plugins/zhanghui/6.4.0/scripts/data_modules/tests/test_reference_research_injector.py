#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import pytest
import sys


def _build_minimal_tree(project_root, book_safe="fanren", ref_title="凡人修仙传",
                        do_not_copy=None, canon_contamination=None,
                        borrowable=None, satisfaction=None):
    """Build a minimal reference_research tree at project_root/.webnovel/reference_research/<book_safe>/."""
    import pathlib
    from init_reference_tree import build_reference_tree

    schema = {
        "source": {"reference_title": ref_title, "reference_source": "book_name",
                   "analysis_mode": "quick", "confidence": 0.9},
        "reader_promise": "",
        "opening_hook_patterns": [],
        "cool_point_loops": [],
        "protagonist_patterns": "",
        "antagonist_pressure_patterns": "",
        "pacing_notes": "",
        "narrative_function": "升级流",
        "boundary_reason": {},
        "protagonist_action_chain": [],
        "emotion_curve": [],
        "satisfaction_point": satisfaction or [],
        "foreshadowing": [],
        "gains_costs": [],
        "character_changes": [],
        "borrowable_structures": borrowable or [],
        "differentiation_requirements": "",
        "init_candidates": {},
        "do_not_copy": do_not_copy or [],
        "canon_contamination_warnings": canon_contamination or [],
        "quality": {"passed": True, "confidence": 0.9, "coverage": 0.9},
    }
    return build_reference_tree(project_root, schema, ref_title)


def test_build_step1_summary_with_no_trees(tmp_path):
    from data_modules.reference_research_injector import build_step1_summary
    assert build_step1_summary(tmp_path) == ""


def test_build_step1_summary_with_one_tree(tmp_path):
    from data_modules.reference_research_injector import build_step1_summary
    _build_minimal_tree(tmp_path, borrowable=["宗门阶梯式升级"])
    summary = build_step1_summary(tmp_path)
    assert "对标参考" in summary
    assert "凡人修仙传" in summary
    assert "升级流" in summary


def test_build_step1_summary_token_limit(tmp_path):
    from data_modules.reference_research_injector import build_step1_summary
    _build_minimal_tree(
        tmp_path,
        do_not_copy=["X" * 50 for _ in range(20)],
        canon_contamination=["Y" * 50 for _ in range(20)],
        borrowable=["Z" * 50 for _ in range(20)],
        satisfaction=["W" * 50 for _ in range(10)],
    )
    summary = build_step1_summary(tmp_path)
    assert len(summary) <= 800


def test_build_step2a_section_with_no_trees(tmp_path):
    from data_modules.reference_research_injector import build_step2a_prompt_section
    assert build_step2a_prompt_section(tmp_path) == ""


def test_build_step2a_section_includes_do_not_copy(tmp_path):
    from data_modules.reference_research_injector import build_step2a_prompt_section
    _build_minimal_tree(tmp_path, do_not_copy=["韩立人设", "神秘小瓶机制"])
    section = build_step2a_prompt_section(tmp_path)
    assert "对标书红黑名单" in section
    assert "不可照搬" in section
    assert "韩立人设" in section
    assert "神秘小瓶机制" in section


def test_build_step2a_section_includes_canon_contamination(tmp_path):
    from data_modules.reference_research_injector import build_step2a_prompt_section
    _build_minimal_tree(tmp_path, canon_contamination=["原作人物名: 韩立", "原作地名: 落云宗"])
    section = build_step2a_prompt_section(tmp_path)
    assert "原作人物名" in section
    assert "韩立" in section


def test_build_step2a_section_borrowable_limited(tmp_path):
    from data_modules.reference_research_injector import build_step2a_prompt_section
    _build_minimal_tree(tmp_path, borrowable=[f"结构{i}" for i in range(10)])
    section = build_step2a_prompt_section(tmp_path)
    borrowable_lines = [l for l in section.split("\n") if l.startswith("- 结构")]
    assert len(borrowable_lines) <= 5


def test_build_step2a_section_includes_satisfaction(tmp_path):
    from data_modules.reference_research_injector import build_step2a_prompt_section
    _build_minimal_tree(tmp_path, satisfaction=["灵根检测反转", "宗门大比逆袭"])
    section = build_step2a_prompt_section(tmp_path)
    assert "灵根检测反转" in section


def test_build_do_not_copy_check_data_finds_violation(tmp_path):
    from data_modules.reference_research_injector import build_do_not_copy_check_data
    _build_minimal_tree(tmp_path, do_not_copy=["韩立人设"])
    # NOTE (P3 C3 fix): the matcher no longer splits 韩立人设 to a 2-char
    # '韩立' token (avoids false positives like 韩立群 → 韩立). The full
    # item '韩立人设' is now used as the match token. Update chapter_text
    # to contain the full token.
    chapter_text = "第一章：觉醒。\n韩立人设的设定不能照搬。"
    violations = build_do_not_copy_check_data(tmp_path, chapter_text)
    assert len(violations) >= 1
    assert violations[0]["item"] == "韩立人设"
    assert violations[0]["chapter_line"] == 2
    assert "韩立" in violations[0]["matched_text"]
    assert violations[0]["severity"] == "critical"
    assert violations[0]["category"] == "do_not_copy_violation"


def test_build_do_not_copy_check_data_no_violation(tmp_path):
    from data_modules.reference_research_injector import build_do_not_copy_check_data
    _build_minimal_tree(tmp_path, do_not_copy=["韩立人设"])
    chapter_text = "第一章：主角李明开始修炼。"
    violations = build_do_not_copy_check_data(tmp_path, chapter_text)
    assert violations == []


def test_build_do_not_copy_check_data_no_trees(tmp_path):
    from data_modules.reference_research_injector import build_do_not_copy_check_data
    violations = build_do_not_copy_check_data(tmp_path, "anything")
    assert violations == []


def test_build_step1_summary_multiple_trees_primary_first(tmp_path):
    from data_modules.reference_research_injector import build_step1_summary
    _build_minimal_tree(tmp_path, book_safe="a", ref_title="《A书》")
    _build_minimal_tree(tmp_path, book_safe="b", ref_title="《B书》")
    webnovel = tmp_path / ".webnovel"
    webnovel.mkdir(exist_ok=True)
    (webnovel / "idea_bank.json").write_text(
        json.dumps({"reference_research_path": ".webnovel/reference_research/b/"}),
        encoding="utf-8",
    )
    summary = build_step1_summary(tmp_path)
    assert summary.index("B书") < summary.index("A书")


# --- P3 adversarial fix tests (C2 + C3 + C4 + C5) ---


def test_cli_build_step1_summary(tmp_path):
    """CLI invocation produces non-empty output when trees exist."""
    import subprocess
    import sys
    _build_minimal_tree(tmp_path, borrowable=["宗门升级"])
    helper = "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/zhanghui/scripts/data_modules/reference_research_injector.py"
    result = subprocess.run(
        [sys.executable, helper, "build-step1-summary", "--project-root", str(tmp_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"CLI failed: stderr={result.stderr}"
    assert result.stdout.strip(), "CLI produced empty output"


def test_cli_build_step2a_section(tmp_path):
    import subprocess, sys
    _build_minimal_tree(tmp_path, do_not_copy=["韩立人设"])
    helper = "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/zhanghui/scripts/data_modules/reference_research_injector.py"
    result = subprocess.run(
        [sys.executable, helper, "build-step2a-section", "--project-root", str(tmp_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "对标书红黑名单" in result.stdout


def test_cli_build_do_not_copy_check_data(tmp_path):
    import subprocess, sys, json
    _build_minimal_tree(tmp_path, do_not_copy=["韩立人设"])
    helper = "/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace/zhanghui/scripts/data_modules/reference_research_injector.py"
    # Use full forbidden token to trigger violation under the new 3-char
    # matcher (see C3 fix).
    chapter_text = "韩立人设不能照搬。\n"
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