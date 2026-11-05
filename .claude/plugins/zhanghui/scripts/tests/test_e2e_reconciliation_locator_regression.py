import json
from pathlib import Path

import pytest

from data_modules.reconciliation import reconcile_changes
from data_modules.revision_planner import locate_issue, apply_edits, RevisionApplyError, sha256_text


def test_real_chapter_five_state_and_plot_share_observation():
    fixture = Path(__file__).parent / 'fixtures/e2e_chapter5_reconciliation.json'
    data = json.loads(fixture.read_text(encoding='utf-8'))
    result = reconcile_changes(data['proposed'], data['observed'], chapter_text='')
    matches = { (m['proposed']['source'], m['proposed']['index']): m['observed'] for m in result['matched'] }
    assert {'source': 'state_deltas', 'index': 1} in matches['character_state_changes', 0]
    assert {'source': 'state_deltas', 'index': 1} in matches['new_plot_points', 0]
    assert matches['character_state_changes', 1] == [{'source': 'state_deltas', 'index': 3}]
    assert not result['conflicts']


def test_real_chapter_four_character_states_match():
    fixture = Path(__file__).parent / 'fixtures/e2e_chapter4_reconciliation.json'
    data = json.loads(fixture.read_text(encoding='utf-8'))
    result = reconcile_changes(data['proposed'], data['observed'], chapter_text='')
    matches = {(m['proposed']['source'], m['proposed']['index']): m['observed'] for m in result['matched']}
    assert matches['character_state_changes', 1] == [{'source': 'state_deltas', 'index': 2}]
    assert matches['character_state_changes', 2] == [{'source': 'state_deltas', 'index': 5}]
    assert not result['conflicts']


def test_evidence_quote_and_paragraph_number():
    draft = '\n\n'.join(f'第{i}个段落的正文。' for i in range(1, 100))
    quote = locate_issue(draft, {'category': 'logic', 'evidence': '“第73个段落的正文”'})
    assert quote.resolvable and quote.before_text == '第73个段落的正文。'
    paragraph = locate_issue(draft, {'category': 'logic', 'location': '第73段'})
    assert paragraph.resolvable and paragraph.before_text == '第73个段落的正文。'
    assert paragraph.file_line_start == 145


@pytest.mark.parametrize('severity', ['high', 'critical'])
def test_unresolved_fact_remains_blocking(severity):
    from data_modules.gate_finding_adapters import adapt_unresolved_fact_review
    from data_modules.gate_findings import WorkflowAction
    from data_modules.gate_severity_policy import GateSeverityPolicy
    issue = {'severity': severity, 'category': 'continuity', 'location': '第73段 vs 第91段', 'description': '事实矛盾', 'blocking': False}
    draft = '\n\n'.join(f'正文{i}' for i in range(100))
    target = locate_issue(draft, issue)
    assert not target.resolvable
    plan = {'draft_sha256': sha256_text(draft), 'targets': [target.to_dict()], 'editable_spans': []}
    with pytest.raises(RevisionApplyError):
        apply_edits(draft, plan, [{'target_id': target.issue_id, 'new_text': '修改'}])
    findings = adapt_unresolved_fact_review(chapter=1, review={'issues': [issue]})
    assert GateSeverityPolicy().evaluate(findings, policy_version='test', scope={'chapter': 1}).aggregate_action == WorkflowAction.REQUIRE_HUMAN


def test_unrelated_character_cannot_borrow_another_character_state():
    fixture = Path(__file__).parent / 'fixtures/e2e_chapter5_reconciliation.json'
    data = json.loads(fixture.read_text(encoding='utf-8'))
    data['proposed']['character_state_changes'][0]['character_id'] = '无关人物'
    result = reconcile_changes(data['proposed'], data['observed'], chapter_text='')
    assert not any(m['proposed'] == {'source': 'character_state_changes', 'index': 0} for m in result['matched'])


def test_same_person_unrelated_fact_is_not_matched():
    fixture = Path(__file__).parent / 'fixtures/e2e_chapter4_reconciliation.json'
    data = json.loads(fixture.read_text(encoding='utf-8'))
    data['proposed']['character_state_changes'][1]['new_state'] = '许知远决定远赴北京学习船舶发动机维修技术'
    result = reconcile_changes(data['proposed'], data['observed'], chapter_text='')
    assert not any(m['proposed'] == {'source': 'character_state_changes', 'index': 1} for m in result['matched'])


def test_ambiguous_quote_without_location_is_unresolved():
    target = locate_issue('他关上门。\n\n他关上门。', {'description': '“他关上门”存在问题', 'category': 'logic'})
    assert not target.resolvable
    assert target.ambiguity == 'ambiguous_quote'


def test_multiple_numbered_locations_are_not_guessed():
    draft = '\n\n'.join(f'正文第{i}段' for i in range(1, 100))
    target = locate_issue(draft, {'location': '第73段 vs 第91段', 'category': 'continuity'})
    assert not target.resolvable
    assert target.ambiguity == 'multiple_locations_require_explicit_quotes'


def test_unresolved_target_cannot_insert_text():
    draft = '第一段。\n\n第二段。'
    target = locate_issue(draft, {'location': '某处', 'category': 'logic'})
    plan = {'draft_sha256': sha256_text(draft), 'targets': [target.to_dict()], 'editable_spans': []}
    with pytest.raises(RevisionApplyError):
        apply_edits(draft, plan, [{'target_id': target.issue_id, 'new_text': '错误插入'}])
