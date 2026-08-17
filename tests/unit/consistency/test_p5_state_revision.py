from scripts.consistency.patches.p5_state_revision import P5StateRevision
from scripts.consistency.core.patch_base import CheckContext, ApplyContext
from pathlib import Path


def _ctx(state, chapter=10):
    return CheckContext(project_root=Path("/tmp"), chapter_num=chapter, state=state, chapter_outline=None, previous_chapters=[], chapter_text=None)


def test_no_expected_revision_passes():
    """If caller didn't set _expected_revision, skip the check."""
    p = P5StateRevision()
    state = {"state": {"_revision": 15}}
    blockers = p.check(_ctx(state))
    assert blockers == []


def test_matching_revision_passes():
    p = P5StateRevision()
    state = {"state": {"_revision": 15}, "_expected_revision": 15}
    blockers = p.check(_ctx(state))
    assert blockers == []


def test_stale_revision_blocks():
    p = P5StateRevision()
    state = {"state": {"_revision": 15}, "_expected_revision": 10}
    blockers = p.check(_ctx(state))
    assert len(blockers) == 1
    assert "不匹配" in blockers[0].message or "stale" in blockers[0].message.lower()
    assert "10" in blockers[0].message
    assert "15" in blockers[0].message


def test_apply_increments_revision():
    p = P5StateRevision()
    state = {"state": {"_revision": 5, "_last_modified_by": "old"}}
    ctx = ApplyContext(project_root=Path("/tmp"), chapter_num=10, state=state)
    p.apply(ctx)
    assert state["state"]["_revision"] == 6
    assert state["state"]["_last_modified_by"] == "webnovel-write/ch10"


def test_apply_works_when_state_field_missing():
    p = P5StateRevision()
    state = {}  # no "state" key
    ctx = ApplyContext(project_root=Path("/tmp"), chapter_num=5, state=state)
    p.apply(ctx)
    assert state["state"]["_revision"] == 1
    assert state["state"]["_last_modified_by"] == "webnovel-write/ch5"