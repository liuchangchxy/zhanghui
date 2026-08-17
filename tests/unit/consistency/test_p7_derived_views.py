from pathlib import Path
import tempfile

from scripts.consistency.patches.p7_derived_views import P7DerivedViews
from scripts.consistency.core.patch_base import CheckContext, ApplyContext


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
        blockers = p.check(_ctx(state, root))
        assert blockers == []


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
        blockers = p.check(_ctx(state, root))
        assert any("fs_005" in b.message for b in blockers)


def test_check_passes_when_views_dir_missing():
    """If views/ doesn't exist, derived views are disabled → skip."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = {"story_craft": {"foreshadow_chain": {"dag": [{"id": "fs_001"}]}}}
        p = P7DerivedViews()
        blockers = p.check(_ctx(state, root))
        assert blockers == []


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
