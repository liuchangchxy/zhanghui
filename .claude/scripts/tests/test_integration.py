"""集成测试——5 正例 + 5 反例对照。"""
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
GATE_SCRIPT = ROOT / "scripts" / "changes_gate.py"


def run_gate(chapter_text: str, db_path: Path, *extra_args: str) -> dict:
    chapter_file = Path(tempfile.gettempdir()) / f"_test_chapter_{uuid.uuid4().hex[:8]}.md"
    try:
        chapter_file.write_text(chapter_text, encoding="utf-8")
        cmd = [
            sys.executable, str(GATE_SCRIPT),
            "--chapter-file", str(chapter_file),
            "--db", str(db_path),
            "--json",
            *extra_args,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode not in (0, 1):
            pytest.fail(f"gate crashed: stderr={result.stderr}")
        return json.loads(result.stdout)
    finally:
        chapter_file.unlink(missing_ok=True)


def make_chapter(changes_obj) -> str:
    return f"""# 第5章

<chapter_changes>
{json.dumps(changes_obj, ensure_ascii=False)}
</chapter_changes>
"""


# 5 个正例
def test_positive_minimal_empty(test_db: Path):
    """最小合法 CHANGES：所有数组为空，time_progression=null。"""
    changes = {f: [] for f in [
        "character_state_changes", "new_plot_points", "foreshadowing_actions",
        "location_state_changes", "faction_state_changes",
        "item_transfers", "unresolved_questions"
    ]}
    changes["time_progression"] = None
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is True, result


def test_positive_known_entities(test_db: Path):
    changes = {
        "character_state_changes": [{"character_id": "C-001", "importance": "important"}],
        "new_plot_points": [],
        "foreshadowing_actions": [{"foreshadow_id": "F1-001", "action": "setup"}],
        "location_state_changes": [],
        "faction_state_changes": [],
        "time_progression": None,
        "item_transfers": [],
        "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is True, result


def test_positive_alias_reference(test_db: Path):
    """用 alias 而非 ID 也应该通过。"""
    changes = {
        "character_state_changes": [{"character_id": "陈默", "importance": "normal"}],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is True, result


def test_positive_small_trust_delta(test_db: Path):
    changes = {
        "character_state_changes": [{
            "character_id": "C-001",
            "relationship_changes": {"C-002": {"trust_delta": 5}},
            "importance": "important"
        }],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is True, result


def test_positive_valid_setup_action(test_db: Path):
    changes = {
        "character_state_changes": [], "new_plot_points": [],
        "foreshadowing_actions": [{"foreshadow_id": "F1-001", "action": "setup"}],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is True, result


# 5 个反例
def test_negative_missing_field(test_db: Path):
    """缺少必填字段。"""
    changes = {
        "character_state_changes": [], "new_plot_points": [],
        "foreshadowing_actions": [], "location_state_changes": [],
        "faction_state_changes": [], "time_progression": None,
        "unresolved_questions": []
        # 缺 item_transfers
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is False
    assert any("item_transfers" in f["message"] for f in result["failures"])


def test_negative_invalid_enum(test_db: Path):
    changes = {
        "character_state_changes": [{"importance": "very-important"}],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is False
    assert any(f["rule_id"] == "R2" for f in result["failures"])


def test_negative_unknown_entity(test_db: Path):
    changes = {
        "character_state_changes": [{"character_id": "Z-999"}],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is False
    assert any(f["rule_id"] == "R3" for f in result["failures"])


def test_negative_huge_trust_delta(test_db: Path):
    changes = {
        "character_state_changes": [{
            "character_id": "C-001",
            "relationship_changes": {"C-002": {"trust_delta": 100}}
        }],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is False
    assert any(f["rule_id"] == "R5" for f in result["failures"])


def test_negative_unknown_foreshadow(test_db: Path):
    changes = {
        "character_state_changes": [], "new_plot_points": [],
        "foreshadowing_actions": [{"foreshadow_id": "F9-999", "action": "setup"}],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is False
    assert any(f["rule_id"] == "R4" for f in result["failures"])