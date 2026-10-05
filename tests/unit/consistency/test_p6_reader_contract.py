from scripts.consistency.patches.p6_reader_contract import P6ReaderContract
from scripts.consistency.core.patch_base import CheckContext
from scripts.consistency.core.patch_base import PatchFinding
from pathlib import Path
from copy import deepcopy


CLEAN_STATE = {
    "story_craft": {
        "reader_contract": {
            "version": 1,
            "expectation_debt": [],
            "causal_credits": {"protagonist_actions_used_without_setup": []},
            "endgame_reserves": [],
            "swap_debts": []
        }
    }
}

BREACH_STATE = {
    "story_craft": {
        "reader_contract": {
            "version": 1,
            "expectation_debt": [
                {"id": f"exp_{i:03d}", "created_chapter": i, "category": "x", "satisfied_chapter": None}
                for i in range(1, 12)
            ],
            "causal_credits": {"protagonist_actions_used_without_setup": ["突然领悟绝学"]},
            "endgame_reserves": [
                {"id": "er_001", "description": "x", "used_chapter": 5},
                {"id": "er_003", "description": "y", "used_chapter": 8}
            ],
            "swap_debts": []
        }
    }
}


def _ctx(state, chapter=10, chapter_text=None):
    return CheckContext(project_root=Path("/tmp"), chapter_num=chapter, state=state, chapter_outline=None, previous_chapters=[], chapter_text=chapter_text)


def test_clean_passes():
    p = P6ReaderContract()
    findings = p.check(_ctx(CLEAN_STATE, chapter=5))
    assert findings == []


def test_expectation_debt_pileup_blocks():
    p = P6ReaderContract()
    findings = p.check(_ctx(BREACH_STATE, chapter=10))
    assert any("期待债" in b.message for b in findings)


def test_causal_credit_violation_blocks():
    p = P6ReaderContract()
    findings = p.check(_ctx(BREACH_STATE, chapter=10, chapter_text="主角突然领悟绝学，震惊全场"))
    assert any(b.issue_code == "unsetup_action" for b in findings)
    assert all("突然领悟绝学" not in b.message for b in findings)


def test_endgame_reserve_overuse_blocks():
    p = P6ReaderContract()
    findings = p.check(_ctx(BREACH_STATE, chapter=10))
    assert any("终局底牌" in b.message for b in findings)


def test_missing_field_fails():
    p = P6ReaderContract()
    findings = p.check(_ctx({}, chapter=5))
    assert any("未初始化" in b.message or "reader_contract" in b.message for b in findings)


def test_endgame_reserves_as_string_list_does_not_crash():
    """Fix C: endgame_reserves can be a list of strings (per spec example), not dicts.
    Should not crash; should treat them as unused."""
    p = P6ReaderContract()
    state = {
        "story_craft": {
            "reader_contract": {
                "version": 1,
                "expectation_debt": [],
                "causal_credits": {"protagonist_actions_used_without_setup": []},
                "endgame_reserves": ["最终决战伏笔", "终局揭示"],  # strings, not dicts
                "swap_debts": []
            }
        }
    }
    # Should not raise; should pass (no reserves used)
    findings = p.check(_ctx(state, chapter=10))
    assert not any("终局底牌" in b.message for b in findings)


def test_causal_credits_wrong_type_does_not_crash():
    p = P6ReaderContract()
    state = {
        "story_craft": {
            "reader_contract": {
                "version": 1,
                "expectation_debt": [],
                "causal_credits": {"protagonist_actions_used_without_setup": "should be list"},
                "endgame_reserves": [],
                "swap_debts": []
            }
        }
    }
    # Should not raise
    findings = p.check(_ctx(state, chapter=10, chapter_text="突然领悟绝学"))
    assert not any("突然领悟绝学" in b.message for b in findings)


def test_load_error_reports_finding():
    p = P6ReaderContract()
    state = {"_load_error": "JSONDecodeError: bad"}
    findings = p.check(_ctx(state, chapter=5))
    assert any("无法读取 state.json" in b.message for b in findings)


def test_p6_findings_are_typed_evidenced_and_keep_aggregate_subjects_optional():
    state = {
        "story_craft": {"reader_contract": {
            "expectation_debt": [{"satisfied_chapter": None} for _ in range(11)],
            "causal_credits": {"protagonist_actions_used_without_setup": ["secret phrase"]},
            "endgame_reserves": [{"used_chapter": 1}, {"used_chapter": 2}],
            "swap_debts": [{"risk": "high", "old_book": "A", "new_book": "B"}],
            "contract_fulfillment": [{"promise_id": "P7", "status": "broken",
                                      "chapter_promised": 3, "chapter_satisfied": None}],
        }}
    }
    before = deepcopy(state)
    findings = P6ReaderContract().check(_ctx(state, chapter=10, chapter_text="secret phrase appears"))
    by_code = {finding.issue_code: finding for finding in findings}
    assert set(by_code) == {"high_expectation_debt", "unsetup_action", "endgame_limit", "high_swap_risk", "broken_promise"}
    assert all(isinstance(finding, PatchFinding) for finding in findings)
    assert by_code["high_expectation_debt"].evidence["observed"] == 11
    assert by_code["high_expectation_debt"].subject_id is None
    assert by_code["unsetup_action"].evidence["action_index"] == 0
    assert "secret phrase" not in by_code["unsetup_action"].message
    assert by_code["unsetup_action"].subject_id is None
    assert by_code["endgame_limit"].evidence["observed"] == 2
    assert by_code["endgame_limit"].subject_id is None
    assert by_code["high_swap_risk"].subject_id is None
    assert by_code["broken_promise"].subject_id == "promise:P7"
    assert by_code["broken_promise"].evidence["status"] == "broken"
    assert all(finding.checker_id == "reader_contract" for finding in findings)
    assert state == before


def test_p6_invalid_state_is_typed():
    finding = P6ReaderContract().check(_ctx({}, chapter=5))[0]
    assert finding.issue_code == "invalid_state"
    assert finding.evidence["source_field"] == "story_craft.reader_contract"
    assert finding.subject_id is None


def test_swap_debt_high_risk_blocks():
    p = P6ReaderContract()
    state = {
        "story_craft": {
            "reader_contract": {
                "version": 1,
                "expectation_debt": [],
                "causal_credits": {"protagonist_actions_used_without_setup": []},
                "endgame_reserves": [],
                "swap_debts": [
                    {"old_book": "凡人资本论", "new_book": "仙尊重生", "risk": "high"}
                ],
                "contract_fulfillment": []
            }
        }
    }
    findings = p.check(_ctx(state, chapter=5))
    assert any("换书债" in b.message for b in findings)


def test_contract_fulfillment_broken_blocks():
    p = P6ReaderContract()
    state = {
        "story_craft": {
            "reader_contract": {
                "version": 1,
                "expectation_debt": [],
                "causal_credits": {"protagonist_actions_used_without_setup": []},
                "endgame_reserves": [],
                "swap_debts": [],
                "contract_fulfillment": [
                    {"promise_id": "P1", "chapter_promised": 3, "chapter_satisfied": None, "status": "broken"}
                ]
            }
        }
    }
    findings = p.check(_ctx(state, chapter=5))
    assert any("履约" in b.message for b in findings)
