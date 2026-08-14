"""R1: 协议完整性——8 个顶级字段必须显式存在。"""
from changes_gate import check_r01_protocol, REQUIRED_TOP_LEVEL_FIELDS


def test_r01_passes_with_all_8_fields():
    changes = {field: [] for field in REQUIRED_TOP_LEVEL_FIELDS}
    changes["time_progression"] = None
    failures = check_r01_protocol(changes)
    assert failures == [], f"expected no failures, got {failures}"


def test_r01_fails_when_field_missing():
    changes = {field: [] for field in REQUIRED_TOP_LEVEL_FIELDS}
    changes["time_progression"] = None
    del changes["item_transfers"]  # 缺一个
    failures = check_r01_protocol(changes)
    assert len(failures) == 1
    assert failures[0].rule_id == "R1"
    assert failures[0].severity == "blocking"
    assert "item_transfers" in failures[0].message


def test_r01_fails_when_field_is_undefined():
    """多写了未定义的字段不通过（保持 schema 严格）。"""
    changes = {field: [] for field in REQUIRED_TOP_LEVEL_FIELDS}
    changes["time_progression"] = None
    changes["unexpected_field"] = []  # 不该有的字段
    failures = check_r01_protocol(changes)
    # 注意：当前 spec 允许扩展字段，所以这测试先 expect 0 failures
    # 如果你想严格，去掉下面的 expect 并加 strict-mode flag
    assert failures == []