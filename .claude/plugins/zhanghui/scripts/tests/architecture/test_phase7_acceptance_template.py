"""H1 acceptance manifest template must not claim results about itself."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
MANIFEST = ROOT / "docs/superpowers/acceptance/2026-10-06-phase-7-final-acceptance.md"


def test_h1_acceptance_template_is_complete_and_result_free():
    assert MANIFEST.is_file()
    text = MANIFEST.read_text(encoding="utf-8")
    for required in ("baseline SHA", "exact commands", "writer coverage", "reader coverage",
                     "bypass reproduction", "CHANGES denominators", "INSUFFICIENT",
                     "source/mode matrix", "reviewer verdict", "known limits", "git diff --check"):
        assert required.lower() in text.lower(), required
    assert "tested_implementation_head:" not in text
    assert "PASS — Phase 7" not in text
    assert "reviewer verdict: PASS" not in text


def test_h1_acceptance_commands_reference_existing_test_files():
    text = MANIFEST.read_text(encoding="utf-8")
    for relative in (
        ".claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_inventory.py",
        ".claude/plugins/zhanghui/scripts/tests/architecture/test_ownership_documentation.py",
        ".claude/plugins/zhanghui/scripts/tests/architecture/test_phase7_acceptance_template.py",
        ".claude/plugins/zhanghui/scripts/data_modules/tests/test_changes_shadow_report.py",
        ".claude/plugins/zhanghui/scripts/data_modules/tests/test_chapter_commit_service.py",
        ".claude/plugins/zhanghui/scripts/data_modules/tests/test_event_projection_router.py",
        ".claude/plugins/zhanghui/scripts/data_modules/tests/test_context_manager.py",
        ".claude/plugins/zhanghui/scripts/data_modules/tests/test_ownership_writer_bypass.py",
        ".claude/plugins/zhanghui/scripts/data_modules/tests/test_prompt_integrity.py",
        ".claude/plugins/zhanghui/scripts/data_modules/tests/test_projection_writers.py",
        ".claude/plugins/zhanghui/scripts/data_modules/tests/test_projections_cli.py",
    ):
        assert (ROOT / relative).is_file(), relative
        assert relative in text, relative
    assert "test_projection_rebuild.py" not in text
