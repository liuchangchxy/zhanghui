#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pre-commit manifest guard 的行为测试。

这个 guard 的唯一目的：阻止无效 plugin.json 进入历史，导致 Claude Code
"failed to load" 整个 plugin。它必须满足 4 条，否则要么形同虚设、要么
制造假阳性把人（和 AI）逼去用 --no-verify：

1. 校验对象 = 调用它的那个 worktree，而不是硬编码的主工作区
2. 校验内容 = 即将提交的 index 内容，而不是磁盘工作区内容
3. 只在 manifest / skills / commands 结构真的变了时触发，不是碰任何插件文件都触发
4. 失败信息不得给出 --no-verify 绕过指引
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PLUGIN_ROOT.parents[2]
VALIDATOR = PLUGIN_ROOT / "scripts" / "dev-only" / "validate_plugin_manifest.sh"
PRECOMMIT = REPO_ROOT / ".git" / "hooks" / "pre-commit"

PLUGIN_REL = ".claude/plugins/webnovel-writer_chang"

VALID_MANIFEST = {
    "name": "webnovel-writer_chang",
    "version": "6.4.0",
    "description": "test fixture manifest",
    "skills": "./skills/",
    "commands": "./commands/",
}
# `agents` 是 FORBIDDEN_FIELDS 之一——Claude Code 自动发现 agents/，
# manifest 再声明会导致 plugin 加载失败。
BROKEN_MANIFEST = dict(VALID_MANIFEST, agents=["agents/x.md"])


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
    )


def _output(result: subprocess.CompletedProcess) -> str:
    """git 把 pre-commit hook 的 stdout 转到 stderr，只看 stdout 的断言会永远为真。"""
    return (result.stdout or "") + (result.stderr or "")


def _write_manifest(plugin_root: Path, manifest: dict) -> None:
    path = plugin_root / ".claude-plugin" / "plugin.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_plugin_tree(plugin_root: Path, manifest: dict) -> None:
    """最小但完整的 plugin 布局：manifest + skills/ + commands/ 都要真实存在。"""
    _write_manifest(plugin_root, manifest)
    skill = plugin_root / "skills" / "demo-skill"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    (skill / "helper.py").write_text("x = 1\n", encoding="utf-8")
    commands = plugin_root / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    (commands / "demo.md").write_text("# demo command\n", encoding="utf-8")
    devonly = plugin_root / "scripts" / "dev-only"
    devonly.mkdir(parents=True, exist_ok=True)
    shutil.copy2(VALIDATOR, devonly / VALIDATOR.name)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """一个装好 pre-commit hook 的真 git repo，内含真 plugin 布局。"""
    root = tmp_path / "repo"
    root.mkdir()
    _git("init", "-b", "main", cwd=root)
    _make_plugin_tree(root / PLUGIN_REL, VALID_MANIFEST)
    _git("add", "-A", cwd=root)
    _git("commit", "-m", "init", cwd=root)

    hooks_dir = root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    installed = hooks_dir / "pre-commit"
    shutil.copy2(PRECOMMIT, installed)
    installed.chmod(0o755)
    return root


def _run_validator(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(VALIDATOR), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


# --- 1. worktree 正确性：validator 不得硬编码主工作区路径 ---


def test_validator_without_args_validates_its_own_plugin_root(tmp_path: Path):
    """无参调用时，校验对象必须是 validator 自己所在的 plugin，而不是硬编码路径。

    pre-commit 里是 `bash "$VALIDATOR"`（无参）。如果 validator 回退到硬编码的
    主工作区路径，那 worktree 里 commit 校验的就是别人的文件——该拦的不拦、
    不该拦的乱拦。
    """
    fake_plugin = tmp_path / "elsewhere" / "webnovel-writer_chang"
    _make_plugin_tree(fake_plugin, BROKEN_MANIFEST)

    result = subprocess.run(
        ["bash", str(fake_plugin / "scripts" / "dev-only" / VALIDATOR.name)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0, (
        "validator 无参运行时放行了一个 agents 字段非法的 manifest——"
        "说明它校验的是硬编码的主工作区，不是自己所在的 plugin。\n"
        f"stdout:\n{result.stdout}"
    )
    assert "agents" in result.stdout


def test_hook_in_worktree_blocks_manifest_broken_in_that_worktree(repo: Path):
    """在 worktree 里提交坏 manifest 必须被拦——即使主工作区的 manifest 是好的。"""
    wt = repo / "wt"
    _git("worktree", "add", "-b", "feature", str(wt), cwd=repo)

    _write_manifest(wt / PLUGIN_REL, BROKEN_MANIFEST)
    _git("add", "-A", cwd=wt)
    result = _git("commit", "-m", "break manifest in worktree", cwd=wt, check=False)

    assert result.returncode != 0, (
        "worktree 里提交了非法 manifest 却没被拦。hook 校验的是主工作区的文件。\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_hook_in_worktree_allows_commit_when_only_main_workspace_is_dirty(repo: Path):
    """主工作区 manifest 坏掉，不该拦住 worktree 里毫不相干的提交。

    这是把人逼去用 --no-verify 的那个假阳性：报错内容和你改的东西毫无关系。
    """
    wt = repo / "wt"
    _git("worktree", "add", "-b", "feature", str(wt), cwd=repo)

    # 主工作区改坏（仅工作区，未 stage、未提交）
    _write_manifest(repo / PLUGIN_REL, BROKEN_MANIFEST)

    # worktree 里改一个完全无关的 skill 文件
    (wt / PLUGIN_REL / "skills" / "demo-skill" / "helper.py").write_text("x = 2\n", encoding="utf-8")
    _git("add", "-A", cwd=wt)
    result = _git("commit", "-m", "unrelated skill edit", cwd=wt, check=False)

    assert result.returncode == 0, (
        "worktree 里一个无关改动被主工作区的脏 manifest 拦住了。\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# --- 2. 校验 index，而不是磁盘 ---


def test_hook_blocks_manifest_broken_only_in_the_index(repo: Path):
    """index 里是坏的、磁盘上是好的 —— 必须拦。

    进入历史的是 index 的内容。validator 读磁盘的话，这种状态会被放行，
    坏 manifest 直接进 commit。
    """
    plugin = repo / PLUGIN_REL
    _write_manifest(plugin, BROKEN_MANIFEST)
    _git("add", "-A", cwd=repo)
    # stage 完再把磁盘改回好的：index=坏，worktree=好
    _write_manifest(plugin, VALID_MANIFEST)

    result = _git("commit", "-m", "broken only in index", cwd=repo, check=False)

    assert result.returncode != 0, (
        "index 里的非法 manifest 被放行了——validator 校验的是磁盘工作区内容。\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_hook_allows_manifest_broken_only_in_the_worktree(repo: Path):
    """磁盘上是坏的、但没 stage —— 不该拦。改到一半不影响提交别的东西。"""
    plugin = repo / PLUGIN_REL
    (plugin / "skills" / "demo-skill" / "SKILL.md").write_text("# demo v2\n", encoding="utf-8")
    _git("add", str(plugin / "skills" / "demo-skill" / "SKILL.md"), cwd=repo)
    # 磁盘上 manifest 改坏，但不 stage
    _write_manifest(plugin, BROKEN_MANIFEST)

    result = _git("commit", "-m", "unrelated staged change", cwd=repo, check=False)

    assert result.returncode == 0, (
        "一个未 stage 的坏 manifest 拦住了无关提交。\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# --- 3. 触发范围：只在 manifest / 目录结构真变了时跑 ---


def test_hook_skips_validation_when_only_skill_content_changed(repo: Path):
    """改 skill 里的 .py / 测试 / README 不该触发 manifest 校验。

    触发面太宽 => 大量因果不成立的拦截 => 被判定为工具故障 => --no-verify。
    """
    (repo / PLUGIN_REL / "skills" / "demo-skill" / "helper.py").write_text("x = 3\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)

    result = _git("commit", "-m", "edit skill helper", cwd=repo, check=False)

    assert result.returncode == 0
    assert "validating plugin manifest" not in _output(result), (
        "只改了 skill 内容，却跑了 manifest 校验。\n"
        f"输出:\n{_output(result)}"
    )


def test_hook_validates_when_declared_command_dir_becomes_empty(repo: Path):
    """删掉 commands/ 里最后一个文件 —— manifest 没动，但 commands 声明失效，必须拦。

    这正是斜杠命令消失那次事故的形状：manifest 声明的目录不存在了。
    """
    _git("rm", f"{PLUGIN_REL}/commands/demo.md", cwd=repo)

    result = _git("commit", "-m", "remove last command", cwd=repo, check=False)

    assert result.returncode != 0, (
        "manifest 声明的 commands/ 目录被清空却放行了。\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_hook_skips_validation_for_non_plugin_files(repo: Path):
    """插件外的文件完全不触发。"""
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)

    result = _git("commit", "-m", "edit readme", cwd=repo, check=False)

    assert result.returncode == 0
    assert "validating plugin manifest" not in _output(result)


# --- 4. 不得给出绕过指引 ---


def test_hook_does_not_advertise_no_verify_bypass(repo: Path):
    """失败信息里不能写 --no-verify。

    在 blocking error 里给出官方 escape hatch，等于授权绕过：读到报错的人
    （和 AI）会把它当成"按提示操作"，而不是绕过一道防线。
    """
    _write_manifest(repo / PLUGIN_REL, BROKEN_MANIFEST)
    _git("add", "-A", cwd=repo)
    result = _git("commit", "-m", "break manifest", cwd=repo, check=False)

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "--no-verify" not in combined, (
        "失败信息里出现了 --no-verify 绕过指引。\n"
        f"输出:\n{combined}"
    )


def test_hook_source_does_not_mention_no_verify():
    assert "--no-verify" not in PRECOMMIT.read_text(encoding="utf-8"), (
        "pre-commit 源码里仍写着 --no-verify 提示"
    )


# --- 5. hook 必须能被 setup_dev_env.sh 安装 ---


TRACKED_HOOK_SOURCE = PLUGIN_ROOT / "scripts" / "dev-only" / "pre-commit"


def _bash(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_tracked_hook_source_exists_and_stays_in_sync_with_installed():
    """hook 源文件必须在 repo 里（不被 .git/hooks/ 隔离），且和安装版内容一致。

    .git/hooks/ 不进版本控制；如果源文件不在 repo 里，另一台机器 clone
    后就没这道防线。
    """
    assert TRACKED_HOOK_SOURCE.exists(), (
        f"hook 源文件不在版本控制里: {TRACKED_HOOK_SOURCE}"
    )
    assert TRACKED_HOOK_SOURCE.read_text(encoding="utf-8") == PRECOMMIT.read_text(encoding="utf-8"), (
        ".git/hooks/pre-commit 和 scripts/dev-only/pre-commit 不一致"
    )


SETUP_SCRIPT = PLUGIN_ROOT / "scripts" / "dev-only" / "setup_dev_env.sh"


def _run_install_step(repo: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    """只跑 setup_dev_env.sh 里安装 pre-commit 那一段，避免无关副作用。

    把内联脚本写到临时文件再 bash 执行，而不是塞进 `bash -c` 的字符串——
    后者在 subprocess + pytest 的组合里会被吞掉部分内容（实测）。

    路径必须用 `cd` 进 repo 后再走 `git rev-parse --git-common-dir`——
    因为 bash 子进程的 CWD 不一定是 repo 根，相对路径会写错地方。
    """
    script = tmp_path / "_install_hook.sh"
    src_posix = TRACKED_HOOK_SOURCE.as_posix()
    script.write_text(
        f"""#!/usr/bin/env bash
set -e
cd '{repo.as_posix()}'
HOOKS_DIR="$(cd "$(git rev-parse --git-common-dir)" && pwd)/hooks"
install_git_hook() {{
    local src="$1" name="$2"
    local dst="$HOOKS_DIR/$name"
    if [ ! -f "$src" ]; then
        echo "  WARN hook source missing, skipped: $src"
        return 0
    fi
    mkdir -p "$HOOKS_DIR"
    cp "$src" "$dst"
    chmod +x "$dst"
    echo "  OK installed $name -> $dst"
}}
install_git_hook "{src_posix}" "pre-commit"
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_setup_dev_env_installs_fresh_hook(tmp_path: Path):
    """没装过时，install 步骤把 source 复制到 .git/hooks/pre-commit 并 chmod +x。

    source 是真值，.git/hooks/ 是其影子——这是同步契约的根基。
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-b", "main", cwd=repo)
    target = repo / ".git" / "hooks" / "pre-commit"
    assert not target.exists()

    result = _run_install_step(repo, tmp_path)
    assert result.returncode == 0, f"install failed:\nstderr={result.stderr}"

    assert target.exists(), "hook 没被安装"
    assert target.stat().st_mode & 0o111, "installed hook 不可执行"
    assert target.read_text(encoding="utf-8") == TRACKED_HOOK_SOURCE.read_text(encoding="utf-8"), (
        "installed hook 内容 ≠ source"
    )


def test_setup_dev_env_overwrites_stale_installed_hook(tmp_path: Path):
    """已存在但内容不一致时必须用 source 覆盖——否则 hook 静默漂移。

    这就是这条修复要消除的根问题：.git/hooks/ 没版本控制，老 hook 永远在，
    source 改了没人同步。
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-b", "main", cwd=repo)

    target = repo / ".git" / "hooks" / "pre-commit"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("#!/bin/bash\necho OLD\n", encoding="utf-8")
    target.chmod(0o755)

    result = _run_install_step(repo, tmp_path)
    assert result.returncode == 0, f"install failed:\nstderr={result.stderr}"

    assert "# OLD" not in target.read_text(encoding="utf-8"), (
        "已存在的旧 hook 没被覆盖——未来 source 改了 hook 不会更新"
    )
    assert target.read_text(encoding="utf-8") == TRACKED_HOOK_SOURCE.read_text(encoding="utf-8")


def test_install_writes_into_worktree_shared_hooks_dir(tmp_path: Path):
    """从 worktree 里 install 时，应写入 worktree 共用的 .git/hooks/。

    git 的 hooks dir 在 git-common-dir（不是 git-dir）。worktree 里跑
    `git rev-parse --git-dir` 会拿到 worktree 自己的路径，但 hook 仍按
    主仓库的 .git/hooks/ 解析——必须用 --git-common-dir。
    """
    main_repo = tmp_path / "main"
    main_repo.mkdir()
    _git("init", "-b", "main", cwd=main_repo)

    wt = main_repo / "wt"
    _git("worktree", "add", "-b", "feature", str(wt), cwd=main_repo)

    _run_install_step(wt, tmp_path)

    shared_hook = main_repo / ".git" / "hooks" / "pre-commit"
    wt_local_hook = wt / ".git" / "hooks" / "pre-commit"

    assert shared_hook.exists(), "worktree install 没写入共享 hooks dir"
    assert not wt_local_hook.exists(), (
        "hook 被错误写入了 worktree 自己的 .git/hooks/——"
        "它根本不会生效，且会让每个 worktree 状态发散"
    )


def test_setup_dev_env_references_install_step():
    """setup_dev_env.sh 必须包含安装步骤。不能被 refactor 时悄悄删掉。

    上次 fix 之所以漏掉，就是 hook 不在 repo 里、setup 不管它，没有交叉
    约束。今后在 repo 里加一行 install_git_hook 调用 = 测试门槛。
    """
    setup_text = SETUP_SCRIPT.read_text(encoding="utf-8")
    assert "install_git_hook" in setup_text, (
        "setup_dev_env.sh 移除了 hook 安装——hook 又会静默失效"
    )
    assert "pre-commit" in setup_text, (
        "setup_dev_env.sh 不再 install pre-commit"
    )
