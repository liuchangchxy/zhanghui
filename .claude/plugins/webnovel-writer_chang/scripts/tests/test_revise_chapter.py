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
    """--dry-run：不调 LLM，只输出 targets_text + 受影响段落预览。

    默认 include_advisory=False：blocking=False 的 §4 不在 target_sections 里。
    """
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
    # §2 是 blocking=True → 出现
    assert "§2" in out["target_sections"]
    # §4 是 blocking=False（advisory）→ 默认排除
    assert "§4" not in out["target_sections"]
    assert "补 200 字战斗描写" in out["targets_text"]


def test_revise_dry_run_with_include_advisory_includes_advisory(tmp_path: Path):
    """--include-advisory：advisory issue 也进入 target_sections。"""
    chapter_file = tmp_path / "ch0005.md"
    chapter_file.write_text(SAMPLE_CHAPTER, encoding="utf-8")
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(json.dumps(CONTRACT_JSON), encoding="utf-8")

    result = run_revise(
        "--chapter-file", str(chapter_file),
        "--contract", str(contract_file),
        "--dry-run",
        "--include-advisory",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    out = json.loads(result.stdout)
    assert "§2" in out["target_sections"]
    assert "§4" in out["target_sections"]


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


def test_apply_revised_sections_preserves_backslashes_in_replacement():
    """C4: replacement 里的反斜杠序列（\n \t \1）不应被 re.sub 展开为转义字符。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    from revise_chapter import apply_revised_sections
    # 原文 + 替换内容里都含反斜杠（如 Windows 路径）
    original = (
        "# 第1章\n\n"
        "## §1 开场\n\n"
        "路径 C:\\temp\\new 文件。\n\n"
        "## §2 战斗\n\n"
        "打了一架。\n"
    )
    new_content = (
        "## §1 开场（新文）\n\n"
        "路径 C:\\temp\\new 文件（保留反斜杠）。\n\n"
    )
    out = apply_revised_sections(original, {"§1": new_content})
    # 反斜杠必须保留（不能被 re.sub 当成 \n 转成换行）
    assert "C:\\temp\\new" in out, f"反斜杠被吞了: {out!r}"
    # 不应出现意外换行（替换内容只有一个 \n\n）
    assert out.count("## §1 开场（新文）") == 1


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
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    result = revise_chapter.call_llm_for_revision(
        section_id="§2",
        original="原文内容",
        instruction="补 200 字战斗",
        model="claude-sonnet-4-5",
    )
    assert "新文" in result
    kw = captured["kwargs"]
    assert kw["model"] == "claude-sonnet-4-5"
    assert kw["max_tokens"] == 8192
    # 必须包含原内容 + 修复指令 + 段 ID
    user_msg = kw["messages"][0]["content"]
    assert "原文内容" in user_msg
    assert "补 200 字战斗" in user_msg
    assert "§2" in user_msg


# === C7: 缺 ANTHROPIC_API_KEY → RuntimeError ===
def test_call_llm_for_revision_raises_without_api_key(monkeypatch):
    """ANTHROPIC_API_KEY 未设置或为空 → RuntimeError，不静默用 SDK 默认凭据。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    import revise_chapter

    class FakeAnthropic:
        def __init__(self, *a, **kw): pass
        @property
        def messages(self): return None

    monkeypatch.setattr(revise_chapter, "anthropic",
                        type("X", (), {"Anthropic": FakeAnthropic})())
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        revise_chapter.call_llm_for_revision("§2", "x", "y", "claude-sonnet-4-5")

    # 空字符串也应视为未设置
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  ")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        revise_chapter.call_llm_for_revision("§2", "x", "y", "claude-sonnet-4-5")


# === C6: 空 / 拒绝 / 截断 → RuntimeError，不静默吞掉 ===
def test_call_llm_for_revision_raises_on_empty_response(monkeypatch):
    """LLM 返回空内容 → RuntimeError（不静默替换为原文）。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    import revise_chapter

    class FakeMessages:
        def create(self, **kwargs):
            class FakeResp:
                content = []  # 空
                stop_reason = "end_turn"
            return FakeResp()

    class FakeAnthropic:
        def __init__(self, *a, **kw): pass
        @property
        def messages(self): return FakeMessages()

    monkeypatch.setattr(revise_chapter, "anthropic",
                        type("X", (), {"Anthropic": FakeAnthropic})())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    with pytest.raises(RuntimeError, match="空"):
        revise_chapter.call_llm_for_revision("§2", "x", "y", "claude-sonnet-4-5")


def test_call_llm_for_revision_raises_on_refusal(monkeypatch):
    """stop_reason=refusal → RuntimeError。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    import revise_chapter

    class FakeMessages:
        def create(self, **kwargs):
            class FakeResp:
                content = [type("B", (), {"text": ""})()]
                stop_reason = "refusal"
            return FakeResp()

    class FakeAnthropic:
        def __init__(self, *a, **kw): pass
        @property
        def messages(self): return FakeMessages()

    monkeypatch.setattr(revise_chapter, "anthropic",
                        type("X", (), {"Anthropic": FakeAnthropic})())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    with pytest.raises(RuntimeError, match="refusal"):
        revise_chapter.call_llm_for_revision("§2", "x", "y", "claude-sonnet-4-5")


def test_call_llm_for_revision_raises_on_max_tokens(monkeypatch):
    """stop_reason=max_tokens → RuntimeError（截断视为失败）。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    import revise_chapter

    class FakeMessages:
        def create(self, **kwargs):
            class FakeResp:
                content = [type("B", (), {"text": "## §2 残..."})()]
                stop_reason = "max_tokens"
            return FakeResp()

    class FakeAnthropic:
        def __init__(self, *a, **kw): pass
        @property
        def messages(self): return FakeMessages()

    monkeypatch.setattr(revise_chapter, "anthropic",
                        type("X", (), {"Anthropic": FakeAnthropic})())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    with pytest.raises(RuntimeError, match="max_tokens"):
        revise_chapter.call_llm_for_revision("§2", "x", "y", "claude-sonnet-4-5")


def test_call_llm_for_revision_raises_on_missing_heading(monkeypatch):
    """LLM 返回不含 ## §N 标题的内容 → RuntimeError（无法替换）。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    import revise_chapter

    class FakeMessages:
        def create(self, **kwargs):
            class FakeResp:
                content = [type("B", (), {"text": "我只是文本，没有标题"})()]
                stop_reason = "end_turn"
            return FakeResp()

    class FakeAnthropic:
        def __init__(self, *a, **kw): pass
        @property
        def messages(self): return FakeMessages()

    monkeypatch.setattr(revise_chapter, "anthropic",
                        type("X", (), {"Anthropic": FakeAnthropic})())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    with pytest.raises(RuntimeError, match="标题"):
        revise_chapter.call_llm_for_revision("§2", "x", "y", "claude-sonnet-4-5")


def test_call_llm_for_revision_keeps_section_heading(monkeypatch):
    """LLM 输出必须保留 ## §N 标题（否则 apply_revised_sections 无法定位）。

    用 monkeypatch.setattr 替代裸赋值，monkeypatch 会自动还原。
    """
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

    monkeypatch.setattr(revise_chapter, "anthropic",
                        type("X", (), {"Anthropic": FakeAnthropic})())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    result = revise_chapter.call_llm_for_revision("§3", "x", "y", "claude-sonnet-4-5")
    assert result.startswith("## §3") or "## §3" in result.split("\n", 1)[0]


# === C5: 一个 section 多个 issue → 一次 LLM 调用 ===
def test_main_makes_one_llm_call_per_section_with_multiple_issues(tmp_path: Path, monkeypatch):
    """contract 里同一段有 2+ issue → main() 只调一次 LLM（不是每个 issue 各调一次）。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    import revise_chapter

    chapter = tmp_path / "ch0005.md"
    chapter.write_text(SAMPLE_CHAPTER, encoding="utf-8")

    # 同一段 §2 有 2 条 issue + §4 有 1 条 → 期望只调 2 次 LLM
    contract_data = {
        "chapter": 5,
        "issues": [
            {
                "severity": "critical",
                "category": "continuity",
                "location": "§2",
                "description": "战斗段空",
                "fix_hint": "补 200 字战斗",
                "blocking": True,
            },
            {
                "severity": "high",
                "category": "pacing",
                "location": "§2",
                "description": "节奏拖",
                "fix_hint": "加快节奏",
                "blocking": True,
            },
            {
                "severity": "high",
                "category": "character",
                "location": "§4",
                "description": "腔调错",
                "fix_hint": "改口语",
                "blocking": False,
            },
        ],
    }
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(json.dumps(contract_data), encoding="utf-8")

    calls: list[dict] = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            sec_id = "未知"
            for line in kwargs["messages"][0]["content"].split("\n"):
                if "待重写段" in line:
                    sec_id = line.split(":")[1].strip()
                    break
            return type("R", (), {
                "content": [type("B", (), {"text": f"## {sec_id} 新文"})()],
            })()

    class FakeAnthropic:
        def __init__(self, *a, **kw): pass
        @property
        def messages(self): return FakeMessages()

    monkeypatch.setattr(revise_chapter, "anthropic",
                        type("X", (), {"Anthropic": FakeAnthropic})())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    # I6: include_advisory 默认 False —— §4 是 advisory 不该被重写
    rc = revise_chapter.main([
        "--chapter-file", str(chapter),
        "--contract", str(contract_file),
        "--include-advisory",  # 显式开 advisory 才能让 §4 也被改
        "--output", str(tmp_path / "out.md"),
    ])
    assert rc == 0, f"stderr / output"
    # §2 有 2 issue → 1 次；§4 有 1 issue → 1 次
    assert len(calls) == 2, f"应为 2 次 LLM 调用，实际 {len(calls)}"

    # 那次调用的指令里必须含两条 fix_hint（合并而非丢弃）
    sec2_call = next(c for c in calls if "补 200 字战斗" in c["messages"][0]["content"])
    instr = sec2_call["messages"][0]["content"]
    assert "加快节奏" in instr, "§2 的第二条 fix_hint 应被合并进同一次调用的指令"


# === I5: location 范围与中文紧跟标题 ===
def test_extract_section_handles_chinese_after_section_id():
    """C5/I5: '## §2冲突'（紧跟中文，无空格）也能被提取。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    from revise_chapter import extract_section

    text = (
        "# 第1章\n\n"
        "## §1开场\n\n"
        "开场。\n\n"
        "## §2冲突\n\n"
        "冲突发生。\n\n"
        "## §3结尾\n\n"
        "收尾。\n"
    )
    sec = extract_section(text, "§2")
    assert "## §2冲突" in sec, f"未匹配中文紧跟的标题: {sec!r}"
    assert "冲突发生" in sec
    assert "## §3" not in sec


def test_build_revise_plan_expands_range():
    """I5: '§2-§5' 应展开为 §2/§3/§4/§5 四个段。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    from revise_chapter import build_revise_plan, _expand_section_id
    from rejection_contract import IssueRef, RejectionContract, Severity

    # 范围
    assert _expand_section_id("§2-§5") == ["§2", "§3", "§4", "§5"]
    # 反向范围（容错）
    assert _expand_section_id("§5-§2") == ["§2", "§3", "§4", "§5"]
    # 单个
    assert _expand_section_id("§3") == ["§3"]
    # 带说明
    assert _expand_section_id("§2-§5 第2-5段") == ["§2", "§3", "§4", "§5"]
    # 非 § 开头
    assert _expand_section_id("第3段") == []

    text = SAMPLE_CHAPTER
    contract = RejectionContract(chapter=5, issues=[
        IssueRef(Severity.CRITICAL, "continuity", "§2-§5", "范围问题", "重写范围", True),
    ])
    plan = build_revise_plan(text, contract)
    assert set(plan.keys()) == {"§2", "§3", "§4", "§5"}
    # 每个 plan 段的 ## 标题必须出现
    assert "## §2" in plan["§2"]
    assert "## §5" in plan["§5"]


def test_main_exits_invalid_when_no_sections_resolved(tmp_path: Path):
    """I5: contract 有 issue 但全部 location 都是非 §N 格式 → 退出 EXIT_INVALID=1。"""
    chapter_file = tmp_path / "ch0005.md"
    chapter_file.write_text(SAMPLE_CHAPTER, encoding="utf-8")
    contract_data = {
        "chapter": 5,
        "issues": [
            {
                "severity": "high",
                "category": "character",
                "location": "第3段",  # 非 §N 格式
                "description": "x",
                "fix_hint": "y",
                "blocking": True,
            },
        ],
    }
    contract_file = tmp_path / "contract.json"
    contract_file.write_text(json.dumps(contract_data), encoding="utf-8")

    result = run_revise(
        "--chapter-file", str(chapter_file),
        "--contract", str(contract_file),
        "--dry-run",
    )
    # dry_run 模式：有 issue 但没段解析出来 → EXIT_INVALID
    assert result.returncode == 1
    assert "没有" in result.stderr or "解析" in result.stderr


def test_apply_revised_sections_handles_chinese_after_section_id():
    """I5: '## §2冲突'（紧跟中文）也能被 apply_revised_sections 替换。"""
    sys.path.insert(0, str(REVISE_SCRIPT.parent))
    from revise_chapter import apply_revised_sections

    original = (
        "# 第1章\n\n"
        "## §1开场\n\n"
        "开场。\n\n"
        "## §2冲突\n\n"
        "旧冲突。\n\n"
        "## §3结尾\n\n"
        "收尾。\n"
    )
    new = "## §2冲突（新文）\n\n新冲突。\n"
    out = apply_revised_sections(original, {"§2": new})
    assert "新冲突" in out
    assert "旧冲突" not in out
    # §1 / §3 原样
    assert "开场" in out
    assert "收尾" in out
