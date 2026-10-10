#!/usr/bin/env bash
# [DEPRECATED] deploy-plugin.sh
# 
# 历史遗留脚本已彻底废弃。
# 不再维护任何 whitelist、copy、或 marketplace 副本同步逻辑。
#
# 请使用仓库根目录的唯一 canonical 安装/更新路径：
#   bin/install-plugin.sh

echo "ERROR: deploy-plugin.sh has been permanently deprecated." >&2
echo "Claude Code now loads Zhanghui directly from the canonical repository." >&2
echo "Please run 'bin/install-plugin.sh' from the repository root instead." >&2
exit 1