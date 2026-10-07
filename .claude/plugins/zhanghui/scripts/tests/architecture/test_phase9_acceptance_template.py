import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[6]
TEMPLATE = ROOT / "docs/superpowers/acceptance/phase-9-h1-acceptance-template.md"
H2 = ROOT / "docs/superpowers/acceptance/phase-9-h2-evidence.md"


def test_phase9_h1_template_exists_and_keeps_binding_fields_empty():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "record_type: phase-9-h1-acceptance-template" in text
    assert 'tested_implementation_head: ""' in text
    assert 'tested_implementation_tree: ""' in text
    assert 'tested_implementation_parent: ""' in text


def test_phase9_h1_template_has_no_results_hashes_node_ids_or_dispositions():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert not re.search(r"\b[0-9a-f]{40}(?:[0-9a-f]{24})?\b", text, re.I)
    assert "::test_" not in text
    assert not re.search(r"\b(?:PASS|FAIL|PASSED|FAILED|SKIPPED)\b", text, re.I)
    assert not re.search(r"\b(?:passed|failed|skipped)\s*[:=]\s*\d+", text, re.I)
    assert not re.search(r"\b(?:run|node)_id\s*:\s*[^\"']+", text, re.I)


def test_phase9_h2_evidence_record_is_not_created_in_h1():
    assert not H2.exists()
