#!/usr/bin/env bash
# [DEPRECATED] setup_dev_env.sh
#
# 插件分发与安装已统一收拢至 canonical 路径：
#   bin/install-plugin.sh
# 本脚本不再同步 marketplace 副本，亦不再管理 cache symlink。
# 仅保留 git hooks 安装功能供仓库开发使用。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../" && pwd)"
PLUGIN_ROOT="$REPO_ROOT/.claude/plugins/zhanghui"

echo "========================================================================" >&2
echo "NOTICE: setup_dev_env.sh is DEPRECATED for plugin distribution." >&2
echo "Claude Code now loads Zhanghui directly from the canonical repository." >&2
echo "Please run 'bin/install-plugin.sh' from the repository root instead." >&2
echo "========================================================================" >&2

# === 安装 git hooks ===
echo "Installing git hooks..."
cd "$REPO_ROOT"
HOOKS_DIR="$(cd "$(git rev-parse --git-common-dir)" && pwd)/hooks"

install_git_hook() {
    local src="$1" name="$2"
    local dst="$HOOKS_DIR/$name"
    if [ ! -f "$src" ]; then
        echo "  ⚠ hook source missing, skipped: $src" >&2
        return 0
    fi
    mkdir -p "$HOOKS_DIR"
    cp "$src" "$dst"
    chmod +x "$dst"
    echo "  ✓ installed $name → $dst"
}

install_git_hook "$PLUGIN_ROOT/scripts/dev-only/pre-commit" "pre-commit"

echo ""
echo "Git hooks up to date. To install/verify Claude Code plugin, run:"
echo "  bin/install-plugin.sh"
