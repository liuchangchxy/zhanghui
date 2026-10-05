import pytest
from pathlib import Path
from scripts.consistency.core.runner import ConsistencyRunner


FIXTURES = Path(__file__).parent.parent / "fixtures" / "cross_volume"


@pytest.mark.parametrize("fixture_name,chapter,expected_patch,expected_keyword", [
    ("project_clean", 5, None, None),
    ("project_dag_violation", 5, "foreshadow_dag", "循环"),
    ("project_dag_violation", 100, "foreshadow_dag", "超期"),
    ("project_anchor_overrun", 8, "volume_anchor", "进度偏离"),
    ("project_event_pattern_break", 5, "event_matrix", "连续"),
    ("project_event_pattern_break", 5, "event_matrix", "soft"),
    ("project_pacing_drift", 4, "pacing_tracker", "连续"),
    ("project_pacing_drift", 4, "pacing_tracker", "慢档"),
    ("project_reader_contract_breach", 10, "reader_contract", "期待债"),
    ("project_reader_contract_breach", 10, "reader_contract", "终局底牌"),
    ("project_derived_view_mismatch", 5, "derived_views", "fs_005"),
])
def test_runner_with_fixture(fixture_name, chapter, expected_patch, expected_keyword):
    runner = ConsistencyRunner(FIXTURES / fixture_name)
    evaluation = runner.run_all(chapter=chapter)
    assert evaluation.status == "evaluated"
    if expected_patch is None:
        assert evaluation.findings == []
    else:
        matching = [b for b in evaluation.findings if b.patch == expected_patch]
        assert any(expected_keyword in b.message for b in matching), \
            f"Expected '{expected_keyword}' in {expected_patch} findings, got: {[b.message for b in matching]}"
