from dataclasses import fields
from pathlib import Path

from data_modules.canon_correction_resolver import EffectiveHistoryResult


ROOT = Path(__file__).resolve().parents[6]
TEMPLATE = ROOT / "docs/superpowers/acceptance/2026-10-06-phase-8-h1-acceptance-template.md"


def test_phase9_handoff_consumes_only_the_effective_history_result_contract():
    names = {field.name for field in fields(EffectiveHistoryResult)}
    assert names == {"ok", "chapter", "base_commit_sha256", "effective_revision_id", "effective_status",
                     "effective_extraction_result", "applied_correction_ids", "effective_content_sha256", "diagnostics"}


def test_h1_acceptance_template_is_result_free_and_non_self_referential():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "tested_implementation_head: \"\"" in text
    assert "tested_implementation_tree: \"\"" in text
    assert "tested_implementation_head: 28" not in text
    for field in ("focused_correction_tests", "git_diff_check_result", "accepted_base_unchanged", "normal_runtime_unchanged"):
        assert f'{field}: ""' in text
    assert "HUMAN APPROVAL CONFIRMED" not in text
    assert "test-only verification fixtures are not project or user approval evidence" in text


def test_h1_does_not_include_the_result_filled_h2_record():
    h2 = ROOT / "docs/superpowers/acceptance/2026-10-06-phase-8-final-acceptance.md"
    assert not h2.exists()
