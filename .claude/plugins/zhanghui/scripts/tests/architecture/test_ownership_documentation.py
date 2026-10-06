"""Active plugin documentation ownership drift tests."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[6]
MARKETPLACE = ROOT / ".claude-plugin/marketplace.json"
EXPECTED_ROOT = ROOT / ".claude/plugins/zhanghui"


def active_root():
    catalog = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    source = catalog["plugins"][0]["source"]
    return (ROOT / source).resolve()


def test_marketplace_selects_canonical_active_root_and_excludes_snapshot():
    selected = active_root()
    assert selected == EXPECTED_ROOT.resolve()
    assert selected / "skills/webnovel-write/SKILL.md" in active_paths()
    assert not any("/6.4.0/" in str(path) for path in active_paths())


def active_paths():
    root = active_root()
    paths = [
        "skills/webnovel-write/SKILL.md", "skills/webnovel-review/SKILL.md",
        "skills/webnovel-plan/SKILL.md", "skills/webnovel-init/SKILL.md",
        "skills/webnovel-query/SKILL.md", "skills/webnovel-query/references/system-data-flow.md",
        "skills/webnovel-query/references/tag-specification.md",
        "skills/webnovel-init/references/system-data-flow.md",
        "skills/webnovel-resume/SKILL.md", "skills/webnovel-resume/references/system-data-flow.md",
        "skills/webnovel-resume/references/workflow-resume.md",
        "agents/context-agent.md", "agents/data-agent.md", "references/shared/core-constraints.md",
        "docs/context-provenance.md", "docs/projection-rebuild.md",
        "../../../docs/architecture/architecture-constitution.md",
    ]
    resolved = [root / path for path in paths]
    missing = [path.relative_to(root).as_posix() for path in resolved if not path.is_file()]
    assert not missing, f"active documentation manifest contains missing paths: {missing}"
    return resolved


def test_active_docs_keep_commit_and_projection_ownership_contract():
    texts = {path: path.read_text(encoding="utf-8") for path in active_paths()}
    all_text = "\n".join(texts.values())
    assert "Data Agent 只生成临时提取产物" in all_text
    assert "chapter-commit" in texts[EXPECTED_ROOT / "skills/webnovel-write/SKILL.md"]
    assert "projection" in all_text.lower()
    from tests.architecture.ownership_inventory_guard import unqualified_ownership_claims
    assert not unqualified_ownership_claims(all_text)
    write_doc = texts[EXPECTED_ROOT / "skills/webnovel-write/SKILL.md"]
    for projection in ("state", "index", "summary", "memory", "vector"):
        assert projection in write_doc[write_doc.index("postcommit projection 五项验证"):]
    assert "`projections retry` 已成功" in write_doc


def test_ownership_document_rule_rejects_unqualified_false_claim_but_allows_labeled_history():
    from tests.architecture.ownership_inventory_guard import is_historical_claim, unqualified_ownership_claims

    bad = "Data Agent writes state.json as the story truth."
    assert not is_historical_claim(bad)
    old = "Historical legacy workflow: Data Agent wrote state.json as a compatibility projection."
    assert is_historical_claim(old)
    assert unqualified_ownership_claims(bad)
    assert not unqualified_ownership_claims(old)


def test_all_selected_active_paths_have_no_unqualified_ownership_claims():
    from tests.architecture.ownership_inventory_guard import unqualified_ownership_claims

    violations = {
        path.relative_to(active_root()).as_posix(): unqualified_ownership_claims(path.read_text(encoding="utf-8"))
        for path in active_paths()
    }
    violations = {path: rows for path, rows in violations.items() if rows}
    assert not violations, violations
