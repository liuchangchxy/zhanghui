import ast
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


def test_phase9_python_core_has_no_host_specific_ui_dependency():
    core = ROOT / ".claude/plugins/zhanghui/scripts/data_modules"
    modules = (
        "canon_correction_store.py",
        "canon_correction_workflow.py",
        "canon_correction_resolver.py",
        "effective_history.py",
        "projection_generation.py",
    )
    forbidden = ("codex", "claude", "request_user_input", "askuserquestion")
    for name in modules:
        path = core / name
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
                imported.extend(alias.name for alias in node.names)
        assert not any(any(marker in item.lower() for marker in forbidden) for item in imported), str(path)
        assert not any(marker in source.lower() for marker in forbidden), str(path)


def test_correction_skill_keeps_human_decision_in_host_adapter():
    skill = ROOT / ".claude/plugins/zhanghui/skills/webnovel-correction-confirm/SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "AskUserQuestion" in text
    assert "Do not select a choice, infer one" in text
    assert "No answer or an unavailable interaction UI leaves the request pending" in text
