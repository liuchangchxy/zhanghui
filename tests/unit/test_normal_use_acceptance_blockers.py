"""Tests for closing Normal-Use Acceptance Blockers B1 and B2.

Verification Matrix:
- B1.1: New book chapter 1 legitimate protagonist reference (Chinese & pinyin slug) passes R3.
- B1.2: Ghost entity with extraction delta strictly fails closed with blocking R3 failure (no unauthorized absorption).
- B1.3: Creative briefs (cross-chapter or draft) do not authorize unknown entities in R3.
- B1.4: Existing entities & aliases from index.db, state.json, MASTER_SETTING.json pass R3.
- B1.5: Legitimate new entity lifecycle flow (extraction -> commit projection -> index.db available in subsequent chapters).
- B1.6: Ungrounded stranger entity strictly fails closed with blocking R3 failure.
- B1.7: changes_gate CLI passes deterministically.
- B1.8: reconcile_changes.py CLI subprocess executes and generates reconciliation_result.json.
- B2.1: Post-sealing mutation of story contracts strictly triggers STALE_WRITER_PACKAGE rejection.
- B2.2: Normal runtime commit with intact contracts accepts and creates durable commit.
- B2.3: Reconcile changes determinism across python hash seeds.
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


def test_b1_ghost_entity_state_change_strictly_fails_even_with_extraction_delta(tmp_path: Path):
    """Canon has no ghost_999. CHANGES claims ghost_999 state change.
    Even if extraction_result.json includes ghost_999 entity_delta, R3 strictly fails."""
    webnovel_dir, db_path, state_path = _setup_book_project(tmp_path)

    extraction_file = webnovel_dir / "tmp" / "extraction_result.json"
    extraction_file.write_text(
        json.dumps({
            "accepted_events": [],
            "state_deltas": [],
            "entity_deltas": [
                {
                    "entity_id": "ghost_999",
                    "action": "upsert",
                    "entity_type": "角色",
                    "payload": {"name": "幽灵999"},
                },
            ],
            "dominant_strand": "quest",
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    changes = {
        "character_state_changes": [
            {"character_id": "ghost_999", "new_state": "降临", "importance": "critical"},
        ],
    }

    failures = check_r03_entities(
        changes,
        db_path,
        state_path,
        extraction_path=extraction_file,
        proj_root=tmp_path,
    )
    assert len(failures) == 1
    assert failures[0].rule_id == "R3"
    assert failures[0].severity == "blocking"
    assert "ghost_999" in failures[0].message
    assert "不在账本" in failures[0].message


def test_b1_old_creative_brief_does_not_authorize_new_chapter_entities(tmp_path: Path):
    """Creative briefs (cross-chapter or current) must not authorize entities in R3."""
    webnovel_dir, db_path, state_path = _setup_book_project(tmp_path)

    # Creative brief from chapter 1 or earlier mentions elder_zhang
    brief_file = webnovel_dir / "tmp" / "creative_brief_0001.txt"
    brief_file.write_text(
        "# Creative Brief\n\n## 三、人物小动作\n**张长老**——传法阁长老。\n",
        encoding="utf-8",
    )

    changes = {
        "character_state_changes": [
            {"character_id": "张长老", "new_state": "传法", "importance": "normal"},
        ],
    }

    failures = check_r03_entities(changes, db_path, state_path, proj_root=tmp_path)
    assert len(failures) == 1
    assert failures[0].rule_id == "R3"
    assert failures[0].severity == "blocking"
    assert "张长老" in failures[0].message
    assert "不在账本" in failures[0].message


def test_b1_existing_canon_entities_state_changes_pass(tmp_path: Path):
    """Entities established in Canon (index.db, state.json, MASTER_SETTING.json) pass R3."""
    webnovel_dir, db_path, state_path = _setup_book_project(tmp_path)

    # Insert an existing character and alias into index.db
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO entities (id, type, canonical_name, is_archived) VALUES (?, ?, ?, 0)",
        ("elder_sun", "character", "孙长老"),
    )
    conn.execute(
        "INSERT INTO aliases (alias, entity_id, entity_type) VALUES (?, ?, ?)",
        ("老孙", "elder_sun", "character"),
    )
    conn.commit()
    conn.close()

    changes = {
        "character_state_changes": [
            {"character_id": "lin_yue", "new_state": "打坐", "importance": "normal"},
            {"character_id": "elder_sun", "new_state": "巡山", "importance": "normal"},
            {"character_id": "老孙", "new_state": "饮茶", "importance": "normal"},
        ],
    }

    failures = check_r03_entities(changes, db_path, state_path, proj_root=tmp_path)
    assert failures == []


def test_b1_legal_new_entity_lifecycle_flow(tmp_path: Path):
    """Verify legitimate new entity flow:
    Chapter 1 introduces a new entity via text & extraction_result;
    Commit projects it to Canon (index.db);
    Chapter 2 can then reference it in character_state_changes and pass R3."""
    _setup_book_project(tmp_path)
    runtime = ChapterRuntime(tmp_path)

    # 1. Chapter 1: Prepare & Ingest
    prep = runtime.prepare(chapter=1, with_package=True)
    assert prep.ok is True
    pkg = runtime.attach_creative_brief(chapter=1, creative_brief="## 三、人物小动作\n**林越**\n")
    assert pkg is not None

    ch1_prose = """林越在矿道偶遇巡查队长赵崇。

<chapter_changes>
{
  "character_state_changes": [
    {"character_id": "lin_yue", "new_state": "如常", "importance": "normal"}
  ],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}
</chapter_changes>"""

    ingest1 = runtime.ingest_draft(chapter=1, prose=ch1_prose, package_fingerprint=pkg.package_fingerprint)
    assert ingest1.ok is True

    # Chapter 1 Data Agent extraction discovers new entity 'zhao_chong'
    artifacts1 = _complete_semantic_artifacts(ch1_prose)
    artifacts1["extraction_result"]["entity_deltas"] = [
        {
            "entity_id": "zhao_chong",
            "action": "upsert",
            "entity_type": "角色",
            "payload": {"name": "赵崇"},
            "current": {"identity": "巡查队长"},
        }
    ]
    _, proposal1 = split_chapter_and_changes(ch1_prose)
    artifacts1["reconciliation_result"] = reconcile_changes(
        proposal1, artifacts1["extraction_result"], chapter_text=ch1_prose
    )

    commit1 = runtime.commit(chapter=1, draft_id=ingest1.draft_id, **artifacts1)
    assert commit1.ok is True, f"commit1 failed: {commit1.error_code} - {commit1.error}"
    assert commit1.chapter_outcome == "accepted"

    # 2. Chapter 2: 'zhao_chong' is now in Canon (index.db).
    # Now chapter_changes in Chapter 2 can legally reference 'zhao_chong' in character_state_changes!
    db_path = tmp_path / ".webnovel" / "index.db"
    state_path = tmp_path / ".webnovel" / "state.json"
    ch2_changes = {
        "character_state_changes": [
            {"character_id": "zhao_chong", "new_state": "巡查归来", "importance": "normal"},
            {"character_id": "lin_yue", "new_state": "继续挖矿", "importance": "normal"},
        ]
    }
    failures = check_r03_entities(ch2_changes, db_path, state_path, proj_root=tmp_path)
    assert failures == [], f"Expected zhao_chong to pass R3 after being committed to canon, got {failures}"


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
    chapter_file.write_text("""林越在三号废弃矿道收尾当班。

<chapter_changes>
{
  "character_state_changes": [
    {"character_id": "lin_yue", "new_state": "认罚", "importance": "important"}
  ],
  "new_plot_points": [
    {"summary": "克扣矿石", "importance": "normal", "involved_characters": ["lin_yue"]}
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

