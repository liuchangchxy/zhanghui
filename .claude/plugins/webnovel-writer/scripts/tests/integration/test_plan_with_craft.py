import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from story_craft import (
    init_story_craft, init_volume_beat, fill_beat,
    add_foreshadow, payoff_foreshadow, add_timed_lock,
    record_emotion_peak, set_chapter_meta, check_volume_beat,
    add_thematic_echo, set_character_arc,
)


def test_full_volume_plan_flow():
    """Simulate a complete volume plan with all craft mechanisms."""
    # 1. Init state
    state = init_story_craft("/tmp/dummy.json")
    state["project_info"] = {"genre": "玄幻", "target_chapters": 50}
    state["progress"] = {"current_volume": 1, "volumes_planned": []}

    # 2. Init volume beat
    init_volume_beat(state, volume=1, total_chapters=50)

    # 3. Fill critical beats
    fill_beat(state, volume=1, beat_name="Midpoint", chapter=25, notes="假胜利")
    fill_beat(state, volume=1, beat_name="All Is Lost", chapter=37, notes="师尊陨落")
    fill_beat(state, volume=1, beat_name="Final Image", chapter=50, notes="新卷开场")

    # 4. Verify no BLOCKER
    issues = check_volume_beat(state, volume=1)
    blockers = [i for i in issues if "BLOCKER" in i]
    assert blockers == [], f"Unexpected blockers: {blockers}"

    # 5. Add foreshadows (3 layers)
    add_foreshadow(state, {
        "type": "物谶", "depth": "表层",
        "buried_chapter": 1, "expected_payoff_chapter": 2,
        "content": "新手卡"
    })
    add_foreshadow(state, {
        "type": "物谶", "depth": "中层",
        "buried_chapter": 5, "expected_payoff_chapter": 25,
        "content": "神秘令牌"
    })
    add_foreshadow(state, {
        "type": "习惯", "depth": "深层",
        "buried_chapter": 1, "expected_payoff_chapter": 50,
        "content": "主角下意识动作"
    })
    assert len(state["story_craft"]["foreshadow_chain"]) == 3

    # 6. Pay off mid-level foreshadow
    payoff_foreshadow(state, "FS-002", chapter=25, quality="强")

    # 7. Add timed locks
    add_timed_lock(state, {"description": "主角 3 章内出村", "deadline_chapter": 3})
    add_timed_lock(state, {"description": "Midpoint 必须反转", "deadline_chapter": 25})

    # 8. Record rhythm
    record_emotion_peak(state, chapter=5, intensity=7, type_="medium_cool_point")

    # 9. Set chapter meta with full Scene-Sequel
    set_chapter_meta(
        state, chapter=5,
        beat_position="Setup",
        hook_type="悬念式",
        scene_goal="进入秘境",
        scene_conflict="守护者阻挡",
        scene_setback="被击退",
        scene_resolution="暂时撤退",
        sequel_reaction="分析弱点",
        sequel_dilemma="独自 vs 求援",
        sequel_decision="独自潜入",
        foreshadow_buried=["FS-002"]
    )

    # 10. Character arc + thematic echoes
    set_character_arc(state, {
        "name": "林川",
        "starting_state": "归乡迷茫",
        "ending_state": "接受本源",
        "transformation": "通过卡池觉醒"
    })
    add_thematic_echo(state, premise="真正的强大是记忆而非力量",
                      chapter=5, manifestation="回忆根源时力量觉醒")

    # 11. Verify all data persisted in state
    assert state["story_craft"]["foreshadow_chain"][1]["status"] == "paid_off"
    assert state["chapter_meta"]["5"]["hook_type"] == "悬念式"
    assert state["chapter_meta"]["5"]["scene_goal"] == "进入秘境"
    assert state["chapter_meta"]["5"]["foreshadow_buried"] == ["FS-002"]
    assert state["story_craft"]["volume_beat"]["beats"][8]["filled"] is True
    assert state["story_craft"]["character_arc"]["name"] == "林川"
    assert len(state["story_craft"]["thematic_echoes"]) == 1
    assert state["story_craft"]["timed_locks"][0]["description"] == "主角 3 章内出村"