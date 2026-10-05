"""Tests for ConsistencyRunner orchestrator.

Source: original
Path in references: N/A
"""
import json
import tempfile
from pathlib import Path

from scripts.consistency.core.runner import ConsistencyRunner
from scripts.consistency.core.patch_base import Patch, CheckContext, ApplyContext, PatchFinding
from copy import deepcopy


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
    def check(self, ctx): return [PatchFinding(patch="failing", chapter=ctx.chapter_num,
                                               issue_code="unknown_test_issue", message="bad",
                                               evidence={"reason": "test"})]
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


class CanonMutationPatch(Patch):
    name = "canon_mutation"
    description = "attempts to edit commit-owned state projections"
    depends_on = ()
    def __init__(self): self.called = False
    def check(self, ctx): return []
    def apply(self, ctx):
        self.called = True
        ctx.state["entity_state"]["hero"]["realm"] = "伪造境界"
        ctx.state["progress"]["current_chapter"] = 999
        ctx.state["plot_threads"]["foreshadowing"].append({"content": "绕过提交"})
        ctx.state["story_craft"]["volume_anchors"]["anchors"].append({"volume": 2})


def test_runner_with_clean_patches():
    runner = ConsistencyRunner(project_root=Path("/tmp"), patches=[CleanPatch()])
    result = runner.run_all(chapter=1)
    assert result.findings == []
    assert result.status == "evaluated"
    assert result.source_input_fingerprint


def test_runner_source_fingerprint_includes_checker_version():
    patch = StaticFindingPatch()
    runner = ConsistencyRunner(project_root=Path("/tmp"), patches=[patch])
    first = runner.run_all(chapter=1)
    patch.checker_version = "2"
    second = runner.run_all(chapter=1)
    assert first.source_input_fingerprint != second.source_input_fingerprint
    assert second.findings[0].checker_version == "2"


def test_runner_can_execute_only_the_requested_patch():
    runner = ConsistencyRunner(project_root=Path("/tmp"), patches=[CrashingPatch(), CleanPatch()])
    result = runner.run_all(chapter=1, patch_names={"clean"})
    assert result.status == "evaluated"
    assert result.findings == []
    assert result.diagnostics == []


def test_runner_with_failing_patch():
    runner = ConsistencyRunner(project_root=Path("/tmp"), patches=[FailingPatch()])
    result = runner.run_all(chapter=1)
    assert len(result.findings) == 1
    assert result.findings[0].patch == "failing"


def test_runner_runs_all_patches():
    runner = ConsistencyRunner(project_root=Path("/tmp"), patches=[CleanPatch(), FailingPatch(), CleanPatch()])
    result = runner.run_all(chapter=1)
    assert len(result.findings) == 1


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
    """A patch crash is incomplete infrastructure status, not a story finding."""
    runner = ConsistencyRunner(project_root=Path("/tmp"), patches=[CrashingPatch()])
    result = runner.run_all(chapter=1)
    assert result.status == "incomplete"
    assert result.findings == []
    assert result.diagnostics[0].checker_id == "crashing"
    assert result.diagnostics[0].error_type == "RuntimeError"
    assert not hasattr(result, "policy_action")


def test_runner_continues_after_patch_crash():
    runner = ConsistencyRunner(
        project_root=Path("/tmp"),
        patches=[CleanPatch(), CrashingPatch(), FailingPatch()],
    )
    result = runner.run_all(chapter=1)
    assert result.status == "incomplete"
    assert len(result.findings) == 1
    assert result.findings[0].patch == "failing"
    assert {diagnostic.checker_id for diagnostic in result.diagnostics} == {"crashing"}


def test_runner_load_state_handles_corrupt_json():
    """Fix D: corrupt state.json should not raise; should report _load_error."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".webnovel").mkdir(parents=True)
        state_path = root / ".webnovel" / "state.json"
        state_path.write_text("this is not valid json {{{", encoding="utf-8")
        runner = ConsistencyRunner(project_root=root, patches=[CleanPatch()])
        # Should not raise
        result = runner.run_all(chapter=1)
        assert result.status == "incomplete"
        assert result.findings == []
        assert result.diagnostics[0].error_type == "JSONDecodeError"


def test_runner_load_state_handles_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        runner = ConsistencyRunner(project_root=root, patches=[CleanPatch()])
        result = runner.run_all(chapter=1)
        assert result.status == "evaluated"
        assert result.findings == []


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
        outcomes = runner.apply_all(chapter=1)
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        assert "_apply_errors" in saved
        assert any("crashing_apply" in err for err in saved["_apply_errors"])
        assert [(item.patch, item.status, item.error_type) for item in outcomes] == [
            ("clean", "applied", None), ("crashing_apply", "failed", "ValueError"), ("clean", "applied", None),
        ]


def test_runner_apply_corrupt_state_reports_failure_without_overwriting(tmp_path):
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True)
    original = "{bad state"
    state_path.write_text(original, encoding="utf-8")
    outcomes = ConsistencyRunner(tmp_path, patches=[CleanPatch()]).apply_all(chapter=1)
    assert [(item.patch, item.status, item.error_type) for item in outcomes] == [
        ("consistency.runner", "failed", "JSONDecodeError"),
    ]
    assert state_path.read_text(encoding="utf-8") == original


def test_runner_apply_all_preserves_commit_owned_state_projections():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".webnovel").mkdir(parents=True)
        state_path = root / ".webnovel" / "state.json"
        original = {
            "entity_state": {"hero": {"realm": "斗者"}},
            "progress": {"current_chapter": 4},
            "plot_threads": {"foreshadowing": [{"content": "已有伏笔"}]},
            "story_craft": {"volume_anchors": {"anchors": []}},
        }
        state_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
        ConsistencyRunner(root, patches=[CanonMutationPatch()]).apply_all(chapter=5)

        saved = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved["entity_state"] == original["entity_state"]
        assert saved["progress"] == original["progress"]
        assert saved["plot_threads"] == original["plot_threads"]
        assert saved["story_craft"]["volume_anchors"]["anchors"] == [{"volume": 2}]


def test_story_system_apply_does_not_persist_any_patch_state(tmp_path):
    story_root = tmp_path / ".story-system"
    story_root.mkdir()
    (story_root / "MASTER_SETTING.json").write_text("{}", encoding="utf-8")
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True)
    original = {
        "entity_state": {"hero": {"realm": "斗者"}},
        "progress": {"current_chapter": 4},
        "plot_threads": {"foreshadowing": []},
        "story_craft": {"volume_anchors": {"anchors": [{"current_chapter": 4}]}, "foreshadow_chain": []},
        "state": {"_revision": 7},
    }
    state_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

    patch = CanonMutationPatch()
    ConsistencyRunner(tmp_path, patches=[patch]).apply_all(chapter=5)

    assert json.loads(state_path.read_text(encoding="utf-8")) == original
    assert patch.called is False


def test_legacy_apply_still_persists_patch_mutations(tmp_path):
    state_path = tmp_path / ".webnovel" / "state.json"
    state_path.parent.mkdir(parents=True)
    original = {
        "entity_state": {"hero": {"realm": "斗者"}},
        "progress": {"current_chapter": 4},
        "plot_threads": {"foreshadowing": []},
        "story_craft": {"volume_anchors": {"anchors": []}},
    }
    state_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

    ConsistencyRunner(tmp_path, patches=[CanonMutationPatch()]).apply_all(chapter=5)

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["story_craft"]["volume_anchors"]["anchors"] == [{"volume": 2}]


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


class StaticFindingPatch(Patch):
    name = "foreshadow_dag"
    description = "returns a stable observation for fingerprint tests"
    depends_on = ()
    def check(self, ctx):
        return [PatchFinding(patch=self.name, chapter=ctx.chapter_num, issue_code="missing_id",
                             message="same", evidence={"missing_indices": [0], "count": 1})]
    def apply(self, ctx): pass


def test_source_fingerprint_tracks_actual_patch_inputs_not_findings_or_unused_context():
    runner = ConsistencyRunner(Path("/tmp"), patches=[StaticFindingPatch()])
    state_a = {"story_craft": {"foreshadow_chain": [{"description": "source A"}]}, "unused": "A"}
    state_b = {"story_craft": {"foreshadow_chain": [{"description": "source B"}]}, "unused": "A"}
    first = runner.run_all(1, state=state_a, chapter_outline={"unused": 1}, previous_chapters=[{"unused": 1}])
    same_inputs = runner.run_all(1, state={**state_a, "unused": "B"}, chapter_outline={"unused": 2}, previous_chapters=[])
    changed_source = runner.run_all(1, state=state_b)
    changed_chapter = runner.run_all(2, state=state_a)
    assert first.findings[0].evidence == changed_source.findings[0].evidence
    assert first.source_input_fingerprint == same_inputs.source_input_fingerprint
    assert first.source_input_fingerprint != changed_source.source_input_fingerprint
    assert first.source_input_fingerprint != changed_chapter.source_input_fingerprint
    assert first.findings[0].input_ref["source_input_fingerprint"] == first.source_input_fingerprint


def test_runner_fingerprints_chapter_text_and_external_view_content_when_read(tmp_path):
    from scripts.consistency.patches.p2_volume_anchor import P2VolumeAnchor
    from scripts.consistency.patches.p7_derived_views import P7DerivedViews

    state = {"story_craft": {"volume_anchors": {"anchors": []},
                             "foreshadow_chain": {"dag": [{"id": "F1"}]}}}
    p2_runner = ConsistencyRunner(tmp_path, patches=[P2VolumeAnchor()])
    first_text = p2_runner.run_all(1, state=state, chapter_text="text A")
    second_text = p2_runner.run_all(1, state=state, chapter_text="text B")
    assert first_text.source_input_fingerprint != second_text.source_input_fingerprint

    view = tmp_path / ".webnovel" / "views" / "foreshadow_table.md"
    view.parent.mkdir(parents=True)
    view.write_text("F1", encoding="utf-8")
    p7_runner = ConsistencyRunner(tmp_path, patches=[P7DerivedViews()])
    first_view = p7_runner.run_all(1, state=state)
    view.write_text("F1 F2", encoding="utf-8")
    second_view = p7_runner.run_all(1, state=state)
    assert first_view.source_input_fingerprint != second_view.source_input_fingerprint


def test_runner_normalizes_all_default_producers_and_binds_source_fingerprint(tmp_path):
    from scripts.consistency.patches.p1_foreshadow_dag import P1ForeshadowDAG
    from scripts.consistency.patches.p2_volume_anchor import P2VolumeAnchor
    from scripts.consistency.patches.p3_event_matrix import P3EventMatrix
    from scripts.consistency.patches.p4_pacing_tracker import P4PacingTracker
    from scripts.consistency.patches.p5_state_revision import P5StateRevision
    from scripts.consistency.patches.p6_reader_contract import P6ReaderContract
    from scripts.consistency.patches.p7_derived_views import P7DerivedViews

    state = {
        "_expected_revision": 1,
        "state": {"_revision": 2},
        "story_craft": {
            "foreshadow_chain": {"dag": [{"id": "A", "depends_on": ["B"]}, {"id": "B", "depends_on": ["A"]}]},
            "volume_anchors": {"anchors": [{"volume": 1, "total_chapters": 10, "current_chapter": 1}]},
            "event_matrix_state": {"history": [{"primary": "conflict_thrill"}] * 5},
            "pacing_history": {"history": [{"tier": "fast"}] * 4},
            "reader_contract": {"expectation_debt": [{"satisfied_chapter": None}] * 11},
        },
    }
    before = deepcopy(state)
    view = tmp_path / ".webnovel" / "views" / "foreshadow_table.md"
    view.parent.mkdir(parents=True)
    view.write_text("", encoding="utf-8")
    patches = [P1ForeshadowDAG(), P2VolumeAnchor(), P3EventMatrix(), P4PacingTracker(),
               P5StateRevision(), P6ReaderContract(), P7DerivedViews()]
    result = ConsistencyRunner(tmp_path, patches=patches).run_all(100, state=state, chapter_text="unused")
    assert result.status == "evaluated"
    assert {finding.patch for finding in result.findings} == {patch.name for patch in patches}
    assert all(finding.input_ref["source_input_fingerprint"] == result.source_input_fingerprint
               for finding in result.findings)
    assert state == before
