from pathlib import Path
import tempfile

from scripts.consistency.patches.p7_derived_views import P7DerivedViews
from scripts.consistency.core.patch_base import CheckContext, ApplyContext, PatchFinding
from scripts.consistency.core.runner import ConsistencyRunner


def _ctx(state, project_root: Path, chapter=5):
    return CheckContext(project_root=project_root, chapter_num=chapter, state=state, chapter_outline=None, previous_chapters=[], chapter_text=None)


def test_check_passes_when_view_complete():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        views_dir = root / ".webnovel" / "views"
        views_dir.mkdir(parents=True)
        (views_dir / "foreshadow_table.md").write_text(
            "| ID | 内容 |\n| fs_001 | ok |\n| fs_002 | ok |\n",
            encoding="utf-8",
        )
        state = {
            "story_craft": {
                "foreshadow_chain": {
                    "dag": [
                        {"id": "fs_001", "content": "ok"},
                        {"id": "fs_002", "content": "ok"},
                    ]
                }
            }
        }
        p = P7DerivedViews()
        findings = p.check(_ctx(state, root))
        assert findings == []


def test_check_blocks_when_view_missing_fs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        views_dir = root / ".webnovel" / "views"
        views_dir.mkdir(parents=True)
        (views_dir / "foreshadow_table.md").write_text(
            "| ID | 内容 |\n| fs_001 | ok |\n",
            encoding="utf-8",
        )
        state = {
            "story_craft": {
                "foreshadow_chain": {
                    "dag": [
                        {"id": "fs_001", "content": "ok"},
                        {"id": "fs_005", "content": "missing"},
                    ]
                }
            }
        }
        p = P7DerivedViews()
        findings = p.check(_ctx(state, root))
        assert any("fs_005" in b.message for b in findings)


def test_missing_projection_row_is_typed_with_stable_subject_and_generation_without_repair():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        views_dir = root / ".webnovel" / "views"
        views_dir.mkdir(parents=True)
        view_path = views_dir / "foreshadow_table.md"
        view_path.write_text("| ID | 内容 |\n| fs_001 | ok |\n", encoding="utf-8")
        original_content = view_path.read_bytes()
        state = {
            "state": {"_revision": 17},
            "story_craft": {"foreshadow_chain": {"dag": [{"id": "fs_001"}, {"id": "fs_005"}]}},
        }
        findings = P7DerivedViews().check(_ctx(state, root))
        finding = next(item for item in findings if item.issue_code == "missing_foreshadow_view_row")
        assert isinstance(finding, PatchFinding)
        assert finding.subject_id == "foreshadow:fs_005"
        assert finding.evidence == {"view": "foreshadow_table.md", "foreshadow_id": "fs_005",
                                   "present": False, "source_generation": 17}
        assert finding.input_ref["source"] == str(view_path)
        assert view_path.read_bytes() == original_content


def test_check_uses_runner_captured_view_snapshot_for_fingerprint_consistency(tmp_path):
    views_dir = tmp_path / ".webnovel" / "views"
    views_dir.mkdir(parents=True)
    view_path = views_dir / "foreshadow_table.md"
    view_path.write_text("F1", encoding="utf-8")
    ctx = CheckContext(
        project_root=tmp_path, chapter_num=5,
        state={"story_craft": {"foreshadow_chain": {"dag": [{"id": "F1"}]}}},
        chapter_outline=None, previous_chapters=[], chapter_text=None,
        external_inputs={"foreshadow_table.md": {"present": True, "content": "F1"}},
    )
    view_path.write_text("", encoding="utf-8")
    assert P7DerivedViews().check(ctx) == []


def test_check_reports_missing_projection_when_views_dir_missing():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = {"story_craft": {"foreshadow_chain": {"dag": [{"id": "fs_001"}]}}}
        p = P7DerivedViews()
        findings = p.check(_ctx(state, root))
        assert [(item.issue_code, item.subject_id) for item in findings] == [
            ("missing_foreshadow_view_row", "foreshadow:fs_001"),
        ]


def test_runner_snapshot_of_missing_view_does_not_reread_a_later_file(tmp_path):
    patch = P7DerivedViews()
    runner = ConsistencyRunner(tmp_path, patches=[patch])
    diagnostics = []
    snapshot = runner._capture_external_inputs(patch, diagnostics)
    view = tmp_path / ".webnovel" / "views" / "foreshadow_table.md"
    view.parent.mkdir(parents=True)
    view.write_text("F1", encoding="utf-8")
    context = CheckContext(
        project_root=tmp_path, chapter_num=5,
        state={"story_craft": {"foreshadow_chain": {"dag": [{"id": "F1"}]}}},
        chapter_outline=None, previous_chapters=[], chapter_text=None, external_inputs=snapshot,
    )
    findings = patch.check(context)
    assert [item.issue_code for item in findings] == ["missing_foreshadow_view_row"]


def test_check_no_false_positive_with_substring():
    """fs_1 should not match fs_10 in view."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        views_dir = root / ".webnovel" / "views"
        views_dir.mkdir(parents=True)
        (views_dir / "foreshadow_table.md").write_text(
            "| ID | 内容 |\n| fs_10 | unrelated |\n",
            encoding="utf-8",
        )
        state = {
            "story_craft": {
                "foreshadow_chain": {
                    "dag": [{"id": "fs_1", "content": "ok"}]
                }
            }
        }
        p = P7DerivedViews()
        findings = p.check(_ctx(state, root))
        assert any("fs_1" in b.message for b in findings)


def test_apply_generates_foreshadow_table():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = {
            "story_craft": {
                "foreshadow_chain": {
                    "dag": [
                        {"id": "fs_001", "content": "伏笔1", "level": "表层", "planted_chapter": 1, "paid_off_chapter": None, "status": "active"},
                        {"id": "fs_002", "content": "伏笔2", "level": "中层", "planted_chapter": 3, "paid_off_chapter": 5, "status": "active"},
                    ]
                }
            }
        }
        ctx = ApplyContext(project_root=root, chapter_num=5, state=state)
        P7DerivedViews().apply(ctx)

        view_path = root / ".webnovel" / "views" / "foreshadow_table.md"
        assert view_path.exists()
        content = view_path.read_text(encoding="utf-8")
        assert "fs_001" in content
        assert "fs_002" in content
        assert "伏笔1" in content
        assert "伏笔2" in content
