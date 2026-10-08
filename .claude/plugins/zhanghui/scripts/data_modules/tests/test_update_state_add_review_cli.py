#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys


def test_update_state_cli_add_review_writes_checkpoint(tmp_path, monkeypatch):
    import update_state as update_state_module

    webnovel_dir = tmp_path / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "project_info": {},
        "progress": {"current_chapter": 1, "total_words": 0},
        "protagonist_state": {
            "power": {"realm": "炼气", "layer": 1, "bottleneck": None},
            "location": "村口",
        },
        "relationships": {},
        "world_settings": {},
        "plot_threads": {},
        "review_checkpoints": [],
    }
    state_file = webnovel_dir / "state.json"
    state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    # 避免在测试里创建备份目录/修改权限等非核心行为
    monkeypatch.setattr(update_state_module.StateUpdater, "backup", lambda self: True)

    report_file = "review/report_1_2.md"
    monkeypatch.setattr(
        sys,
        "argv",
        ["update_state", "--project-root", str(tmp_path), "--add-review", "1-2", report_file],
    )
    update_state_module.main()

    updated = json.loads(state_file.read_text(encoding="utf-8"))
    checkpoints = updated.get("review_checkpoints")
    assert isinstance(checkpoints, list)
    assert checkpoints[-1]["chapters"] == "1-2"
    assert checkpoints[-1]["report"] == report_file


def test_update_state_cli_volume_planned_keeps_base_only_compatibility(tmp_path, monkeypatch):
    import update_state as update_state_module

    webnovel_dir = tmp_path / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    state_file = webnovel_dir / "state.json"
    state_file.write_text(json.dumps({
        "schema_version": "v6.2.1", "project_info": {}, "progress": {},
        "protagonist_state": {"power": {}, "location": ""}, "relationships": {},
        "world_settings": {}, "plot_threads": {}, "review_checkpoints": [],
    }), encoding="utf-8")
    monkeypatch.setattr(update_state_module.StateUpdater, "backup", lambda self: True)
    monkeypatch.setattr(sys, "argv", [
        "update_state", "--project-root", str(tmp_path), "--volume-planned", "2",
        "--chapters-range", "11-20",
    ])

    update_state_module.main()

    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["progress"]["volumes_planned"][0]["volume"] == 2


def test_update_state_rejects_canon_mutation_in_story_system_mode(tmp_path, monkeypatch):
    import pytest
    import update_state as update_state_module

    webnovel_dir = tmp_path / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    state = {
        "project_info": {},
        "progress": {"current_chapter": 1, "total_words": 0},
        "protagonist_state": {"power": {"realm": "炼气", "layer": 1, "bottleneck": None}, "location": "村口"},
        "relationships": {}, "world_settings": {}, "plot_threads": {}, "review_checkpoints": [],
    }
    state_file = webnovel_dir / "state.json"
    original = json.dumps(state, ensure_ascii=False)
    state_file.write_text(original, encoding="utf-8")
    story_root = tmp_path / ".story-system"
    story_root.mkdir()
    (story_root / "MASTER_SETTING.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", [
        "update_state", "--project-root", str(tmp_path), "--protagonist-power", "金丹", "2", "雷劫",
    ])
    with pytest.raises(SystemExit) as exc:
        update_state_module.main()

    assert exc.value.code == 2
    assert state_file.read_text(encoding="utf-8") == original


def test_update_state_allows_review_metadata_in_story_system_mode(tmp_path, monkeypatch):
    import update_state as update_state_module

    webnovel_dir = tmp_path / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    state = {
        "project_info": {},
        "progress": {"current_chapter": 1, "total_words": 0},
        "protagonist_state": {"power": {"realm": "炼气", "layer": 1, "bottleneck": None}, "location": "村口"},
        "relationships": {}, "world_settings": {}, "plot_threads": {}, "review_checkpoints": [],
    }
    state_file = webnovel_dir / "state.json"
    state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    story_root = tmp_path / ".story-system"
    story_root.mkdir()
    (story_root / "MASTER_SETTING.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(update_state_module.StateUpdater, "backup", lambda self: True)
    monkeypatch.setattr(sys, "argv", [
        "update_state", "--project-root", str(tmp_path), "--add-review", "1-2", "review/report.md",
    ])

    update_state_module.main()

    updated = json.loads(state_file.read_text(encoding="utf-8"))
    assert updated["review_checkpoints"][-1]["report"] == "review/report.md"
