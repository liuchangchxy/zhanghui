"""revise_chapter.py 集成测试。

注意：完整的 LLM 重写测试需要 mock（PR3 阶段先验证骨架，
真实 LLM 调用留到 PR 3 末尾的 smoke test）。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REVISE_SCRIPT = Path(__file__).resolve().parent.parent / "revise_chapter.py"


SAMPLE_CHAPTER = """# 第5章 玄之归来

## §1 开场

陈默站在论剑台上，夜风把他的衣角吹得猎猎作响。

## §2 战斗

## §3 玄之回场

王玄之从台下跃起，长剑出鞘。

## §4 对话

"好久不见。"玄之说。

## §5 结尾

陈默微笑。

"""


CONTRACT_JSON = {
    "chapter": 5,
    "issues": [
        {
            "severity": "critical",
            "category": "continuity",
            "location": "§2",
            "description": "战斗段空",
            "fix_hint": "补 200 字战斗描写",
            "blocking": True,
        },
        {
            "severity": "high",
            "category": "character",
            "location": "§4",
            "description": "对白与角色库矛盾",
            "fix_hint": "改成粗犷口语",
            "blocking": False,
        },
    ],
}


def run_revise(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REVISE_SCRIPT), *args],
        capture_output=True, text=True,
    )


def test_revise_dry_run_outputs_target_sections(tmp_path: Path):
    """--dry-run：不调 LLM，只输出 targets_text + 受影响段落预览。"""
    chapter_file = tmp_path / "ch0005.md"
    chapter_file.write_text(SAMPLE_CHAPTER, encoding="utf-8")
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(json.dumps(CONTRACT_JSON), encoding="utf-8")

    result = run_revise(
        "--chapter-file", str(chapter_file),
        "--contract", str(contract_file),
        "--dry-run",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    out = json.loads(result.stdout)
    assert out["dry_run"] is True
    assert "§2" in out["target_sections"]
    assert "§4" in out["target_sections"]
    assert "补 200 字战斗描写" in out["targets_text"]


def test_revise_rejects_missing_chapter_file(tmp_path: Path):
    """章节文件不存在 → exit 2。"""
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(json.dumps(CONTRACT_JSON), encoding="utf-8")
    result = run_revise(
        "--chapter-file", str(tmp_path / "missing.md"),
        "--contract", str(contract_file),
        "--dry-run",
    )
    assert result.returncode == 2


def test_revise_rejects_invalid_contract(tmp_path: Path):
    """contract 缺 location → exit 1。"""
    chapter_file = tmp_path / "ch0005.md"
    chapter_file.write_text(SAMPLE_CHAPTER, encoding="utf-8")
    bad_contract = {
        "chapter": 5,
        "issues": [
            {
                "severity": "high",
                "category": "continuity",
                "location": "",  # 非法
                "description": "x",
                "fix_hint": "y",
                "blocking": True,
            }
        ],
    }
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(json.dumps(bad_contract), encoding="utf-8")
    result = run_revise(
        "--chapter-file", str(chapter_file),
        "--contract", str(contract_file),
        "--dry-run",
    )
    assert result.returncode == 1
    assert "location" in result.stderr


def test_extract_section_returns_correct_span():
    """extract_section('§2', chapter_text) → 返回 ## §2 段到下一个 ## 之前。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    from revise_chapter import extract_section
    text = SAMPLE_CHAPTER
    sec = extract_section(text, "§2")
    assert "## §2" in sec
    assert "## §3" not in sec
    # §4 段
    sec4 = extract_section(text, "§4")
    assert "好久不见" in sec4
    assert "## §5" not in sec4


def test_revise_plan_returns_per_section_actions():
    """build_revise_plan() 返回 {section: 原内容} 的字典，给 LLM 喂。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    from revise_chapter import build_revise_plan
    from rejection_contract import build_contract_from_reviewer_output

    contract = build_contract_from_reviewer_output(CONTRACT_JSON, include_advisory=True)
    plan = build_revise_plan(SAMPLE_CHAPTER, contract)
    assert "§2" in plan
    assert "§4" in plan
    assert "§1" not in plan  # 不在 contract 里就不动
    assert "## §2" in plan["§2"]


def test_apply_revised_sections_replaces_only_marked_sections():
    """apply_revised_sections(orig, {"§2": new, "§4": new4}) → 只替换 §2 和 §4，其他原样。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    from revise_chapter import apply_revised_sections
    new_text = apply_revised_sections(
        SAMPLE_CHAPTER,
        {
            "§2": "## §2 战斗（新写）\n\n陈默拔剑迎敌。\n",
            "§4": "## §4 对话（新写）\n\n\"嘿！你小子！\"玄之大喊。\n",
        },
    )
    # §1 §3 §5 应原样
    assert "陈默站在论剑台上" in new_text
    assert "王玄之从台下跃起" in new_text
    assert "陈默微笑" in new_text
    # §2 §4 替换
    assert "陈默拔剑迎敌" in new_text
    assert '"嘿！你小子！"' in new_text
    # 旧内容消失
    assert '"好久不见。"玄之说' not in new_text


def test_call_llm_for_revision_uses_anthropic_messages_api(monkeypatch):
    """call_llm_for_revision 必须调 anthropic SDK（mock 验证 prompt 字段）。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    import revise_chapter

    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            class FakeResp:
                content = [type("Block", (), {"text": "## §2（新文）"})()]
            return FakeResp()

    class FakeAnthropic:
        def __init__(self, *a, **kw):
            pass
        @property
        def messages(self):
            return FakeMessages()

    monkeypatch.setattr(revise_chapter, "anthropic", type("X", (), {"Anthropic": FakeAnthropic})())

    result = revise_chapter.call_llm_for_revision(
        section_id="§2",
        original="原文内容",
        instruction="补 200 字战斗",
        model="claude-sonnet-4-5",
    )
    assert "新文" in result
    kw = captured["kwargs"]
    assert kw["model"] == "claude-sonnet-4-5"
    # 必须包含原内容 + 修复指令 + 段 ID
    user_msg = kw["messages"][0]["content"]
    assert "原文内容" in user_msg
    assert "补 200 字战斗" in user_msg
    assert "§2" in user_msg


def test_call_llm_for_revision_keeps_section_heading():
    """LLM 输出必须保留 ## §N 标题（否则 apply_revised_sections 无法定位）。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    import revise_chapter

    class FakeMessages:
        def create(self, **kwargs):
            class FakeResp:
                content = [type("Block", (), {"text": "## §3（新文）\n\n正文"})()]
            return FakeResp()

    class FakeAnthropic:
        def __init__(self, *a, **kw): pass
        @property
        def messages(self): return FakeMessages()

    import importlib
    revise_chapter.anthropic = type("X", (), {"Anthropic": FakeAnthropic})
    result = revise_chapter.call_llm_for_revision("§3", "x", "y", "claude-sonnet-4-5")
    assert result.startswith("## §3") or "## §3" in result.split("\n", 1)[0]
