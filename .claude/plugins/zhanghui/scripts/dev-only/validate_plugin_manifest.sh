#!/usr/bin/env bash
# plugin.json manifest validator — 防止无效字段导致 plugin "failed to load"。
#
# 用法：./validate_plugin_manifest.sh [plugin_root] [manifest_path]
#   plugin_root   默认 = 本脚本所在的那个 plugin（scripts/dev-only/../..）。
#                 必须靠脚本位置推导，不能硬编码绝对路径：否则在 git worktree
#                 里调用时会去校验主工作区的文件——该拦的不拦，不该拦的乱拦。
#   manifest_path 默认 = plugin_root/.claude-plugin/plugin.json。
#                 pre-commit 会传入从 index 抽出的那份，因为进入历史的是 index
#                 的内容，不是磁盘工作区的内容。
#
# 跑在 setup_dev_env.sh / sync_dev_to_marketplace.sh 之后能挡住所有已知错误。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PLUGIN_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PLUGIN_ROOT="${1:-$DEFAULT_PLUGIN_ROOT}"
MANIFEST="${2:-$PLUGIN_ROOT/.claude-plugin/plugin.json}"

echo "=== validating plugin manifest ==="
echo "plugin root: $PLUGIN_ROOT"
echo "manifest:    $MANIFEST"
echo ""

if [ ! -f "$MANIFEST" ]; then
    echo "ERROR: manifest 不存在: $MANIFEST"
    exit 1
fi

ERRORS=0

# 用 python 解析 + 校验（路径走环境变量，避免路径里的引号/空格破坏 heredoc）
WN_MANIFEST="$MANIFEST" WN_PLUGIN_ROOT="$PLUGIN_ROOT" python3 <<'PYEOF'
import json
import os
import sys
from pathlib import Path

manifest_path = Path(os.environ["WN_MANIFEST"])
plugin_root = Path(os.environ["WN_PLUGIN_ROOT"])
data = json.loads(manifest_path.read_text(encoding="utf-8"))

errors = []

# 1. 必填字段
for field in ("name", "version", "description"):
    if field not in data:
        errors.append(f"缺少必填字段: {field}")

# 2. 非法字段（Claude Code 自动加载或不支持）
FORBIDDEN_FIELDS = ("agents", "hooks")
for field in FORBIDDEN_FIELDS:
    if field in data:
        errors.append(
            f"非法字段: {field!r}（agents 从 agents/ 目录自动发现；"
            f"hooks/hooks.json 自动加载，manifest 不应再声明）"
        )

# 3. name 必须匹配目录名
if data.get("name") and data["name"] != plugin_root.name:
    errors.append(
        f"plugin.name {data['name']!r} 不匹配目录名 {plugin_root.name!r}"
    )

# 4. skills 字段声明的目录必须存在
if "skills" in data:
    skills_dir = plugin_root / data["skills"].lstrip("./")
    if not skills_dir.is_dir():
        errors.append(f"skills 字段声明的目录不存在: {skills_dir}")

# 5. commands 字段声明的目录必须存在
if "commands" in data:
    commands_dir = plugin_root / data["commands"].lstrip("./")
    if not commands_dir.is_dir():
        errors.append(f"commands 字段声明的目录不存在: {commands_dir}")

# 6. version 必须是 semver 字符串
version = data.get("version", "")
if not version.count(".") >= 2 or not all(p.isdigit() for p in version.split(".") if p):
    errors.append(f"version 格式不像 semver: {version!r}")

if errors:
    print(f"✘ {len(errors)} 个错误:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("✓ manifest 验证通过")
    print(f"  name:     {data['name']}")
    print(f"  version:  {data['version']}")
    print(f"  fields:   {list(data.keys())}")
    if "skills" in data:
        n_skills = len(list((plugin_root / data['skills'].lstrip('./')).iterdir()))
        print(f"  skills:   {n_skills} 个目录")
    if "commands" in data:
        n_cmds = len(list((plugin_root / data['commands'].lstrip('./')).glob('*.md')))
        print(f"  commands: {n_cmds} 个 .md")
PYEOF
RC=$?

if [ $RC -ne 0 ]; then
    echo
    echo "✘ manifest 验证失败——Claude Code 会拒绝加载这个 plugin"
    exit $RC
fi
echo
echo "✓ 可以安全 sync 到 marketplace / cache"
