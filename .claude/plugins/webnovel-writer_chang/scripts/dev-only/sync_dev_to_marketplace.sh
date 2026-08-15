#!/usr/bin/env bash
# 同步 dev workspace 的 plugin 源码到 marketplace 仓库。
# cache 走 symlink（见 Task 4 Step 7）会自动跟上。
set -euo pipefail

# scripts/dev-only/sync_dev_to_marketplace.sh → ../.. 是 plugin root
DEV_PLUGIN="$(cd "$(dirname "$0")/../.." && pwd)"
MKT_PLUGIN="$HOME/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang"

if [[ ! -d "$DEV_PLUGIN" ]]; then
    echo "ERROR: dev plugin 不存在: $DEV_PLUGIN" >&2
    exit 1
fi

# 首次运行或目录被清空时自动创建 marketplace plugin 目录
mkdir -p "$MKT_PLUGIN"

# rsync 同步，--delete 保证 marketplace 不残留旧文件
# 使用 .gitignore 作为排除规则，避免与 .gitignore 漂移
rsync -a --delete \
    --exclude-from="$DEV_PLUGIN/.gitignore" \
    "$DEV_PLUGIN/" "$MKT_PLUGIN/"

echo "synced: $DEV_PLUGIN -> $MKT_PLUGIN"

# 校验 vendor/uv/ 二进制完整性（rsync 后确认没损坏）
if [[ -f "$MKT_PLUGIN/vendor/uv/SHA256SUMS" ]]; then
    echo "Verifying uv binary sha256..."
    # 仅校验当前平台对应条目；SHA256SUMS 文本里有所有平台 hash
    # shasum -a 256 -c 会处理
    (
        cd "$MKT_PLUGIN/vendor/uv" && shasum -a 256 -c SHA256SUMS
    ) || {
        echo "ERROR: uv binary sha256 校验失败（marketplace 上的 vendor/uv/ 已损坏）" >&2
        exit 1
    }
else
    echo "WARN: vendor/uv/SHA256SUMS 不存在，跳过 sha256 校验" >&2
fi