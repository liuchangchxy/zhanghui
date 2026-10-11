"""Tests for deterministic R3 entity authority and lifecycle closure.

Requirements:
A. structured Canon entity → R3 PASS
B. accepted previous entity → R3 PASS
C. random unknown entity → R3 FAIL
D. 与已知地点共享 3 个汉字的未知地点 → 仍 FAIL
E. Markdown 普通 ## 标题 → 不自动获得 entity authority
F. rejected retry → 可重试
G. accepted commit → immutable
"""
import json
import sqlite3
from pathlib import Path

import pytest
from changes_gate import check_r03_entities, run_changes_gate
from data_modules.config import DataModulesConfig
from data_modules.index_manager import IndexManager
from data_modules.index_projection_writer import IndexProjectionWriter


def _create_empty_test_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            tier TEXT DEFAULT '装饰',
            desc TEXT,
            current_json TEXT,
            first_appearance INTEGER DEFAULT 0,
            last_appearance INTEGER DEFAULT 0,
            is_protagonist INTEGER DEFAULT 0,
            is_archived INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE aliases (
            alias TEXT,
            entity_id TEXT,
            entity_type TEXT,
            PRIMARY KEY (alias, entity_id, entity_type)
        );
        CREATE TABLE scenes (
            id INTEGER PRIMARY KEY,
            chapter INTEGER,
            scene_order INTEGER,
            location TEXT
        );
        CREATE TABLE story_events (
            id INTEGER PRIMARY KEY,
            event_id TEXT,
            chapter INTEGER,
            event_type TEXT,
            subject TEXT,
            payload TEXT
        );
    """)
    conn.commit()
    conn.close()


def test_r03_structured_canon_entity_passes_and_random_unknown_fails(tmp_path: Path):
    """A: Structured Canon entity from state.json / MASTER_SETTING.json -> PASS; C: random unknown -> FAIL."""
    db_path = tmp_path / ".webnovel" / "index.db"
    _create_empty_test_db(db_path)

    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.write_text(
        json.dumps({
            "entity_state": {
                "林越": {"身份": "主角"},
                "梅叔": {"身份": "退休档案员", "状态": "保管一批未数字化旧档案"},
            },
            "world_settings": {
                "locations": ["临汐城", "咸水巷"],
                "items": ["黄铜钥匙"],
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    story_system = tmp_path / ".story-system"
    story_system.mkdir(parents=True, exist_ok=True)
    (story_system / "MASTER_SETTING.json").write_text(
        json.dumps({
            "entities": [{"name": "韩策", "type": "角色"}],
            "locations": ["白塔"],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    # A: All structured canon entities PASS
    good_changes = {
        "character_state_changes": [
            {"character_id": "林越", "importance": "critical"},
            {"character_id": "梅叔", "importance": "important"},
            {"character_id": "韩策", "importance": "normal"},
        ],
        "location_state_changes": [
            {"location_id": "临汐城", "new_state": "防潮穹顶开启", "importance": "normal"},
            {"location_id": "白塔", "new_state": "封存中", "importance": "normal"},
        ],
        "item_transfers": [
            {"item_id": "黄铜钥匙", "from_holder": "梅叔", "to_holder": "林越"},
        ],
    }
    failures = check_r03_entities(good_changes, db_path, state_path)
    assert failures == []

    # C: Random unknown entities strictly FAIL
    bad_changes = {
        "character_state_changes": [
            {"character_id": "未知神秘人999", "importance": "important"},
        ],
        "location_state_changes": [
            {"location_id": "外星基地777", "new_state": "活跃", "importance": "normal"},
        ],
        "item_transfers": [
            {"item_id": "核聚变魔方999", "from_holder": "梅叔", "to_holder": "林越"},
        ],
    }
    bad_failures = check_r03_entities(bad_changes, db_path, state_path)
    assert len(bad_failures) == 3
    msgs = [f.message for f in bad_failures]
    assert any("未知神秘人999" in m for m in msgs)
    assert any("外星基地777" in m for m in msgs)
    assert any("核聚变魔方999" in m for m in msgs)


def test_r03_accepted_previous_entity_passes(tmp_path: Path):
    """B: Accepted previous entity in ledger index.db -> R3 PASS."""
    db_path = tmp_path / ".webnovel" / "index.db"
    _create_empty_test_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO entities (id, type, canonical_name) VALUES ('延清装订修补铺', '地点', '延清装订修补铺')")
    conn.execute("INSERT INTO aliases (alias, entity_id, entity_type) VALUES ('修补铺', '延清装订修补铺', '地点')")
    conn.commit()
    conn.close()

    changes = {
        "location_state_changes": [
            {"location_id": "延清装订修补铺", "new_state": "正常营业", "importance": "normal"},
            {"location_id": "修补铺", "new_state": "正常营业", "importance": "normal"},
        ]
    }
    failures = check_r03_entities(changes, db_path)
    assert failures == []


def test_r03_unknown_location_sharing_three_characters_fails(tmp_path: Path):
    """D: Unknown location sharing 3+ characters with known location -> strictly FAILS (no substring heuristic)."""
    db_path = tmp_path / ".webnovel" / "index.db"
    _create_empty_test_db(db_path)

    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.write_text(
        json.dumps({
            "world_settings": {
                "locations": ["地下档案库", "咸水巷"],
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    # "咸水巷地下七号防汛杂档库" shares "咸水巷" (3 chars) and "地下" (2 chars)
    # "地下档案库密室" shares "地下档案库" (5 chars)
    # Under deterministic authority, neither is in ledger -> MUST FAIL!
    changes = {
        "location_state_changes": [
            {"location_id": "咸水巷地下七号防汛杂档库", "new_state": "闭锁", "importance": "important"},
            {"location_id": "地下档案库密室", "new_state": "警戒", "importance": "normal"},
        ]
    }
    failures = check_r03_entities(changes, db_path, state_path)
    assert len(failures) == 2
    msgs = [f.message for f in failures]
    assert any("咸水巷地下七号防汛杂档库" in m and "不在账本" in m for m in msgs)
    assert any("地下档案库密室" in m and "不在账本" in m for m in msgs)


def test_r03_markdown_heading_does_not_grant_entity_authority(tmp_path: Path):
    """E: Markdown ## headings in 设定集/*.md do NOT automatically grant Canon entity authority."""
    db_path = tmp_path / ".webnovel" / "index.db"
    _create_empty_test_db(db_path)

    settings_dir = tmp_path / "设定集"
    settings_dir.mkdir(parents=True)
    (settings_dir / "角色设定.md").write_text("# 角色设定\n\n## 神秘老人（隐世高手）\n", encoding="utf-8")
    (settings_dir / "物品设定.md").write_text("# 物品设定\n\n## 绝密青铜印\n- 描述：特殊印章\n", encoding="utf-8")
    (settings_dir / "世界观.md").write_text("# 世界观\n## 隐秘回廊\n- 主要地点：隐秘回廊\n", encoding="utf-8")

    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.write_text(
        json.dumps({
            "entity_state": {"林越": {"身份": "主角"}},
            "world_settings": {"locations": ["临汐城"]},
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    # Entities from markdown headings only, not in structured JSON -> MUST FAIL CLOSED
    changes = {
        "character_state_changes": [
            {"character_id": "神秘老人", "importance": "normal"},
        ],
        "location_state_changes": [
            {"location_id": "隐秘回廊", "new_state": "封闭", "importance": "normal"},
        ],
        "item_transfers": [
            {"item_id": "绝密青铜印", "from_holder": "林越", "to_holder": "神秘老人"},
        ],
    }
    failures = check_r03_entities(changes, db_path, state_path)
    assert len(failures) >= 3
    msgs = [f.message for f in failures]
    assert any("神秘老人" in m for m in msgs)
    assert any("隐秘回廊" in m for m in msgs)
    assert any("绝密青铜印" in m for m in msgs)


def test_rejected_chapter_allows_prewrite_rework(tmp_path: Path):
    """F: A chapter with status 'rejected' remains ready for prewrite/rework, not blocked by chapter_committed."""
    from data_modules.project_phase import (
        INIT_REQUIRED_DIRS,
        INIT_REQUIRED_FILES,
        resolve_project_phase,
        PHASE_CHAPTER_CONTRACT_READY,
    )

    for rel in INIT_REQUIRED_DIRS:
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)
    for rel in INIT_REQUIRED_FILES:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".json"):
            p.write_text(json.dumps({"project_info": {"title": "测试", "genre": "悬疑"}, "progress": {"current_chapter": 1}}, ensure_ascii=False), encoding="utf-8")
        else:
            p.write_text("placeholder\n", encoding="utf-8")

    story_system = tmp_path / ".story-system"
    (story_system / "commits").mkdir(parents=True, exist_ok=True)
    (story_system / "chapters").mkdir(parents=True, exist_ok=True)
    (story_system / "reviews").mkdir(parents=True, exist_ok=True)

    # Chapter 1 accepted
    (story_system / "commits" / "chapter_001.commit.json").write_text(json.dumps({
        "meta": {"chapter": 1, "status": "accepted"}
    }), encoding="utf-8")

    # Chapter 2 rejected
    (story_system / "commits" / "chapter_002.commit.json").write_text(json.dumps({
        "meta": {"chapter": 2, "status": "rejected"}
    }), encoding="utf-8")

    # Chapter 2 contracts present
    (story_system / "volumes").mkdir(parents=True, exist_ok=True)
    (story_system / "volumes" / "volume_001.json").write_text(json.dumps({"meta": {"volume": 1}}), encoding="utf-8")
    (story_system / "MASTER_SETTING.json").write_text(json.dumps({"meta": {}}), encoding="utf-8")
    (story_system / "chapters" / "chapter_002.json").write_text(json.dumps({"meta": {}}), encoding="utf-8")
    (story_system / "reviews" / "chapter_002.review.json").write_text(json.dumps({"meta": {}}), encoding="utf-8")

    snapshot = resolve_project_phase(tmp_path, chapter=2)
    assert snapshot.phase == PHASE_CHAPTER_CONTRACT_READY


def test_rejected_commit_can_be_superseded_by_retry_and_accepted_is_immutable(tmp_path: Path):
    """F & G: A rejected commit does not block retry attempt; accepted commits remain strictly immutable."""
    from data_modules.chapter_commit_service import ChapterCommitService, ChapterCommitError

    service = ChapterCommitService(tmp_path)
    commits_dir = tmp_path / ".story-system" / "commits"
    commits_dir.mkdir(parents=True, exist_ok=True)

    # 1. Simulate Attempt 1 failing and writing a rejected commit
    rejected_payload = {
        "meta": {"schema_version": "story-system/v1", "chapter": 1, "status": "rejected"},
        "contract_refs": {"master": "MASTER_SETTING.json", "volume": "volume_001.json", "chapter": "chapter_001.json", "review": "chapter_001.review.json"},
        "provenance": {"write_fact_role": "chapter_commit", "projection_role": "derived_read_models", "legacy_state_role": "projection_only"},
        "review_result": {"blocking_count": 1, "overall_score": 50},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"accepted_events": [], "state_deltas": [], "entity_deltas": []},
    }
    p1 = service.persist_commit(rejected_payload)
    assert p1.is_file()
    saved_1 = json.loads(p1.read_text(encoding="utf-8"))
    assert saved_1["meta"]["status"] == "rejected"

    # 2. Simulate Attempt 2 retry succeeding without passing on_conflict
    accepted_payload = {
        "meta": {"schema_version": "story-system/v1", "chapter": 1, "status": "accepted"},
        "contract_refs": {"master": "MASTER_SETTING.json", "volume": "volume_001.json", "chapter": "chapter_001.json", "review": "chapter_001.review.json"},
        "provenance": {"write_fact_role": "chapter_commit", "projection_role": "derived_read_models", "legacy_state_role": "projection_only"},
        "review_result": {"blocking_count": 0, "overall_score": 90},
        "fulfillment_result": {"planned_nodes": [], "covered_nodes": [], "missed_nodes": [], "extra_nodes": []},
        "disambiguation_result": {"pending": []},
        "extraction_result": {"accepted_events": [], "state_deltas": [], "entity_deltas": []},
    }
    p2 = service.persist_commit(accepted_payload)
    assert p2.is_file()
    saved_2 = json.loads(p2.read_text(encoding="utf-8"))
    assert saved_2["meta"]["status"] == "accepted"
    assert saved_2["review_result"]["overall_score"] == 90

    # 3. Once ACCEPTED, attempting to overwrite or write without skip MUST fail closed
    with pytest.raises(ChapterCommitError, match="Conflict policy rejected"):
        service.persist_commit(accepted_payload)

    with pytest.raises(ChapterCommitError, match="overwrite is forbidden for canonical chapter commits"):
        service.persist_commit(accepted_payload, on_conflict="overwrite")


def test_index_manager_applies_entity_name_and_normalizes_type(tmp_path: Path):
    """IndexManager.apply_entity_delta handles entity_name and maps english type to chinese."""
    config = DataModulesConfig(project_root=tmp_path)
    manager = IndexManager(config)

    delta = {
        "entity_name": "延清装订修补铺",
        "entity_type": "location",
        "action": "create",
        "description": "位于下城区咸水巷盲区的旧纸装订作坊",
        "chapter": 1,
    }
    applied = manager.apply_entity_delta(delta)
    assert applied is True

    ent = manager.get_entity("延清装订修补铺")
    assert ent is not None
    assert ent["canonical_name"] == "延清装订修补铺"
    assert ent["type"] == "地点"


def test_index_projection_writer_syncs_state_json_and_master_setting_canon(tmp_path: Path):
    """IndexProjectionWriter syncs canonical structured entities from state.json and MASTER_SETTING.json."""
    webnovel_dir = tmp_path / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    state_file = webnovel_dir / "state.json"
    state_file.write_text(
        json.dumps({
            "entity_state": {
                "林越": {"身份": "主角"},
                "梅叔": {"身份": "退休档案员"},
            },
            "world_settings": {
                "locations": ["临汐城"],
                "items": ["黄铜钥匙"],
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    story_sys = tmp_path / ".story-system"
    story_sys.mkdir(parents=True)
    (story_sys / "MASTER_SETTING.json").write_text(
        json.dumps({
            "locations": ["白塔"],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    writer = IndexProjectionWriter(tmp_path)
    config = DataModulesConfig(project_root=tmp_path)
    manager = IndexManager(config)

    from data_modules.story_system_mode import canonical_projection_write_scope
    with canonical_projection_write_scope(tmp_path):
        synced = writer._sync_canonical_state_entities(manager)
    assert synced >= 5
    assert manager.get_entity("梅叔") is not None
    assert manager.get_entity("林越") is not None
    assert manager.get_entity("临汐城") is not None
    assert manager.get_entity("黄铜钥匙") is not None
    assert manager.get_entity("白塔") is not None


def test_replay_run005_chapter_2_ungrounded_location_fails_closed():
    """Replay evidence: ungrounded location in run-005 writer output fails closed without heuristics."""
    writer_output_path = Path("/Users/chang/Desktop/Code/zhanghui-benchmark/runs/pilot-tide-archive-001/run-005-post-native-repair/_invocations/inv-zh-ch02-step2a_writer-a6a33249/output.txt")
    db_path = Path("/Users/chang/Desktop/Code/zhanghui-benchmark/runs/pilot-tide-archive-001/run-005-post-native-repair/zhanghui/.webnovel/index.db")
    state_path = Path("/Users/chang/Desktop/Code/zhanghui-benchmark/runs/pilot-tide-archive-001/run-005-post-native-repair/zhanghui/.webnovel/state.json")

    if not writer_output_path.is_file() or not db_path.is_file() or not state_path.is_file():
        pytest.skip("Run-005 artifacts not found on local path")

    chapter_text = writer_output_path.read_text(encoding="utf-8")
    result = run_changes_gate(
        chapter_text=chapter_text,
        db_path=db_path,
        state_path=state_path,
        chapter=2,
    )
    # "咸水巷地下七号防汛杂档库" is not in Canon ledger -> R3 must fail closed
    r3_failures = [f for f in result.failures if f.rule_id == "R3"]
    assert len(r3_failures) >= 1
    msgs = [f.message for f in r3_failures]
    assert any("咸水巷地下七号防汛杂档库" in m for m in msgs)
    assert result.passed is False


def test_writer_prompt_contract_distinguishes_new_entity_from_state_change():
    """A: WriterPackage.to_writer_prompt explicitly distinguishes new entities from state changes."""
    from data_modules.chapter_runtime import WriterPackage
    pkg = WriterPackage(
        chapter=2,
        package_fingerprint="fp123",
        source_fingerprints={},
        story_identity={"title": "测试小说"},
        current_intent={"chapter": 2, "outline": "大纲"},
        governed_canon={"canon_items": [], "appearing_characters": []},
        constraints={"core_tone": "压抑"},
        writer_context={},
        creative_brief="第2章创作策划任务书：林越前往旧档案室调查。",
        creative_brief_fingerprint="brief_fp_123",
    )
    prompt = pkg.to_writer_prompt()
    # Contract must explicitly instruct that new entities != state changes
    assert "不属于 state change" in prompt
    assert "严禁仅为了“登记新实体”而把它写入" in prompt or "不属于 state change" in prompt
    assert "location_state_changes" in prompt
    assert "地下档案修复室" in prompt or "首次出现" in prompt


def test_r03_strictly_fails_on_unknown_location_state_change(tmp_path: Path):
    """B: R3 remains strict: unknown location claimed as state change must FAIL."""
    db_path = tmp_path / ".webnovel" / "index.db"
    _create_empty_test_db(db_path)
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.write_text(json.dumps({
        "world_settings": {"locations": ["临汐城", "咸水巷"]}
    }, ensure_ascii=False), encoding="utf-8")

    # Known location state change passes
    good = {"location_state_changes": [{"location_id": "临汐城", "new_state": "封锁"}]}
    assert check_r03_entities(good, db_path, state_path) == []

    # Newly invented unknown location in state changes must strictly fail closed
    bad = {"location_state_changes": [{"location_id": "全新未知防汛暗室", "new_state": "封锁"}]}
    bad_failures = check_r03_entities(bad, db_path, state_path)
    assert len(bad_failures) == 1
    assert "全新未知防汛暗室" in bad_failures[0].message
    assert "不在账本" in bad_failures[0].message


def test_new_entity_in_extraction_enters_index_projection(tmp_path: Path):
    """C: New entity in extraction_result.entity_deltas formally enters index.db projection."""
    from data_modules.story_system_mode import canonical_projection_write_scope

    webnovel_dir = tmp_path / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    state_file = webnovel_dir / "state.json"
    state_file.write_text(json.dumps({
        "progress": {"current_chapter": 2},
        "world_settings": {"locations": ["临汐城"]},
    }, ensure_ascii=False), encoding="utf-8")

    story_sys = tmp_path / ".story-system"
    story_sys.mkdir(parents=True)

    commit_payload = {
        "meta": {"schema_version": "story-system/v1", "chapter": 2, "status": "accepted"},
        "extraction_result": {
            "chapter_meta": {"chapter": 2, "title": "第2章"},
            "accepted_events": [],
            "state_deltas": [],
            "entity_deltas": [
                {
                    "entity_name": "新设立观测哨",
                    "entity_type": "location",
                    "description": "林越在撤离路线中首次发现的离线观测哨",
                    "chapter": 2,
                }
            ],
        },
    }

    writer = IndexProjectionWriter(tmp_path)
    with canonical_projection_write_scope(tmp_path):
        res = writer._apply_accepted_commit(commit_payload)
    assert res["applied"] is True

    # Verify that the new entity is now in index.db entities
    manager = IndexManager(DataModulesConfig(project_root=tmp_path))
    ent = manager.get_entity("新设立观测哨")
    assert ent is not None
    assert ent["canonical_name"] == "新设立观测哨"
    assert ent["type"] == "地点"


def test_canary_new_entity_flow_from_prose_to_projection(tmp_path: Path):
    """End-to-end Canary:
    1. Writer produces prose with a new location, but location_state_changes is [] (per new contract).
    2. changes_gate PASSES.
    3. Data Agent extraction observes new entity in entity_deltas.
    4. Accepted commit projects it into index.db.
    5. Next chapter R3 recognizes the new location as a known entity!
    """
    from data_modules.story_system_mode import canonical_projection_write_scope

    webnovel_dir = tmp_path / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    state_file = webnovel_dir / "state.json"
    state_file.write_text(json.dumps({
        "progress": {"current_chapter": 1},
        "entity_state": {"林越": {"身份": "主角"}},
        "world_settings": {"locations": ["临汐城", "咸水巷"]},
    }, ensure_ascii=False), encoding="utf-8")

    db_path = webnovel_dir / "index.db"
    _create_empty_test_db(db_path)

    # Step 1 & 2: Prose introduces "地下暗渠节点", changes proposal does NOT claim it as state change
    chapter_prose = """
林越穿过咸水巷，独自进入了地下暗渠节点。这是他第一次踏足这个隐秘区域。

<chapter_changes>
{
  "character_state_changes": [
    {"character_id": "林越", "new_state": "进入暗渠", "importance": "normal"}
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
"""
    gate_res = run_changes_gate(chapter_text=chapter_prose, db_path=db_path, state_path=state_file, chapter=1)
    assert gate_res.passed is True

    # Step 3 & 4: Data Agent observed "地下暗渠节点" in entity_deltas, commit accepted and projected
    commit_payload = {
        "meta": {"schema_version": "story-system/v1", "chapter": 1, "status": "accepted"},
        "extraction_result": {
            "chapter_meta": {"chapter": 1, "title": "第1章"},
            "accepted_events": [],
            "state_deltas": [],
            "entity_deltas": [
                {
                    "entity_name": "地下暗渠节点",
                    "entity_type": "location",
                    "description": "咸水巷地下的未标记暗渠枢纽",
                    "chapter": 1,
                }
            ],
        },
    }

    story_sys = tmp_path / ".story-system"
    story_sys.mkdir(parents=True)
    writer = IndexProjectionWriter(tmp_path)
    with canonical_projection_write_scope(tmp_path):
        writer._apply_accepted_commit(commit_payload)

    # Step 5: In Chapter 2, "地下暗渠节点" is now in index.db ledger!
    # Therefore, a subsequent chapter state change on "地下暗渠节点" passes R3!
    ch2_changes = {
        "location_state_changes": [
            {"location_id": "地下暗渠节点", "new_state": "水位暴涨封锁", "importance": "normal"}
        ]
    }
    failures = check_r03_entities(ch2_changes, db_path, state_file)
    assert failures == []
