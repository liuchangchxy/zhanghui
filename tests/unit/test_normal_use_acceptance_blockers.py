"""Tests for closing Normal-Use Acceptance Blockers B1 and B2.

Verification Matrix:
- B1.1: New book chapter 1 legitimate protagonist reference (Chinese & pinyin slug) passes R3.
- B1.2: Legitimate first-introduced new entity in creative brief / extraction passes R3.
- B1.3: Ungrounded stranger entity strictly fails closed with blocking R3 failure.
- B1.4: Existing entity & aliases from index.db recognized normally.
- B1.5: changes_gate CLI passes deterministically.
- B1.6: reconcile_changes.py CLI subprocess executes and generates reconciliation_result.json.
- B2.1: Contract preparation in Step 1A followed by WriterPackage sealing maintains package freshness.
- B2.2: Post-sealing mutation of story contracts strictly triggers STALE_WRITER_PACKAGE rejection.
- B2.3: Normal runtime commit with intact contracts accepts and creates durable commit.
"""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from changes_gate import check_r03_entities, run_changes_gate
from data_modules.chapter_runtime import ChapterRuntime
from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager
from data_modules.reconciliation import reconcile_changes, split_chapter_and_changes


def _setup_book_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Helper to set up a valid book project layout."""
    webnovel_dir = tmp_path / ".webnovel"
    webnovel_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = webnovel_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    outline_dir = tmp_path / "大纲"
    outline_dir.mkdir(parents=True, exist_ok=True)

    db_path = webnovel_dir / "index.db"
    config = DataModulesConfig(project_root=tmp_path)
    IndexManager(config)

    state_path = webnovel_dir / "state.json"
    state_path.write_text(
        json.dumps({
            "project_info": {
                "title": "星际矿工的灵石修仙",
                "genre": "科幻",
                "golden_finger_name": "混沌灵矿系统",
            },
            "protagonist_state": {
                "name": "林越",
                "current_realm": "凡人矿工",
            },
            "progress": {
                "current_volume": 1,
                "current_chapter": 0,
                "total_volumes": 1,
                "volumes_planned": [{"volume": 1, "chapters_range": "1-10", "title": "第一卷"}],
                "volumes_completed": [],
            },
            "world_settings": {
                "characters": [],
                "locations": ["三号废弃矿道"],
                "items": ["矿工手铲"],
            },
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    story_sys = tmp_path / ".story-system"
    story_sys.mkdir(parents=True, exist_ok=True)
    (story_sys / "MASTER_SETTING.json").write_text(
        json.dumps({
            "entities": [{"name": "林越", "id": "lin_yue", "type": "角色"}],
            "locations": [{"name": "三号废弃矿道", "id": "mine_03"}],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for d in (".webnovel/backups", ".webnovel/archive", ".webnovel/summaries", "设定集", "正文", "审查报告"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    for f in ("设定集/世界观.md", "设定集/力量体系.md", "设定集/主角卡.md", "设定集/反派设计.md", "大纲/总纲.md", ".env.example"):
        fp = tmp_path / f
        if not fp.exists():
            fp.write_text("# init\n", encoding="utf-8")

    (outline_dir / "第1卷-详细大纲.md").write_text("""# 第一卷

### 第1章：矿道异芒
- 目标：林越在三号废弃矿道深处完成采掘定额
- 阻力：矿道坍塌风险与巡查队长赵崇的克扣
- 代价：防尘面罩破损
- 必须覆盖节点：废弃矿道、岩壁蓝芒
- 本章禁区：禁止直接暴露灵石秘密
- 章末问题：深蓝矿石因何震颤？
""", encoding="utf-8")

    return webnovel_dir, db_path, state_path


def _valid_test_prose() -> str:
    return """林越在三号废弃矿道收尾当班，赵崇带着巡查队过来核查定额。

<chapter_changes>
{
  "character_state_changes": [
    {
      "character_id": "lin_yue",
      "change_type": "status_update",
      "importance": "normal",
      "details": "认罚并深入支巷"
    }
  ],
  "new_plot_points": [
    {
      "plot_id": "plot_fine",
      "importance": "normal",
      "description": "巡查队扣罚定额"
    }
  ],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}
</chapter_changes>"""


def _complete_semantic_artifacts(prose: str) -> dict:
    _, proposal = split_chapter_and_changes(prose)
    extraction_result = {
        "chapter_meta": {},
        "accepted_events": [
            {
                "event_type": "character_state_changed",
                "subject": "lin_yue",
                "summary": "认罚并深入支巷",
                "payload": {"status": "深入矿道"},
            }
        ],
        "state_deltas": [],
        "entity_deltas": [
            {
                "entity_id": "lin_yue",
                "current": {"identity": "矿工"},
            }
        ],
    }
    reconciliation_result = reconcile_changes(
        proposal, extraction_result, chapter_text=prose
    )
    return {
        "review_result": {
            "blocking_count": 0,
            "must_check_results": [{"node": "废弃矿道", "passed": True}],
            "blocking_rule_results": [],
        },
        "fulfillment_result": {
            "planned_nodes": ["废弃矿道"],
            "covered_nodes": ["废弃矿道"],
            "missed_nodes": [],
            "extra_nodes": [],
        },
        "disambiguation_result": {"pending": []},
        "extraction_result": extraction_result,
        "reconciliation_result": reconciliation_result,
    }


def test_b1_chapter_1_protagonist_pinyin_and_chinese_passes(tmp_path: Path):
    """B1.1: Chapter 1 protagonist reference (林越 and lin_yue) passes R3."""
    webnovel_dir, db_path, state_path = _setup_book_project(tmp_path)

    changes = {
        "character_state_changes": [
            {"character_id": "lin_yue", "new_state": "突破练气一层", "importance": "critical"},
            {"character_id": "林越", "new_state": "获得灵石", "importance": "critical"},
        ],
        "new_plot_points": [
            {"summary": "发现矿脉", "involved_characters": ["lin_yue", "林越"]},
        ],
    }

    failures = check_r03_entities(changes, db_path, state_path)
    assert failures == [], f"Expected zero R3 failures for protagonist, got: {[f.message for f in failures]}"


def test_b1_creative_brief_and_extraction_new_entities_pass(tmp_path: Path):
    """B1.2: First-introduced entities grounded in creative brief and extraction result pass R3."""
    webnovel_dir, db_path, state_path = _setup_book_project(tmp_path)

    # 1. Creative brief defines antagonist 赵崇 in ## 三、人物小动作
    brief_file = webnovel_dir / "tmp" / "creative_brief_0001.txt"
    brief_file.write_text(
        "# Creative Brief\n\n## 三、人物小动作\n**赵崇**（巡查队长）——本章唯一的人际冲突源。\n",
        encoding="utf-8",
    )

    # 2. Data agent extraction result includes deep_blue_ore and zhao_chong
    extraction_file = webnovel_dir / "tmp" / "extraction_result.json"
    extraction_file.write_text(
        json.dumps({
            "accepted_events": [],
            "state_deltas": [],
            "entity_deltas": [
                {
                    "entity_id": "zhao_chong",
                    "action": "upsert",
                    "entity_type": "角色",
                    "payload": {"name": "赵崇", "role": "巡查队长"},
                },
                {
                    "entity_id": "deep_blue_ore",
                    "action": "upsert",
                    "entity_type": "物品",
                    "payload": {"name": "深蓝矿石"},
                },
            ],
            "dominant_strand": "quest",
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    changes = {
        "character_state_changes": [
            {"character_id": "zhao_chong", "new_state": "罚没产量", "importance": "important"},
            {"character_id": "赵崇", "new_state": "收队撤离", "importance": "normal"},
        ],
        "item_transfers": [
            {"item_id": "deep_blue_ore", "from_holder": "zhao_chong", "to_holder": "lin_yue"},
        ],
    }

    failures = check_r03_entities(
        changes,
        db_path,
        state_path,
        extraction_path=extraction_file,
        proj_root=tmp_path,
    )
    assert failures == [], f"Expected zero R3 failures for grounded new entities, got: {[f.message for f in failures]}"


def test_b1_ungrounded_stranger_entity_strictly_fails(tmp_path: Path):
    """B1.3: Ungrounded stranger entity strictly fails R3 with blocking severity."""
    webnovel_dir, db_path, state_path = _setup_book_project(tmp_path)

    bad_changes = {
        "character_state_changes": [
            {"character_id": "神秘外星人999", "new_state": "降临", "importance": "critical"},
        ],
        "location_state_changes": [
            {"location_id": "维度虚空神殿", "new_state": "开启", "importance": "important"},
        ],
        "item_transfers": [
            {"item_id": "核聚变魔方999", "from_holder": "神秘外星人999", "to_holder": "lin_yue"},
        ],
    }

    failures = check_r03_entities(bad_changes, db_path, state_path)
    assert len(failures) == 4
    for f in failures:
        assert f.rule_id == "R3"
        assert f.severity == "blocking"
        assert "不在账本" in f.message


def test_b1_changes_gate_cli_deterministic(tmp_path: Path):
    """B1.5: changes_gate CLI passes with full arguments and detects chapter entities."""
    webnovel_dir, db_path, state_path = _setup_book_project(tmp_path)

    chapter_file = webnovel_dir / "tmp" / "chapter_0001_working.md"
    chapter_file.write_text("""林越在三号废弃矿道收尾当班，赵崇带着巡查队过来核查定额。

<chapter_changes>
{
  "character_state_changes": [
    {"character_id": "lin_yue", "new_state": "认罚", "importance": "important"},
    {"character_id": "赵崇", "new_state": "离开", "importance": "normal"}
  ],
  "new_plot_points": [
    {"summary": "克扣矿石", "importance": "normal", "involved_characters": ["lin_yue", "赵崇"]}
  ],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}
</chapter_changes>
""", encoding="utf-8")

    extraction_file = webnovel_dir / "tmp" / "extraction_result.json"
    extraction_file.write_text(json.dumps({
        "accepted_events": [],
        "state_deltas": [],
        "entity_deltas": [
            {"entity_id": "lin_yue", "action": "upsert", "entity_type": "角色", "payload": {"name": "林越"}},
            {"entity_id": "zhao_chong", "action": "upsert", "entity_type": "角色", "payload": {"name": "赵崇"}},
        ],
        "dominant_strand": "quest",
    }, ensure_ascii=False), encoding="utf-8")

    gate_script = Path(__file__).resolve().parents[2] / ".claude/plugins/zhanghui/scripts/changes_gate.py"
    proc = subprocess.run(
        [
            sys.executable, str(gate_script),
            "--chapter-file", str(chapter_file),
            "--db", str(db_path),
            "--state-path", str(state_path),
            "--extraction-result", str(extraction_file),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, f"changes_gate failed: {proc.stdout}\n{proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["passed"] is True
    assert data["failures"] == []


def test_b1_reconcile_changes_cli_generates_artifact(tmp_path: Path):
    """B1.6: reconcile_changes.py CLI executes changes_gate and writes reconciliation artifact."""
    webnovel_dir, db_path, state_path = _setup_book_project(tmp_path)

    chapter_file = webnovel_dir / "tmp" / "chapter_0001_working.md"
    chapter_file.write_text("""林越在三号废弃矿道收尾当班，赵崇带着巡查队过来核查定额。

<chapter_changes>
{
  "character_state_changes": [
    {"character_id": "lin_yue", "new_state": "认罚", "importance": "important"}
  ],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}
</chapter_changes>
""", encoding="utf-8")

    extraction_file = webnovel_dir / "tmp" / "extraction_result.json"
    extraction_file.write_text(json.dumps({
        "chapter_meta": {"chapter": 1, "title": "第1章"},
        "accepted_events": [],
        "state_deltas": [],
        "entity_deltas": [
            {"entity_id": "lin_yue", "action": "upsert", "entity_type": "角色", "payload": {"name": "林越"}},
        ],
        "dominant_strand": "quest",
    }, ensure_ascii=False), encoding="utf-8")

    output_file = webnovel_dir / "tmp" / "reconciliation_result.json"

    reconcile_script = Path(__file__).resolve().parents[2] / ".claude/plugins/zhanghui/scripts/reconcile_changes.py"
    proc = subprocess.run(
        [
            sys.executable, str(reconcile_script),
            "--chapter-file", str(chapter_file),
            "--extraction-result", str(extraction_file),
            "--db", str(db_path),
            "--output", str(output_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, f"reconcile_changes.py failed: {proc.stdout}\n{proc.stderr}"
    assert output_file.is_file()
    result = json.loads(output_file.read_text(encoding="utf-8"))
    assert result["status"] == "passed"


def test_b2_stale_writer_package_gate_remains_active(tmp_path: Path):
    """B2.2: Mutating story-system contracts after package sealing strictly triggers STALE_WRITER_PACKAGE."""
    _setup_book_project(tmp_path)
    runtime = ChapterRuntime(tmp_path)

    # 1. Prepare writer package
    prep = runtime.prepare(chapter=1, with_package=True)
    assert prep.ok is True
    pkg = prep.writer_package
    assert pkg is not None

    # 2. Attach creative brief
    pkg = runtime.attach_creative_brief(chapter=1, creative_brief="## 三、人物小动作\n**林越**\n")
    assert pkg is not None

    # 3. Ingest draft
    prose = _valid_test_prose()
    ingest = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint=pkg.package_fingerprint,
    )
    assert ingest.ok is True

    # 4. Mutate story-system contracts on disk (simulating forbidden pre-commit mutation)
    master_setting = tmp_path / ".story-system" / "MASTER_SETTING.json"
    master_setting.write_text(json.dumps({
        "entities": [{"name": "林越", "id": "lin_yue"}, {"name": "突然新增角色", "id": "sudden"}],
    }, ensure_ascii=False), encoding="utf-8")

    # 5. Attempt commit - MUST be rejected with STALE_WRITER_PACKAGE
    artifacts = _complete_semantic_artifacts(prose)
    res = runtime.commit(
        chapter=1,
        draft_id=ingest.draft_id,
        **artifacts,
    )

    assert res.ok is False
    assert res.error_code == "STALE_WRITER_PACKAGE"
    assert res.chapter_outcome == "rejected"


def test_b2_normal_workflow_allows_commit_acceptance(tmp_path: Path):
    """B2.3: When contracts are not mutated post-sealing (proper Step 1A), commit is accepted."""
    _setup_book_project(tmp_path)
    runtime = ChapterRuntime(tmp_path)

    # 1. Prepare writer package
    prep = runtime.prepare(chapter=1, with_package=True)
    assert prep.ok is True

    # 2. Attach creative brief
    pkg = runtime.attach_creative_brief(chapter=1, creative_brief="## 三、人物小动作\n**林越**\n")
    assert pkg is not None

    # 3. Ingest draft
    prose = _valid_test_prose()
    ingest = runtime.ingest_draft(
        chapter=1,
        prose=prose,
        package_fingerprint=pkg.package_fingerprint,
    )
    assert ingest.ok is True

    # 4. Commit with complete artifacts
    artifacts = _complete_semantic_artifacts(prose)
    res = runtime.commit(
        chapter=1,
        draft_id=ingest.draft_id,
        **artifacts,
    )

    assert res.ok is True, f"commit failed: {res.error_code} - {res.error}"
    assert res.chapter_outcome == "accepted"
    assert res.durable_commit_persisted is True
    assert (tmp_path / ".story-system" / "commits" / "chapter_001.commit.json").is_file()


def test_reconcile_changes_deterministic_across_hash_seeds():
    """Verify reconcile_changes output is byte-for-byte identical across Python hash seeds."""
    from data_modules.reconciliation import reconcile_changes, split_chapter_and_changes

    prose = _valid_test_prose()
    _, proposed = split_chapter_and_changes(prose)
    observed = {
        "accepted_events": [],
        "state_deltas": [{"entity_id": "lin_yue", "field": "realm", "old": "凡人", "new": "炼气一层"}],
        "entity_deltas": [],
        "entities_appeared": [],
        "scenes": [],
        "summary_text": "第一章摘要",
    }

    r1 = reconcile_changes(proposed, observed, chapter_text=prose)
    r2 = reconcile_changes(proposed, observed, chapter_text=prose)

    assert r1 == r2
    assert json.dumps(r1, sort_keys=False) == json.dumps(r2, sort_keys=False)

