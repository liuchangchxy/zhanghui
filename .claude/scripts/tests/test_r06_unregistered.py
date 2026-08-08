"""R6: 未登记实体——正文提到但未申报的实体 ≤ 5。"""
import re
from pathlib import Path

from changes_gate import extract_chapter_entities, check_r06_unregistered


def test_extract_finds_known_and_unknown():
    text = """
    陈默走向论剑台。
    神秘的黑衣女子出现了。
    王玄之在角落里观察。
    """
    known = {"陈默", "王玄之", "论剑台"}
    registered = {"陈默", "王玄之", "论剑台"}  # 假设这三个都在账本
    mentioned = extract_chapter_entities(text)
    unknown = [m for m in mentioned if m not in registered]
    assert "黑衣女子" in unknown
    assert "陈默" not in unknown
    assert "论剑台" not in unknown


def test_r06_passes_with_few_unknowns():
    text = "陈默在论剑台等王玄之。"
    changes = {"new_entities_mentioned": []}  # 没申报
    failures = check_r06_unregistered(text, changes, registered={"陈默", "王玄之", "论剑台"})
    assert failures == []


def test_r06_fails_with_too_many_unknowns():
    text = "陈默遇到了黑衣人、白衣剑客、灰衣老者、红发魔女、青袍道士、绿衫少女。"
    changes = {"new_entities_mentioned": []}
    failures = check_r06_unregistered(text, changes, registered={"陈默"})
    assert len(failures) == 1
    assert failures[0].rule_id == "R6"
    assert "5" in failures[0].message or "过多" in failures[0].message
