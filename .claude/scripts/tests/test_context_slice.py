"""context_slice.py 单元测试。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from context_slice import (
    ContextSlice,
    SLICES,
    read_slice,
    estimate_tokens,
    list_slices,
)


def test_writer_slice_has_minimal_white_list():
    """writer_slice 必须只包含：章纲 + 角色卡 + 前 2 章摘要 + 当前章大纲相关设定。"""
    s = SLICES["writer"]
    patterns = [e.pattern for e in s.entries]
    # 必须有：当前章大纲
    assert any("大纲/第1卷-详细大纲.md" in p or "第1卷-详细大纲.md" in p for p in patterns)
    # 必须有：角色库
    assert any("设定集/角色库/" in p for p in patterns)
    # 必须有：前 N 章摘要（用 glob）
    assert any("summaries" in p.lower() for p in patterns)
    # 不应包含：所有章的正文（除非是当前章）
    assert not any("正文/" in p and "*" in p for p in patterns)


def test_reviewer_slice_focuses_on_local_context():
    """reviewer_slice 主要喂：当前章正文 + 周围 2 章正文 + 爽点规划 + 设定卡（仅相关）。"""
    s = SLICES["reviewer"]
    patterns = [e.pattern for e in s.entries]
    # 应包含当前章正文（chapter 号来自参数，不在 schema 里硬编码）
    assert any("正文/第{NNNN}章" in p for p in patterns)
    # 应包含前后 ±2 章
    assert any("±2" in p or "前后" in repr(s.entries) for p in [repr(s)])


def test_polisher_slice_minimal():
    """polisher_slice 只喂：当前章正文 + 文风规则 + 白名单。"""
    s = SLICES["polisher"]
    patterns = [e.pattern for e in s.entries]
    assert any("正文/第{NNNN}章" in p for p in patterns)
    assert any("deslop" in p.lower() or "白名单" in repr(s) for p in [repr(s)])
    # 不应包含：完整大纲
    assert not any("总纲" in p for p in patterns)


def test_list_slices_returns_known_names():
    """list_slices() 返回所有内置 slice 名。"""
    names = list_slices()
    assert "writer" in names
    assert "reviewer" in names
    assert "polisher" in names


def test_read_slice_concatenates_matched_files(tmp_path: Path):
    """read_slice(project_root, 'writer', chapter=5) → 返回拼接的 {path: content}。"""
    # 准备最小项目
    (tmp_path / "设定集" / "角色库").mkdir(parents=True)
    (tmp_path / "设定集" / "角色库" / "陈默.md").write_text("陈默，21岁", encoding="utf-8")
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "第1卷-详细大纲.md").write_text("# 第1卷\nch5: 玄之归来", encoding="utf-8")
    (tmp_path / ".webnovel" / "summaries").mkdir(parents=True)
    (tmp_path / ".webnovel" / "summaries" / "ch0003.md").write_text("ch3 摘要", encoding="utf-8")
    (tmp_path / ".webnovel" / "summaries" / "ch0004.md").write_text("ch4 摘要", encoding="utf-8")
    (tmp_path / ".webnovel" / "summaries" / "ch0005.md").write_text("ch5 摘要（应被排除）", encoding="utf-8")

    result = read_slice(tmp_path, "writer", chapter=5)
    paths = {p for p in result.keys()}
    # 角色 + 大纲 + 前 2 章摘要
    assert "设定集/角色库/陈默.md" in paths
    assert "大纲/第1卷-详细大纲.md" in paths
    assert ".webnovel/summaries/ch0003.md" in paths
    assert ".webnovel/summaries/ch0004.md" in paths
    # 当前章摘要应被排除（要写的是它本身，不是回顾它）
    assert ".webnovel/summaries/ch0005.md" not in paths


def test_read_slice_skips_missing_files(tmp_path: Path):
    """白名单匹配但文件不存在 → 静默跳过，不报错。"""
    (tmp_path / "设定集" / "角色库").mkdir(parents=True)
    # 没有陈默.md
    (tmp_path / "大纲").mkdir()
    (tmp_path / "大纲" / "第1卷-详细大纲.md").write_text("x", encoding="utf-8")

    result = read_slice(tmp_path, "writer", chapter=1)
    # 不抛错，返回的 dict 不含缺失文件
    assert "大纲/第1卷-详细大纲.md" in result


def test_estimate_tokens_rough_chinese():
    """estimate_tokens: 中文 1 字 ≈ 1.5 token；英文 1 word ≈ 1.3 token。"""
    assert 6 <= estimate_tokens("你好世界") <= 10  # 4 字 × 1.5 = 6
    assert 3 <= estimate_tokens("hello") <= 6
