from scripts.consistency.patches.p6_reader_contract import P6ReaderContract
from scripts.consistency.core.patch_base import CheckContext
from pathlib import Path


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
    blockers = p.check(_ctx(CLEAN_STATE, chapter=5))
    assert blockers == []


def test_expectation_debt_pileup_blocks():
    p = P6ReaderContract()
    blockers = p.check(_ctx(BREACH_STATE, chapter=10))
    assert any("期待债" in b.message for b in blockers)


def test_causal_credit_violation_blocks():
    p = P6ReaderContract()
    blockers = p.check(_ctx(BREACH_STATE, chapter=10, chapter_text="主角突然领悟绝学，震惊全场"))
    assert any("突然领悟绝学" in b.message for b in blockers)


def test_endgame_reserve_overuse_blocks():
    p = P6ReaderContract()
    blockers = p.check(_ctx(BREACH_STATE, chapter=10))
    assert any("终局底牌" in b.message for b in blockers)


def test_missing_field_fails():
    p = P6ReaderContract()
    blockers = p.check(_ctx({}, chapter=5))
    assert any("未初始化" in b.message or "reader_contract" in b.message for b in blockers)


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
    blockers = p.check(_ctx(state, chapter=10))
    assert not any("终局底牌" in b.message for b in blockers)


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
    blockers = p.check(_ctx(state, chapter=10, chapter_text="突然领悟绝学"))
    assert not any("突然领悟绝学" in b.message for b in blockers)


def test_load_error_reports_blocker():
    p = P6ReaderContract()
    state = {"_load_error": "JSONDecodeError: bad"}
    blockers = p.check(_ctx(state, chapter=5))
    assert any("无法读取 state.json" in b.message for b in blockers)


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
    blockers = p.check(_ctx(state, chapter=5))
    assert any("换书债" in b.message for b in blockers)


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
    blockers = p.check(_ctx(state, chapter=5))
    assert any("履约" in b.message for b in blockers)
