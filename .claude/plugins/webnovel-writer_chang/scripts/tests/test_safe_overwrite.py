from pathlib import Path
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
