"""End-to-end: init → --all-volumes plan → pre-write gate check.

Spec 2026-08-19 §6: full flow from init to BLOCKER clearance.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from init_project import init_project, generate_volume_blueprints
from data_modules.volume_state import VolumeStateManager
from data_modules.promise_ledger import ForeshadowEntry, ForeshadowStatus
from data_modules.chunked_write import evaluate_pre_write_gates


def test_e2e_full_flow(tmp_path):
    """Init 3-volume project → --all-volumes → upsert overdue foreshadow → BLOCKER → payoff clears."""
    # Init
    init_project(
        project_dir=str(tmp_path),
        title="E2E Macro-Micro", genre="玄幻",
        target_chapters=240, target_words=720000,
        volume_skeleton=[
            {"index": 1, "title": "V1", "chapter_range": [1, 80],
             "core_conflict": "A", "climax": "B",
             "status": "confirmed", "source": "human"},
            {"index": 2, "title": "V2", "chapter_range": [81, 160],
             "core_conflict": "C", "climax": "D",
             "status": "confirmed", "source": "human"},
            {"index": 3, "title": "V3", "chapter_range": [161, 240],
             "core_conflict": "E", "climax": "F",
             "status": "confirmed", "source": "human"},
        ],
    )

    # --all-volumes plan stage
    written = generate_volume_blueprints(tmp_path, all_volumes=True)
    assert written == 3
    for vol in (1, 2, 3):
        assert (tmp_path / "大纲" / f"第{vol}卷-详细大纲.md").is_file()
        assert (tmp_path / "大纲" / f"第{vol}卷-15节拍.md").is_file()
        assert (tmp_path / "大纲" / f"第{vol}卷-时间线.md").is_file()

    # Upsert overdue foreshadow: planted V1, expected payoff V2 ch100
    state_path = tmp_path / ".webnovel" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    mgr = VolumeStateManager(state)
    mgr.upsert_promise_entry(ForeshadowEntry(
        id="fs_e2e", type="foreshadow", depth=2,
        planted_chapter=10, planted_volume=1,
        expected_payoff_chapter=100, expected_payoff_volume=2,
        status=ForeshadowStatus.PENDING,
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
    ))
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # Pre-write gate at V2 ch110: BLOCKER expected (payoff missed)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    mgr = VolumeStateManager(state)
    overdue = mgr.list_overdue_foreshadows(current_chapter=110, current_volume=2)
    issues = evaluate_pre_write_gates(
        chapter=110, current_volume=2,
        overdue_foreshadows=overdue,
    )
    assert len(issues) == 1
    assert "fs_e2e" in issues[0]
    assert "BLOCKER" in issues[0]

    # Payoff → re-evaluate → no blocker
    mgr.payoff_foreshadow("fs_e2e", at_chapter=112)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    mgr = VolumeStateManager(state)
    overdue = mgr.list_overdue_foreshadows(current_chapter=112, current_volume=2)
    issues = evaluate_pre_write_gates(
        chapter=112, current_volume=2,
        overdue_foreshadows=overdue,
    )
    assert issues == []