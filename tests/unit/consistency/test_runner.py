"""Tests for ConsistencyRunner orchestrator.

Source: original
Path in references: N/A
"""
from scripts.consistency.core.runner import ConsistencyRunner
from scripts.consistency.core.patch_base import Patch, CheckContext, ApplyContext, Blocker
from pathlib import Path


class CleanPatch(Patch):
    name = "clean"
    description = "always passes"
    depends_on = ()
    def check(self, ctx): return []
    def apply(self, ctx): pass


class FailingPatch(Patch):
    name = "failing"
    description = "always fails"
    depends_on = ()
    def check(self, ctx): return [Blocker(patch="failing", chapter=ctx.chapter_num, message="bad", fix_hint="fix")]
    def apply(self, ctx): pass


def test_runner_with_clean_patches():
    runner = ConsistencyRunner(project_root=Path("/tmp"), patches=[CleanPatch()])
    assert runner.run_all(chapter=1) == []


def test_runner_with_failing_patch():
    runner = ConsistencyRunner(project_root=Path("/tmp"), patches=[FailingPatch()])
    blockers = runner.run_all(chapter=1)
    assert len(blockers) == 1
    assert blockers[0].patch == "failing"


def test_runner_runs_all_patches():
    runner = ConsistencyRunner(project_root=Path("/tmp"), patches=[CleanPatch(), FailingPatch(), CleanPatch()])
    blockers = runner.run_all(chapter=1)
    assert len(blockers) == 1


def test_runner_uses_default_patches_when_none_given():
    runner = ConsistencyRunner(project_root=Path("/tmp"))
    import pytest
    with pytest.raises(NotImplementedError):
        runner.run_all(chapter=1)
