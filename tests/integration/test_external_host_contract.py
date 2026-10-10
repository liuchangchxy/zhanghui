#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External Host Contract Test for Runtime API v1 (Issue #25)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from external_host_adapter import ExternalHostAdapter


def _setup_minimal_book_project(tmp_path: Path, chapter: int = 1) -> Path:
    """Create a minimal valid book project containing ONLY state and outline."""
    project_root = tmp_path / "test_book"
    project_root.mkdir(parents=True, exist_ok=True)
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    outline_dir = project_root / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "project_info": {
            "title": "测试纪元",
            "genre": "玄幻",
            "target_readers": "大众",
        },
        "progress": {
            "current_volume": 1,
            "current_chapter": 0,
            "total_volumes": 3,
            "volumes_planned": [
                {"volume": 1, "chapters_range": "1-10", "title": "第一卷 觉醒"}
            ],
            "volumes_completed": [],
        },
        "entity_state": {},
    }
    (webnovel_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    outline_text = f"""# 第一卷 觉醒

### 第{chapter}章：初入宗门
- 目标：主角林凡通过灵根测试进入天阳宗
- 阻力：外门执事李执事的刁难与轻视
- 代价：暴露残缺玉佩的微弱异动
- 必须覆盖节点：灵根测试、执事刁难、入宗铭牌
- 本章禁区：禁止直接突破练气三层、禁止暴露太古神帝记忆
- 章末问题：玉佩深处的封印因何松动？

### 第{chapter + 1}章：藏经阁之争
- 目标：林凡在藏经阁寻找基础吐纳法，引发未来暗线
- 阻力：外门大弟子王霸的阻挠
- 必须覆盖节点：挑选残破古经、结下梁子
"""
    (outline_dir / "第1卷-详细大纲.md").write_text(outline_text, encoding="utf-8")
    return project_root


def test_external_host_contract_orchestration(tmp_path: Path):
    """Verify an external host completes chapter 1 via Runtime API without private layout knowledge."""
    project_root = _setup_minimal_book_project(tmp_path, chapter=1)
    evidence_dir = tmp_path / "evidence"

    adapter = ExternalHostAdapter(project_root=project_root, evidence_dir=evidence_dir)
    res = adapter.run_chapter(chapter=1)

    assert adapter.private_contract_writes == 0
    commit_res = res["commit_res"]
    assert commit_res.ok is True
    assert commit_res.chapter_outcome == "accepted"
    assert commit_res.projection_success is True

    required_files = [
        "request.json",
        "writer_package.json",
        "final_writer_prompt.txt",
        "draft_receipt.json",
        "runtime_workflow_state.json",
        "commit_outcome.json",
        "projection_status.json",
    ]
    for filename in required_files:
        filepath = evidence_dir / filename
        assert filepath.exists(), f"Missing evidence: {filename}"
        assert filepath.stat().st_size > 0, f"Empty evidence: {filename}"

    req = json.loads((evidence_dir / "request.json").read_text(encoding="utf-8"))
    assert req["action"] == "orchestrate_chapter"
    assert req["chapter"] == 1

    pkg = json.loads((evidence_dir / "writer_package.json").read_text(encoding="utf-8"))
    assert pkg["chapter"] == 1
    assert "灵根测试" in str(pkg["current_intent"])
    assert "藏经阁之争" not in str(pkg["current_intent"])

    receipt = json.loads((evidence_dir / "draft_receipt.json").read_text(encoding="utf-8"))
    assert receipt["ok"] is True
    assert receipt["draft_id"].startswith("draft-001-")

    state = json.loads((evidence_dir / "runtime_workflow_state.json").read_text(encoding="utf-8"))
    assert state["draft_status"] == "ingested"
    assert state["draft_id"] == receipt["draft_id"]

    commit_out = json.loads((evidence_dir / "commit_outcome.json").read_text(encoding="utf-8"))
    assert commit_out["ok"] is True
    assert commit_out["chapter_outcome"] == "accepted"

    proj_out = json.loads((evidence_dir / "projection_status.json").read_text(encoding="utf-8"))
    assert proj_out["projection_success"] is True
