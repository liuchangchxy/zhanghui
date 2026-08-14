# webnovel-writer plugin 自包含化重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 fork 出来的 webnovel-writer plugin 重构成 self-contained，任何书项目目录 cd 进去就能用，不再要求每个项目手动配 `.claude/`。

**Architecture:** 把 plugin 重命名为 `webnovel-writer_chang`，建立独立 marketplace `webnovel-chang-marketplace`，把 dev workspace 的 5 个项目级 skill + 10 个脚本全部内化到 plugin，所有路径变量统一到 `${CLAUDE_PLUGIN_ROOT}` 与 `python3`。书项目侧零 `.claude/` 配置。

**Tech Stack:** Python 3.14 (本机 `python3`)、pytest、Claude Code marketplace 机制、shell symlink。无新依赖。

**Spec:** `docs/superpowers/specs/2026-08-15-webnovel-plugin-self-contained-refactor-design.md`

---

## 全局约定

- **Python 解释器**：本机没有 `python` 别名，统一用 `python3 -X utf8`（spec §0.4）
- **CLAUDE_PLUGIN_ROOT**：Claude Code 自动注入，指向 plugin cache 路径（dev 模式下 symlink 到 dev workspace 的 `plugins/webnovel-writer_chang/`）
- **CLAUDE_PROJECT_DIR**：plugin 内不再使用，仅 dev workspace 的 settings.json 引用
- **Commit 粒度**：每个 Task 末尾一个 commit，格式 `<type>(<scope>): <what>`（type ∈ {feat, fix, refactor, test, docs, chore}）
- **测试位置**：`plugins/webnovel-writer_chang/scripts/tests/`，统一命令：
  ```bash
  cd plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/ -v
  ```
- **重启时机**：每完成 Phase（B / C / D / E / F）后建议重启 Claude Code 一次让 cache 重新加载（marketplace cache 路径通过 symlink 关联 dev workspace，cache 内的 plugin.json / hooks.json 不会自动 reload）

---

## 文件结构总览（重构后）

| 文件/目录 | 用途 |
|---|---|
| `ai写小说工具开发/.claude/plugins/webnovel-writer_chang/` | ★ plugin 源码（dev workspace） |
| `ai写小说工具开发/.claude/plugins/webnovel-writer_chang/.claude-plugin/plugin.json` | name: webnovel-writer_chang |
| `ai写小说工具开发/.claude/plugins/webnovel-writer_chang/hooks/hooks.json` | SessionStart + PreToolUse guard |
| `ai写小说工具开发/.claude/plugins/webnovel-writer_chang/scripts/` | 核心脚本（webnovel.py + 内化脚本） |
| `ai写小说工具开发/.claude/plugins/webnovel-writer_chang/scripts/_shared/` | 跨 skill 共享脚本（text_humanizer.py） |
| `ai写小说工具开发/.claude/plugins/webnovel-writer_chang/skills/` | 14 个 SKILL.md（9 个原有 + 5 个迁移：fast-write/revise/deslop-check/resume/chart-scan） |
| `ai写小说工具开发/.claude/plugins/webnovel-writer_chang/agents/` | 4 个 agent md |
| `ai写小说工具开发/.claude/plugins/webnovel-writer_chang/templates/` | 个人语料默认内容（init 时 copy 出去） |
| `~/.claude/plugins/marketplaces/webnovel-chang-marketplace/` | 你的专属 marketplace |
| `~/.claude/plugins/marketplaces/webnovel-chang-marketplace/.claude-plugin/marketplace.json` | 声明 plugin: webnovel-writer_chang |
| `~/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/` | plugin 副本（dev → marketplace 同步目标） |
| `~/.claude/plugins/cache/webnovel-chang-marketplace/webnovel-writer_chang/` | Claude Code 实际加载的 cache |
| `~/.claude/settings.json` | marketplaces + enabledPlugins |
| `ai写小说工具开发/.claude/settings.json` | dev 配置（瘦身后只保留 enabledPlugins + 必要权限） |
| `ai写小说工具开发/docs/PROJECT_MAP.md` | 新增：参考 vs 开发分层图 |
| `ai写小说工具开发/README.md` | 重写为 fork 开发指南 |
| `ai写小说工具开发/docs/KNOWN_ISSUES.md` | 删除 M-H8 / MED-5 / MED-52 |

---

# Phase 0: 准备

## Task 1: 创建 worktree 隔离重构

**Files:**
- Create: `.claude/worktrees/refactor-self-contained/` (git worktree)

- [ ] **Step 1: 检查 git 状态干净**

```bash
cd /Users/chang/Desktop/ai写小说工具开发 && git status
```

预期输出：`nothing to commit, working tree clean`（如果有未提交改动，先 commit 或 stash）

- [ ] **Step 2: 创建 worktree**

```bash
cd /Users/chang/Desktop/ai写小说工具开发 && git worktree add .claude/worktrees/refactor-self-contained -b refactor/self-contained
```

预期输出：`Preparing worktree (new branch 'refactor/self-contained')... HEAD is now at 26e6c11 ...` 类似

- [ ] **Step 3: 切换到 worktree 工作**

```bash
cd .claude/worktrees/refactor-self-contained && pwd
```

预期输出：`/Users/chang/Desktop/ai写小说工具开发/.claude/worktrees/refactor-self-contained`

- [ ] **Step 4: 验证 plugin 还在**

```bash
ls .claude/plugins/webnovel-writer/hooks/hooks.json && cat .claude/settings.json | head -5
```

预期输出：两个文件都存在且能读

**Note:** 后续所有 Task 都在这个 worktree 路径下操作；最终 merge 回 main 前在 main 分支 cherry-pick 或 squash。

---

# Phase A: Plugin 重命名

## Task 2: 重命名 plugin 目录 webnovel-writer → webnovel-writer_chang

**Files:**
- Rename: `.claude/plugins/webnovel-writer/` → `.claude/plugins/webnovel-writer_chang/`

- [ ] **Step 1: git mv 重命名目录**

```bash
cd /Users/chang/Desktop/ai写小说工具开发/.claude/worktrees/refactor-self-contained
git mv .claude/plugins/webnovel-writer .claude/plugins/webnovel-writer_chang
```

- [ ] **Step 2: 验证重命名成功**

```bash
ls -la .claude/plugins/
```

预期输出：看到 `webnovel-writer_chang/`，没有 `webnovel-writer/`

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(plugin): rename webnovel-writer to webnovel-writer_chang (dir only)"
```

---

## Task 3: 更新 plugin.json 的 name + version 字段

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/.claude-plugin/plugin.json:3-4`

- [ ] **Step 1: 读取当前 name + version 字段**

```bash
cat .claude/plugins/webnovel-writer_chang/.claude-plugin/plugin.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('name:', d['name']); print('version:', d['version'])"
```

预期输出：`name: webnovel-writer` 与 `version: 6.2.1`

- [ ] **Step 2: 用 Python 同时改写 name 与 version 字段**

```bash
python3 -c "
import json
from pathlib import Path
p = Path('.claude/plugins/webnovel-writer_chang/.claude-plugin/plugin.json')
data = json.loads(p.read_text(encoding='utf-8'))
data['name'] = 'webnovel-writer_chang'
data['version'] = '6.3.0'
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('updated name:', data['name'])
print('updated version:', data['version'])
"
```

预期输出：`updated name: webnovel-writer_chang` 与 `updated version: 6.3.0`

- [ ] **Step 3: 验证 JSON 仍合法**

```bash
python3 -c "import json; json.load(open('.claude/plugins/webnovel-writer_chang/.claude-plugin/plugin.json'))" && echo "JSON OK"
```

预期输出：`JSON OK`

- [ ] **Step 4: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/.claude-plugin/plugin.json
git commit -m "refactor(plugin): rename plugin.json name to webnovel-writer_chang and bump version to 6.3.0"
```

---

## Task 4: 创建独立 marketplace + 首次 cp plugin + 建 cache symlink

**Files:**
- Create: `~/.claude/plugins/marketplaces/webnovel-chang-marketplace/.claude-plugin/marketplace.json`
- Create: `~/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/`（plugin 副本）
- Symlink: `~/.claude/plugins/cache/webnovel-chang-marketplace/webnovel-writer_chang/` → dev workspace

- [ ] **Step 1: 创建 marketplace 目录**

```bash
mkdir -p ~/.claude/plugins/marketplaces/webnovel-chang-marketplace/.claude-plugin
```

- [ ] **Step 2: 写 marketplace.json**

```bash
cat > ~/.claude/plugins/marketplaces/webnovel-chang-marketplace/.claude-plugin/marketplace.json <<'EOF'
{
  "name": "webnovel-chang-marketplace",
  "owner": {
    "name": "chang",
    "email": "chang@local"
  },
  "plugins": [
    {
      "name": "webnovel-writer_chang",
      "description": "fork of webnovel-writer with self-contained plugin layout; see ai写小说工具开发/ docs/PROJECT_MAP.md",
      "version": "6.3.0",
      "source": "./webnovel-writer_chang"
    }
  ]
}
EOF
```

- [ ] **Step 3: 验证 JSON 合法**

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/marketplaces/webnovel-chang-marketplace/.claude-plugin/marketplace.json')); print('plugins:', [p['name'] for p in d['plugins']])"
```

预期输出：`plugins: ['webnovel-writer_chang']`

- [ ] **Step 4: 首次手动 cp plugin 源码到 marketplace**

```bash
cp -R .claude/plugins/webnovel-writer_chang ~/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang
ls ~/.claude/plugins/marketplaces/webnovel-chang-marketplace/
```

预期输出：看到 `webnovel-writer_chang/` 子目录和 `.claude-plugin/`

- [ ] **Step 5: 创建 cache 目录（先空目录，等 Claude Code 安装触发）**

```bash
mkdir -p ~/.claude/plugins/cache/webnovel-chang-marketplace
ls -la ~/.claude/plugins/cache/webnovel-chang-marketplace/
```

预期输出：cache 目录存在但 webnovel-writer_chang 子目录还未创建

- [ ] **Step 6: 写 sync_dev_to_marketplace.sh 脚本**

```bash
mkdir -p .claude/plugins/webnovel-writer_chang/scripts/dev-only
cat > .claude/plugins/webnovel-writer_chang/scripts/dev-only/sync_dev_to_marketplace.sh <<'BASH_EOF'
#!/usr/bin/env bash
# 同步 dev workspace 的 plugin 源码到 marketplace 仓库。
# cache 走 symlink（见 Task 4 Step 7）会自动跟上。
set -euo pipefail

DEV_PLUGIN="/Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang"
MKT_PLUGIN="$HOME/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang"

if [[ ! -d "$DEV_PLUGIN" ]]; then
    echo "ERROR: dev plugin 不存在: $DEV_PLUGIN" >&2
    exit 1
fi
if [[ ! -d "$MKT_PLUGIN" ]]; then
    echo "ERROR: marketplace plugin 不存在: $MKT_PLUGIN" >&2
    exit 1
fi

# rsync 同步，--delete 保证 marketplace 不残留旧文件
rsync -a --delete \
    --exclude='.git/' \
    --exclude='__pycache__/' \
    --exclude='.pytest_cache/' \
    --exclude='.in_use/' \
    "$DEV_PLUGIN/" "$MKT_PLUGIN/"

echo "synced: $DEV_PLUGIN -> $MKT_PLUGIN"
BASH_EOF
chmod +x .claude/plugins/webnovel-writer_chang/scripts/dev-only/sync_dev_to_marketplace.sh
ls -la .claude/plugins/webnovel-writer_chang/scripts/dev-only/
```

预期输出：脚本存在并可执行

- [ ] **Step 7: Commit marketplace 与 sync 脚本**

注：marketplace JSON 在 `~/.claude/plugins/marketplaces/` 下，不在 dev workspace 的 git 里。dev workspace 只 commit sync 脚本。

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/dev-only/sync_dev_to_marketplace.sh
git commit -m "feat(plugin): add dev-only/sync_dev_to_marketplace.sh"
```

## Task 4b: 把 cache 建为指向 dev workspace 的 symlink

**Files:**
- Symlink: `~/.claude/plugins/cache/webnovel-chang-marketplace/webnovel-writer_chang/` → dev workspace

- [ ] **Step 1: 关闭 Claude Code（手动操作）**

注：cache 目录若已存在（之前 Claude Code 安装过），先确认是否空。

- [ ] **Step 2: 创建 symlink**

```bash
ln -sfn /Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang \
    ~/.claude/plugins/cache/webnovel-chang-marketplace/webnovel-writer_chang
ls -la ~/.claude/plugins/cache/webnovel-chang-marketplace/
```

预期输出：看到 `webnovel-writer_chang -> /Users/chang/Desktop/ai写小说工具开发/.claude/plugins/webnovel-writer_chang`

- [ ] **Step 3: 验证 symlink 解析**

```bash
readlink ~/.claude/plugins/cache/webnovel-chang-marketplace/webnovel-writer_chang
ls ~/.claude/plugins/cache/webnovel-chang-marketplace/webnovel-writer_chang/.claude-plugin/plugin.json
```

预期输出：
- `readlink` 输出 dev workspace 的绝对路径
- `ls` 能解析到 plugin.json（symlink 工作）

- [ ] **Step 4: 重启 Claude Code 让 cache symlink 生效**

注：手动操作。重启后 Claude Code 从 symlink 解析 plugin，加载 dev workspace 的代码。

---

# Phase B: 切换 user-level settings.json

## Task 5: 添加 marketplaces 字段指向新 marketplace

**Files:**
- Modify: `~/.claude/settings.json`

- [ ] **Step 1: 备份 user settings**

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak.$(date +%Y%m%d-%H%M%S)
ls -la ~/.claude/settings.json.bak.*
```

预期输出：至少一个新备份文件

- [ ] **Step 2: 读取当前 settings.json 看结构**

```bash
python3 -c "
import json
from pathlib import Path
p = Path.home() / '.claude' / 'settings.json'
data = json.loads(p.read_text(encoding='utf-8'))
print('top keys:', list(data.keys()))
print('has marketplaces:', 'marketplaces' in data)
print('enabledPlugins:', data.get('enabledPlugins'))
"
```

预期输出：实际看到的当前结构（user settings.json 当前**没有** `enabledPlugins` 或 `marketplaces` 字段——这两个字段会被本次 task 新增；plugin 当前是 dev workspace scope 启用的，不是 user scope）

- [ ] **Step 3: 加 marketplaces 字段**

```bash
python3 <<'PYEOF'
import json
from pathlib import Path
from os.path import expanduser

p = Path(expanduser('~/.claude/settings.json'))
data = json.loads(p.read_text(encoding='utf-8'))
data.setdefault('marketplaces', {})
data['marketplaces']['webnovel-chang-marketplace'] = expanduser('~/.claude/plugins/marketplaces/webnovel-chang-marketplace')
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('marketplaces:', list(data['marketplaces'].keys()))
PYEOF
```

预期输出：`marketplaces: ['webnovel-chang-marketplace']`

- [ ] **Step 4: 验证 JSON 仍合法**

```bash
python3 -c "import json; json.load(open('$HOME/.claude/settings.json'))" && echo "JSON OK"
```

预期输出：`JSON OK`

---

## Task 6: 添加 fork plugin 到 enabledPlugins，关闭旧 plugin

**Files:**
- Modify: `~/.claude/settings.json`

- [ ] **Step 1: 切换 enabledPlugins**

```bash
python3 <<'PYEOF'
import json
from pathlib import Path
from os.path import expanduser

p = Path(expanduser('~/.claude/settings.json'))
data = json.loads(p.read_text(encoding='utf-8'))
ep = data.setdefault('enabledPlugins', {})
ep['webnovel-writer@webnovel-writer-marketplace'] = False
ep['webnovel-writer_chang@webnovel-chang-marketplace'] = True
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('enabledPlugins:', json.dumps(ep, indent=2))
PYEOF
```

预期输出：`webnovel-writer@webnovel-writer-marketplace: false` 与 `webnovel-writer_chang@webnovel-chang-marketplace: true`

- [ ] **Step 2: 验证 JSON**

```bash
python3 -c "import json; json.load(open('$HOME/.claude/settings.json'))" && echo "JSON OK"
```

预期输出：`JSON OK`

- [ ] **Step 3: 重启 Claude Code 让新 plugin 生效**

注：手动操作，关闭当前 claude 会话、重新启动 `claude` 命令。第一次启动时 Claude Code 会从 marketplace 仓库安装 plugin 到 cache（cache 是 Task 4b Step 2 建好的 symlink → dev workspace），所以新装的就是 dev workspace 当前版本的 plugin。

**注**：user-scope 启用 `webnovel-writer_chang@webnovel-chang-marketplace: true` 会与 dev-workspace 的 `enabledPlugins`（裸名 `webnovel-writer`，Task 24 会改成 `_chang` 后缀）共存——两者指向同一个 plugin 名，Claude Code 会去重为一份加载。预期。

---

# Phase C: 路径变量统一（python3 + CLAUDE_PLUGIN_ROOT）

## Task 7: 修 hooks/hooks.json：python → python3

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/hooks/hooks.json`

- [ ] **Step 1: 读当前 hooks.json**

```bash
cat .claude/plugins/webnovel-writer_chang/hooks/hooks.json
```

预期输出：3 条 `command` 字段都是 `python -X utf8 ...`

- [ ] **Step 2: 替换 python → python3**

```bash
sed -i '' 's/"python -X utf8/"python3 -X utf8/g' .claude/plugins/webnovel-writer_chang/hooks/hooks.json
```

- [ ] **Step 3: 验证替换结果**

```bash
grep -c '"python3 -X utf8' .claude/plugins/webnovel-writer_chang/hooks/hooks.json
grep -c '"python -X utf8"' .claude/plugins/webnovel-writer_chang/hooks/hooks.json
```

预期输出：第一个命令输出 `3`（3 处已替换），第二个命令输出 `0`（无残留裸 `python`）

- [ ] **Step 4: 验证 JSON 合法**

```bash
python3 -c "import json; json.load(open('.claude/plugins/webnovel-writer_chang/hooks/hooks.json'))" && echo "JSON OK"
```

预期输出：`JSON OK`

- [ ] **Step 5: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/hooks/hooks.json
git commit -m "fix(plugin/hooks): use python3 not python (macOS has no python alias)"
```

---

## Task 8: 修所有 plugin 自带 SKILL.md：python → python3

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/skills/*/SKILL.md`（10 个文件）

- [ ] **Step 1: 列出待修改文件**

```bash
find .claude/plugins/webnovel-writer_chang/skills -name SKILL.md
```

预期输出：14 个 SKILL.md

- [ ] **Step 2: 替换所有 SKILL.md 里的 python → python3**

```bash
find .claude/plugins/webnovel-writer_chang/skills -name SKILL.md -exec sed -i '' 's/python -X utf8/python3 -X utf8/g' {} +
```

- [ ] **Step 3: 验证替换（用宽松 grep 覆盖有引号/无引号两种写法）**

```bash
echo "裸 python -X utf8 残留："
grep -rEn '(?<![A-Za-z0-9_])python -X utf8' .claude/plugins/webnovel-writer_chang/skills/ | wc -l
echo "python3 -X utf8 命中数："
grep -rn 'python3 -X utf8' .claude/plugins/webnovel-writer_chang/skills/ | wc -l
```

预期输出：第一个数字 `0`，第二个数字大于 0

- [ ] **Step 4: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/skills/
git commit -m "fix(plugin/skills): use python3 not python in all SKILL.md"
```

---

## Task 9: 全局 sweep：所有 SKILL.md 与 agent md 的 CLAUDE_PROJECT_DIR 改为 CLAUDE_PLUGIN_ROOT

**Files:**
- Modify: 8 个 SKILL.md（init/plan/write/dashboard/review/query/learn/doctor）的 `export WORKSPACE_ROOT=...` 行
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md:136`（SCRIPTS_DIR 反模式 fallback）

**注意**：`scripts/project_locator.py`（6 处）与 `hooks/session_start.py:33` 的 `CLAUDE_PROJECT_DIR` 引用**有意保留**（spec §2.4）——本 Task 不动这些。TDD 测试 `test_no_claude_project_dir_in_skills` 范围**仅限** skills/agents md。

- [ ] **Step 1: 列出所有需要修的 SKILL.md**

```bash
grep -rln 'CLAUDE_PROJECT_DIR' .claude/plugins/webnovel-writer_chang/skills/ .claude/plugins/webnovel-writer_chang/agents/
```

预期输出：列出 8 个 SKILL.md（init/plan/write/dashboard/review/query/learn/doctor）+ 0 个 agent md（agent md 不引用 CLAUDE_PROJECT_DIR）。具体行号如：
- `skills/webnovel-init/SKILL.md:141`
- `skills/webnovel-doctor/SKILL.md:27`
- `skills/webnovel-learn/SKILL.md:16`
- `skills/webnovel-write/SKILL.md:135,136`
- `skills/webnovel-plan/SKILL.md:31`
- `skills/webnovel-dashboard/SKILL.md:20`
- `skills/webnovel-review/SKILL.md:16`
- `skills/webnovel-query/SKILL.md:17`

- [ ] **Step 2: 全局替换 WORKSPACE_ROOT 表达式**

对每个 SKILL.md，把：
```bash
export WORKSPACE_ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
```
替换为：
```bash
export WORKSPACE_ROOT="${CLAUDE_PLUGIN_ROOT}/.."   # plugin/..  ≈ plugin 父目录（即包含 .claude/ 的 workspace 根）
```

或更准确：因 `CLAUDE_PROJECT_DIR` 在 marketplace 安装下未被注入，但 `CLAUDE_PLUGIN_ROOT` 一定存在；plugin 父目录就是 Claude Code 启动时的 PWD（即 dev workspace 或书项目根）。所以 `${CLAUDE_PLUGIN_ROOT}/..` 等价于 `${CLAUDE_PROJECT_DIR:-$PWD}`。

批量替换：
```bash
find .claude/plugins/webnovel-writer_chang/skills -name SKILL.md -exec sed -i '' 's|export WORKSPACE_ROOT="\${CLAUDE_PROJECT_DIR:-\$PWD}"|export WORKSPACE_ROOT="\${CLAUDE_PLUGIN_ROOT}/.."|g' {} +
```

- [ ] **Step 3: 修 webnovel-write SKILL.md 的 SCRIPTS_DIR 反模式 fallback（line 136）**

```bash
sed -i '' 's|export SCRIPTS_DIR="\${CLAUDE_PLUGIN_ROOT:-\${CLAUDE_PROJECT_DIR:-\$PWD}}/.claude/plugins/webnovel-writer/scripts"|export SCRIPTS_DIR="\${CLAUDE_PLUGIN_ROOT}/scripts"|g' \
    .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
grep -n 'SCRIPTS_DIR' .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
```

预期输出：SCRIPTS_DIR 行已无 CLAUDE_PROJECT_DIR

- [ ] **Step 4: 修 webnovel-write SKILL.md 里 `python3 ${CLAUDE_PROJECT_DIR:-...}/.claude/scripts/...` 调用**

```bash
grep -n 'CLAUDE_PROJECT_DIR' .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
```

预期输出：列出 line 149/330/352/355 等。对每一处 `python3 ${CLAUDE_PROJECT_DIR:-${PWD}}/.claude/scripts/<name>.py` 或 `python3 ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/<name>.py` 改为 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py`。

```bash
sed -i '' 's|python3 \${CLAUDE_PROJECT_DIR:-\${PWD}}/.claude/scripts/|python3 ${CLAUDE_PLUGIN_ROOT}/scripts/|g' .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
sed -i '' 's|python3 \${CLAUDE_PROJECT_DIR:-\$(pwd)}/.claude/scripts/|python3 ${CLAUDE_PLUGIN_ROOT}/scripts/|g' .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
sed -i '' 's|node \${CLAUDE_PROJECT_DIR:-\${PWD}}/.claude/scripts/|node ${CLAUDE_PLUGIN_ROOT}/scripts/|g' .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
sed -i '' 's|node \${CLAUDE_PROJECT_DIR:-\$(pwd)}/.claude/scripts/|node ${CLAUDE_PLUGIN_ROOT}/scripts/|g' .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
```

- [ ] **Step 5: 验证 SKILL.md / agent md 内无 CLAUDE_PROJECT_DIR**

```bash
grep -rn 'CLAUDE_PROJECT_DIR' .claude/plugins/webnovel-writer_chang/skills/ .claude/plugins/webnovel-writer_chang/agents/
```

预期输出：0 行（scripts/project_locator.py 与 hooks/session_start.py 不在 grep 范围内，保留 CLAUDE_PROJECT_DIR 引用是允许的）

- [ ] **Step 6: 验证 hooks.json / agent md 内也无反模式**

```bash
grep -rn 'python -X utf8' .claude/plugins/webnovel-writer_chang/skills/ .claude/plugins/webnovel-writer_chang/agents/ .claude/plugins/webnovel-writer_chang/hooks/
grep -rn 'CLAUDE_PLUGIN_ROOT:-' .claude/plugins/webnovel-writer_chang/skills/ .claude/plugins/webnovel-writer_chang/agents/
```

预期输出：两个 grep 都输出 0 行

- [ ] **Step 7: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/skills/ .claude/plugins/webnovel-writer_chang/agents/
git commit -m "fix(plugin): replace CLAUDE_PROJECT_DIR with CLAUDE_PLUGIN_ROOT across all SKILL.md and agent md"
```

---

## Task 10: 修 plugin 自带 agent md：python → python3

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/agents/*.md`（4 个文件）

- [ ] **Step 1: 列出 agents**

```bash
ls .claude/plugins/webnovel-writer_chang/agents/
```

预期输出：`context-agent.md` `data-agent.md` `reviewer.md` `deconstruction-agent.md`

- [ ] **Step 2: 替换 python → python3**

```bash
find .claude/plugins/webnovel-writer_chang/agents -name '*.md' -exec sed -i '' 's/python -X utf8/python3 -X utf8/g' {} +
```

- [ ] **Step 3: 验证替换**

```bash
echo "裸 python -X utf8 残留："
grep -rn '"python -X utf8' .claude/plugins/webnovel-writer_chang/agents/ | wc -l
echo "python3 -X utf8 命中："
grep -rn 'python3 -X utf8' .claude/plugins/webnovel-writer_chang/agents/ | wc -l
```

预期输出：第一个 `0`，第二个 > 0

- [ ] **Step 4: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/agents/
git commit -m "fix(plugin/agents): use python3 not python in all agent md"
```

---

# Phase D: Dev skills 迁移到 plugin

## Task 11: 建 plugin 的 scripts/_shared/ 目录

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/scripts/_shared/` + `.gitkeep`

- [ ] **Step 1: 建目录**

```bash
mkdir -p .claude/plugins/webnovel-writer_chang/scripts/_shared
touch .claude/plugins/webnovel-writer_chang/scripts/_shared/.gitkeep
```

- [ ] **Step 2: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/_shared/.gitkeep
git commit -m "chore(plugin/scripts): add _shared/ directory for cross-skill scripts"
```

---

## Task 12: 迁移 text_humanizer.py 到 _shared/

**Files:**
- Move: `.claude/scripts/text_humanizer.py` → `.claude/plugins/webnovel-writer_chang/scripts/_shared/text_humanizer.py`

- [ ] **Step 1: git mv 移动文件**

```bash
git mv .claude/scripts/text_humanizer.py .claude/plugins/webnovel-writer_chang/scripts/_shared/text_humanizer.py
```

- [ ] **Step 2: 验证 .claude/scripts/ 已无 text_humanizer.py**

```bash
ls .claude/scripts/text_humanizer.py 2>&1 || echo "OK: 已移走"
```

预期输出：`OK: 已移走`

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(scripts): move text_humanizer.py to plugin/scripts/_shared/"
```

---

## Task 13: 迁移 webnovel-fast-write skill + 依赖脚本

**Files:**
- Move:
  - `.claude/skills/webnovel-fast-write/` → `.claude/plugins/webnovel-writer_chang/skills/webnovel-fast-write/`
  - `.claude/scripts/changes_gate.py` → `.claude/plugins/webnovel-writer_chang/scripts/changes_gate.py`
  - `.claude/scripts/context_slice.py` → `.claude/plugins/webnovel-writer_chang/scripts/context_slice.py`
  - `.claude/scripts/snapshot_manager.py` → `.claude/plugins/webnovel-writer_chang/scripts/snapshot_manager.py`
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-fast-write/SKILL.md`（更新脚本路径）

- [ ] **Step 1: 移动 skill 目录**

```bash
git mv .claude/skills/webnovel-fast-write .claude/plugins/webnovel-writer_chang/skills/webnovel-fast-write
```

- [ ] **Step 2: 移动依赖脚本（3 个）**

```bash
git mv .claude/scripts/changes_gate.py .claude/plugins/webnovel-writer_chang/scripts/changes_gate.py
git mv .claude/scripts/context_slice.py .claude/plugins/webnovel-writer_chang/scripts/context_slice.py
git mv .claude/scripts/snapshot_manager.py .claude/plugins/webnovel-writer_chang/scripts/snapshot_manager.py
```

- [ ] **Step 3: 改 SKILL.md 里的脚本路径**

打开 `.claude/plugins/webnovel-writer_chang/skills/webnovel-fast-write/SKILL.md`，把所有 `python3 ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/<name>.py` 替换为 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py`（涉及 `changes_gate.py`、`context_slice.py`、`snapshot_manager.py`、`text_humanizer.py`）

- [ ] **Step 4: 跑 tests 验证未破坏**

注：`changes_gate.py` 当前在 dev `tests/` 里**没有对应 pytest 文件**——dev 测试目录只有 `test_context_slice.py` / `test_snapshot_manager.py` / `test_rejection_contract.py` 等少数脚本级测试，changes_gate 是 CLI 工具，行为靠手动跑测。Task 13/14 阶段只验证存在的脚本级测试：

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_context_slice.py tests/test_snapshot_manager.py -v 2>&1 | tail -20
```

预期输出：现有测试全绿（仅这两个文件）

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发/.claude/worktrees/refactor-self-contained
git add -A
git commit -m "feat(plugin/skills): migrate webnovel-fast-write + changes_gate/context_slice/snapshot_manager"
```

---

## Task 14: 迁移 webnovel-revise skill + 依赖脚本

**Files:**
- Move:
  - `.claude/skills/webnovel-revise/` → `.claude/plugins/webnovel-writer_chang/skills/webnovel-revise/`
  - `.claude/scripts/revise_chapter.py` → `.claude/plugins/webnovel-writer_chang/scripts/revise_chapter.py`
  - `.claude/scripts/rejection_contract.py` → `.claude/plugins/webnovel-writer_chang/scripts/rejection_contract.py`
  - `.claude/scripts/normalize-punctuation.js` → `.claude/plugins/webnovel-writer_chang/scripts/normalize-punctuation.js`
- Modify: SKILL.md 路径更新

- [ ] **Step 1: 移动 skill 目录**

```bash
git mv .claude/skills/webnovel-revise .claude/plugins/webnovel-writer_chang/skills/webnovel-revise
```

- [ ] **Step 2: 移动依赖脚本**

```bash
git mv .claude/scripts/revise_chapter.py .claude/plugins/webnovel-writer_chang/scripts/revise_chapter.py
git mv .claude/scripts/rejection_contract.py .claude/plugins/webnovel-writer_chang/scripts/rejection_contract.py
git mv .claude/scripts/normalize-punctuation.js .claude/plugins/webnovel-writer_chang/scripts/normalize-punctuation.js
```

- [ ] **Step 3: 改 SKILL.md 路径**

把所有 `python3 ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/<name>.py` / `node ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/<name>.js` 替换为 `${CLAUDE_PLUGIN_ROOT}/scripts/<name>`（涉及 `revise_chapter.py`、`rejection_contract.py`、`normalize-punctuation.js`）

- [ ] **Step 4: 跑 tests**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_revise_chapter.py tests/test_rejection_contract.py -v 2>&1 | tail -20
```

预期输出：全绿

- [ ] **Step 5: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发/.claude/worktrees/refactor-self-contained
git add -A
git commit -m "feat(plugin/skills): migrate webnovel-revise + revise_chapter/rejection_contract/normalize-punctuation"
```

---

## Task 15: 迁移 webnovel-deslop-check skill

**Files:**
- Move: `.claude/skills/webnovel-deslop-check/` → `.claude/plugins/webnovel-writer_chang/skills/webnovel-deslop-check/`
- Modify: SKILL.md 路径（text_humanizer 走 _shared/）

- [ ] **Step 1: 移动 skill 目录**

```bash
git mv .claude/skills/webnovel-deslop-check .claude/plugins/webnovel-writer_chang/skills/webnovel-deslop-check
```

- [ ] **Step 2: 改 SKILL.md 路径**

text_humanizer.py 现在在 `_shared/`，改 SKILL.md 里所有 `text_humanizer.py` 引用为 `${CLAUDE_PLUGIN_ROOT}/scripts/_shared/text_humanizer.py`；`check-ai-patterns.js` 引用为 `${CLAUDE_PLUGIN_ROOT}/scripts/check-ai-patterns.js`（注意 check-ai-patterns.js 还在 dev/.claude/scripts/，稍后迁移）

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat(plugin/skills): migrate webnovel-deslop-check"
```

---

## Task 16: 迁移 check-ai-patterns.js + 改 webnovel-deslop-check SKILL.md

**Files:**
- Move: `.claude/scripts/check-ai-patterns.js` → `.claude/plugins/webnovel-writer_chang/scripts/check-ai-patterns.js`
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-deslop-check/SKILL.md`

- [ ] **Step 1: 移动脚本**

```bash
git mv .claude/scripts/check-ai-patterns.js .claude/plugins/webnovel-writer_chang/scripts/check-ai-patterns.js
```

- [ ] **Step 2: 改 SKILL.md 里 check-ai-patterns.js 路径**

把所有 `node ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/check-ai-patterns.js` 替换为 `node ${CLAUDE_PLUGIN_ROOT}/scripts/check-ai-patterns.js`

- [ ] **Step 3: 跑 test（如果有）**

```bash
find .claude/plugins/webnovel-writer_chang/scripts/tests -name '*check*ai*' 2>/dev/null
```

预期输出：可能有 `test_check_ai_patterns.py` 之类的，跑一下确认

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(plugin/scripts): migrate check-ai-patterns.js"
```

---

## Task 17: 迁移 webnovel-resume + webnovel-chart-scan skills

**Files:**
- Move:
  - `.claude/skills/webnovel-resume/` → `.claude/plugins/webnovel-writer_chang/skills/webnovel-resume/`
  - `.claude/skills/webnovel-chart-scan/` → `.claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/`

- [ ] **Step 1: 移动 webnovel-resume**

```bash
git mv .claude/skills/webnovel-resume .claude/plugins/webnovel-writer_chang/skills/webnovel-resume
```

- [ ] **Step 2: 移动 webnovel-chart-scan**

```bash
git mv .claude/skills/webnovel-chart-scan .claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan
```

- [ ] **Step 3: 检查并修 SKILL.md 里残留的 CLAUDE_PROJECT_DIR**

```bash
grep -rn 'CLAUDE_PROJECT_DIR' .claude/plugins/webnovel-writer_chang/skills/webnovel-resume/ .claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/ 2>/dev/null
```

预期输出：可能 0 行（这两个 skill 没引用 CLAUDE_PROJECT_DIR 变量），如有就替换为 CLAUDE_PLUGIN_ROOT

- [ ] **Step 4: 修 webnovel-chart-scan SKILL.md 的硬编码绝对路径**

`webnovel-chart-scan/SKILL.md` 当前用 dev workspace 绝对路径（line 28、line 87）：

```bash
grep -n '/Users/chang/Desktop' .claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/SKILL.md
```

预期输出：列出含 `/Users/chang/Desktop/...webnovel-chart-scan/...` 的行

把硬编码绝对路径改为 `${CLAUDE_PLUGIN_ROOT}` 引用：

```bash
sed -i '' 's|python /Users/chang/Desktop/ai写小说工具开发/.claude/skills/webnovel-chart-scan/scripts/scan.py|python3 ${CLAUDE_PLUGIN_ROOT}/skills/webnovel-chart-scan/scripts/scan.py|g' .claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/SKILL.md
sed -i '' 's|cd /Users/chang/Desktop/ai写小说工具开发/.claude/skills/webnovel-chart-scan|cd ${CLAUDE_PLUGIN_ROOT}/skills/webnovel-chart-scan|g' .claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/SKILL.md
grep -n '/Users/chang/Desktop' .claude/plugins/webnovel-writer_chang/skills/webnovel-chart-scan/SKILL.md
```

预期输出：第二次 grep 输出 0 行

- [ ] **Step 5: 改 webnovel-deslop-check SKILL.md 的裸相对路径**

`webnovel-deslop-check/SKILL.md` 用了 `python3 .claude/scripts/text_humanizer.py` 和 `node .claude/scripts/check-ai-patterns.js` 这种**无变量前缀**的裸相对路径（line 65、81、95）。这些路径在 book 项目下找不到 `.claude/scripts/`，必坏。

```bash
grep -n '\.claude/scripts/' .claude/plugins/webnovel-writer_chang/skills/webnovel-deslop-check/SKILL.md
```

预期输出：列出 line 65/81/95 的 `python3 .claude/scripts/` 与 `node .claude/scripts/`

把裸路径改为 `${CLAUDE_PLUGIN_ROOT}`（text_humanizer.py 走 `_shared/`）：

```bash
sed -i '' 's|python3 \.claude/scripts/text_humanizer\.py|python3 ${CLAUDE_PLUGIN_ROOT}/scripts/_shared/text_humanizer.py|g' .claude/plugins/webnovel-writer_chang/skills/webnovel-deslop-check/SKILL.md
sed -i '' 's|node \.claude/scripts/check-ai-patterns\.js|node ${CLAUDE_PLUGIN_ROOT}/scripts/check-ai-patterns.js|g' .claude/plugins/webnovel-writer_chang/skills/webnovel-deslop-check/SKILL.md
grep -n '\.claude/scripts/' .claude/plugins/webnovel-writer_chang/skills/webnovel-deslop-check/SKILL.md
```

预期输出：第二次 grep 输出 0 行

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(plugin/skills): migrate webnovel-resume + webnovel-chart-scan + fix chart-scan absolute path + fix deslop-check bare relative paths"
```

---

## Task 18: 迁移 style_fingerprint.py + tracking_query.py 到 plugin/scripts/

**Files:**
- Move:
  - `.claude/scripts/style_fingerprint.py` → `.claude/plugins/webnovel-writer_chang/scripts/style_fingerprint.py`
  - `.claude/scripts/tracking_query.py` → `.claude/plugins/webnovel-writer_chang/scripts/tracking_query.py`
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md`（如有路径引用）

- [ ] **Step 1: 移动 style_fingerprint.py**

```bash
git mv .claude/scripts/style_fingerprint.py .claude/plugins/webnovel-writer_chang/scripts/style_fingerprint.py
```

- [ ] **Step 2: 移动 tracking_query.py**

```bash
git mv .claude/scripts/tracking_query.py .claude/plugins/webnovel-writer_chang/scripts/tracking_query.py
```

- [ ] **Step 3: 检查 webnovel-write SKILL.md 是否引用**

```bash
grep -n 'style_fingerprint\|tracking_query' .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
```

预期输出：可能 0 行（webnovel-write 通过 SCRIPTS_DIR 变量间接引用），如有就替换为 `${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py`

- [ ] **Step 4: 清理 test_style_fingerprint.py 的双副本断言**

`test_style_fingerprint.py:18` 定义 `STANDALONE_COPY = PLUGIN_COPY.parents[3] / "scripts" / "style_fingerprint.py"`，line 94-99 用 `test_two_copies_stay_identical` 校验 plugin 副本与 dev `.claude/scripts/` 副本的 SHA-256 一致。重构后 dev `.claude/scripts/` 不存在，测试会 `pytest.skip`——silently pass 的双副本守门失去意义。

```bash
grep -n 'STANDALONE_COPY\|two_copies' .claude/plugins/webnovel-writer_chang/scripts/tests/test_style_fingerprint.py | head -10
```

预期输出：列出 line 18 与 line 94-99 的相关代码

打开文件做以下修改：
1. 删除 `STANDALONE_COPY = ...` 常量定义（line 18）
2. 删除 `test_two_copies_stay_identical` 整个测试函数（line 92-100 附近）
3. 在文件顶部加注释：
```python
# Note: 双副本 SHA 校验已删除——重构后 style_fingerprint.py 只在 plugin/scripts/ 一份，
# dev workspace 不再保留独立副本。如未来需要副本一致性校验，参考 git history 中此测试的旧实现。
```

```bash
python3 -c "
from pathlib import Path
p = Path('.claude/plugins/webnovel-writer_chang/scripts/tests/test_style_fingerprint.py')
text = p.read_text(encoding='utf-8')
# 删除 STANDALONE_COPY 定义
import re
text = re.sub(r'^STANDALONE_COPY = .*?\$', '', text, count=1, flags=re.MULTILINE)
# 删除整个 test_two_copies_stay_identical 函数（粗略匹配：函数 def 到下一个 def 或 class 开头）
text = re.sub(r'@pytest\.mark\.\w+\n\s*\n\s*def test_two_copies_stay_identical.*?(?=\n\s*(?:@|def |class ))', '', text, flags=re.DOTALL)
# 加注释
if '双副本 SHA 校验已删除' not in text:
    text = '# Note: 双副本 SHA 校验已删除——重构后 style_fingerprint.py 只在 plugin/scripts/ 一份，\n# dev workspace 不再保留独立副本。\n' + text
p.write_text(text, encoding='utf-8')
print('cleaned')
"
grep -c 'STANDALONE_COPY\|test_two_copies' .claude/plugins/webnovel-writer_chang/scripts/tests/test_style_fingerprint.py
```

预期输出：`0`（双副本相关代码已清理）

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(plugin/scripts): migrate style_fingerprint.py + tracking_query.py + clean up test_style_fingerprint.py two-copy assertion"
```

---

## Task 19: 删除 dev/.claude/skills/ 和 dev/.claude/scripts/ 残留

**Files:**
- Remove: `.claude/skills/`（应已空）
- Remove: `.claude/scripts/`（应已空或仅剩 tests/）

- [ ] **Step 1: 检查 .claude/skills/ 是否已空**

```bash
ls -la .claude/skills/ 2>&1
```

预期输出：`No such file or directory` 或只有 `.` `..`

- [ ] **Step 2: 检查 .claude/scripts/ 剩余文件**

```bash
ls .claude/scripts/
```

预期输出：应只剩 `tests/`（如果 tests 还在）或完全空；如果还有遗漏的脚本文件，重复 Phase D 迁移它们

- [ ] **Step 3: 把 dev `.claude/scripts/tests/` 内文件逐个 git mv 到 plugin tests/（注意 conftest.py 合并）**

dev `tests/` 有 17 个文件，plugin `tests/` 已有 16 个文件。**两个目录都有 `conftest.py`**——直接 `git mv` 会冲突。先合并 conftest.py，再逐个移文件。

```bash
# 1. 看两边 conftest.py 大小
echo "dev conftest.py 行数："
wc -l .claude/scripts/tests/conftest.py
echo "plugin conftest.py 行数："
wc -l .claude/plugins/webnovel-writer_chang/scripts/tests/conftest.py

# 2. 把 plugin 的 conftest.py 备份（保留 plugin 版本作为基础）
cp .claude/plugins/webnovel-writer_chang/scripts/tests/conftest.py /tmp/plugin-conftest.bak.py

# 3. 移动 dev tests 到 plugin tests/，但先跳过 conftest.py
mkdir -p /tmp/dev-tests
cp -R .claude/scripts/tests/. /tmp/dev-tests/
rm -f /tmp/dev-tests/conftest.py  # 不动 plugin 的 conftest.py
ls /tmp/dev-tests/

# 4. 手动对比 conftest.py：取 plugin 为主，dev 的辅助 fixture（如有）合并进去
diff .claude/scripts/tests/conftest.py .claude/plugins/webnovel-writer_chang/scripts/tests/conftest.py
```

预期输出：diff 会显示两边差异（可能 dev 有 plugin 没有的 fixture，或反之）。合并策略：以 plugin 版本为基础，把 dev 的独有 fixture 加进去。

```bash
# 5. 把 dev 独有 test 文件逐个 git mv（先确认无重名）
for f in /tmp/dev-tests/*.py; do
    name=$(basename "$f")
    if [[ -f ".claude/plugins/webnovel-writer_chang/scripts/tests/$name" ]]; then
        echo "COLLISION: $name exists in both, manual merge needed"
    else
        git mv ".claude/scripts/tests/$name" ".claude/plugins/webnovel-writer_chang/scripts/tests/$name"
    fi
done
```

预期输出：除非有重名，否则所有 dev test_*.py 文件都被 git mv

```bash
# 6. 处理 conftest.py：合并后写回 plugin tests/conftest.py
python3 <<'PYEOF'
from pathlib import Path

plugin_cf = Path('.claude/plugins/webnovel-writer_chang/scripts/tests/conftest.py')
dev_cf = Path('.claude/scripts/tests/conftest.py')

plugin_text = plugin_cf.read_text(encoding='utf-8')
dev_text = dev_cf.read_text(encoding='utf-8')

# 简单合并策略：plugin 为主，把 dev 的独有 fixture 函数 append 进去
import re
def extract_fixtures(text):
    return set(re.findall(r'^def\s+(\w+)\s*\(', text, re.MULTILINE))

plugin_fixtures = extract_fixtures(plugin_text)
dev_fixtures = extract_fixtures(dev_text)

unique_to_dev = dev_fixtures - plugin_fixtures
if unique_to_dev:
    print(f"dev 独有 fixture: {unique_to_dev}")
    # 提取 dev 独有函数体
    extras = []
    for fname in unique_to_dev:
        m = re.search(rf'(^def\s+{re.escape(fname)}\s*\([^)]*\)[^\n]*\n(?:.+\n)*?)(?=^def\s+|^class\s+|^@|\Z)',
                      dev_text, re.MULTILINE)
        if m:
            extras.append(m.group(1))
    if extras:
        plugin_text = plugin_text.rstrip() + '\n\n# === merged from dev/.claude/scripts/tests/conftest.py ===\n\n' + '\n'.join(extras)
        plugin_cf.write_text(plugin_text, encoding='utf-8')
        print(f"merged {len(extras)} fixtures into plugin conftest.py")
else:
    print("no unique dev fixtures to merge")
PYEOF
```

预期输出：要么 `no unique dev fixtures to merge`，要么 `merged N fixtures`

```bash
# 7. 删除 dev tests/ 和 scripts/
rm .claude/scripts/tests/conftest.py
rmdir .claude/scripts/tests/
rmdir .claude/scripts/
```

- [ ] **Step 4: 删除 .claude/skills/ 如果是空**

```bash
rmdir .claude/skills/ 2>/dev/null || echo "already empty or gone"
```

- [ ] **Step 5: 验证最终结构**

```bash
echo "dev .claude/ 剩余："
ls -la .claude/
echo
echo "plugin 全部 skill："
ls .claude/plugins/webnovel-writer_chang/skills/
echo
echo "plugin 全部 script："
ls .claude/plugins/webnovel-writer_chang/scripts/
echo
echo "plugin tests/ 文件数："
ls .claude/plugins/webnovel-writer_chang/scripts/tests/ | wc -l
```

预期输出：
- dev `.claude/` 剩：`plugins/` `references/` `sources/` `worktrees/` `settings.json` `.webnovel-current-project`
- plugin skills 含 14 个目录（init/plan/write/fast-write/revise/deslop-check/resume/chart-scan/doctor/learn/review/query/dashboard/style-profile）
- plugin scripts 含 webnovel.py + 迁移的脚本 + _shared/
- plugin tests/ 应为合并后的 ~30 个文件（plugin 16 + dev 17 - 3 个 conftest 重叠 = ~30）

- [ ] **Step 6: 跑 plugin tests 验证合并后未破坏**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/ -v 2>&1 | tail -30
```

预期输出：全绿，或有少量失败可逐个修复（合并 conftest 不应破坏）

- [ ] **Step 7: Commit**

```bash
cd /Users/chang/Desktop/ai写小说工具开发/.claude/worktrees/refactor-self-contained
git add -A
git commit -m "chore(dev): remove empty .claude/skills/ and .claude/scripts/ after migration + merge tests/conftest.py"
```

---

# Phase E: webnovel-init 个人语料改路径（顺手实现新功能）

## Task 20: 创建默认模板文件 + 改 webnovel-init SKILL.md

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/templates/个人语料.md`（默认模板）
- Create: `.claude/plugins/webnovel-writer_chang/templates/写作宪法.md`（默认模板）
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-init/SKILL.md`

- [ ] **Step 1: 创建 templates/个人语料.md 默认模板**

```bash
cat > .claude/plugins/webnovel-writer_chang/templates/个人语料.md <<'MD_EOF'
# 个人语料（写给 AI 的写作风格指南）

> 本文件由 `webnovel-init` 自动从 plugin templates/ copy 到书项目的 `.webnovel/writer-profile/`。
> 用户应直接编辑书项目里的副本，**不要**改 plugin 内的源模板（升级会被覆盖）。

## 1. 主角定位

- 性格：{{待填}}
- 说话方式：{{待填}}
- 内心独白风格：{{待填}}

## 2. 写作偏好

- 句长偏好：{{短句/中句/长句}}
- 对话比例：{{待填}}
- 内心戏比例：{{待填}}
- 视角：{{第一人称/第三人称/全知}}
- 时态：{{过去/现在}}

## 3. 禁忌

- 不要写：{{待填}}
- 不要出现：{{敏感词列表}}

## 4. 标点与格式

- 引号风格：{{直引号"" / 弯引号""}}
- 段落长度：{{最长多少字}}
- 章节切分偏好：{{按场景/按时间/按 POV}}

---

填好后保存，后续 `/webnovel-write` 会自动加载本文件作为上下文。
MD_EOF
ls .claude/plugins/webnovel-writer_chang/templates/个人语料.md
```

预期输出：文件存在

- [ ] **Step 2: 创建 templates/写作宪法.md 默认模板**

```bash
cat > .claude/plugins/webnovel-writer_chang/templates/写作宪法.md <<'MD_EOF'
# 写作宪法（贯穿全书的不变规则）

> 与 个人语料.md 不同，本文件是**硬约束**，写章节时 AI 必须遵守。
> 同样由 webnovel-init 自动 copy，用户直接编辑书项目里的副本。

## 1. 设定硬约束

- 力量体系上限：{{待填}}
- 主角不可逾越的红线：{{待填}}

## 2. 叙事硬约束

- 不允许穿越/重生类金手指（除非作品本身设定如此）
- 不允许时间倒流（除非作品本身设定如此）
- 不允许 NPC 凭空知道主角秘密（除非已合理解释）

## 3. 风格硬约束

- 章节末不写"欲知后事如何"式钩子（除非作品本身风格如此）
- 不出现现代网络用语（除非作品本身风格如此）
- 不出现"叮，系统提示"等系统文标志（除非作品本身是系统流）

## 4. 自定义硬约束

- {{待填}}

---

填好后保存。`/webnovel-review` 会把本文件作为合规性检查的硬基线。
MD_EOF
ls .claude/plugins/webnovel-writer_chang/templates/写作宪法.md
```

预期输出：文件存在

- [ ] **Step 3: 改 webnovel-init SKILL.md 文档**

打开 `.claude/plugins/webnovel-writer_chang/skills/webnovel-init/SKILL.md`，在合适位置加一段（搜索 "Step 3.5" 之类 init 流程描述附近）：

```markdown
# Step 3.6 - 复制个人语料默认模板到书项目
mkdir -p "${PROJECT_ROOT}/.webnovel/writer-profile"
cp "${CLAUDE_PLUGIN_ROOT}/templates/个人语料.md" "${PROJECT_ROOT}/.webnovel/writer-profile/个人语料.md"
cp "${CLAUDE_PLUGIN_ROOT}/templates/写作宪法.md" "${PROJECT_ROOT}/.webnovel/writer-profile/写作宪法.md"
echo "✅ 个人语料模板已写入 ${PROJECT_ROOT}/.webnovel/writer-profile/，请编辑后保存。"
```

如 SKILL.md 里有 Step 3.6 实际编号则保留编号；如无则作为新段落加入。

- [ ] **Step 4: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/templates/ .claude/plugins/webnovel-writer_chang/skills/webnovel-init/SKILL.md
git commit -m "feat(plugin/webnovel-init): add 个人语料 + 写作宪法 default templates + copy-to-book-project step in SKILL.md"
```

---

## Task 21: 让 init_project.py 真正执行 copy

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/scripts/init_project.py`（或 `data_modules/init_logic.py` 等，按实际位置）

- [ ] **Step 1: 定位 init 写文件的函数**

```bash
grep -rn 'def.*init\|设定集/世界观\|设定集/主角' .claude/plugins/webnovel-writer_chang/scripts/init_project.py .claude/plugins/webnovel-writer_chang/scripts/data_modules/ 2>/dev/null | grep -i 'write\|create\|setup' | head -10
```

预期输出：列出 init 写文件的函数位置（通常在 init_project.py 后半段）

- [ ] **Step 2: 在 init 流程末尾加 writer-profile 块**

找到 init 流程最后写入 state.json 之前的代码块，在其后插入：

```python
# === 个人语料 + 写作宪法模板写入（Task 21）===
import shutil
from pathlib import Path as _Path

_template_dir = _Path(__file__).resolve().parent.parent / "templates"
_writer_profile = project_root / ".webnovel" / "writer-profile"
_writer_profile.mkdir(parents=True, exist_ok=True)
for template_name in ("个人语料.md", "写作宪法.md"):
    src = _template_dir / template_name
    dst = _writer_profile / template_name
    if not dst.exists() and src.exists():
        shutil.copy(src, dst)
        print(f"✅ 已写入 {dst}")
```

（如 init_project.py 实际不在 scripts/ 而在 scripts/data_modules/，路径相应调整）

- [ ] **Step 3: 写 pytest 验证 init 落点**

```bash
cat > .claude/plugins/webnovel-writer_chang/scripts/tests/test_writer_profile_init.py <<'PY_EOF'
"""测试 init 把 templates/个人语料.md 与 写作宪法.md copy 到 <book>/.webnovel/writer-profile/。"""
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


def test_init_creates_writer_profile(tmp_path: Path) -> None:
    """在临时书项目目录跑 init，验证 .webnovel/writer-profile/{个人语料,写作宪法}.md 被创建。"""
    repo_root = Path(__file__).resolve().parents[2]  # scripts/tests/ → scripts/ → plugin/
    webnovel_py = repo_root / "scripts" / "webnovel.py"
    if not webnovel_py.exists():
        pytest.skip(f"webnovel.py 不存在: {webnovel_py}")

    book = tmp_path / "book"
    book.mkdir()
    # 用最少的命令行参数跑 init（按实际参数调整）
    result = subprocess.run(
        ["python3", str(webnovel_py), "--project-root", str(book), "init", "--minimal"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    writer_profile = book / ".webnovel" / "writer-profile"
    assert writer_profile.exists(), f"writer-profile 未创建: {writer_profile}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert (writer_profile / "个人语料.md").exists(), "个人语料.md 未 copy"
    assert (writer_profile / "写作宪法.md").exists(), "写作宪法.md 未 copy"
PY_EOF
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_writer_profile_init.py -v 2>&1 | tail -20
```

预期输出：测试通过（或根据实际 init 参数调整后通过）

- [ ] **Step 4: 改 webnovel-write SKILL.md:158 读路径**

打开 `.claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md`，找到含 `个人语料.md` 的 line（约 158）：

```bash
grep -n '个人语料' .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
```

把 `设定集/个人语料.md` 之类路径改为 `${PROJECT_ROOT}/.webnovel/writer-profile/个人语料.md`。

```bash
sed -i '' 's|${PROJECT_ROOT}/设定集/个人语料\.md|${PROJECT_ROOT}/.webnovel/writer-profile/个人语料.md|g' .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
sed -i '' 's|${PROJECT_ROOT}/.*个人语料\.md|${PROJECT_ROOT}/.webnovel/writer-profile/个人语料.md|g' .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
grep -n '个人语料' .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
```

预期输出：grep 仅显示新路径

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(init): copy 个人语料 + 写作宪法 templates to .webnovel/writer-profile/ + update webnovel-write read path"
```

---

# Phase F: Dev settings.json 瘦身

## Task 22: 删 dev settings.json 的 hooks 块

**Files:**
- Modify: `ai写小说工具开发/.claude/worktrees/refactor-self-contained/.claude/settings.json`

**为什么**：dev settings.json 的 hooks 块是用 `${CLAUDE_PROJECT_DIR}/.claude/plugins/webnovel-writer/hooks/...` 拼出来的——这是 dev 调试遗留（plugin 路径已重命名为 `_chang`，marketplace 自带 hooks.json 用 `${CLAUDE_PLUGIN_ROOT}` 是正确的）。dev hooks 本身已经用 `python3`（不像 plugin 的 hooks.json 用 `python`），删掉是对的。

- [ ] **Step 1: 读当前 settings.json**

```bash
cat .claude/settings.json
```

- [ ] **Step 2: 用 Python 删除 hooks 块**

```bash
python3 <<'PYEOF'
import json
from pathlib import Path
p = Path('.claude/settings.json')
data = json.loads(p.read_text(encoding='utf-8'))
data.pop('hooks', None)
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('after delete hooks, top keys:', list(data.keys()))
PYEOF
```

预期输出：`top keys: ['enabledPlugins', 'permissions', 'model']`（无 hooks）

- [ ] **Step 3: 验证 JSON**

```bash
python3 -c "import json; json.load(open('.claude/settings.json'))" && echo "JSON OK"
```

预期输出：`JSON OK`

- [ ] **Step 4: Commit**

```bash
git add .claude/settings.json
git commit -m "refactor(dev/settings): remove hooks override (marketplace provides hooks.json)"
```

---

## Task 23: 重写 dev settings.json 的 permissions.allow

**Files:**
- Modify: `.claude/settings.json`（permissions.allow）

**为什么不是只删**：Phase A 把 plugin 目录重命名为 `_chang`，Phase D 把所有 `.claude/scripts/` 与 `.claude/plugins/webnovel-writer/` 下的脚本迁到 plugin。旧 permissions 里 9 条规则指向这些**已不存在的路径**，留着只会造成 noise + 真用 plugin 脚本时无 allow 命中弹提示窗。所以要**整段重写**。

- [ ] **Step 1: 用 Python 完全重写 permissions.allow**

```bash
python3 <<'PYEOF'
import json
from pathlib import Path

p = Path('.claude/settings.json')
data = json.loads(p.read_text(encoding='utf-8'))

NEW_ALLOW = [
    # plugin 主脚本
    'Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/webnovel.py*)',
    # 迁移到 plugin scripts/ 的脚本
    'Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/changes_gate.py*)',
    'Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/context_slice.py*)',
    'Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/snapshot_manager.py*)',
    'Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/revise_chapter.py*)',
    'Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/rejection_contract.py*)',
    'Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/style_fingerprint.py*)',
    'Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/tracking_query.py*)',
    'Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract_chapter_context.py*)',
    'Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/_shared/text_humanizer.py*)',
    # node 脚本
    'Bash(node ${CLAUDE_PLUGIN_ROOT}/scripts/check-ai-patterns.js*)',
    'Bash(node ${CLAUDE_PLUGIN_ROOT}/scripts/normalize-punctuation.js*)',
    # plugin style-profile skill node 调用
    'Bash(node ${CLAUDE_PLUGIN_ROOT}/skills/webnovel-style-profile/*)',
    # dev workspace 工作流（git 提交、读 settings 等）
    'Bash(git status)',
    'Bash(git diff*)',
    'Bash(git log*)',
    'Bash(git add*)',
    'Bash(git commit*)',
    # dev 调试：跑 plugin 测试
    'Bash(python3 -m pytest*)',
    # dev 调试：rsync 同步 dev → marketplace
    'Bash(rsync*)',
    'Bash(mkdir*)',
    'Bash(ln -sfn*)',
]

data['permissions']['allow'] = NEW_ALLOW
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'wrote {len(NEW_ALLOW)} allow rules')
PYEOF
```

预期输出：`wrote 22 allow rules`

- [ ] **Step 2: 验证 JSON**

```bash
python3 -c "import json; json.load(open('.claude/settings.json'))" && echo "JSON OK"
```

预期输出：`JSON OK`

- [ ] **Step 3: 验证无残留过期路径**

```bash
grep -E '\.claude/scripts/|\.claude/plugins/webnovel-writer[^_]' .claude/settings.json
```

预期输出：0 行（不再含指向 `.claude/scripts/` 或旧名 plugin 的 allow 规则）

- [ ] **Step 4: Commit**

```bash
git add .claude/settings.json
git commit -m "refactor(dev/settings): rewrite permissions.allow for new plugin path layout"
```

---

## Task 24: 更新 dev settings.json 的 enabledPlugins 名称

**Files:**
- Modify: `.claude/settings.json`

- [ ] **Step 1: 读当前 enabledPlugins**

```bash
python3 -c "import json; print(json.load(open('.claude/settings.json'))['enabledPlugins'])"
```

预期输出：`{'webnovel-writer': True}`（裸名）

- [ ] **Step 2: 改为完整 marketplace 名**

```bash
python3 <<'PYEOF'
import json
from pathlib import Path
p = Path('.claude/settings.json')
data = json.loads(p.read_text(encoding='utf-8'))
ep = data.get('enabledPlugins', {})
if 'webnovel-writer' in ep:
    val = ep.pop('webnovel-writer')
    ep['webnovel-writer_chang@webnovel-chang-marketplace'] = val
data['enabledPlugins'] = ep
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('enabledPlugins:', ep)
PYEOF
```

预期输出：`{'webnovel-writer_chang@webnovel-chang-marketplace': True}`

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.json
git commit -m "refactor(dev/settings): update enabledPlugins to webnovel-writer_chang@webnovel-chang-marketplace"
```

---

# Phase G: 自包含测试

## Task 25: 写 test_self_contained.py（先写失败测试）

**Files:**
- Create: `.claude/plugins/webnovel-writer_chang/scripts/tests/test_self_contained.py`

- [ ] **Step 1: 看现有 tests 目录布局**

```bash
ls .claude/plugins/webnovel-writer_chang/scripts/tests/ | head -20
```

预期输出：现有 pytest 文件列表

- [ ] **Step 2: 写测试文件**

```python
# .claude/plugins/webnovel-writer_chang/scripts/tests/test_self_contained.py
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
def test_no_claude_project_dir_in_skills(md_file: Path) -> None:
    """plugin 内不应使用 CLAUDE_PROJECT_DIR（仅 dev workspace 的 settings.json 用）。"""
    text = md_file.read_text(encoding="utf-8")
    assert "CLAUDE_PROJECT_DIR" not in text, (
        f"{md_file.relative_to(PLUGIN_ROOT)} 含 CLAUDE_PROJECT_DIR 引用，违反 self-contained 原则"
    )


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
    """plugin.json 的 name 必须**精确等于** 'webnovel-writer_chang'——endswith 太宽松（'x_chang_y' 也通过）。"""
    import json
    data = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"] == "webnovel-writer_chang", (
        f"plugin name 必须是 'webnovel-writer_chang'，实际是 {data['name']!r}"
    )


def test_plugin_version_is_6_3_0() -> None:
    """plugin.json version 必须是 6.3.0——避免 marketplace.json 6.3.0 与 plugin.json 6.2.1 drift。"""
    import json
    data = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["version"] == "6.3.0", f"plugin version 必须是 6.3.0，实际是 {data['version']!r}"


def test_no_scripts_in_dev_dotclaude() -> None:
    """dev .claude/scripts/ 与 .claude/skills/ 在重构后应已清空。"""
    for path in [".claude/scripts", ".claude/skills"]:
        full = PLUGIN_ROOT.parent.parent / path  # plugin/.. = .claude/, 再上 = dev root
        if full.exists():
            contents = list(full.iterdir())
            assert not contents, f"{path} 应已清空但还有: {contents}"
```

- [ ] **Step 3: 跑测试（应大部分失败，因为 Phase C/D/F 还没全做完；这是预期的 TDD 失败）**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_self_contained.py -v 2>&1 | tail -40
```

预期输出：很多 `FAIL`（python/CLAUDE_PROJECT_DIR/skill path 三类都会报）；但以下三项**应已通过**（Task 3 已改）：
- `test_plugin_name_is_exact` ✓
- `test_plugin_version_is_6_3_0` ✓
- `test_hooks_use_python3` ✓（Task 7 已修）

如有任何一项红，回溯 Task 3 看是否漏了字段。

- [ ] **Step 4: Commit 测试本身**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/tests/test_self_contained.py
git commit -m "test(plugin): add self-contained invariant tests (initially failing per TDD)"
```

---

## Task 26: 跑全部 plugin 测试，确认 self-contained 测试全绿

**Files:**
- Read: `.claude/plugins/webnovel-writer_chang/scripts/tests/`

- [ ] **Step 1: 跑所有 tests**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/ -v 2>&1 | tail -50
```

预期输出：全绿，包括 `test_self_contained.py`（因为 Phase C/D/F 已修完路径）

- [ ] **Step 2: 如有失败，按失败信息回溯**

如有 `test_no_python2_alias` 失败，回到 Task 7/8/10 看遗漏的 `python -X utf8`
如有 `test_no_claude_project_dir_in_skills` 失败，回到 Task 9 找反模式
如有 `test_no_dev_path_fallback` 失败，回到 Task 9

- [ ] **Step 3: Commit（如有修）**

```bash
git add -A
git commit -m "fix(plugin): address self-contained test failures (path cleanup)"
```

---

# Phase H: 文档

## Task 27: 新增 docs/PROJECT_MAP.md

**Files:**
- Create: `docs/PROJECT_MAP.md`

- [ ] **Step 1: 写 PROJECT_MAP.md**

```markdown
# Project Map — 参考 vs 开发

> 最近更新：2026-08-15（plugin self-contained 重构后）

这个 fork 是基于 upstream `lingfengQAQ/webnovel-writer` 的个人工作区。**我们只开发 plugin 主体本身**，其它都是参考。

## 三层结构

### 层 1：dev workspace（你唯一的项目）
`/Users/chang/Desktop/ai写小说工具开发/`

| 路径 | 性质 | 说明 |
|---|---|---|
| `.claude/plugins/webnovel-writer_chang/` | **开发** | plugin 源码（self-contained） |
| `.claude/settings.json` | **开发** | dev 配置（瘦身后只剩 enabledPlugins + 必要权限） |
| `.claude/.webnovel-current-project` | **开发** | dev 指针，仅 dev workspace 内部用 |
| `.claude/references/` | 参考 | 文档参考 |
| `.claude/sources/webnovel-writer-upstream/` | 参考 | upstream fork 源快照 |
| `.claude/worktrees/` | — | git worktree 目录 |
| `docs/` | **开发** | 实施计划、复盘报告 |
| `README.md` | **开发** | fork 开发指南 |

### 层 2：marketplace（plugin 发布仓库）
`~/.claude/plugins/marketplaces/webnovel-chang-marketplace/`

| 路径 | 性质 | 说明 |
|---|---|---|
| `.claude-plugin/marketplace.json` | **开发** | marketplace manifest |
| `webnovel-writer_chang/` | **开发** | plugin 副本（与 dev workspace 同步） |

### 层 3：cache（Claude Code 实际加载位置）
`~/.claude/plugins/cache/webnovel-chang-marketplace/webnovel-writer_chang/`

dev 模式下 symlink 到 dev workspace 的 `plugins/webnovel-writer_chang/`，修改立即生效。

## 修改规则

- **改 plugin 代码**：在 `.claude/plugins/webnovel-writer_chang/` 里改，cache 通过 symlink 自动 reload
- **改 plugin metadata**：plugin.json / hooks.json 在 plugin 目录里改
- **改 marketplace manifest**：直接改 `~/.claude/plugins/marketplaces/webnovel-chang-marketplace/.claude-plugin/marketplace.json`
- **同步 dev → marketplace**：跑 `scripts/sync_dev_to_marketplace.sh`（后续可加；当前手动 cp）

## 参考区（不要改）

- `.claude/sources/webnovel-writer-upstream/`：upstream fork 源快照，要对比时看这里
- `.claude/references/`：历史参考文档
```

- [ ] **Step 2: Commit**

```bash
git add docs/PROJECT_MAP.md
git commit -m "docs: add PROJECT_MAP.md (reference vs development layers)"
```

---

## Task 28: 重写 README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 读当前 README 看长度**

```bash
wc -l README.md
```

- [ ] **Step 2: 重写 README**

```markdown
# ai写小说工具开发

> 个人 fork 的 webnovel-writer 工具开发 workspace

## 这是什么

基于 [webnovel-writer](https://github.com/lingfengQAQ/webnovel-writer) 的个人 fork，加上 `_chang` 后缀做身份区分。**整个 fork 的目标：让 Claude Code 在任何书项目目录下直接加载这个 plugin，不要求书项目有 `.claude/` 配置。**

## 目录地图

详见 [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md)。

简版：
- `.claude/plugins/webnovel-writer_chang/` — 你开发的 plugin（self-contained）
- `docs/PROJECT_MAP.md` — 参考 vs 开发分层
- `docs/superpowers/specs/` — 设计文档
- `docs/superpowers/plans/` — 实施计划

## 加载机制

1. Claude Code 启动时读 `~/.claude/settings.json` 的 `enabledPlugins`
2. 找到 `webnovel-writer_chang@webnovel-chang-marketplace: true`
3. 加载 `~/.claude/plugins/marketplaces/webnovel-chang-marketplace/` 里的 marketplace.json
4. 安装 plugin 到 `~/.claude/plugins/cache/webnovel-chang-marketplace/webnovel-writer_chang/`
5. 注入 `CLAUDE_PLUGIN_ROOT` 环境变量
6. plugin 自带的 hooks / skills / agents 全部可用

dev 模式下 cache 是 dev workspace 的 symlink，**修改立即生效**无需重启（但 hooks.json / plugin.json 改动建议重启一次）。

## 修改 plugin 代码

直接在 `.claude/plugins/webnovel-writer_chang/` 里改。完成后跑：
```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/ -v
```

## 同步到 marketplace（dev → marketplace）

```bash
rsync -a --delete .claude/plugins/webnovel-writer_chang/ \
    ~/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/
```

（首次手动 cp 即可；后续可写 `scripts/sync_dev_to_marketplace.sh`）

## 写新章节

在任何书项目目录下：
```bash
cd /path/to/your-novel
claude
# 在 claude 里：
# /webnovel-init   # 首次初始化
# /webnovel-write  # 写章节
# /webnovel-doctor # 诊断
```

**书项目侧不需要任何 `.claude/` 配置。**

## 版本

当前 plugin version: 6.3.0（自我包含重构首发版）
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): rewrite as fork development guide (no more symlink instructions)"
```

---

## Task 29: 删 KNOWN_ISSUES.md 的过时条目

**Files:**
- Modify: `docs/KNOWN_ISSUES.md`

- [ ] **Step 1: 看 KNOWN_ISSUES.md 现有内容**

```bash
cat docs/KNOWN_ISSUES.md | head -100
```

- [ ] **Step 2: 删除 M-H8 / MED-5 / MED-52 条目**

打开 `docs/KNOWN_ISSUES.md`，找到 M-H8、MED-5、MED-52（如果存在），整段删除。如果条目编号不准确，按实际内容（`CLAUDE_PLUGIN_ROOT 在项目级 symlink 安装时未设`、`CLAUDE_PROJECT_DIR 拼接` 等关键词）搜索删除。

- [ ] **Step 3: Commit**

```bash
git add docs/KNOWN_ISSUES.md
git commit -m "docs: remove obsolete CLAUDE_PROJECT_DIR-related known issues (rooted in refactor)"
```

---

# Phase I: 端到端验证

## Task 30: 在 dev workspace 跑 webnovel-doctor 验证 dev 加载

**Files:** (无文件改动，仅验证)

- [ ] **Step 1: cd 到 dev workspace**

```bash
cd /Users/chang/Desktop/ai写小说工具开发/.claude/worktrees/refactor-self-contained
```

- [ ] **Step 2: 启动 claude（新会话）**

注：手动操作，关闭当前 claude、启动新会话，确保 hooks / plugin 重新加载

- [ ] **Step 3: 在 claude 里跑 /webnovel-doctor**

命令：`/webnovel-doctor`

预期输出：诊断报告，`phase: init_scaffolded` 或更新后的 phase，无 blocker

- [ ] **Step 4: 跑 /webnovel-query 测试 skill 调用**

命令：`/webnovel-query protagonist`

预期输出：能返回主角「林川」的状态信息（前提是项目有 state.json）

- [ ] **Step 5: 记录结果**

如失败：检查 marketplace cache 是否 symlink 到 dev、plugin.json name 是否正确、hooks.json 命令是否 python3
如成功：进 Task 31

---

## Task 31: 根治测试——在根源牌序 下跑 webnovel-doctor

**Files:** (无文件改动，仅验证)

- [ ] **Step 1: cd 到根源牌序**

```bash
cd /Users/chang/Desktop/根源牌序
```

- [ ] **Step 2: 确认 book 项目下无 .claude/**

```bash
ls -la .claude/ 2>&1 || echo "OK: 无 .claude/"
```

预期输出：`OK: 无 .claude/`

- [ ] **Step 3: 启动 claude（新会话）**

注：手动操作

- [ ] **Step 4: SessionStart hook 应自动跑**

观察 session start 输出，应能看到 `project: 《根源牌序》, root: /Users/chang/Desktop/根源牌序, phase: ...`

- [ ] **Step 5: 跑 /webnovel-doctor**

命令：`/webnovel-doctor`

预期输出：完整诊断报告，**即使 book 项目零 `.claude/` 配置也能跑**

- [ ] **Step 6: 跑 /webnovel-query**

命令：`/webnovel-query protagonist`

预期输出：能读到主角状态

- [ ] **Step 7: 跑 /webnovel-init 重做初始化（验证个人语料新路径）**

命令：`/webnovel-init`

预期输出：init 流程把 templates/ 内容 copy 到 `<book>/.webnovel/writer-profile/`

- [ ] **Step 8: 验证 writer-profile/ 创建**

```bash
ls /Users/chang/Desktop/根源牌序/.webnovel/writer-profile/
```

预期输出：看到 `个人语料.md` 等默认文件

- [ ] **Step 9: 记录结果**

**这是关键验收点**：如通过，说明「书项目零 `.claude/` 配置也能完整用 webnovel-writer」的根治目标达成。

---

## Task 32: 跑一次完整的 /webnovel-write 流程验证数据链

**Files:** (无文件改动，仅验证)

- [ ] **Step 1: 仍在根源牌序 目录**

```bash
cd /Users/chang/Desktop/根源牌序
```

- [ ] **Step 2: 跑 /webnovel-write**

命令：`/webnovel-write 1`（写第 1 章；如已写过则换其它章节号）

预期输出：完整写章节流程跑通（context → draft → review → polish → data），期间调用的所有 plugin 脚本（webnovel.py、tracking_query.py、style_fingerprint.py 等）都从 `${CLAUDE_PLUGIN_ROOT}` 解析成功

- [ ] **Step 3: 检查 chapter commit artifacts**

```bash
ls .webnovel/commit/ch0001/ 2>/dev/null
ls 正文/第0001章*/ 2>/dev/null
```

预期输出：commit 目录存在、章节文件存在

- [ ] **Step 4: 跑 /webnovel-doctor 再确认**

预期输出：所有指标 OK，无新增 blocker

- [ ] **Step 5: 记录结果**

如成功：重构完成，进 Task 33（merge 回 main）
如失败：按失败信息回溯（检查 plugin cache 是否过期、hooks.json python3 是否正确、init 时是否建了 writer-profile/）

---

# Phase J: 收尾

## Task 33: 把 worktree 改动 merge 回 main 分支

**Files:** (无文件改动，仅 git 操作)

**Merge 策略：推荐 squash**。理由：30+ 个原子 commit 跨 10 个 Phase，单 PR/单 commit 对回溯更友好；squash 后 commit message 引用 spec doc，未来 cherry-pick / revert 都清楚。如偏好保留每个原子 commit 的历史，把 `git merge --squash` 换成 `git merge --no-ff` 即可。

- [ ] **Step 1: 切回 main**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git checkout main
```

- [ ] **Step 2: 看 worktree 分支的 commits**

```bash
git log --oneline refactor/self-contained ^main | head -40
```

预期输出：列出 refactor 分支独有的 commits（约 30-35 个）

- [ ] **Step 3: Squash merge**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git merge --squash refactor/self-contained
git status
```

预期输出：`git status` 显示 staged 但未 committed 的所有 refactor 改动

```bash
git commit -m "refactor: webnovel-writer plugin self-contained (spec 2026-08-15)

把 webnovel-writer fork 重构为 self-contained：plugin 重命名为 _chang 后缀，
建立独立 marketplace，所有 SKILL.md/agent md 路径变量统一到 CLAUDE_PLUGIN_ROOT，
5 个项目级 skill + 10 个脚本迁入 plugin，dev workspace 零 .claude/scripts 依赖。
书项目（根源牌序 等）无需任何 .claude/ 配置即可加载。

详见：
- docs/superpowers/specs/2026-08-15-webnovel-plugin-self-contained-refactor-design.md
- docs/superpowers/plans/2026-08-15-webnovel-plugin-self-contained-refactor-impl.md"
```

- [ ] **Step 4: 跑最终全测试**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/ -v 2>&1 | tail -10
```

预期输出：全绿

- [ ] **Step 5: 清理 worktree**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git worktree remove .claude/worktrees/refactor-self-contained
git branch -d refactor/self-contained
```

- [ ] **Step 6: 同步 marketplace（cache symlink 自动跟上）**

注：dev workspace 无 remote，无需 push。cache 是 symlink（Task 4b）→ dev workspace，无需同步。但 marketplace 仓库是独立目录，需要 cp：

```bash
bash .claude/plugins/webnovel-writer_chang/scripts/dev-only/sync_dev_to_marketplace.sh
```

---

## 自检清单（plan 完成时检查）

- [ ] 所有改动都对应 spec 的 §4 改动清单？
- [ ] 没有 TBD / TODO / "implement later" 占位符？
- [ ] 每个 task 的代码块完整可直接用？
- [ ] 每个 task 的命令有预期输出？
- [ ] 任务粒度是 2-5 分钟一步？
- [ ] 共享脚本归位策略（`_shared/`）已明确？
- [ ] user-level settings.json 改动步骤清楚？
- [ ] 根治测试（Task 31）覆盖了"书项目零 `.claude/`"验收点？
