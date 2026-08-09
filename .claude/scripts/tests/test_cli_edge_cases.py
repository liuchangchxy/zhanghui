"""集成测试：CLI 边界情况与现实 LLM 输出回归。"""
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
        # Bug 3/12 修复：不应再有 uncaught crash（exit code 应在 {0,1}）
        assert result.returncode in (0, 1), (
            f"Unexpected exit {result.returncode}: stderr={result.stderr}"
        )
        return json.loads(result.stdout)
    finally:
        chapter_file.unlink(missing_ok=True)


def make_chapter(changes_obj) -> str:
    return f"""# 第5章

<chapter_changes>
{json.dumps(changes_obj, ensure_ascii=False)}
</chapter_changes>
"""


def test_db_is_directory(tmp_path: Path):
    """Bug 12: --db 指向目录不应崩溃。"""
    dir_path = tmp_path / "is_dir"
    dir_path.mkdir()
    changes = {
        "character_state_changes": [{"character_id": "Z-999", "importance": "important"}],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), dir_path)
    # 应正常返回 JSON（不必通过 R3 等规则）
    assert "passed" in result
    assert "failures" in result


def test_chapter_file_is_directory(tmp_path: Path):
    """Bug 12: --chapter-file 指向目录不应崩溃。"""
    dir_path = tmp_path / "chap_dir"
    dir_path.mkdir()
    cmd = [
        sys.executable, str(GATE_SCRIPT),
        "--chapter-file", str(dir_path),
        "--db", str(tmp_path / "dummy.db"),
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # 必须返回 exit 1 而非 traceback
    assert result.returncode in (0, 1), f"Unexpected exit code: {result.stderr}"
    # 如果输出 JSON，含 R0 报错
    if result.stdout.strip():
        data = json.loads(result.stdout)
        assert data["passed"] is False
        assert any("R0" in f["rule_id"] for f in data["failures"])


def test_chapter_file_not_exists(tmp_path: Path):
    """MAJOR: --chapter-file 不存在应给清晰错误信息而非 traceback。"""
    cmd = [
        sys.executable, str(GATE_SCRIPT),
        "--chapter-file", str(tmp_path / "does_not_exist.md"),
        "--db", str(tmp_path / "dummy.db"),
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode in (0, 1)
    if result.stdout.strip():
        data = json.loads(result.stdout)
        assert data["passed"] is False


def test_no_rule_argument_accepts(test_db: Path):
    """回归: 不传 --rule 时跑全部规则，合法 CHANGES 应通过。"""
    changes = {f: [] for f in [
        "character_state_changes", "new_plot_points", "foreshadowing_actions",
        "location_state_changes", "faction_state_changes",
        "item_transfers", "unresolved_questions"
    ]}
    changes["time_progression"] = None
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is True, result


# === Bug E 回归（第一性原理 A5.3）：恢复并真正实现 --rule 过滤 ===
def test_rule_flag_filters_to_only_r1(test_db: Path):
    """同时违反 R1（缺字段）+ R2（错枚举）+ R3（错 ID）时，--rule R1 应只保留 R1。"""
    # 故意触发多个规则
    changes = {
        "character_state_changes": [{"character_id": "Z-999", "importance": "BAD_ENUM"}],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [],
        # 缺 unresolved_questions → R1
    }
    result = run_gate(make_chapter(changes), test_db, "--rule", "R1")
    assert result["passed"] is False
    assert {f["rule_id"] for f in result["failures"]} == {"R1"}, result


def test_rule_flag_filters_to_multiple_rules(test_db: Path):
    """--rule R2,R3 应同时报告两类违规。"""
    changes = {
        "character_state_changes": [{"character_id": "Z-999", "importance": "BAD_ENUM"}],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [],
        "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db, "--rule", "R2,R3")
    assert result["passed"] is False
    rule_ids = {f["rule_id"] for f in result["failures"]}
    assert rule_ids == {"R2", "R3"}, result


def test_rule_flag_unknown_value_raises_r0(test_db: Path):
    """未知规则名是新的攻击向量（把所有 failure 过滤光 → 静默通过），必须 R0 loud fail。"""
    changes = {f: [] for f in [
        "character_state_changes", "new_plot_points", "foreshadowing_actions",
        "location_state_changes", "faction_state_changes",
        "item_transfers", "unresolved_questions"
    ]}
    changes["time_progression"] = None
    result = run_gate(make_chapter(changes), test_db, "--rule", "R99")
    assert result["passed"] is False
    assert any(f["rule_id"] == "R0" and "未知规则" in f["message"]
               for f in result["failures"]), result


def test_rule_flag_keeps_r0_even_when_filtered_out(test_db: Path):
    """R0（基础设施错误）必须永远保留，否则 --rule R1 会藏起解析错误。"""
    # 不含 <chapter_changes> → 触发 R0
    chapter = "# 第1章\n散文中没有任何 CHANGES 容器\n"
    result = run_gate(chapter, test_db, "--rule", "R3")
    assert result["passed"] is False
    assert any(f["rule_id"] == "R0" for f in result["failures"]), result
    # R3 不应被触发（没人引用）
    assert not any(f["rule_id"] == "R3" for f in result["failures"])


def test_trailing_comma_passes(test_db: Path):
    """Bug 5: 末尾逗号应被修复。"""
    chapter = """# 第5章

<chapter_changes>
{
  "character_state_changes": [],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": [],
}
</chapter_changes>
"""
    result = run_gate(chapter, test_db)
    assert result["passed"] is True, result


def test_missing_table_does_not_crash(tmp_path: Path):
    """Bug 3: db 文件存在但无 tables 时不应崩溃。"""
    import sqlite3
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(db_path)
    conn.close()  # 真正的空 db

    changes = {
        "character_state_changes": [{"character_id": "C-001", "importance": "important"}],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), db_path)
    # 不应 crash；passed 取决于 R3 是否触发（空 db → 不触发）
    assert "passed" in result
