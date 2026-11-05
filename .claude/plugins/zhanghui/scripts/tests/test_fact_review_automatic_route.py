"""Contract for routing high-priority fact findings before commit."""
from pathlib import Path
import importlib.util

import pytest

from data_modules.gate_finding_adapters import adapt_unresolved_fact_review
from data_modules.gate_findings import WorkflowAction
from data_modules.gate_severity_policy import GateSeverityPolicy
from data_modules.revision_planner import OWNER_FACT_REVIEW, classify_finding_owner

PLUGIN = Path(__file__).resolve().parents[2]
REPO = PLUGIN.parents[2]


@pytest.mark.parametrize('severity', ['high', 'critical'])
def test_formal_fact_correction_with_host_edits_and_rereview(tmp_path, monkeypatch, severity):
    """Exercise the real CLI lifecycle with simulated host edits and Reviewer output."""
    path = REPO / 'tests' / 'integration' / 'test_revise_fact_fix_flow.py'
    spec = importlib.util.spec_from_file_location('fact_fix_existing_integration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = module._review_finding

    def review(*args, **kwargs):
        result = original(*args, **kwargs)
        result['issues'][0]['severity'] = severity
        result['issues'][0]['blocking'] = False
        return result

    monkeypatch.setattr(module, '_review_finding', review)
    module.test_fact_correction_runs_through_the_formal_revise_flow(tmp_path)


@pytest.mark.parametrize('skill', ['webnovel-write', 'webnovel-fast-write'])
def test_writing_entry_routes_fact_review_before_commit(skill):
    text = (PLUGIN / 'skills' / skill / 'SKILL.md').read_text(encoding='utf-8')
    assert '自动事实纠错' in text
    assert 'LOCAL_FACT' in text or 'webnovel-revise' in text
    assert 'PENDING_REREVIEW' in text
    assert 'pending_human' in text
    assert text.index('自动事实纠错') < text.index('### Step 4.5')


@pytest.mark.parametrize('severity', ['high', 'critical'])
def test_unresolved_fact_is_deferred_for_correction_and_blocked_at_commit(severity):
    issue = {'severity': severity, 'category': 'continuity', 'description': '数量矛盾', 'location': '第2段'}
    assert classify_finding_owner(issue, style_only=True) == OWNER_FACT_REVIEW
    findings = adapt_unresolved_fact_review(chapter=1, review={'issues': [issue]})
    result = GateSeverityPolicy().evaluate(findings, policy_version='test', scope={'chapter': 1})
    assert result.aggregate_action == WorkflowAction.REQUIRE_HUMAN
    clean = adapt_unresolved_fact_review(chapter=1, review={'issues': []})
    assert GateSeverityPolicy().evaluate(clean, policy_version='test', scope={'chapter': 1}).aggregate_action == WorkflowAction.ALLOW_WITH_ADVISORY
