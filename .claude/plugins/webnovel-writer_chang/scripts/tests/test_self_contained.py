"""断言 plugin 是 self-contained：不依赖 CLAUDE_PROJECT_DIR，所有路径用 CLAUDE_PLUGIN_ROOT，所有脚本自带。
"""
import os
import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]  # tests/ → scripts/ → plugin/


def _all_md_files() -> list[Path]:
    return list(PLUGIN_ROOT.glob("skills/*/SKILL.md")) + list(PLUGIN_ROOT.glob("agents/*.md"))


def _all_json_files() -> list[Path]:
    return list(PLUGIN_ROOT.glob("hooks/*.json")) + list(PLUGIN_ROOT.glob(".claude-plugin/*.json"))


@pytest.mark.parametrize("md_file", _all_md_files(), ids=lambda p: str(p.relative_to(PLUGIN_ROOT)))
def test_no_python2_alias(md_file: Path) -> None:
    """SKILL.md 和 agent md 不应使用 `python` 别名（macOS 没 python）。"""
    text = md_file.read_text(encoding="utf-8")
    bad = re.findall(r"(?<![A-Za-z0-9_])python -X utf8", text)
    assert not bad, f"{md_file.relative_to(PLUGIN_ROOT)} 仍含 `python -X utf8` 别名: {bad}"


@pytest.mark.parametrize("md_file", _all_md_files(), ids=lambda p: str(p.relative_to(PLUGIN_ROOT)))
def test_no_claude_project_dir_in_skills(md_file: Path) -> None:
    """plugin 内不应使用 CLAUDE_PROJECT_DIR（仅 dev workspace 的 settings.json 用）。"""
    text = md_file.read_text(encoding="utf-8")
    assert "CLAUDE_PROJECT_DIR" not in text, (
        f"{md_file.relative_to(PLUGIN_ROOT)} 含 CLAUDE_PROJECT_DIR 引用，违反 self-contained 原则"
    )


@pytest.mark.parametrize("md_file", _all_md_files(), ids=lambda p: str(p.relative_to(PLUGIN_ROOT)))
def test_no_dev_path_fallback(md_file: Path) -> None:
    """不应有 ${CLAUDE_PLUGIN_ROOT:-...CLAUDE_PROJECT_DIR.../.claude/...} 反模式 fallback。"""
    text = md_file.read_text(encoding="utf-8")
    bad = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT:-\$\{CLAUDE_PROJECT_DIR", text)
    assert not bad, f"{md_file.relative_to(PLUGIN_ROOT)} 含反模式 fallback: {bad}"


@pytest.mark.parametrize("json_file", _all_json_files(), ids=lambda p: str(p.relative_to(PLUGIN_ROOT)))
def test_hooks_use_python3(json_file: Path) -> None:
    """hooks.json 命令用 python3 而非 python。"""
    text = json_file.read_text(encoding="utf-8")
    if "hooks.json" not in str(json_file):
        pytest.skip("not hooks.json")
    bad = re.findall(r"(?<![A-Za-z0-9_])python -X utf8", text)
    assert not bad, f"{json_file.relative_to(PLUGIN_ROOT)} 仍用 `python -X utf8`: {bad}"


def test_plugin_name_is_exact() -> None:
    """plugin.json 的 name 必须**精确等于** 'webnovel-writer_chang'——endswith 太宽松（'x_chang_y' 也通过）。"""
    import json
    data = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "webnovel-writer_chang", (
        f"plugin name 必须是 'webnovel-writer_chang'，实际是 {data['name']!r}"
    )


def test_plugin_version_is_6_3_0() -> None:
    """plugin.json version 必须是 6.3.0——避免 marketplace.json 6.3.0 与 plugin.json 6.2.1 drift。"""
    import json
    data = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["version"] == "6.3.0", f"plugin version 必须是 6.3.0，实际是 {data['version']!r}"


def test_no_scripts_in_dev_dotclaude() -> None:
    """dev .claude/scripts/ 应已清空；.claude/skills/ 不应残留 webnovel-* 重复副本（系统级 skill 如 writing-layered-plans 是合法 dev 工作流）。"""
    # scripts/ 必须为空
    scripts_full = PLUGIN_ROOT.parent.parent.parent / ".claude/scripts"
    if scripts_full.exists():
        contents = list(scripts_full.iterdir())
        assert not contents, f".claude/scripts 应已清空但还有: {contents}"
    # skills/ 只能不含 webnovel-* 重复（系统级 skill 合法）
    skills_full = PLUGIN_ROOT.parent.parent.parent / ".claude/skills"
    if skills_full.exists():
        leftover = [p for p in skills_full.iterdir() if p.name.startswith("webnovel-")]
        assert not leftover, f".claude/skills/ 不应残留 webnovel-* 重复: {leftover}"