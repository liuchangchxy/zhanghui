#!/usr/bin/env bash
# dev 环境一键初始化：建 cache symlink + 验证 marketplace + 验证 venv 可用
# idempotent，跑完一次之后日常只改代码 + 重启 Claude Code 即可
#
# spec §2.3 强制要求 cache 是 ln -sfn 指向 dev workspace 的 plugin/。
# 没有这一步的话，改了代码 Claude Code 看不到，plugin 直接挂。

set -euo pipefail

# === 配置（按本机配置硬编码，跨机器用 sed 替换） ===
PLUGIN_ROOT="/Users/chang/Desktop/zhanghui/.claude/plugins/zhanghui"
MARKETPLACE="/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace"
CACHE="/Users/chang/.claude/plugins/cache/webnovel-chang-marketplace/zhanghui"

echo "=== dev environment setup ==="
echo "plugin root: $PLUGIN_ROOT"
echo "marketplace: $MARKETPLACE"
echo "cache:       $CACHE"
echo ""

# === 工具函数：race-safe 安装 cache symlink ===
# 旧实现是 `rm -rf $CACHE && ln -sfn ...`，中间被打断会丢 cache。
# 新实现：先 ln -sfn 到 .new 临时名，验证 symlink 能解析到有效 plugin，
# 然后 atomic mv 替换。任何一步失败 .new 自动清理，cache 永远不会是空。
install_cache_symlink() {
    local target="$1"      # plugin root 路径
    local link_path="$2"   # cache 路径

    local tmp_link="${link_path}.new.$$"

    # 1. 先建临时 symlink（如果 .new 残留先清）
    rm -f "$tmp_link"
    if ! ln -sfn "$target" "$tmp_link"; then
        echo "  ERROR: ln -sfn 失败（权限？路径错误？）"
        rm -f "$tmp_link"
        return 1
    fi

    # 2. 验证临时 symlink 能解析到有效 plugin
    if [ ! -f "$tmp_link/.claude-plugin/plugin.json" ]; then
        echo "  ERROR: 临时 symlink 无法解析到 plugin（plugin.json 不存在）"
        echo "    symlink → $target"
        echo "    但 $target/.claude-plugin/plugin.json 不存在"
        rm -f "$tmp_link"
        return 1
    fi

    # 3. 删旧 cache + atomic 替换（mv 是 atomic，不会半截状态）
    rm -rf "$link_path" 2>/dev/null || true
    if ! mv "$tmp_link" "$link_path"; then
        echo "  ERROR: mv 失败（权限？冲突？）"
        rm -f "$tmp_link"
        return 1
    fi

    echo "  ✓ cache symlink installed (race-safe): $link_path → $target"
}

# === 1. 验证 plugin source 存在 ===
echo "[1/5] Checking plugin source..."
if [ ! -d "$PLUGIN_ROOT" ]; then
    echo "ERROR: plugin root not found: $PLUGIN_ROOT"
    exit 1
fi
if [ ! -f "$PLUGIN_ROOT/.claude-plugin/plugin.json" ]; then
    echo "ERROR: plugin.json missing — 不是有效 plugin 目录"
    exit 1
fi
echo "  ✓ plugin source present"

# === 2. 验证 marketplace plugin 副本 ===
echo "[2/5] Checking marketplace plugin copy..."
if [ ! -d "$MARKETPLACE/zhanghui" ]; then
    echo "  marketplace plugin dir missing. Syncing from dev workspace..."
    mkdir -p "$MARKETPLACE"
    rsync -a --delete \
        --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='.worktrees' --exclude='.tmp' \
        "$PLUGIN_ROOT/" "$MARKETPLACE/zhanghui/"
    echo "  ✓ marketplace plugin synced"
else
    echo "  ✓ marketplace plugin present"
fi

# === 3. 设置 cache symlink（spec §2.3 强制） ===
echo "[3/5] Setting up cache symlink..."
if [ -L "$CACHE" ]; then
    TARGET=$(readlink "$CACHE")
    if [ "$TARGET" = "$PLUGIN_ROOT" ]; then
        echo "  ✓ cache symlink already correct → $TARGET"
    else
        echo "  cache symlink points to wrong target: $TARGET"
        echo "  expected: $PLUGIN_ROOT"
        read -p "  Fix to point to plugin root? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            install_cache_symlink "$PLUGIN_ROOT" "$CACHE"
        else
            echo "  skipped (you'll need to fix manually)"
        fi
    fi
elif [ -d "$CACHE" ]; then
    echo "  cache is a regular directory (not symlink). Replacing with symlink (race-safe)..."
    install_cache_symlink "$PLUGIN_ROOT" "$CACHE"
elif [ -e "$CACHE" ]; then
    echo "  cache exists but is neither symlink nor directory: $CACHE"
    exit 1
else
    echo "  cache does not exist. Creating symlink..."
    mkdir -p "$(dirname "$CACHE")"
    install_cache_symlink "$PLUGIN_ROOT" "$CACHE"
fi

# === 4. 验证 symlink 真的指向 plugin source ===
echo "[4/6] Verifying cache symlink works..."
if [ ! -L "$CACHE" ]; then
    echo "ERROR: cache is not a symlink (setup failed)"
    exit 1
fi
TARGET=$(readlink "$CACHE")
if [ "$TARGET" != "$PLUGIN_ROOT" ]; then
    echo "ERROR: cache symlink points to: $TARGET"
    echo "  expected: $PLUGIN_ROOT"
    exit 1
fi
if [ ! -f "$CACHE/.claude-plugin/plugin.json" ]; then
    echo "ERROR: cache doesn't resolve to plugin source (plugin.json missing)"
    exit 1
fi
echo "  ✓ cache symlink → $TARGET (resolves to valid plugin)"

# === 5. 安装 git hooks ===
# pre-commit 源文件在 repo 里（scripts/dev-only/pre-commit）。.git/hooks/ 不进
# 版本控制；这一步把源复制到 git 实际执行的位置。已存在的旧版本会被覆盖，
# 让"改 source 后跑一次 setup"成为同步契约。
# cd 进 plugin root，因为 install 时 bash 的 CWD 不一定是它。
echo "[5/6] Installing git hooks from scripts/dev-only/..."
cd "$PLUGIN_ROOT"
HOOKS_DIR="$(cd "$(git rev-parse --git-common-dir)" && pwd)/hooks"
install_git_hook() {
    local src="$1" name="$2"
    local dst="$HOOKS_DIR/$name"
    if [ ! -f "$src" ]; then
        echo "  ⚠ hook source missing, skipped: $src"
        return 0
    fi
    mkdir -p "$HOOKS_DIR"
    cp "$src" "$dst"
    chmod +x "$dst"
    echo "  ✓ installed $name → $dst"
}
install_git_hook "$PLUGIN_ROOT/scripts/dev-only/pre-commit" "pre-commit"

# === 6. Smoke test ===
echo "[6/6] Running smoke test..."
if PYTHONPATH="$PLUGIN_ROOT/hooks" python3 -c "
from pathlib import Path
from install_python_deps import compute_install_stamp, select_uv_binary, resolve_cache_dir
print('  ✓ install_python_deps importable')
uv = select_uv_binary(Path('$PLUGIN_ROOT/vendor/uv'))
print(f'  ✓ select_uv_binary: {uv.name}')
cache = resolve_cache_dir()
print(f'  ✓ resolve_cache_dir: {cache}')
" 2>&1; then
    echo ""
    echo "=== setup complete ==="
    echo "Cache symlink: $CACHE → $PLUGIN_ROOT"
    echo ""
    echo "Next steps:"
    echo "  1. Restart Claude Code (cache symlink will pick up new code immediately)"
    echo "  2. Run /webnovel-doctor in your book project to verify"
    echo ""
    echo "Daily workflow:"
    echo "  Edit code → save → restart Claude Code (no rehash needed)"
    echo "  Avoid: copying files into cache manually, running install scripts directly"
else
    echo "ERROR: smoke test failed"
    exit 1
fi
