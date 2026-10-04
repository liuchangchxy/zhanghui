"""rejection_contract.py 单元测试。"""
import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rejection_contract import (
    IssueRef,
    RejectionContract,
    build_contract_from_reviewer_output,
    validate_contract,
    merge_contracts,
    targets_text,
    Severity,
)


REVIEWER_JSON = {
    "chapter": 5,
    "issues": [
        {
            "severity": "critical",
            "category": "continuity",
            "location": "第3段",
            "description": "上章钩子未回应",
            "evidence": "上章末尾提到玄之会回来，本章没出现",
            "fix_hint": "在第3段加入玄之回场的桥段",
            "blocking": True,
        },
        {
            "severity": "high",
            "category": "character",
            "location": "第5段",
            "description": "陈默的对话风格与角色库矛盾",
            "evidence": "原文：'在下告辞'。角色库标注：粗犷不拘礼节",
            "fix_hint": "改为更口语化的告别方式",
            "blocking": False,
        },
        {
            "severity": "low",
            "category": "pacing",
            "location": "第7段",
            "description": "节奏略拖",
            "evidence": "环境描写 800 字无推进",
            "fix_hint": "压缩到 300 字",
            "blocking": False,
        },
    ],
    "blocking_count": 1,
    "issues_count": 3,
}


def test_build_contract_from_reviewer_output_keeps_blocking_only_by_default():
    """默认只把 blocking=true 的 issue 转成 IssueRef。"""
    contract = build_contract_from_reviewer_output(REVIEWER_JSON)
    assert contract.chapter == 5
    assert len(contract.issues) == 1
    issue = contract.issues[0]
    assert issue.category == "continuity"
    assert issue.location == "第3段"
    assert issue.severity == Severity.CRITICAL


def test_build_contract_with_include_advisory_includes_low():
    """include_advisory=True → 全收。"""
    contract = build_contract_from_reviewer_output(
        REVIEWER_JSON, include_advisory=True
    )
    assert len(contract.issues) == 3
    cats = [i.category for i in contract.issues]
    assert "continuity" in cats and "character" in cats and "pacing" in cats


def test_validate_contract_rejects_empty():
    """空 contract → raise。"""
    c = RejectionContract(chapter=1, issues=[])
    with pytest.raises(ValueError, match="至少一个 issue"):
        validate_contract(c)


def test_validate_contract_rejects_unknown_category():
    """category 不在白名单 → raise。"""
    bad = RejectionContract(
        chapter=1,
        issues=[IssueRef(
            severity=Severity.HIGH,
            category="fashion",  # 不合法
            location="第1段",
            description="x",
            fix_hint="y",
            blocking=True,
        )],
    )
    with pytest.raises(ValueError, match="category"):
        validate_contract(bad)


def test_validate_contract_rejects_missing_required_field():
    """IssueRef 缺 location/description/fix_hint → raise。"""
    bad = RejectionContract(
        chapter=1,
        issues=[IssueRef(
            severity=Severity.HIGH,
            category="continuity",
            location="",
            description="x",
            fix_hint="y",
            blocking=True,
        )],
    )
    with pytest.raises(ValueError, match="location"):
        validate_contract(bad)


def test_merge_contracts_concatenates_issues():
    """两个 contract 合并 → issues 拼接，chapter 必须一致。"""
    a = build_contract_from_reviewer_output(REVIEWER_JSON)
    b = build_contract_from_reviewer_output(REVIEWER_JSON)
    merged = merge_contracts([a, b])
    assert merged.chapter == 5
    assert len(merged.issues) == 2

    other = RejectionContract(chapter=6, issues=a.issues)
    with pytest.raises(ValueError, match="同一章节"):
        merge_contracts([a, other])


def test_targets_text_groups_by_location():
    """targets_text() 按 location 聚合 fix_hint。"""
    contract = RejectionContract(
        chapter=1,
        issues=[
            IssueRef(Severity.CRITICAL, "continuity", "第2段", "缺钩子", "加回场", True),
            IssueRef(Severity.HIGH, "character", "第5段", "腔调错", "改口语", False),
            IssueRef(Severity.HIGH, "character", "第5段", "用典错", "换典故", False),
        ],
    )
    targets = targets_text(contract)
    assert "第2段" in targets
    assert "第5段" in targets
    # 第5段有两条 fix_hint
    seg5 = targets.split("第5段")[1]
    assert "改口语" in seg5 and "换典故" in seg5


def test_merge_contracts_source_is_sorted():
    """I4: source 字段拼接前应 sorted()，避免 set 顺序导致结果不稳定。"""
    a = RejectionContract(chapter=1, issues=[
        IssueRef(Severity.HIGH, "other", "x", "x", "x", True),
    ], source="reviewer")
    b = RejectionContract(chapter=1, issues=[
        IssueRef(Severity.HIGH, "other", "y", "y", "y", True),
    ], source="anti-slop")
    c = RejectionContract(chapter=1, issues=[
        IssueRef(Severity.HIGH, "other", "z", "z", "z", True),
    ], source="data-agent")
    # 故意以非字母顺序传入
    merged = merge_contracts([c, a, b])
    # sorted: anti-slop < data-agent < reviewer
    assert merged.source == "anti-slop+data-agent+reviewer"
    # 反向传入也得同样结果
    merged2 = merge_contracts([b, c, a])
    assert merged2.source == "anti-slop+data-agent+reviewer"


def test_rejection_contract_accepts_do_not_copy_violation():
    """C1: VALID_CATEGORIES 白名单必须包含 P3 新增的 do_not_copy_violation。

    否则 reviewer 在 do_not_copy 维度抛 high issue 时，revise_chapter.py:264
    validate_contract() 会拒绝该 contract → EXIT_INVALID → 章节永远无法
    自动局部重写（silent flow breakage）。
    """
    contract = build_contract_from_reviewer_output({
        "chapter": 1,
        "issues": [{
            "severity": "critical",
            "category": "do_not_copy_violation",
            "location": "第2段",
            "description": "出现禁用元素",
            "fix_hint": "改写",
            "blocking": True,
        }]
    })
    validate_contract(contract)  # MUST NOT raise
    assert contract.issues[0].category == "do_not_copy_violation"
