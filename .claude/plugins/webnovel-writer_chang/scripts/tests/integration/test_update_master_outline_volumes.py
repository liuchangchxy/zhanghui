"""Verify spec §5.4 contract for update_master_outline.py V+1 anchor writeback.

NOTE: This is a behavioral + module-level scaffold test. The full V+1
writeback flow is agent-driven: the agent reads `.webnovel/state.json`'s
`volumes[]` and produces `大纲/第N卷-总纲写回.json`, which
`update_master_outline.sync_master_outline()` consumes to write the V+1
row in `大纲/总纲.md`.

We verify here that:
  1. The module imports successfully (no regression).
  2. When the agent provides a writeback JSON containing a V+1 anchor,
     sync_master_outline() writes the V+1 row using those fields.
  3. No V+2+ detailed outline / 节拍表 / 时间线 artifacts are produced
     (the spec §5.4 hard constraint).

See: docs/superpowers/specs/2026-08-18-multi-volume-init-design.md §5.4
"""
import sys
import json
import tempfile
from pathlib import Path

import pytest

# File: scripts/tests/integration/test_update_master_outline_volumes.py
# Path bug to avoid: do NOT append "/scripts" — parents[2] IS the scripts dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from update_master_outline import _require_current_volume_artifacts, MasterOutlineSyncError  # noqa: E402


def test_module_imports():
    """update_master_outline is importable (no regression)."""
    from update_master_outline import sync_master_outline, MasterOutlineSyncError  # noqa: F401


def test_sync_master_outline_writes_v_plus_1_row_from_writeback():
    """When writeback JSON has V+1 anchor, sync_master_outline writes the V+1 row."""
    from update_master_outline import sync_master_outline

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        outline_dir = project_root / "大纲"
        outline_dir.mkdir(parents=True, exist_ok=True)

        # Minimal 总纲.md with a 卷划分 table that has V1 already
        (outline_dir / "总纲.md").write_text(
            "# 总纲\n\n## 卷划分\n\n"
            "| 卷号 | 卷名 | 章节范围 | 核心冲突 | 卷末高潮 |\n"
            "|------|------|----------|----------|----------|\n"
            "| 1 | V1 | 第1-50章 | A | B |\n",
            encoding="utf-8",
        )
        # Required current-volume artifacts for sync_master_outline to run
        for fname in ("第1卷-节拍表.md", "第1卷-时间线.md", "第1卷-详细大纲.md"):
            (outline_dir / fname).write_text("# stub\n", encoding="utf-8")
        # Writeback JSON with V+1 anchor
        (outline_dir / "第1卷-总纲写回.json").write_text(
            json.dumps({
                "next_volume_anchor": {
                    "volume": 2,
                    "volume_name": "V2-深入",
                    "core_conflict": "敌派渗透",
                    "volume_end_climax": "师尊负伤",
                    "chapters_range": "第51-100章",
                },
            }, ensure_ascii=False),
            encoding="utf-8",
        )

        result = sync_master_outline(str(project_root), volume=1)

        assert result["ok"] is True
        assert result["volume_anchor_written"] is True

        after = (outline_dir / "总纲.md").read_text(encoding="utf-8")
        # V+1 row reflects writeback fields
        assert "V2-深入" in after
        assert "敌派渗透" in after
        assert "师尊负伤" in after

        # Hard constraint: no V2+ detailed artifacts generated
        assert not (outline_dir / "第2卷-详细大纲.md").exists()
        assert not (outline_dir / "第2卷-节拍表.md").exists()
        assert not (outline_dir / "第2卷-时间线.md").exists()
        assert not (outline_dir / "第3卷-详细大纲.md").exists()


def test_require_current_volume_artifacts_all_volumes_mode_skips(tmp_path):
    """Spec §6.3: in --all-volumes mode, missing V1 artifacts must NOT raise."""
    # No artifacts created
    (tmp_path / "大纲").mkdir()
    # Should NOT raise — all_volumes_mode=True short-circuits
    result = _require_current_volume_artifacts(tmp_path, volume=1, all_volumes_mode=True)
    assert result == []


def test_require_current_volume_artifacts_default_still_enforces(tmp_path):
    """Default behavior unchanged: missing artifacts raise MasterOutlineSyncError."""
    (tmp_path / "大纲").mkdir()
    with pytest.raises(MasterOutlineSyncError, match="planning artifacts are incomplete"):
        _require_current_volume_artifacts(tmp_path, volume=1)