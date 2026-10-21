"""Assert the `scripts_dir` contract holds between agents and their callers.

Why this exists (2026-10-21, Stage-2 perf re-verify):

`agents/*.md` tell the agent to run `"${SCRIPTS_DIR}/webnovel.py"`, but a subagent's
Bash does **not** inherit the calling skill's `export SCRIPTS_DIR`, and
`CLAUDE_PLUGIN_ROOT` is not set in that environment either. The path is only there if
the caller writes it into the Agent prompt.

`reviewer.md` declares `scripts_dir` as an input, so the write skill always passes it —
reviewers ran with 0.1–0.6 s of tool time. `data-agent.md` and `context-agent.md` used
`${SCRIPTS_DIR}` without declaring it, so whether they got the path was left to the main
model. In the 2026-10-21 re-verify it did not, in any of the 6 invocations, and both
agents went looking for the scripts directory with `find /` — hitting the 120 s Bash
timeout every time (3 distinct 120 s windows = 360.7 s of the 3-chapter run; chapter 2
issued two commands in one message, both blocked behind the same window).

These tests keep the two halves of that contract in sync.
"""
import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]  # tests/ → scripts/ → plugin/

# Agents whose docs shell out to "${SCRIPTS_DIR}/webnovel.py".
AGENTS = ("data-agent.md", "context-agent.md", "reviewer.md")
# Skills that hand work to those agents through the Agent tool.
CALLER_SKILLS = ("webnovel-write", "webnovel-fast-write", "webnovel-revise")


def _read(rel: str) -> str:
    return (PLUGIN_ROOT / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("agent", AGENTS)
def test_agent_declares_scripts_dir_when_it_uses_it(agent: str) -> None:
    """An agent that runs ${SCRIPTS_DIR}/... must declare scripts_dir as an input."""
    text = _read(f"agents/{agent}")
    if "${SCRIPTS_DIR}" not in text:
        pytest.skip(f"{agent} does not use ${{SCRIPTS_DIR}}")
    assert re.search(r"`scripts_dir`", text), (
        f"agents/{agent} 用 ${{SCRIPTS_DIR}} 调脚本，却没在输入契约里声明 `scripts_dir`；"
        f"子代理的 Bash 不继承主会话的 export，拿不到路径就会去 find / 找。"
    )


@pytest.mark.parametrize("agent", AGENTS)
def test_agent_forbids_filesystem_root_scan(agent: str) -> None:
    """The fallback when scripts_dir is missing must not be a whole-disk scan."""
    text = _read(f"agents/{agent}")
    if "${SCRIPTS_DIR}" not in text:
        pytest.skip(f"{agent} does not use ${{SCRIPTS_DIR}}")
    assert "find /" in text, (
        f"agents/{agent} 没有禁止 `find /` 全盘扫描的兜底说明；"
        f"该扫描会撞 120s Bash 超时并白烧时间。"
    )


@pytest.mark.parametrize("skill", CALLER_SKILLS)
def test_caller_skills_pass_scripts_dir(skill: str) -> None:
    """A skill that invokes data-agent/context-agent must tell the caller to pass scripts_dir."""
    text = _read(f"skills/{skill}/SKILL.md")
    invoked = [
        name
        for name in ("data-agent", "context-agent")
        if f"zhanghui:{name}" in text
    ]
    if not invoked:
        pytest.skip(f"{skill} does not invoke data-agent/context-agent")
    assert "scripts_dir" in text, (
        f"skills/{skill}/SKILL.md 调用了 {invoked}，但没有让调用方传 `scripts_dir`。"
    )
