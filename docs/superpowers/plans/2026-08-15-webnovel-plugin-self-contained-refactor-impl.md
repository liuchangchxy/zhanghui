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
| `ai写小说工具开发/.claude/plugins/webnovel-writer_chang/skills/` | 10 个 SKILL.md |
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

## Task 3: 更新 plugin.json 的 name 字段

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/.claude-plugin/plugin.json:3`

- [ ] **Step 1: 读取当前 name 字段**

```bash
cat .claude/plugins/webnovel-writer_chang/.claude-plugin/plugin.json | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])"
```

预期输出：`webnovel-writer`

- [ ] **Step 2: 用 Python 改写 name 字段**

```bash
python3 -c "
import json
from pathlib import Path
p = Path('.claude/plugins/webnovel-writer_chang/.claude-plugin/plugin.json')
data = json.loads(p.read_text(encoding='utf-8'))
data['name'] = 'webnovel-writer_chang'
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('updated:', data['name'])
"
```

预期输出：`updated: webnovel-writer_chang`

- [ ] **Step 3: 验证 JSON 仍合法**

```bash
python3 -c "import json; json.load(open('.claude/plugins/webnovel-writer_chang/.claude-plugin/plugin.json'))" && echo "JSON OK"
```

预期输出：`JSON OK`

- [ ] **Step 4: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/.claude-plugin/plugin.json
git commit -m "refactor(plugin): rename plugin.json name field to webnovel-writer_chang"
```

---

## Task 4: 创建独立 marketplace 目录与 marketplace.json

**Files:**
- Create: `~/.claude/plugins/marketplaces/webnovel-chang-marketplace/.claude-plugin/marketplace.json`

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

- [ ] **Step 5: Commit（marketplace 仓库是独立的，不在 dev workspace 的 git 里；跳过 git step）**

注：marketplace 不在 dev workspace 的 git 仓库内，是独立的 Claude Code 管理目录，无需 commit。

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

预期输出：能看到当前结构（已知有 `enabledPlugins.webnovel-writer@webnovel-writer-marketplace: true`）

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

注：手动操作，关闭当前 claude 会话、重新启动 `claude` 命令

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

预期输出：10 个 SKILL.md

- [ ] **Step 2: 替换所有 SKILL.md 里的 python → python3**

```bash
find .claude/plugins/webnovel-writer_chang/skills -name SKILL.md -exec sed -i '' 's/python -X utf8/python3 -X utf8/g' {} +
```

- [ ] **Step 3: 验证替换**

```bash
echo "裸 python -X utf8 残留："
grep -rn '"python -X utf8' .claude/plugins/webnovel-writer_chang/skills/ | wc -l
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

## Task 9: 修 plugin 自带 SKILL.md：反模式 fallback → 严格 CLAUDE_PLUGIN_ROOT:?

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md:136,149,330,352,355` 等

- [ ] **Step 1: 找出所有反模式 fallback**

```bash
grep -rn 'CLAUDE_PLUGIN_ROOT:-.*CLAUDE_PROJECT_DIR' .claude/plugins/webnovel-writer_chang/skills/
```

预期输出：列出所有 `${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}/.claude/...}` 反模式

- [ ] **Step 2: 修 webnovel-write SKILL.md 的 SCRIPTS_DIR fallback（line 136）**

打开 `.claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md`，找到：
```bash
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-$PWD}}/.claude/plugins/webnovel-writer/scripts"
```
替换为：
```bash
export SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT}/scripts"
```

- [ ] **Step 3: 修 webnovel-write SKILL.md 里其它 `python3 ${CLAUDE_PROJECT_DIR:-$PWD}/.claude/scripts/...` 调用**

对每一处 `python3 ${CLAUDE_PROJECT_DIR:-$PWD}/.claude/scripts/<name>.py ...` 改为：
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py ...
```
（涉及 `tracking_query.py`、`changes_gate.py`、`text_humanizer.py`、`check-ai-patterns.js`）

- [ ] **Step 4: 验证无残留**

```bash
grep -rn 'CLAUDE_PLUGIN_ROOT:-' .claude/plugins/webnovel-writer_chang/skills/
grep -rn 'python3 \${CLAUDE_PROJECT_DIR' .claude/plugins/webnovel-writer_chang/skills/
```

预期输出：两个命令都输出 0 行

- [ ] **Step 5: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/skills/webnovel-write/SKILL.md
git commit -m "fix(plugin/webnovel-write): remove CLAUDE_PROJECT_DIR fallback path hacks"
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

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_changes_gate.py tests/test_context_slice.py tests/test_snapshot_manager.py -v 2>&1 | tail -20
```

预期输出：现有测试全绿

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

预期输出：可能 0 行（这两个 skill 没引用脚本），如有就替换为 CLAUDE_PLUGIN_ROOT

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(plugin/skills): migrate webnovel-resume + webnovel-chart-scan"
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

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(plugin/scripts): migrate style_fingerprint.py + tracking_query.py"
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

- [ ] **Step 3: 删除空目录（保留 tests/ 如果在）**

如果 `.claude/scripts/` 完全是空目录：
```bash
rmdir .claude/scripts/
```
如果只剩 `tests/` 子目录：
```bash
# 把 tests/ 也搬进 plugin
git mv .claude/scripts/tests .claude/plugins/webnovel-writer_chang/scripts/tests
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
```

预期输出：
- dev `.claude/` 剩：`plugins/` `references/` `sources/` `worktrees/` `settings.json` `.webnovel-current-project`
- plugin skills 含 10 个目录（init/plan/write/fast-write/revise/deslop-check/resume/chart-scan/doctor/learn/review/query/dashboard/style-profile = 13 个含 dashboard/style-profile 共 15 个，看实际）
- plugin scripts 含 webnovel.py + 迁移的脚本 + _shared/

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore(dev): remove empty .claude/skills/ and .claude/scripts/ after migration"
```

---

# Phase E: webnovel-init 个人语料改路径

## Task 20: 改 webnovel-init SKILL.md：个人语料写到书项目

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/skills/webnovel-init/SKILL.md:200-203`

- [ ] **Step 1: 找出 SKILL.md 里提到个人语料/写作宪法的段落**

```bash
grep -n '个人语料\|写作宪法\|templates' .claude/plugins/webnovel-writer_chang/skills/webnovel-init/SKILL.md | head -20
```

预期输出：列出相关行

- [ ] **Step 2: 改写路径**

打开 SKILL.md，把所有 `${CLAUDE_PLUGIN_ROOT}/skills/webnovel-init/templates/<file>` 替换为 `${PROJECT_ROOT}/.webnovel/writer-profile/<file>`，并加一行说明：
```markdown
# 个人语料默认内容来源：${CLAUDE_PLUGIN_ROOT}/skills/webnovel-init/templates/
# 实际写入位置：${PROJECT_ROOT}/.webnovel/writer-profile/
# （init 时 templates/ 内容会被 copy 到 writer-profile/，用户编辑后者）
```

- [ ] **Step 3: 跑 init_project.py 的 dry-run 看新逻辑**

```bash
python3 .claude/plugins/webnovel-writer_chang/scripts/webnovel.py init --help
```

预期输出：能看到 init 命令的帮助（具体参数按实际）

- [ ] **Step 4: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/skills/webnovel-init/SKILL.md
git commit -m "feat(plugin/webnovel-init): write personal profile to book project's .webnovel/writer-profile/"
```

---

## Task 21: 改 init_project.py 实际实现：copy templates 到 writer-profile/

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/scripts/init_project.py`（如存在该模块）

- [ ] **Step 1: 找出 init 写文件的位置**

```bash
grep -rn '个人语料\|writer-profile\|templates' .claude/plugins/webnovel-writer_chang/scripts/init_project.py 2>/dev/null
grep -rn '个人语料\|writer-profile\|templates' .claude/plugins/webnovel-writer_chang/scripts/data_modules/ 2>/dev/null | head -10
```

- [ ] **Step 2: 按实际位置改路径**

注：实际改哪里取决于 init_project.py 的实现细节——把"写到 plugin templates 目录"改为"copy 到 `<PROJECT_ROOT>/.webnovel/writer-profile/`"。

- [ ] **Step 3: 写小测试验证 init 落点**

```bash
python3 -c "
import os, tempfile, shutil
# 临时建一个 book 项目，跑 init，看 writer-profile/ 是否被创建
tmp = tempfile.mkdtemp()
print('book:', tmp)
# 跑 webnovel.py init --project-root $tmp --dry-run (或真实 run)
# shutil.rmtree(tmp)
"
```

预期输出：init 完后 `tmp/.webnovel/writer-profile/` 目录存在并含默认文件

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(init): write personal profile files to .webnovel/writer-profile/ instead of plugin templates"
```

---

# Phase F: Dev settings.json 瘦身

## Task 22: 删 dev settings.json 的 hooks 块

**Files:**
- Modify: `ai写小说工具开发/.claude/worktrees/refactor-self-contained/.claude/settings.json`

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

## Task 23: 删 dev settings.json 的过宽 permissions

**Files:**
- Modify: `.claude/settings.json`（permissions.allow）

- [ ] **Step 1: 用 Python 清理过宽 permissions**

```bash
python3 <<'PYEOF'
import json
from pathlib import Path
p = Path('.claude/settings.json')
data = json.loads(p.read_text(encoding='utf-8'))
allow = data.get('permissions', {}).get('allow', [])
REMOVE_PATTERNS = [
    'Bash(ls -la*)',
    'Bash(cat *)',
    'Bash(find *)',
    'Bash(grep *)',
    'Bash(mkdir *)',
    'Bash(git status*)',
    'Bash(git diff*)',
    'Bash(git log*)',
    'Bash(pytest*)',
    'Bash(pip install*)',
]
new_allow = [a for a in allow if a not in REMOVE_PATTERNS]
data['permissions']['allow'] = new_allow
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('removed', len(allow) - len(new_allow), 'patterns')
print('remaining', len(new_allow), 'allow rules')
PYEOF
```

预期输出：移除了 N 条过宽规则（具体看实际数量），剩余规则数 = 原数 - 移除数

- [ ] **Step 2: 验证 JSON**

```bash
python3 -c "import json; json.load(open('.claude/settings.json'))" && echo "JSON OK"
```

预期输出：`JSON OK`

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.json
git commit -m "refactor(dev/settings): remove overly broad bash permission globs"
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


def test_plugin_name_is_chang_suffix() -> None:
    """plugin.json 的 name 必须以 _chang 结尾。"""
    import json
    data = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["name"].endswith("_chang"), f"plugin name {data['name']!r} 不以 _chang 结尾"
```

- [ ] **Step 3: 跑测试（应大部分失败，因为 Phase C/D/F 还没全做完；这是预期的 TDD 失败）**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_self_contained.py -v 2>&1 | tail -40
```

预期输出：很多 `FAIL`，但至少 `test_plugin_name_is_chang_suffix` 应通过（Task 3 已改 name）

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

- [ ] **Step 1: 切回 main**

```bash
cd /Users/chang/Desktop/ai写小说工具开发
git checkout main
```

- [ ] **Step 2: 看 worktree 分支的 commits**

```bash
git log --oneline refactor/self-contained ^main | head -40
```

预期输出：列出 refactor 分支独有的 commits（约 20-30 个）

- [ ] **Step 3: 选 merge 策略**

二选一：
- **merge commit**（保留所有原子 commit）：`git merge --no-ff refactor/self-contained`
- **squash**（合成 1 个 commit）：`git merge --squash refactor/self-contained && git commit -m "refactor: webnovel-writer plugin self-contained (spec 2026-08-15)"`

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

- [ ] **Step 6: 推 / 通知**

注：dev workspace 无 remote，无需 push。把重构结果同步到 marketplace 仓库：

```bash
rsync -a --delete .claude/plugins/webnovel-writer_chang/ \
    ~/.claude/plugins/marketplaces/webnovel-chang-marketplace/webnovel-writer_chang/
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
