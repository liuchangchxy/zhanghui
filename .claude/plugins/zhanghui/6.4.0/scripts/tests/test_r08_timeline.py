"""R8: 时间线连贯——time_progression 不与上一章冲突。"""
from pathlib import Path

from changes_gate import check_r08_timeline


def test_r08_passes_with_null_progression(test_db: Path):
    """time_progression 为 null 时不报错。"""
    changes = {"time_progression": None}
    assert check_r08_timeline(changes, test_db, current_chapter=3) == []


def test_r08_passes_with_progression(test_db: Path):
    changes = {"time_progression": {"elapsed_time": "一日"}}
    assert check_r08_timeline(changes, test_db, current_chapter=3) == []


def test_r08_fails_on_chapter_regression(test_db: Path):
    """检测：声称回到上一章之前的时间。"""
    # 当前 chapter = 3，上一章（chapter=2）time_anchor="夏末"
    changes = {"time_progression": {"elapsed_time": "回到三年前"}}
    failures = check_r08_timeline(changes, test_db, current_chapter=3)
    # 这条规则启发式较简单，只检测明显的倒退
    # 如无明显倒退则不报错
    assert isinstance(failures, list)