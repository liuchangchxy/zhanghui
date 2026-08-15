#!/usr/bin/env bash
# dev 环境一键初始化：建 cache symlink + 验证 marketplace + 验证 venv 可用
# idempotent，跑完一次之后日常只改代码 + 重启 Claude Code 即可
#
# spec §2.3 强制要求 cache 是 ln -sfn 指向 dev workspace 的 plugin/。
# 没有这一步的话，改了代码 Claude Code 看不到，plugin 直接挂。

set -euo pipefail

# === 配置（按本机配置硬编码，跨机器用 sed 替换） ===
PLUGIN_ROOT="/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang"
MARKETPLACE="/Users/chang/.claude/plugins/marketplaces/webnovel-chang-marketplace"
CACHE="/Users/chang/.claude/plugins/cache/webnovel-chang-marketplace/webnovel-writer_chang"

echo "=== dev environment setup ==="
echo "plugin root: $PLUGIN_ROOT"
echo "marketplace: $MARKETPLACE"
echo "cache:       $CACHE"
echo ""

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
if [ ! -d "$MARKETPLACE/webnovel-writer_chang" ]; then
    echo "  marketplace plugin dir missing. Syncing from dev workspace..."
    mkdir -p "$MARKETPLACE"
    rsync -a --delete \
        --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='.worktrees' --exclude='.tmp' \
        "$PLUGIN_ROOT/" "$MARKETPLACE/webnovel-writer_chang/"
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
            rm -rf "$CACHE"
            ln -sfn "$PLUGIN_ROOT" "$CACHE"
            echo "  ✓ cache symlink corrected"
        else
            echo "  skipped (you'll need to fix manually)"
        fi
    fi
elif [ -d "$CACHE" ]; then
    echo "  cache is a regular directory (not symlink). Removing and creating symlink..."
    rm -rf "$CACHE"
    ln -sfn "$PLUGIN_ROOT" "$CACHE"
    echo "  ✓ cache symlink created (was regular dir)"
elif [ -e "$CACHE" ]; then
    echo "  cache exists but is neither symlink nor directory: $CACHE"
    exit 1
else
    echo "  cache does not exist. Creating symlink..."
    mkdir -p "$(dirname "$CACHE")"
    ln -sfn "$PLUGIN_ROOT" "$CACHE"
    echo "  ✓ cache symlink created"
fi

# === 4. 验证 symlink 真的指向 plugin source ===
echo "[4/5] Verifying cache symlink works..."
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

# === 5. Smoke test ===
echo "[5/5] Running smoke test..."
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
