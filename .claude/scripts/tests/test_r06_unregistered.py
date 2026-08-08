"""R6: 未登记实体——正文提到但未申报的实体 ≤ 阈值。"""
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
    # 14 个独立称谓 + 1 个已知 = 大量 2/3/4 字切片，远超阈值 15
    text = (
        "陈默遇到了黑衣人、白衣剑客、灰衣老者、红发魔女、青袍道士、绿衫少女、"
        "紫袍真人、银发老妪、金甲武士、黑脸大汉、玉面书生、白袍道人、"
        "青衫剑客、灰袍术士。"
    )
    changes = {"new_entities_mentioned": []}
    failures = check_r06_unregistered(text, changes, registered={"陈默"})
    assert len(failures) == 1
    assert failures[0].rule_id == "R6"
    assert "15" in failures[0].message or "过多" in failures[0].message


def test_r06_skipped_when_no_db():
    """R6 应在 --db 缺失/空账本时跳过——没有账本可对比就是没初始化。"""
    text = "他走了很久然后突然停下看着远方。大家不禁都愣住了。"
    changes = {"new_entities_mentioned": []}
    failures = check_r06_unregistered(text, changes, registered=set())
    assert failures == []
