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
    """plugin.json 的 name 必须**精确等于** 'zhanghui'——endswith 太宽松（'x_chang_y' 也通过）。"""
    import json
    data = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "zhanghui", (
        f"plugin name 必须是 'zhanghui'，实际是 {data['name']!r}"
    )


def test_plugin_version_matches_marketplace_and_is_semver() -> None:
    """plugin.json 与 marketplace.json 的版本必须一致且为 semver。

    这里刻意**不写死具体版本号**：写死会逼着每次发版都改测试，而这一次的验收缺陷恰恰是
    PR #46/#47 合并后版本号没有递增，导致老用户的 `claude plugin update` 永远返回
    "already at the latest version"，修复根本没有到达用户。
    """
    import json
    import re

    plugin = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    marketplace_path = PLUGIN_ROOT.parent.parent.parent / ".claude-plugin" / "marketplace.json"
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    entry = next(p for p in marketplace["plugins"] if p.get("name") == "zhanghui")
    assert re.fullmatch(r"\d+\.\d+\.\d+", str(plugin["version"])), plugin["version"]
    assert entry["version"] == plugin["version"], (
        f"marketplace={entry['version']!r} plugin={plugin['version']!r}"
    )


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