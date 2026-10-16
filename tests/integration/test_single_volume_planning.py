#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single-volume (no V+1) planning tests (task J / M9).

`webnovel-plan` tells the planner: 「V+1 不存在或 deferred 时 V+1 行留空（不伪造）」, but
`master-outline-sync` used to *require* a non-empty `next_volume_anchor`. A single-volume book
therefore could not complete the documented flow without inventing a second volume.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "plugins" / "zhanghui" / "scripts"
for path in (SCRIPTS, SCRIPTS.parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


MASTER_OUTLINE = """# 总纲

## 卷划分

| 卷号 | 卷名 | 章节范围 | 核心冲突 | 卷末高潮 |
|---|---|---|---|---|
| 1 | 潮痕 | 第1-24章 | 追查十年前旧航道事故真相 | 篡改者身份被揭开 |
"""


def _project(tmp_path: Path, *, volumes: list[dict] | None = None) -> Path:
    (tmp_path / "大纲").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".webnovel").mkdir(parents=True, exist_ok=True)
    (tmp_path / "大纲" / "总纲.md").write_text(MASTER_OUTLINE, encoding="utf-8")
    for name in ("第1卷-节拍表.md", "第1卷-时间线.md", "第1卷-详细大纲.md"):
        (tmp_path / "大纲" / name).write_text("# 内容\n", encoding="utf-8")
    (tmp_path / ".webnovel" / "state.json").write_text(
        json.dumps(
            {
                "project_info": {"title": "海港旧信", "genre": "悬疑"},
                "progress": {
                    "current_volume": 1,
                    "volumes_planned": [{"volume": 1, "chapters_range": "1-24", "title": "潮痕"}],
                },
                "volumes": volumes if volumes is not None else [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return tmp_path


def _writeback(tmp_path: Path, anchor, *, extra: dict | None = None) -> Path:
    payload = {"next_volume_anchor": anchor}
    if extra:
        payload.update(extra)
    path = tmp_path / "大纲" / "第1卷-总纲写回.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "anchor",
    [None, "", "none", "deferred", {}, {"status": "deferred"}, {"volume": None, "status": "deferred"}],
)
def test_single_volume_planning_completes_without_inventing_v_plus_1(tmp_path: Path, anchor):
    """M9: 单卷 24 章、无 V+1 —— 完整规划流程不得因不存在的下一卷而失败。"""
    from update_master_outline import sync_master_outline

    root = _project(tmp_path)
    _writeback(root, anchor)

    result = sync_master_outline(root, 1)

    assert result["ok"] is True
    assert result["next_volume_anchor_state"] == "absent"
    assert result["volume_anchor_written"] is False
    # the master outline is untouched: no fabricated second volume row
    assert (root / "大纲" / "总纲.md").read_text(encoding="utf-8") == MASTER_OUTLINE
    assert "第2卷" not in (root / "大纲" / "总纲.md").read_text(encoding="utf-8")


def test_absent_anchor_still_processes_foreshadow_writeback(tmp_path: Path):
    """缺少 V+1 只跳过 V+1 行；伏笔/开放环写回必须照常执行。"""
    from update_master_outline import sync_master_outline

    root = _project(tmp_path)
    _writeback(
        root,
        None,
        extra={
            "foreshadow_writeback": [
                {"content": "潮汐表上的手写日期", "buried_chapter": "第1章", "payoff_chapter": "", "level": "卷级"}
            ]
        },
    )

    result = sync_master_outline(root, 1)
    assert result["ok"] is True
    assert result["next_volume_anchor_state"] == "absent"
    assert result["structured_items_appended"] >= 1


def test_multi_volume_project_still_writes_the_anchor_row(tmp_path: Path):
    """J4: 多卷项目原有行为保持不变。"""
    from update_master_outline import sync_master_outline

    root = _project(
        tmp_path,
        volumes=[
            {"volume": 1, "title": "潮痕", "status": "confirmed"},
            {"volume": 2, "title": "深水", "status": "confirmed", "core_conflict": "暗流", "climax": "沉船"},
        ],
    )
    _writeback(
        root,
        {"volume": 2, "volume_name": "深水", "core_conflict": "旧案余波", "volume_end_climax": "真相公开"},
    )

    result = sync_master_outline(root, 1, on_conflict="overwrite")
    assert result["ok"] is True
    assert result["next_volume_anchor_state"] == "written"
    text = (root / "大纲" / "总纲.md").read_text(encoding="utf-8")
    assert "深水" in text
    assert "旧案余波" in text


def test_missing_key_is_still_an_error(tmp_path: Path):
    """缺字段与「显式空」是两回事：前者仍然是写作回 JSON 的错误。"""
    from update_master_outline import MasterOutlineSyncError, sync_master_outline

    root = _project(tmp_path)
    path = root / "大纲" / "第1卷-总纲写回.json"
    path.write_text(json.dumps({"foreshadow_writeback": []}, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(MasterOutlineSyncError):
        sync_master_outline(root, 1)


def test_partial_anchor_is_still_rejected(tmp_path: Path):
    """声明了 V+1 却缺名称/冲突/高潮 —— 仍然拒绝，避免写半截数据。"""
    from update_master_outline import MasterOutlineSyncError, sync_master_outline

    root = _project(tmp_path)
    _writeback(root, {"volume": 2, "volume_name": "深水"})

    with pytest.raises(MasterOutlineSyncError):
        sync_master_outline(root, 1)
