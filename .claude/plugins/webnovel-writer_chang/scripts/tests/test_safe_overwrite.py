from pathlib import Path

import pytest

from scripts._shared.safe_overwrite import ConflictMode, resolve_conflict, _in_claude_code_context


def test_conflict_mode_values():
    assert ConflictMode.OVERWRITE.value == "overwrite"
    assert ConflictMode.APPEND.value == "append"
    assert ConflictMode.SKIP.value == "skip"
    assert ConflictMode.ASK.value == "ask"


def test_in_claude_code_context_with_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    assert _in_claude_code_context() is True


def test_in_claude_code_context_without_env(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    assert _in_claude_code_context() is False


def test_resolve_conflict_no_exists_no_mode(capsys):
    # exists=False → 不管 mode 是什么都直接通过；不应输出 SKIP/OVERWRITE/APPEND 噪音
    result = resolve_conflict(exists=False, path=Path("/tmp/x"), mode=None)
    assert result is None
    captured = capsys.readouterr()
    assert "SKIP" not in captured.err
    assert "OVERWRITE" not in captured.err
    assert "APPEND" not in captured.err


def test_resolve_conflict_exists_no_mode_raises():
    with pytest.raises(FileExistsError, match="已存在"):
        resolve_conflict(exists=True, path=Path("/tmp/x"), mode=None)


def test_resolve_conflict_skip_does_not_modify(capsys):
    resolve_conflict(exists=True, path=Path("/tmp/skip"), mode="skip")
    captured = capsys.readouterr()
    assert "SKIP" in captured.err


def test_resolve_conflict_overwrite_allows_subsequent(capsys):
    # resolve_conflict 不直接写文件，只返回；调用方负责覆盖
    result = resolve_conflict(exists=True, path=Path("/tmp/ow"), mode="overwrite")
    assert result is None  # 必须显式返回 None，让调用方可以接着覆盖
    captured = capsys.readouterr()
    assert "OVERWRITE" in captured.err


def test_resolve_conflict_append_with_op_executes_op(tmp_path, capsys):
    target = tmp_path / "ap.txt"
    target.write_text("base\n")

    def my_append(p: Path):
        with p.open("a", encoding="utf-8") as f:
            f.write("appended\n")

    resolve_conflict(exists=True, path=target, mode="append", append_op=my_append)
    content = target.read_text()
    assert content == "base\nappended\n"
    captured = capsys.readouterr()
    assert "APPEND" in captured.err
