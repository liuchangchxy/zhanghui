from scripts.consistency.core.patch_base import Patch, CheckContext, ApplyContext, PatchFinding
from pathlib import Path
import pytest

def test_patch_finding_requires_typed_code_and_keeps_optional_subject_and_evidence():
    with pytest.raises(TypeError):
        PatchFinding(patch="event_matrix", chapter=1, message="quota")

    first = PatchFinding(patch="event_matrix", chapter=1, issue_code="gentle_quota", message="quota")
    second = PatchFinding(patch="event_matrix", chapter=1, issue_code="gentle_quota", message="quota")
    assert first.subject_id is None
    assert first.evidence == {}
    assert first.evidence is not second.evidence

    finding = PatchFinding(
        patch="event_matrix", chapter=1, issue_code="gentle_quota", message="quota",
        fix_hint="adjust pacing", evidence={"count": 2, "expected": 3},
        checker_id="consistency.event_matrix", checker_version="2", input_ref={"state_revision": 4},
    )
    assert finding.evidence == {"count": 2, "expected": 3}
    assert finding.checker_id == "consistency.event_matrix"
    assert finding.checker_version == "2"
    assert finding.input_ref == {"state_revision": 4}


def test_legacy_class_is_retired_from_live_consistency_boundary():
    scripts = Path(__file__).resolve().parents[3] / ".claude" / "plugins" / "zhanghui" / "scripts"
    legacy_name = "Block" + "er"
    for relative in (
        "consistency/core/patch_base.py",
        "consistency/core/runner.py",
        "data_modules/consistency_finding_adapters.py",
    ):
        assert legacy_name not in (scripts / relative).read_text(encoding="utf-8")

def test_check_context_construction():
    ctx = CheckContext(
        project_root=Path("/tmp"),
        chapter_num=1,
        state={"foo": 1},
        chapter_outline=None,
        previous_chapters=[],
        chapter_text=None,
    )
    assert ctx.chapter_num == 1
    assert ctx.state == {"foo": 1}

def test_patch_abc_cannot_instantiate():
    with pytest.raises(TypeError):
        Patch()

def test_concrete_patch_implements_interface():
    class MyPatch(Patch):
        name = "my"
        description = "test"
        depends_on = ()
        def check(self, ctx): return []
        def apply(self, ctx): pass

    p = MyPatch()
    assert p.check(CheckContext(project_root=Path("/tmp"), chapter_num=1, state={}, chapter_outline=None, previous_chapters=[], chapter_text=None)) == []
