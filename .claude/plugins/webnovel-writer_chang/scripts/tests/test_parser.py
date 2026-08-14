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
