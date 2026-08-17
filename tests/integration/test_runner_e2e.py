import pytest
from pathlib import Path
from scripts.consistency.core.runner import ConsistencyRunner


FIXTURES = Path(__file__).parent.parent / "fixtures" / "cross_volume"


@pytest.mark.parametrize("fixture_name,chapter,expected_patch,expected_keyword", [
    ("project_clean", 5, None, None),
    ("project_dag_violation", 5, "foreshadow_dag", "循环"),
    ("project_dag_violation", 100, "foreshadow_dag", "超期"),
])
def test_runner_with_fixture(fixture_name, chapter, expected_patch, expected_keyword):
    runner = ConsistencyRunner(FIXTURES / fixture_name)
    blockers = runner.run_all(chapter=chapter)
    if expected_patch is None:
        assert blockers == []
    else:
        matching = [b for b in blockers if b.patch == expected_patch]
        assert any(expected_keyword in b.message for b in matching), \
            f"Expected '{expected_keyword}' in {expected_patch} blockers, got: {[b.message for b in matching]}"