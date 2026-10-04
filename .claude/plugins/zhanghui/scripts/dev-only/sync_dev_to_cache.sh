#!/usr/bin/env bash
# Sync dev plugin to ALL 3 locations:
#   1. Marketplace (for Claude Code install)
#   2. Cache <version>/ (for current Claude Code session — install may be skipped)
# This ensures slash commands appear immediately without needing a Claude Code restart.
#
# Usage:
#   bash scripts/dev-only/sync_dev_to_cache.sh
set -euo pipefail

DEV_PLUGIN="$(cd "$(dirname "$0")/../.." && pwd)"
MKT_PLUGIN="$HOME/.claude/plugins/marketplaces/webnovel-chang-marketplace/zhanghui"
CACHE_DIR="$HOME/.claude/plugins/cache/webnovel-chang-marketplace/zhanghui"

if [[ ! -d "$DEV_PLUGIN" ]]; then
    echo "ERROR: dev plugin 不存在: $DEV_PLUGIN" >&2
    exit 1
fi

# Read version from plugin.json
VERSION=$(python3 -c "import json; print(json.load(open('$DEV_PLUGIN/.claude-plugin/plugin.json'))['version'])")
echo "plugin version: $VERSION"

# 1) Sync dev → marketplace
if [[ -d "$MKT_PLUGIN" ]] || mkdir -p "$MKT_PLUGIN"; then
    rsync -a --delete \
        --exclude-from="$DEV_PLUGIN/.gitignore" \
        "$DEV_PLUGIN/" "$MKT_PLUGIN/"
    echo "synced dev → marketplace"
fi

# 2) Sync dev → cache/<version>/ (with version subdir per Claude Code's expectations)
mkdir -p "$CACHE_DIR/$VERSION"
rsync -a --delete \
    --exclude-from="$DEV_PLUGIN/.gitignore" \
    "$DEV_PLUGIN/" "$CACHE_DIR/$VERSION/"
echo "synced dev → cache/$VERSION/"

echo "OK — slash commands should now be visible to Claude Code."