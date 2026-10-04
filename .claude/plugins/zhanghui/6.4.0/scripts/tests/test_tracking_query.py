"""tracking_query.py 的 pytest 覆盖。

覆盖目标：
- load_foreshadow_index：空 / 单条 / 多条 / 字段别名兼容
- compute_active_foreshadow：排序键（importance → target_chapter → id）、top_k 上限
- compute_overdue_foreshadow：阈值边界、resolved 跳过、target 超期判定
- format_active_foreshadow_md：空、非空、表格渲染
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

import tracking_query
from tracking_query import (
    DEFAULT_ACTIVE_TOP_K,
    DEFAULT_OVERDUE_THRESHOLD,
    compute_active_foreshadow,
    compute_overdue_foreshadow,
    format_active_foreshadow_md,
    format_overdue_foreshadow_md,
    load_foreshadow_index,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def make_state(tmp_path: Path):
    """工厂：写入一份自定义 state.json，返回 path。"""

    def _make(payload: Dict[str, Any]) -> Path:
        p = tmp_path / "state.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return p

    return _make


@pytest.fixture
def base_state() -> Dict[str, Any]:
    """最小可用的 state.json 骨架。"""
    return {
        "progress": {"current_chapter": 5},
        "plot_threads": {
            "foreshadowing": [],
        },
    }


# ---------------------------------------------------------------------------
# load_foreshadow_index
# ---------------------------------------------------------------------------

def test_load_returns_empty_when_state_missing(tmp_path: Path):
    """state.json 不存在 → 空 dict。"""
    assert load_foreshadow_index(tmp_path / "nope.json") == {}


def test_load_returns_empty_for_empty_foreshadowing(make_state, base_state):
    """plot_threads.foreshadowing 为空 → 空 dict。"""
    p = make_state(base_state)
    assert load_foreshadow_index(p) == {}


def test_load_single_foreshadow(make_state, base_state):
    """单条伏笔：所有字段正确归一化。"""
    base_state["plot_threads"]["foreshadowing"] = [{
        "id": "F-001",
        "content": "三年之约",
        "planted_chapter": 1,
        "target_chapter": 10,
        "status": "active",
        "tier": "核心",
    }]
    p = make_state(base_state)
    rows = load_foreshadow_index(p)
    assert "F-001" in rows
    row = rows["F-001"]
    assert row["content"] == "三年之约"
    assert row["tier"] == "核心"
    assert row["weight"] == 3.0
    assert row["is_resolved"] is False
    assert row["planted_chapter"] == 1
    assert row["target_chapter"] == 10


def test_load_field_aliases(make_state, base_state):
    """兼容历史字段：added_chapter / due_chapter / 中文状态 '已埋'。"""
    base_state["plot_threads"]["foreshadowing"] = [{
        "content": "药老身份",
        "added_chapter": 2,        # alias for planted_chapter
        "due_chapter": 20,         # alias for target_chapter
        "status": "已埋",          # 中文同义词
        "tier": "支线",
    }]
    p = make_state(base_state)
    rows = load_foreshadow_index(p)
    assert len(rows) == 1
    row = next(iter(rows.values()))
    assert row["planted_chapter"] == 2
    assert row["target_chapter"] == 20
    assert row["tier"] == "支线"
    assert row["weight"] == 2.0
    assert row["is_resolved"] is False


def test_load_resolved_filter_via_is_resolved(make_state, base_state):
    """is_resolved 字段正确反映 'resolved' / '已回收'。"""
    base_state["plot_threads"]["foreshadowing"] = [
        {"id": "A", "content": "a", "planted_chapter": 1, "status": "resolved"},
        {"id": "B", "content": "b", "planted_chapter": 1, "status": "已回收"},
        {"id": "C", "content": "c", "planted_chapter": 1, "status": "active"},
    ]
    p = make_state(base_state)
    rows = load_foreshadow_index(p)
    assert rows["A"]["is_resolved"] is True
    assert rows["B"]["is_resolved"] is True
    assert rows["C"]["is_resolved"] is False


# ---------------------------------------------------------------------------
# compute_active_foreshadow（排序 / top_k / 排除已回收）
# ---------------------------------------------------------------------------

def _seed_multi(make_state, base_state, items):
    base_state["plot_threads"]["foreshadowing"] = items
    return make_state(base_state)


def test_active_returns_empty_when_no_rows(make_state, base_state):
    p = _seed_multi(make_state, base_state, [])
    assert compute_active_foreshadow(p, current_chapter=5) == []


def test_active_sorts_by_importance_then_target_then_id(make_state, base_state):
    """排序键：核心(3) > 支线(2) > 装饰(1)；同 tier 按 target_chapter 升序。"""
    items = [
        {"id": "decor-1", "content": "装饰A", "planted_chapter": 1, "target_chapter": 5, "status": "active", "tier": "装饰"},
        {"id": "core-1",  "content": "核心A", "planted_chapter": 1, "target_chapter": 30, "status": "active", "tier": "核心"},
        {"id": "sub-1",   "content": "支线A", "planted_chapter": 1, "target_chapter": 8,  "status": "active", "tier": "支线"},
        {"id": "core-2",  "content": "核心B", "planted_chapter": 1, "target_chapter": 5,  "status": "active", "tier": "核心"},
    ]
    p = _seed_multi(make_state, base_state, items)
    rows = compute_active_foreshadow(p, current_chapter=10, top_k=8)
    ids = [r["id"] for r in rows]
    # 期望顺序：核心(2条 target 小的在前) > 支线 > 装饰
    assert ids == ["core-2", "core-1", "sub-1", "decor-1"]


def test_active_excludes_resolved(make_state, base_state):
    items = [
        {"id": "live",    "content": "活",  "planted_chapter": 1, "target_chapter": 5, "status": "active"},
        {"id": "gone",    "content": "死",  "planted_chapter": 1, "target_chapter": 5, "status": "resolved"},
        {"id": "gone-cn", "content": "死2", "planted_chapter": 1, "target_chapter": 5, "status": "已回收"},
    ]
    p = _seed_multi(make_state, base_state, items)
    rows = compute_active_foreshadow(p, current_chapter=10)
    assert [r["id"] for r in rows] == ["live"]


def test_active_top_k_caps_output(make_state, base_state):
    items = [
        {"id": f"id-{i}", "content": f"c-{i}", "planted_chapter": 1,
         "target_chapter": i, "status": "active", "tier": "支线"}
        for i in range(1, 11)  # 10 条
    ]
    p = _seed_multi(make_state, base_state, items)
    rows = compute_active_foreshadow(p, current_chapter=5, top_k=3)
    assert len(rows) == 3
    # top_k=3 应取 target_chapter 最小（最紧）的三条
    assert [r["target_chapter"] for r in rows] == [1, 2, 3]


def test_active_default_top_k_is_eight(make_state, base_state):
    """默认 top_k = 8（oh-story 算法规格）。"""
    items = [
        {"id": f"id-{i:02d}", "content": f"c-{i}", "planted_chapter": 1,
         "target_chapter": i, "status": "active"}
        for i in range(1, 12)  # 11 条
    ]
    p = _seed_multi(make_state, base_state, items)
    rows = compute_active_foreshadow(p, current_chapter=5)  # 用默认 top_k
    assert len(rows) == DEFAULT_ACTIVE_TOP_K == 8


def test_active_handles_missing_target_chapter(make_state, base_state):
    """target_chapter 缺失时排在最后（+∞）。"""
    items = [
        {"id": "no-target", "content": "x", "planted_chapter": 1,
         "status": "active", "tier": "核心"},  # 缺 target
        {"id": "with-target", "content": "y", "planted_chapter": 1,
         "target_chapter": 5, "status": "active", "tier": "核心"},
    ]
    p = _seed_multi(make_state, base_state, items)
    rows = compute_active_foreshadow(p, current_chapter=10)
    assert [r["id"] for r in rows] == ["with-target", "no-target"]


# ---------------------------------------------------------------------------
# compute_overdue_foreshadow
# ---------------------------------------------------------------------------

def test_overdue_threshold_boundary(make_state, base_state):
    """阈值边界：elapsed == threshold 时算 overdue；< threshold 不算。"""
    items = [
        {"id": "edge",  "content": "刚好 20 章", "planted_chapter": 5, "status": "active"},
        {"id": "under", "content": "只埋 19 章", "planted_chapter": 6, "status": "active"},
    ]
    p = _seed_multi(make_state, base_state, items)
    overdue = compute_overdue_foreshadow(p, current_chapter=25, threshold=20)
    # edge: 25 - 5 = 20 >= 20 → overdue
    # under: 25 - 6 = 19 <  20 → skip
    assert [r["id"] for r in overdue] == ["edge"]


def test_overdue_excludes_resolved(make_state, base_state):
    items = [
        {"id": "live-long", "content": "活但长", "planted_chapter": 1, "status": "active"},
        {"id": "dead-long", "content": "回收但长", "planted_chapter": 1, "status": "resolved"},
    ]
    p = _seed_multi(make_state, base_state, items)
    overdue = compute_overdue_foreshadow(p, current_chapter=100, threshold=20)
    assert [r["id"] for r in overdue] == ["live-long"]


def test_overdue_marks_target_overtime(make_state, base_state):
    """target_chapter < current_chapter → overdue_kind='已超期'。"""
    items = [
        {"id": "target-passed", "content": "过期目标", "planted_chapter": 1,
         "target_chapter": 10, "status": "active"},
        {"id": "no-target",     "content": "没目标",   "planted_chapter": 1,
         "status": "active"},
    ]
    p = _seed_multi(make_state, base_state, items)
    overdue = compute_overdue_foreshadow(p, current_chapter=50, threshold=20)
    kinds = {r["id"]: r["overdue_kind"] for r in overdue}
    assert kinds["target-passed"] == "已超期"
    assert kinds["no-target"] == "埋太久未填"


def test_overdue_sorts_overtime_first_then_longest_elapsed(make_state, base_state):
    items = [
        {"id": "kind-1", "content": "a", "planted_chapter": 30, "status": "active"},  # elapsed 20, no target
        {"id": "kind-2", "content": "b", "planted_chapter": 1,  "target_chapter": 10, "status": "active"},  # elapsed 49, overtime
        {"id": "kind-3", "content": "c", "planted_chapter": 25, "status": "active"},  # elapsed 25, no target
    ]
    p = _seed_multi(make_state, base_state, items)
    overdue = compute_overdue_foreshadow(p, current_chapter=50, threshold=20)
    # 已超期应排前面；同内按 elapsed 倒序
    assert [r["id"] for r in overdue] == ["kind-2", "kind-3", "kind-1"]


def test_overdue_default_threshold_is_twenty(make_state, base_state):
    """默认阈值 20（任务规格）。"""
    items = [
        {"id": "edge",  "content": "刚 20 章", "planted_chapter": 5, "status": "active"},
    ]
    p = _seed_multi(make_state, base_state, items)
    # 默认阈值 20：current=25, planted=5 → elapsed=20 → 触发
    overdue = compute_overdue_foreshadow(p, current_chapter=25)
    assert [r["id"] for r in overdue] == ["edge"]
    assert DEFAULT_OVERDUE_THRESHOLD == 20


# ---------------------------------------------------------------------------
# format_active_foreshadow_md / format_overdue_foreshadow_md
# ---------------------------------------------------------------------------

def test_format_active_md_empty():
    md = format_active_foreshadow_md([])
    assert "无" in md or "（无）" in md


def test_format_active_md_contains_table(make_state, base_state):
    items = [
        {"id": "F-1", "content": "三年之约", "planted_chapter": 1,
         "target_chapter": 10, "status": "active", "tier": "核心"},
    ]
    p = _seed_multi(make_state, base_state, items)
    rows = compute_active_foreshadow(p, current_chapter=5)
    md = format_active_foreshadow_md(rows)
    assert "## 活跃伏笔" in md
    assert "| # |" in md  # 表格头
    assert "核心" in md
    assert "三年之约" in md
    assert "第1章" not in md  # active_md 不会用 "第N章" 格式


def test_format_overdue_md_contains_kind(make_state, base_state):
    items = [
        {"id": "F-1", "content": "过期目标", "planted_chapter": 1,
         "target_chapter": 5, "status": "active"},
    ]
    p = _seed_multi(make_state, base_state, items)
    rows = compute_overdue_foreshadow(p, current_chapter=30, threshold=20)
    md = format_overdue_foreshadow_md(rows)
    assert "## 超期伏笔" in md
    assert "已超期" in md or "埋太久未填" in md
    assert "过期目标" in md


def test_format_overdue_md_empty():
    md = format_overdue_foreshadow_md([])
    assert "（无）" in md


# ---------------------------------------------------------------------------
# H-R4-1: state.json DoS 防护（> MAX_STATE_BYTES 必须被拒绝）
# ---------------------------------------------------------------------------

def test_load_rejects_oversized_state(tmp_path: Path, capsys):
    """H-R4-1: state.json > MAX_STATE_BYTES → 静默返回空 + stderr warning。"""
    from tracking_query import MAX_STATE_BYTES
    big = tmp_path / "state.json"
    # 写超过 MAX_STATE_BYTES + 1 字节的内容
    big.write_bytes(b'{"plot_threads":{"foreshadowing":[' + b' ' * (MAX_STATE_BYTES) + b']}}')
    assert big.stat().st_size > MAX_STATE_BYTES
    rows = load_foreshadow_index(big)
    assert rows == {}
    # stderr 应有 WARNING 字样
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "超过上限" in err


def test_load_rejects_50mb_state(tmp_path: Path, capsys):
    """H-R4-1: 真实对抗场景——50MB state.json 必须被拒绝。"""
    big = tmp_path / "state.json"
    # 写一个稀疏但超大的 JSON：键占空间，无实际伏笔
    payload = b'{"a":"' + b'x' * (50 * 1024 * 1024) + b'"}'
    big.write_bytes(payload)
    assert big.stat().st_size > 50 * 1024 * 1024
    rows = load_foreshadow_index(big)
    assert rows == {}
    err = capsys.readouterr().err
    assert "WARNING" in err


# ---------------------------------------------------------------------------
# H-R4-2: _resolve_int 与上游 to_positive_int 行为对齐
# ---------------------------------------------------------------------------

def test_resolve_int_handles_pure_int():
    """普通 int 应该解析。"""
    from tracking_query import _resolve_int
    assert _resolve_int({"x": 5}, ["x"]) == 5


def test_resolve_int_handles_float():
    """5.0 应该解析为 5（H-R4-2 parity）。"""
    from tracking_query import _resolve_int
    assert _resolve_int({"x": 5.0}, ["x"]) == 5


def test_resolve_int_handles_chinese_suffix():
    """'5章' 应该解析（H-R4-2 parity）。"""
    from tracking_query import _resolve_int
    assert _resolve_int({"x": "5章"}, ["x"]) == 5


def test_resolve_int_handles_chinese_prefix_suffix():
    """'第5章' 应该解析（H-R4-2 parity）。"""
    from tracking_query import _resolve_int
    assert _resolve_int({"x": "第5章"}, ["x"]) == 5


def test_resolve_int_handles_full_width_digit():
    """全角数字 '５' 应该解析（H-R4-2 parity）。"""
    from tracking_query import _resolve_int
    assert _resolve_int({"x": "５"}, ["x"]) == 5


def test_resolve_int_handles_full_width_with_chinese():
    """全角数字 '第５章' 应该解析（H-R4-2 parity）。"""
    from tracking_query import _resolve_int
    assert _resolve_int({"x": "第５章"}, ["x"]) == 5


def test_resolve_int_rejects_zero_and_negative():
    """0 / -5 / '0章' 都应被拒绝（> 0 才算有效）。"""
    from tracking_query import _resolve_int
    assert _resolve_int({"x": 0}, ["x"]) is None
    assert _resolve_int({"x": -5}, ["x"]) is None
    assert _resolve_int({"x": "0"}, ["x"]) is None


def test_resolve_int_rejects_bool():
    """True/False 是 int 子类，必须显式拒绝（H-R4-2 parity）。"""
    from tracking_query import _resolve_int
    # bool 是 int 的子类；如果不做 isinstance(v, bool) 拦截，True 会变 1
    assert _resolve_int({"x": True}, ["x"]) is None
    assert _resolve_int({"x": False}, ["x"]) is None


def test_resolve_int_tries_keys_in_order():
    """按候选键顺序取第一个命中（H-R4-2 parity）。"""
    from tracking_query import _resolve_int
    item = {"planted_chapter": 1, "target_chapter": 10}
    # target 键优先时取 10
    assert _resolve_int(item, ["target_chapter", "planted_chapter"]) == 10
    # planted 键优先时取 1
    assert _resolve_int(item, ["planted_chapter", "target_chapter"]) == 1
    # 第一个键不存在则回退
    assert _resolve_int(item, ["missing", "planted_chapter"]) == 1


def test_resolve_int_skips_unparseable():
    """纯中文 / 字母字符串应跳过（H-R4-2 parity）。"""
    from tracking_query import _resolve_int
    assert _resolve_int({"x": "三年之约"}, ["x"]) is None
    assert _resolve_int({"x": "abc"}, ["x"]) is None
    assert _resolve_int({"x": "五章"}, ["x"]) is None  # 中文数字不算（H-R4-2 没扩展到中文数字）


# ---------------------------------------------------------------------------
# M-R4-3: id fallback 使用 hashlib.md5 稳定摘要
# ---------------------------------------------------------------------------

def test_load_id_fallback_is_stable_hash(make_state, base_state):
    """M-R4-3: 同一 content 在多次 load 下应得到同一个 fallback id。"""
    base_state["plot_threads"]["foreshadowing"] = [
        {"content": "三年之约", "planted_chapter": 1, "status": "active"},
    ]
    p = make_state(base_state)
    rows1 = load_foreshadow_index(p)
    rows2 = load_foreshadow_index(p)
    assert list(rows1.keys()) == list(rows2.keys())
    # 应当是 fs:0:<8位hash>
    fid = next(iter(rows1))
    assert fid.startswith("fs:0:")
    assert len(fid.split(":")[-1]) == 8  # 8 hex chars


def test_load_id_fallback_differs_for_different_content(make_state, base_state):
    """M-R4-3: 不同 content 应该 hash 不同。"""
    base_state["plot_threads"]["foreshadowing"] = [
        {"content": "三年之约", "planted_chapter": 1, "status": "active"},
        {"content": "药老身份", "planted_chapter": 1, "status": "active"},
    ]
    p = make_state(base_state)
    rows = load_foreshadow_index(p)
    fids = list(rows.keys())
    assert fids[0].split(":")[-1] != fids[1].split(":")[-1]


# ---------------------------------------------------------------------------
# M-R4-1: format_active_foreshadow_md 表格转义
# ---------------------------------------------------------------------------

def test_format_active_md_escapes_pipe_and_newline():
    """M-R4-1: | 与换行符必须被转义/压缩，否则破坏表格。"""
    rows = [
        {
            "id": "x",
            "content": "多行\n伏笔 | 描述",
            "tier": "支线",
            "weight": 2.0,
            "status": "active",
            "planted_chapter": 1,
            "target_chapter": 5,
            "elapsed": 4,
            "remaining": 1,
        }
    ]
    md = format_active_foreshadow_md(rows)
    # | 在内容中必须是 \|（不是裸 |）
    assert "多行" in md
    assert "\\|" in md
    # 不应出现撑开表格的多余行
    lines = md.split("\n")
    data_lines = [l for l in lines if l.startswith("| ") and l.endswith(" |") and "层级" not in l]
    assert len(data_lines) == 1, (
        f"content 中的换行应被压成空格，避免撑开表格行；"
        f"实际数据行 {len(data_lines)}: {data_lines}"
    )


# ---------------------------------------------------------------------------
# M-R4-4: --chapter 输入校验
# ---------------------------------------------------------------------------

def test_cli_rejects_zero_or_negative_chapter(tmp_path, capsys):
    """M-R4-4: --chapter <= 0 或 > 1_000_000 必须被拒绝。"""
    import subprocess
    import sys
    state_dir = tmp_path / ".webnovel"
    state_dir.mkdir()
    (state_dir / "state.json").write_text(
        '{"plot_threads":{"foreshadowing":[]}}',
        encoding="utf-8",
    )
    script = str(Path(__file__).resolve().parents[1] / "tracking_query.py")
    for bad in ("0", "-1", "-100", "1000001"):
        result = subprocess.run(
            [sys.executable, script, "--project", str(tmp_path), "--chapter", bad],
            capture_output=True, text=True,
        )
        assert result.returncode == 2, f"--chapter {bad} should be rejected"
        assert "非法" in result.stderr or "❌" in result.stderr