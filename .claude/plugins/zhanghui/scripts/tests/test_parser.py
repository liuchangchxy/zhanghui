"""Parser 健壮性回归测试：多块、末尾逗号、单引号 keys、嵌套等。

覆盖对抗式审查报告 CRITICAL Bug 5、6、11；以及第一性原理审查 A1.1 / A2.1
（章节文件编码错误必须报 R0 而非 Python traceback）。
"""
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from changes_gate import (
    extract_changes_block,
    repair_changes_json,
    parse_changes,
    parse_changes_document,
)


GATE_SCRIPT = Path(__file__).resolve().parent.parent / "changes_gate.py"


# === Bug 5: 末尾逗号修复 ===
def test_repair_trailing_comma_in_array():
    """Bug 5: `[\"a\",]` 应被修复成 `[\"a\"]`。"""
    raw = '{"unresolved_questions": [],}'
    repaired = repair_changes_json(raw)
    import json as _json
    parsed = _json.loads(repaired)
    assert parsed == {"unresolved_questions": []}


def test_repair_trailing_comma_in_object():
    raw = '{"a": 1, "b": 2,}'
    repaired = repair_changes_json(raw)
    import json as _json
    parsed = _json.loads(repaired)
    assert parsed == {"a": 1, "b": 2}


def test_repair_trailing_comma_nested():
    raw = '{"x": [1, 2, 3,], "y": {"a": 1,},}'
    repaired = repair_changes_json(raw)
    import json as _json
    parsed = _json.loads(repaired)
    assert parsed == {"x": [1, 2, 3], "y": {"a": 1}}


def test_parse_changes_handles_trailing_comma_in_full_block():
    """Bug 5: 完整的合法 JSON + 末尾逗号应能被 parse_changes 处理。"""
    block = """<chapter_changes>
{
  "character_state_changes": [],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": [],
}
</chapter_changes>"""
    parsed, err = parse_changes(block)
    assert err is None
    assert parsed is not None
    assert "character_state_changes" in parsed


# === Bug 6: 多 block 取最后一个 ===
def test_extract_changes_block_uses_last_when_multiple():
    """Bug 6: 当 LLM 输出多个 <chapter_changes> 块，取最后一个（修正版）。"""
    chapter = """<chapter_changes>
{
  "importance": "BAD_ENUM_FIRST"
}
</chapter_changes>

中间是散文中提到的标签 <chapter_changes>foo</chapter_changes>

<chapter_changes>
{
  "importance": "important"
}
</chapter_changes>"""
    # 当前实现期望最后一个块：含合法 importance
    block = extract_changes_block(chapter)
    assert block is not None
    assert "important" in block
    assert "BAD_ENUM_FIRST" not in block


# === 已有功能继续工作 ===
def test_extract_changes_block_returns_first_match():
    chapter = """<chapter_changes>
{"a": 1}
</chapter_changes>"""
    block = extract_changes_block(chapter)
    assert block is not None
    assert '"a": 1' in block


@pytest.mark.parametrize(
    ("format_name", "render"),
    [
        ("xml", lambda body: f"正文前\n<chapter_changes>\n{body}\n</chapter_changes>\n正文后"),
        ("separator", lambda body: f"正文前\n---CHANGES---\n{body}\n---\n正文后"),
        ("heading", lambda body: f"正文前\n# CHANGES\n{body}\n"),
        ("trailing_json", lambda body: f"正文前\n\n{body}"),
    ],
)
def test_parse_changes_document_returns_selected_proposal_and_removes_its_source(format_name, render):
    proposal = {
        "character_state_changes": [{"character_id": "hero", "field": "realm", "new": "金丹"}],
        "new_plot_points": [], "foreshadowing_actions": [], "location_state_changes": [],
        "faction_state_changes": [], "time_progression": None, "item_transfers": [],
        "unresolved_questions": [],
    }
    chapter = render(json.dumps(proposal, ensure_ascii=False, indent=2))

    document = parse_changes_document(chapter)

    assert document.error is None
    assert document.format == format_name
    assert document.proposed_changes == proposal
    assert document.source_spans
    assert "正文前" in document.prose_only
    assert "character_state_changes" not in document.prose_only
    assert "金丹" not in document.prose_only
    expected_prose = chapter[:document.source_spans[0][0]] + chapter[document.source_spans[-1][1]:]
    assert document.prose_only == expected_prose
    assert document.prose_only.startswith("正文前")
    if format_name in {"xml", "separator"}:
        assert "正文后" in document.prose_only
    assert parse_changes(chapter) == (proposal, None)


def test_parse_changes_document_preserves_non_changes_json_example():
    chapter = '正文 JSON 示例：\n\n{"name": "hero", "realm": "金丹"}'
    document = parse_changes_document(chapter)
    assert document.proposed_changes is None
    assert document.source_spans == ()
    assert document.prose_only == chapter


def test_parse_changes_document_preserves_braces_and_json_like_prose():
    chapter = "正文里的例子：{}，以及 {'name': 'hero'}，它们不是 CHANGES。"
    document = parse_changes_document(chapter)
    assert document.source_spans == ()
    assert document.prose_only == chapter


def test_parse_changes_document_removes_bare_json_when_it_is_the_whole_document():
    proposal = {
        "character_state_changes": [], "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [], "time_progression": None,
        "item_transfers": [], "unresolved_questions": [],
    }
    chapter = json.dumps(proposal, ensure_ascii=False)
    document = parse_changes_document(chapter)
    assert document.format == "trailing_json"
    assert document.proposed_changes == proposal
    assert document.prose_only == ""


def test_parse_changes_document_keeps_current_malformed_trailing_json_error():
    malformed = '{"character_state_changes": [], "new_plot_points": [], "foreshadowing_actions": [], "location_state_changes": [], "broken": }'
    chapter = "正文\n\n" + malformed
    document = parse_changes_document(chapter)
    proposed, error = parse_changes(chapter)
    assert document.format == "trailing_json"
    assert document.proposed_changes is None
    assert document.error == error
    assert proposed is None
    assert "CHANGES JSON 解析失败" in error


def test_multiple_xml_candidates_keep_gate_priority_and_strip_all_candidate_blocks():
    first = '{"character_state_changes": [{"new": "筑基"}]}'
    last = '{"character_state_changes": [{"new": "金丹"}]}'
    chapter = f"正文\n<chapter_changes>{first}</chapter_changes>\n散文\n<chapter_changes>{last}</chapter_changes>"
    document = parse_changes_document(chapter)
    assert document.proposed_changes == json.loads(last)
    assert document.format == "xml"
    assert "筑基" not in document.prose_only
    assert "金丹" not in document.prose_only
    assert "散文" in document.prose_only


def test_same_format_separator_blocks_keep_last_proposal_and_strip_all_blocks():
    first = json.dumps({"character_state_changes": [{"new": "筑基"}]})
    last = json.dumps({"character_state_changes": [{"new": "金丹"}]})
    chapter = f"正文\n---CHANGES---\n{first}\n---\n散文\n---CHANGES---\n{last}\n---"

    document = parse_changes_document(chapter)

    assert document.error is None
    assert document.format == "separator"
    assert document.proposed_changes == {"character_state_changes": [{"new": "金丹"}]}
    assert "筑基" not in document.prose_only
    assert "金丹" not in document.prose_only
    assert "散文" in document.prose_only


@pytest.mark.parametrize(
    "chapter",
    [
        "<chapter_changes>{}</chapter_changes>\n\n" + json.dumps({key: [] for key in [
            "character_state_changes", "new_plot_points", "foreshadowing_actions",
            "location_state_changes", "faction_state_changes", "time_progression",
            "item_transfers", "unresolved_questions",
        ]}),
        "---CHANGES---\n{}\n---\n\n" + json.dumps({key: [] for key in [
            "character_state_changes", "new_plot_points", "foreshadowing_actions",
            "location_state_changes", "faction_state_changes", "time_progression",
            "item_transfers", "unresolved_questions",
        ]}),
        "<chapter_changes>{}</chapter_changes>\n\n# CHANGES\n{}",
        "---CHANGES---\n{}\n---\n\n# CHANGES\n{}",
        "<chapter_changes>{}</chapter_changes>\n\n---CHANGES---\n{}\n---\n\n" + json.dumps({key: [] for key in [
            "character_state_changes", "new_plot_points", "foreshadowing_actions",
            "location_state_changes", "faction_state_changes", "time_progression",
            "item_transfers", "unresolved_questions",
        ]}),
    ],
)
def test_mixed_changes_formats_are_rejected(chapter):
    document = parse_changes_document(chapter)
    parsed, error = parse_changes(chapter)
    assert document.error is not None
    assert "mixed_changes_formats" in document.error
    assert parsed is None
    assert error == document.error
    assert document.proposed_changes is None
    assert document.format is None
    assert document.source_spans == ()
    assert document.prose_only == chapter


def test_xml_changes_preserves_ordinary_json_prose():
    chapter = '<chapter_changes>{}</chapter_changes>\n示例：{"name": "hero"}'
    document = parse_changes_document(chapter)
    assert document.error is None
    assert document.format == "xml"
    assert document.prose_only == '\n示例：{"name": "hero"}'


def test_heading_changes_preserves_code_block_json():
    proposal = json.dumps({"character_state_changes": []})
    chapter = f"# CHANGES\n{proposal}\n\n# 正文示例\n```json\n{{\"name\": \"hero\"}}\n```"
    document = parse_changes_document(chapter)
    assert document.error is None
    assert document.format == "heading"
    assert '```json\n{"name": "hero"}\n```' in document.prose_only


def test_bare_json_changes_is_recognized_and_removed():
    proposal = {key: [] for key in [
        "character_state_changes", "new_plot_points", "foreshadowing_actions",
        "location_state_changes", "faction_state_changes", "time_progression",
        "item_transfers", "unresolved_questions",
    ]}
    chapter = "正文\n\n" + json.dumps(proposal)
    document = parse_changes_document(chapter)
    assert document.error is None
    assert document.format == "trailing_json"
    assert document.proposed_changes == proposal
    assert document.prose_only == "正文\n\n"


def test_repair_removes_chinese_quotes():
    raw = "{「key」: 「value」}"
    repaired = repair_changes_json(raw)
    assert '"key"' in repaired
    assert '"value"' in repaired


def test_repair_single_quote_keys():
    raw = "{'key': 'value'}"
    repaired = repair_changes_json(raw)
    import json as _json
    parsed = _json.loads(repaired)
    assert parsed == {"key": "value"}


# === Bug C: 非 UTF-8 章节文件必须报 R0 而非 traceback（第一性原理 A1.1 / A2.1）===
def _run_with_bytes(name: str, raw: bytes) -> dict:
    """直接以 bytes 写入文件，绕过 Python 的默认 utf-8 编码。"""
    chapter_file = Path(tempfile_safe_dir()) / f"_enc_{name}_{uuid.uuid4().hex[:8]}.md"
    try:
        chapter_file.write_bytes(raw)
        result = subprocess.run(
            [sys.executable, str(GATE_SCRIPT),
             "--chapter-file", str(chapter_file), "--json"],
            capture_output=True, text=True,
        )
        # 第一性原理审查明确要求：rc ∈ {0, 1}，**不允许** traceback 退出（rc=2 或 rc=134）
        assert result.returncode in (0, 1), (
            f"Unexpected exit {result.returncode}; stderr={result.stderr!r}"
        )
        # 如果返回 JSON，则必须是 R0 编码错误
        if result.stdout.strip():
            return json.loads(result.stdout)
        return {}
    finally:
        chapter_file.unlink(missing_ok=True)


def tempfile_safe_dir() -> str:
    import tempfile
    return tempfile.gettempdir()


def test_chapter_file_utf16_raises_clean_r0_error():
    """UTF-16 LE BOM 编码的章节 → R0 编码错误，禁止 traceback。"""
    body = "# 第5章\n<chapter_changes>{}\n</chapter_changes>"
    data = _run_with_bytes("utf16", body.encode("utf-16"))
    assert data.get("passed") is False
    assert any("R0" in f["rule_id"] and "UTF-8" in f["message"] for f in data.get("failures", []))


def test_chapter_file_gbk_raises_clean_r0_error():
    """GBK 编码的章节（中文用户的 Windows 工具链常见）→ R0 编码错误。"""
    body = "# 第5章\n<chapter_changes>{}\n</chapter_changes>"
    data = _run_with_bytes("gbk", body.encode("gbk"))
    assert data.get("passed") is False
    assert any("R0" in f["rule_id"] and "UTF-8" in f["message"] for f in data.get("failures", []))


def test_chapter_file_truncated_utf8_raises_clean_r0_error():
    """截断的多字节 UTF-8 序列 → R0 编码错误。"""
    # "第" 的 UTF-8 是 \xe7\xac\xac，截到前两字节是非法序列
    data = _run_with_bytes("trunc", b"# \xe7\xac\xac5\xe7")
    assert data.get("passed") is False
    assert any("R0" in f["rule_id"] and "UTF-8" in f["message"] for f in data.get("failures", []))


def test_chapter_file_binary_raises_clean_r0_error():
    """纯二进制（NUL 字节、ESC 等）→ R0 编码错误。"""
    data = _run_with_bytes("bin", bytes(range(256)) * 4)
    assert data.get("passed") is False
    assert any("R0" in f["rule_id"] and "UTF-8" in f["message"] for f in data.get("failures", []))


def test_chapter_file_empty_raises_clean_r0_error():
    """空章节文件（0 字节）→ R0 "章节文件为空" 而非通用解析错误。"""
    data = _run_with_bytes("empty", b"")
    assert data.get("passed") is False
    assert any("R0" in f["rule_id"] and ("空" in f["message"] or "CHANGES" in f["message"])
               for f in data.get("failures", []))
