"""Tests for ConsistencyRunner orchestrator.

Source: original
Path in references: N/A
"""
import json
import tempfile
from pathlib import Path

from scripts.consistency.core.runner import ConsistencyRunner
from scripts.consistency.core.patch_base import Patch, CheckContext, ApplyContext, Blocker


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


class CrashingPatch(Patch):
    name = "crashing"
    description = "always raises in check"
    depends_on = ()
    def check(self, ctx): raise RuntimeError("boom")
    def apply(self, ctx): pass


class CrashingApplyPatch(Patch):
    name = "crashing_apply"
    description = "raises in apply"
    depends_on = ()
    def check(self, ctx): return []
    def apply(self, ctx): raise ValueError("apply kaboom")


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
    defaults = runner._default_patches()
    assert len(defaults) == 7
    names = [p.name for p in defaults]
    assert names == [
        "foreshadow_dag",
        "volume_anchor",
        "event_matrix",
        "pacing_tracker",
        "state_revision",
        "reader_contract",
        "derived_views",
    ]


def test_runner_default_patches_have_valid_dependencies():
    runner = ConsistencyRunner(project_root=Path("/tmp"))
    # Should not raise — every default patch's depends_on must resolve to a
    # patch registered in the default set. Catches typos / missing imports.
    defaults = runner._default_patches()
    assert all(isinstance(p, Patch) for p in defaults)


def test_runner_wraps_patch_check_exception():
    """Fix D: a crashing patch.check should not kill the whole runner."""
    runner = ConsistencyRunner(project_root=Path("/tmp"), patches=[CrashingPatch()])
    blockers = runner.run_all(chapter=1)
    assert len(blockers) == 1
    assert blockers[0].patch == "crashing"
    assert "crashed" in blockers[0].message
    assert "RuntimeError" in blockers[0].message


def test_runner_continues_after_patch_crash():
    runner = ConsistencyRunner(
        project_root=Path("/tmp"),
        patches=[CleanPatch(), CrashingPatch(), FailingPatch()],
    )
    blockers = runner.run_all(chapter=1)
    # CrashingPatch becomes 1 Blocker, FailingPatch becomes 1, CleanPatch is silent
    assert len(blockers) == 2
    patches_in_blockers = {b.patch for b in blockers}
    assert "crashing" in patches_in_blockers
    assert "failing" in patches_in_blockers


def test_runner_load_state_handles_corrupt_json():
    """Fix D: corrupt state.json should not raise; should report _load_error."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".webnovel").mkdir(parents=True)
        state_path = root / ".webnovel" / "state.json"
        state_path.write_text("this is not valid json {{{", encoding="utf-8")
        runner = ConsistencyRunner(project_root=root, patches=[CleanPatch()])
        # Should not raise
        blockers = runner.run_all(chapter=1)
        assert blockers == []  # CleanPatch returns [] regardless of state


def test_runner_load_state_handles_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        runner = ConsistencyRunner(project_root=root, patches=[CleanPatch()])
        blockers = runner.run_all(chapter=1)
        assert blockers == []


def test_runner_apply_all_pops_expected_revision():
    """Fix F: _expected_revision should be popped before save."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".webnovel").mkdir(parents=True)
        state_path = root / ".webnovel" / "state.json"
        state_path.write_text(
            json.dumps({"state": {"_revision": 0}, "_expected_revision": 99}, ensure_ascii=False),
            encoding="utf-8",
        )
        runner = ConsistencyRunner(project_root=root, patches=[CleanPatch()])
        runner.apply_all(chapter=1)
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        assert "_expected_revision" not in saved
        assert "_load_error" not in saved


def test_runner_apply_all_continues_after_apply_crash():
    """Fix D: a crashing patch.apply should not abort apply_all for the rest."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".webnovel").mkdir(parents=True)
        state_path = root / ".webnovel" / "state.json"
        state_path.write_text(json.dumps({}, ensure_ascii=False), encoding="utf-8")
        runner = ConsistencyRunner(
            project_root=root,
            patches=[CleanPatch(), CrashingApplyPatch(), CleanPatch()],
        )
        # Should not raise
        runner.apply_all(chapter=1)
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        assert "_apply_errors" in saved
        assert any("crashing_apply" in err for err in saved["_apply_errors"])


def test_runner_save_state_uses_atomic_when_available(monkeypatch):
    """Fix A: when security_utils is importable, _save_state delegates to atomic_write_json."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".webnovel").mkdir(parents=True)
        called = {"count": 0, "lock": None, "backup": None}

        def fake_atomic(path, data, *, use_lock=True, backup=True):
            called["count"] += 1
            called["lock"] = use_lock
            called["backup"] = backup
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        # Force the importer to return our fake
        import scripts.consistency.core.runner as runner_mod
        monkeypatch.setattr(runner_mod, "_import_atomic_write_json", lambda: fake_atomic)
        runner = ConsistencyRunner(project_root=root, patches=[CleanPatch()])
        runner.apply_all(chapter=1)
        assert called["count"] == 1
        assert called["lock"] is True
        assert called["backup"] is True
