from scripts.consistency.patches.p5_state_revision import P5StateRevision
from scripts.consistency.core.patch_base import CheckContext, ApplyContext, PatchFinding
from pathlib import Path


def _ctx(state, chapter=10):
    return CheckContext(project_root=Path("/tmp"), chapter_num=chapter, state=state, chapter_outline=None, previous_chapters=[], chapter_text=None)


def test_no_expected_revision_passes():
    """If caller didn't set _expected_revision, skip the check."""
    p = P5StateRevision()
    state = {"state": {"_revision": 15}}
    findings = p.check(_ctx(state))
    assert findings == []


def test_matching_revision_passes():
    p = P5StateRevision()
    state = {"state": {"_revision": 15}, "_expected_revision": 15}
    findings = p.check(_ctx(state))
    assert findings == []


def test_stale_revision_blocks():
    p = P5StateRevision()
    state = {"state": {"_revision": 15}, "_expected_revision": 10}
    findings = p.check(_ctx(state))
    assert len(findings) == 1
    assert "不匹配" in findings[0].message or "stale" in findings[0].message.lower()
    assert "10" in findings[0].message
    assert "15" in findings[0].message


def test_revision_mismatch_is_typed_and_bound_to_real_revision_record():
    p = P5StateRevision()
    state = {"state": {"_revision": 15}, "_expected_revision": 10}
    finding = p.check(_ctx(state))[0]
    assert isinstance(finding, PatchFinding)
    assert finding.issue_code == "revision_mismatch"
    assert finding.subject_id == "state:_revision"
    assert finding.evidence == {"expected_revision": 10, "observed_revision": 15}
    assert finding.input_ref == {"source": "state._revision", "expected_source": "_expected_revision"}
    assert finding.checker_id == "state_revision"
    assert state == {"state": {"_revision": 15}, "_expected_revision": 10}


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
