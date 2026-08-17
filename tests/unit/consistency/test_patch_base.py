from scripts.consistency.core.patch_base import Patch, Blocker, CheckContext, ApplyContext
from pathlib import Path
import pytest

def test_blocker_construction():
    b = Blocker(patch="test", chapter=1, message="bad", fix_hint="fix it")
    assert b.patch == "test"
    assert b.chapter == 1
    assert b.message == "bad"
    assert b.fix_hint == "fix it"

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
