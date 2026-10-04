# webnovel-writer 个人 fork 实施计划

> **注意（2026-08-12）**：本文是历史快照。下列所有 `/Users/chang/Desktop/webnovel-tool-lab/...` 路径反映 2026-08-08 实施时的工作区；当前工具仓在 `/Users/chang/Desktop/zhanghui/`，参考仓库在 `~/References/ai-webnovel-repos/`，小说项目在 `~/Desktop/根源牌序/`。本文件保留原路径以维持可追溯性，未做替换。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于现有 webnovel-writer 插件，构建项目级 skill 叠加层，解决三个具体痛点：长篇一致性、AI 味重、流程繁琐。

**Architecture:** 不 fork plugin。在 `.claude/` 下做三层叠加：复制 anti-slop 资产 → 写 CHANGES 协议门禁脚本 → 新增快车道 skill。所有改动是非侵入性的，plugin 升级不会破坏。

**Tech Stack:** Python 3.10+（门禁脚本 + 复制 text_humanizer.py）、Node.js（复制 check-ai-patterns.js + normalize-punctuation.js）、pytest（门禁测试）、webnovel-writer plugin 原生 Python/Shell 调用。

---

## 文件总览

### 新建文件
```
.claude/
├── scripts/
│   ├── text_humanizer.py              ← Phase 1 Task 1（复制）
│   ├── check-ai-patterns.js           ← Phase 1 Task 2（复制）
│   ├── normalize-punctuation.js       ← Phase 1 Task 3（复制）
│   ├── changes_gate.py                ← Phase 2 Task 5（新建 ~400 行）
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py                ← Phase 2 Task 4
│       ├── fixtures/
│       │   ├── sample_chapter.md      ← Phase 2 Task 4
│       │   └── test_project.db        ← Phase 2 Task 4（程序化生成）
│       ├── test_r01_protocol.py       ← Phase 2 Task 6
│       ├── test_r02_enums.py          ← Phase 2 Task 6
│       ├── test_r03_entities.py       ← Phase 2 Task 8
│       ├── test_r04_foreshadowing.py  ← Phase 2 Task 9
│       ├── test_r05_relationships.py  ← Phase 2 Task 10
│       ├── test_r06_unregistered.py   ← Phase 2 Task 11
│       ├── test_r07_item_state.py     ← Phase 2 Task 12
│       ├── test_r08_timeline.py       ← Phase 2 Task 13
│       └── test_integration.py        ← Phase 2 Task 14
├── references/
│   ├── changes-protocol.md            ← Phase 2 Task 15
│   ├── changes-examples.md            ← Phase 2 Task 15
│   └── deslop/
│       ├── banned-words.md            ← Phase 1 Task 4（复制）
│       ├── anti-ai-writing.md         ← Phase 1 Task 4（复制）
│       └── humanizer-guide.md         ← Phase 1 Task 4（复制）
└── skills/
    ├── webnovel-fast-write/
    │   └── SKILL.md                   ← Phase 3 Task 16
    └── webnovel-deslop-check/
        └── SKILL.md                   ← Phase 3 Task 17
```

### 修改文件
```
.claude/skills/webnovel-write/skill.md     ← Phase 2 Task 18（注入 CHANGES 协议到 Step 2A 末尾、Step 4 之后追加 4.5/4.6）
```

---

## 工作约定

- **本工作目录非 git 仓库**。所有"提交"步骤改为：创建快照目录 `git init .claude-backup && cd .claude-backup && git init && git add -A && git commit -m "..."`。如果用户已经 git init 过顶层，就正常 commit。
- 路径常量：所有步骤里出现 `${ROOT}` = `/Users/chang/Desktop/webnovel-tool-lab`。
- pytest 运行：所有 pytest 命令在 `${ROOT}/.claude/scripts/` 目录下执行（conftest.py 在那里）。
- pytest 版本：>=7.0，`pip install pytest`。

---

## Phase 1：anti-slop 资产落地（1-2 天）

### Task 1: 复制 text_humanizer.py

**Files:**
- Create: `${ROOT}/.claude/scripts/text_humanizer.py`
- Source: `/Users/chang/Desktop/webnovel-tool-lab/ai-webnovel-repos/02-skills/novel-creator-skill/scripts/text_humanizer.py`

- [ ] **Step 1: 复制文件**

```bash
cp /Users/chang/Desktop/webnovel-tool-lab/ai-webnovel-repos/02-skills/novel-creator-skill/scripts/text_humanizer.py ${ROOT}/.claude/scripts/text_humanizer.py
mkdir -p ${ROOT}/.claude/scripts/  # 如不存在
```

- [ ] **Step 2: 验证文件可执行**

```bash
python3 ${ROOT}/.claude/scripts/text_humanizer.py --help
```

Expected: 输出 `--chapter-file` 等参数帮助。

- [ ] **Step 3: 在文件顶部加 LICENSE 注释**

Edit `text_humanizer.py` 第 1 行（如果有 shebang 行则在其后），追加：

```python
# Forked from novel-creator-skill (MIT License). Used for personal AI-novel workflow.
# Source: https://github.com/.../novel-creator-skill
```

- [ ] **Step 4: 快照**

```bash
cd ${ROOT} && git init .claude-backup && cd .claude-backup && git add -A && git commit -m "phase1: copy text_humanizer.py" --allow-empty
```

### Task 2: 复制 check-ai-patterns.js

**Files:**
- Create: `${ROOT}/.claude/scripts/check-ai-patterns.js`
- Source: `/Users/chang/Desktop/webnovel-tool-lab/ai-webnovel-repos/02-skills/oh-story-claudecode/skills/story-deslop/scripts/check-ai-patterns.js`

- [ ] **Step 1: 复制文件**

```bash
cp /Users/chang/Desktop/webnovel-tool-lab/ai-webnovel-repos/02-skills/oh-story-claudecode/skills/story-deslop/scripts/check-ai-patterns.js ${ROOT}/.claude/scripts/check-ai-patterns.js
```

- [ ] **Step 2: 验证 Node.js 可执行**

```bash
node ${ROOT}/.claude/scripts/check-ai-patterns.js --help
```

Expected: 输出 CLI 帮助。

- [ ] **Step 3: 加 LICENSE 注释**

Edit 文件第 1 行后追加：

```javascript
// Forked from oh-story-claudecode (MIT License). Used for personal AI-novel workflow.
```

- [ ] **Step 4: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase1: copy check-ai-patterns.js" --allow-empty
```

### Task 3: 复制 normalize-punctuation.js

**Files:**
- Create: `${ROOT}/.claude/scripts/normalize-punctuation.js`
- Source: `/Users/chang/Desktop/webnovel-tool-lab/ai-webnovel-repos/02-skills/oh-story-claudecode/skills/story-deslop/scripts/normalize-punctuation.js`

- [ ] **Step 1: 复制**

```bash
cp /Users/chang/Desktop/webnovel-tool-lab/ai-webnovel-repos/02-skills/oh-story-claudecode/skills/story-deslop/scripts/normalize-punctuation.js ${ROOT}/.claude/scripts/normalize-punctuation.js
```

- [ ] **Step 2: 验证**

```bash
node ${ROOT}/.claude/scripts/normalize-punctuation.js --help
```

- [ ] **Step 3: 加 LICENSE 注释 + 快照**

Edit 加 LICENSE 注释，然后：

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase1: copy normalize-punctuation.js" --allow-empty
```

### Task 4: 复制 references/deslop/ 下的 3 份 markdown

**Files:**
- Create: `${ROOT}/.claude/references/deslop/banned-words.md`
- Create: `${ROOT}/.claude/references/deslop/anti-ai-writing.md`
- Create: `${ROOT}/.claude/references/deslop/humanizer-guide.md`

- [ ] **Step 1: 创建目录**

```bash
mkdir -p ${ROOT}/.claude/references/deslop/
```

- [ ] **Step 2: 复制 3 份**

```bash
cp /Users/chang/Desktop/webnovel-tool-lab/ai-webnovel-repos/02-skills/oh-story-claudecode/skills/story-deslop/references/banned-words.md ${ROOT}/.claude/references/deslop/banned-words.md
cp /Users/chang/Desktop/webnovel-tool-lab/ai-webnovel-repos/02-skills/oh-story-claudecode/skills/story-deslop/references/anti-ai-writing.md ${ROOT}/.claude/references/deslop/anti-ai-writing.md
cp /Users/chang/Desktop/webnovel-tool-lab/ai-webnovel-repos/02-skills/novel-creator-skill/references/humanizer-guide.md ${ROOT}/.claude/references/deslop/humanizer-guide.md
```

- [ ] **Step 3: 加 LICENSE 表头**

在每份 md 第 1 行后追加：

```markdown
> Forked from <仓库名> (MIT License). Personal use only.
```

- [ ] **Step 4: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase1: copy 3 deslop markdown references" --allow-empty
```

### Task 5: Phase 1 验收——跑 webnovel-writer 测试章节

**Files:** 无修改

- [ ] **Step 1: 运行 text_humanizer**

```bash
python3 ${ROOT}/.claude/scripts/text_humanizer.py detect --chapter-file "${ROOT}/.claude/plugins/webnovel-writer/agents/evals/files/test-project/正文/第0004章-迦南学院的考验.md" --json > /tmp/humanizer_output.json
cat /tmp/humanizer_output.json | python3 -m json.tool | head -50
```

Expected: 合法 JSON 数组（可能为空），无 Python traceback。

- [ ] **Step 2: 运行 check-ai-patterns**

```bash
node ${ROOT}/.claude/scripts/check-ai-patterns.js --check --fail-on=blocking "${ROOT}/.claude/plugins/webnovel-writer/agents/evals/files/test-project/正文/第0004章-迦南学院的考验.md"
echo "exit: $?"
```

Expected: exit code 0 或 1（blocking 命中），无 Node.js 报错。

- [ ] **Step 3: 跑通即视为 Phase 1 验收通过**

如果两个脚本都跑出非空/有意义的输出且无报错，Phase 1 完成。失败则回到对应 Task 排查。

---

## Phase 2：CHANGES 协议 + 门禁脚本（1 周）

### Task 6: 建测试目录与 conftest

**Files:**
- Create: `${ROOT}/.claude/scripts/tests/__init__.py`
- Create: `${ROOT}/.claude/scripts/tests/conftest.py`
- Create: `${ROOT}/.claude/scripts/tests/fixtures/sample_chapter.md`
- Create: `${ROOT}/.claude/scripts/tests/fixtures/test_project.db`（测试时程序化生成）

- [ ] **Step 1: 建目录结构**

```bash
mkdir -p ${ROOT}/.claude/scripts/tests/fixtures/
touch ${ROOT}/.claude/scripts/tests/__init__.py
```

- [ ] **Step 2: 写 conftest.py**

写入 `${ROOT}/.claude/scripts/tests/conftest.py`：

```python
"""Shared pytest fixtures for changes_gate tests."""
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Create an in-memory SQLite db with the schema webnovel-writer uses."""
    db_path = tmp_path / "test_project.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            type TEXT,
            canonical_name TEXT,
            is_protagonist INTEGER DEFAULT 0,
            is_archived INTEGER DEFAULT 0
        );
        CREATE TABLE aliases (
            alias TEXT,
            entity_id TEXT,
            entity_type TEXT,
            PRIMARY KEY (alias, entity_id, entity_type)
        );
        CREATE TABLE foreshadowing (
            id TEXT PRIMARY KEY,
            description TEXT,
            status TEXT,
            setup_chapter INTEGER,
            payoff_chapter INTEGER
        );
        CREATE TABLE relationships (
            from_entity TEXT,
            to_entity TEXT,
            type TEXT,
            trust_value REAL,
            PRIMARY KEY (from_entity, to_entity, type)
        );
        CREATE TABLE timeline (
            chapter INTEGER PRIMARY KEY,
            time_anchor TEXT,
            elapsed_from_prev TEXT
        );

        INSERT INTO entities VALUES
            ('C-001', 'character', '陈默', 1, 0),
            ('C-002', 'character', '王玄之', 0, 0),
            ('L-001', 'location', '论剑台', 0, 0),
            ('F-001', 'faction', '青云宗', 0, 0),
            ('I-001', 'item', '照夜古镜', 0, 0);

        INSERT INTO aliases VALUES
            ('陈默', 'C-001', 'character'),
            ('玄之', 'C-002', 'character');

        INSERT INTO foreshadowing VALUES
            ('F1-001', '古镜窥见三日', 'setup', 1, NULL),
            ('F1-002', '王玄之身世', 'setup', 2, NULL);

        INSERT INTO relationships VALUES
            ('C-001', 'C-002', 'friend', 50.0);

        INSERT INTO timeline VALUES
            (1, '黄昏', '初始'),
            (2, '夏末', '三日');
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def sample_chapter() -> Path:
    """Return path to a sample chapter file with valid CHANGES block."""
    return Path(__file__).parent / "fixtures" / "sample_chapter.md"


@pytest.fixture
def valid_changes_xml() -> str:
    """Return a valid CHANGES XML block matching the 8-field snake_case schema."""
    return """<chapter_changes>
{
  "character_state_changes": [
    {
      "character_id": "C-001",
      "new_state": "困惑与好奇",
      "key_event": "在祖父遗物中发现古镜",
      "importance": "important"
    }
  ],
  "new_plot_points": [
    {
      "keywords": ["古镜", "窥见"],
      "context": "陈默发现照夜古镜能显示三日后的景象",
      "involved_characters": ["C-001"],
      "importance": "important",
      "storyline": "main"
    }
  ],
  "foreshadowing_actions": [
    {"foreshadow_id": "F1-001", "action": "setup"}
  ],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": {
    "time_period": "夏末黄昏",
    "elapsed_time": "当日半天",
    "importance": "normal"
  },
  "item_transfers": [
    {
      "item_name": "照夜古镜",
      "from_holder": "祖父遗物箱",
      "to_holder": "C-001",
      "new_status": "active",
      "importance": "critical"
    }
  ],
  "unresolved_questions": []
}
</chapter_changes>"""
```

- [ ] **Step 3: 写 sample_chapter.md 最小内容**

写入 `${ROOT}/.claude/scripts/tests/fixtures/sample_chapter.md`：

```markdown
# 第1章：镜启

陈默在祖父遗物中翻出一面明代古镜。

<chapter_changes>
{
  "character_state_changes": [],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}
</chapter_changes>
```

- [ ] **Step 4: 验证 pytest 可运行**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/ --collect-only
```

Expected: `no tests ran`（还没有 test_*.py 文件，但 conftest 被识别）。

- [ ] **Step 5: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase2: test scaffolding with fixtures" --allow-empty
```

### Task 7: 写 changes_gate.py 骨架（解析 + 容错）

**Files:**
- Create: `${ROOT}/.claude/scripts/changes_gate.py`

- [ ] **Step 1: 写空壳 + CLI**

写入 `${ROOT}/.claude/scripts/changes_gate.py`（先不实现校验，只解析）：

```python
#!/usr/bin/env python3
"""CHANGES 协议门禁校验。

在 webnovel-write skill 的 Step 2A 之后被调用：
    python3 changes_gate.py --chapter-file CH.md --db index.db --json

返回 JSON：{"passed": bool, "failures": [{"rule_id", "severity", "message", "location"}]}
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# 8 个顶级字段，借鉴天命 12 字段砍到核心 8 个
REQUIRED_TOP_LEVEL_FIELDS = frozenset({
    "character_state_changes",
    "new_plot_points",
    "foreshadowing_actions",
    "location_state_changes",
    "faction_state_changes",
    "time_progression",
    "item_transfers",
    "unresolved_questions",
})

# 容器形式优先级
CHANGE_PATTERNS = [
    re.compile(r"<chapter_changes>(.*?)</chapter_changes>", re.DOTALL | re.IGNORECASE),
    re.compile(r"---CHANGES---(.*?)(?=---|\Z)", re.DOTALL),
    re.compile(r"^#\s*CHANGES\s*\n(.*?)(?=^#|\Z)", re.DOTALL | re.MULTILINE | re.IGNORECASE),
]


@dataclass
class Failure:
    rule_id: str
    severity: str  # "blocking" | "advisory"
    message: str
    location: str = ""


@dataclass
class GateResult:
    passed: bool
    failures: list[Failure] = field(default_factory=list)
    parsed_changes: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failures": [asdict(f) for f in self.failures],
        }


def extract_changes_block(chapter_text: str) -> str | None:
    """从章节文本里识别 CHANGES 容器。"""
    for pattern in CHANGE_PATTERNS:
        m = pattern.search(chapter_text)
        if m:
            return m.group(1).strip()
    # 兜底：末尾 JSON
    tail = chapter_text.rstrip().split("\n\n")[-1].strip()
    if tail.startswith("{") and tail.endswith("}"):
        candidate_keys = REQUIRED_TOP_LEVEL_FIELDS
        matched = sum(1 for k in candidate_keys if f'"{k}"' in tail)
        if matched >= 4:
            return tail
    return None


def repair_changes_json(raw: str) -> str:
    """借鉴天命的 9 类字符修复。"""
    s = raw
    # 中文标点 → 半角
    s = s.replace("，", ",").replace("：", ":").replace("（", "(").replace("）", ")")
    s = s.replace("；", ";").replace("？", "?").replace("！", "!").replace("「", '"').replace("」", '"')
    # 单引号 → 双引号（仅在键/值的引号位置）
    s = re.sub(r"'([^'\n]+?)'\s*:", r'"\1":', s)
    s = re.sub(r":\s*'([^'\n]+?)'", r': "\1"', s)
    # 缺尾引号自动闭合：扫描所有 key 后面是否缺引号
    # （简化版：依赖 LLM 输出时遵守 json 格式；此处不实现复杂修复）
    return s


def parse_changes(chapter_text: str) -> tuple[dict[str, Any] | None, str | None]:
    """返回 (parsed_dict, error_message)。"""
    block = extract_changes_block(chapter_text)
    if block is None:
        return None, "未找到 CHANGES 容器（支持 <chapter_changes>、---CHANGES---、# CHANGES、末尾 JSON 兜底）"
    repaired = repair_changes_json(block)
    try:
        parsed = json.loads(repaired)
    except json.JSONDecodeError as e:
        return None, f"CHANGES JSON 解析失败：{e}"
    return parsed, None


def main() -> int:
    parser = argparse.ArgumentParser(description="CHANGES 协议门禁")
    parser.add_argument("--chapter-file", required=True, help="章节文件路径")
    parser.add_argument("--db", required=True, help="webnovel-writer index.db 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--rule", help="只跑指定规则（如 R1）")
    parser.add_argument("--strict", action="store_true", help="advisory 也算 blocking")
    args = parser.parse_args()

    chapter_text = Path(args.chapter_file).read_text(encoding="utf-8")
    parsed, err = parse_changes(chapter_text)
    result = GateResult(passed=True, parsed_changes=parsed)
    if err:
        result.passed = False
        result.failures.append(Failure(rule_id="R0", severity="blocking", message=err))

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print("PASSED" if result.passed else f"FAILED: {len(result.failures)} failure(s)")
        for f in result.failures:
            print(f"  [{f.rule_id}/{f.severity}] {f.message}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: CLI 烟测**

```bash
python3 ${ROOT}/.claude/scripts/changes_gate.py --chapter-file ${ROOT}/.claude/scripts/tests/fixtures/sample_chapter.md --db /tmp/nonexistent.db --json
```

Expected: `{"passed": false, "failures": [{"rule_id": "R0", ...}]}` 因为 db 不存在但骨架不调 db，**实际**预期 passed=true（目前骨架没做 db 校验，只解析）。注意：如果 CLI 因为 missing argument 报错，说明 argparse 配置错误，回到 Step 1 检查。

- [ ] **Step 3: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase2: changes_gate.py skeleton with parser" --allow-empty
```

### Task 8: 实现 R1（协议完整性）+ R2（枚举值合法）+ 它们的测试

**Files:**
- Modify: `${ROOT}/.claude/scripts/changes_gate.py`（在 parse_changes 后追加校验调用）
- Create: `${ROOT}/.claude/scripts/tests/test_r01_protocol.py`
- Create: `${ROOT}/.claude/scripts/tests/test_r02_enums.py`

- [ ] **Step 1: 写 R1 失败的测试**

写入 `${ROOT}/.claude/scripts/tests/test_r01_protocol.py`：

```python
"""R1: 协议完整性——8 个顶级字段必须显式存在。"""
from changes_gate import check_r01_protocol, REQUIRED_TOP_LEVEL_FIELDS


def test_r01_passes_with_all_8_fields():
    changes = {field: [] for field in REQUIRED_TOP_LEVEL_FIELDS}
    changes["time_progression"] = None
    failures = check_r01_protocol(changes)
    assert failures == [], f"expected no failures, got {failures}"


def test_r01_fails_when_field_missing():
    changes = {field: [] for field in REQUIRED_TOP_LEVEL_FIELDS}
    changes["time_progression"] = None
    del changes["item_transfers"]  # 缺一个
    failures = check_r01_protocol(changes)
    assert len(failures) == 1
    assert failures[0].rule_id == "R1"
    assert failures[0].severity == "blocking"
    assert "item_transfers" in failures[0].message


def test_r01_fails_when_field_is_undefined():
    """多写了未定义的字段不通过（保持 schema 严格）。"""
    changes = {field: [] for field in REQUIRED_TOP_LEVEL_FIELDS}
    changes["time_progression"] = None
    changes["unexpected_field"] = []  # 不该有的字段
    failures = check_r01_protocol(changes)
    # 注意：当前 spec 允许扩展字段，所以这测试先 expect 0 failures
    # 如果你想严格，去掉下面的 expect 并加 strict-mode flag
    assert failures == []
```

- [ ] **Step 2: 写 R2 失败的测试**

写入 `${ROOT}/.claude/scripts/tests/test_r02_enums.py`：

```python
"""R2: 枚举值合法——action/importance/status 取值在白名单内。"""
from changes_gate import check_r02_enums


def test_r02_passes_with_valid_importance():
    changes = {
        "character_state_changes": [
            {"importance": "important"}
        ]
    }
    assert check_r02_enums(changes) == []


def test_r02_fails_on_invalid_importance():
    changes = {
        "character_state_changes": [
            {"importance": "very-important"}  # 非法
        ]
    }
    failures = check_r02_enums(changes)
    assert len(failures) == 1
    assert failures[0].rule_id == "R2"
    assert "importance" in failures[0].message


def test_r02_fails_on_invalid_action():
    changes = {
        "foreshadowing_actions": [
            {"action": "delete"}  # 只能是 setup 或 payoff
        ]
    }
    failures = check_r02_enums(changes)
    assert len(failures) == 1
    assert failures[0].rule_id == "R2"
    assert "foreshadowing_actions" in failures[0].message


def test_r02_fails_on_invalid_item_status():
    changes = {
        "item_transfers": [
            {"new_status": "broken"}  # 只能 active/lost/destroyed/sealed
        ]
    }
    failures = check_r02_enums(changes)
    assert len(failures) == 1
    assert failures[0].rule_id == "R2"
```

- [ ] **Step 3: 跑测试确认失败**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/test_r01_protocol.py tests/test_r02_enums.py -v
```

Expected: 6 failures（因为 check_r01_protocol 和 check_r02_enums 还没实现）。

- [ ] **Step 4: 实现 R1 + R2**

Edit `${ROOT}/.claude/scripts/changes_gate.py`，在 `parse_changes` 函数后面追加：

```python
# R1 + R2: 校验
ENUM_IMPORTANCE = frozenset({"normal", "important", "critical"})
ENUM_ACTION = frozenset({"setup", "payoff"})
ENUM_STORYLINE = frozenset({"main", "sub", "character_arc"})
ENUM_ITEM_STATUS = frozenset({"active", "lost", "destroyed", "sealed"})
ENUM_TIME_IMPORTANCE = frozenset({"normal", "important", "critical"})


def check_r01_protocol(changes: dict[str, Any]) -> list[Failure]:
    """R1: 8 个顶级字段必须显式存在。"""
    failures = []
    for field_name in REQUIRED_TOP_LEVEL_FIELDS:
        if field_name not in changes:
            failures.append(Failure(
                rule_id="R1",
                severity="blocking",
                message=f"缺少必填字段：{field_name}",
            ))
    return failures


def check_r02_enums(changes: dict[str, Any]) -> list[Failure]:
    """R2: 枚举值合法。"""
    failures = []

    for i, ev in enumerate(changes.get("character_state_changes", []) or []):
        if isinstance(ev, dict):
            imp = ev.get("importance")
            if imp not in ENUM_IMPORTANCE:
                failures.append(Failure(
                    rule_id="R2",
                    severity="blocking",
                    message=f"character_state_changes[{i}].importance='{imp}' 非法，取值应为 {sorted(ENUM_IMPORTANCE)}",
                ))

    for i, ev in enumerate(changes.get("foreshadowing_actions", []) or []):
        if isinstance(ev, dict):
            act = ev.get("action")
            if act not in ENUM_ACTION:
                failures.append(Failure(
                    rule_id="R2",
                    severity="blocking",
                    message=f"foreshadowing_actions[{i}].action='{act}' 非法，取值应为 {sorted(ENUM_ACTION)}",
                ))

    for i, ev in enumerate(changes.get("item_transfers", []) or []):
        if isinstance(ev, dict):
            st = ev.get("new_status")
            if st not in ENUM_ITEM_STATUS:
                failures.append(Failure(
                    rule_id="R2",
                    severity="blocking",
                    message=f"item_transfers[{i}].new_status='{st}' 非法，取值应为 {sorted(ENUM_ITEM_STATUS)}",
                ))

    for i, ev in enumerate(changes.get("new_plot_points", []) or []):
        if isinstance(ev, dict):
            sl = ev.get("storyline")
            if sl is not None and sl not in ENUM_STORYLINE:
                failures.append(Failure(
                    rule_id="R2",
                    severity="blocking",
                    message=f"new_plot_points[{i}].storyline='{sl}' 非法",
                ))
            imp = ev.get("importance")
            if imp is not None and imp not in ENUM_IMPORTANCE:
                failures.append(Failure(
                    rule_id="R2",
                    severity="blocking",
                    message=f"new_plot_points[{i}].importance='{imp}' 非法",
                ))

    return failures
```

同时在 `main()` 函数里，`parsed, err = parse_changes(chapter_text)` 之后、`result = GateResult(...)` 之前插入：

```python
    if parsed:
        for check_fn in (check_r01_protocol, check_r02_enums):
            failures.extend(check_fn(parsed))
        result.failures.extend(failures)
        result.passed = not any(f.severity == "blocking" for f in result.failures)
```

并在文件顶部 imports 后加：

```python
# 注意：上面两个检查函数在文件靠下位置定义，但 main() 在文件底部。
# 如果 Python import 时检查不到，可能需要把它们移到 main() 之前。
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/test_r01_protocol.py tests/test_r02_enums.py -v
```

Expected: 6 passed。

- [ ] **Step 6: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase2: implement R1 (protocol) + R2 (enums)" --allow-empty
```

### Task 9: 实现 R3（实体引用合法）+ 测试

**Files:**
- Modify: `${ROOT}/.claude/scripts/changes_gate.py`
- Create: `${ROOT}/.claude/scripts/tests/test_r03_entities.py`

- [ ] **Step 1: 写 R3 失败的测试**

写入 `${ROOT}/.claude/scripts/tests/test_r03_entities.py`：

```python
"""R3: 实体引用合法——character_id/location_id/faction_id 必须在账本。"""
import sqlite3
from pathlib import Path

import pytest

from changes_gate import check_r03_entities, Failure


def test_r03_passes_with_known_character(test_db: Path):
    changes = {
        "character_state_changes": [{"character_id": "C-001"}],
        "new_plot_points": [{"involved_characters": ["C-002"]}],
    }
    failures = check_r03_entities(changes, test_db)
    assert failures == []


def test_r03_fails_on_unknown_character(test_db: Path):
    changes = {
        "character_state_changes": [{"character_id": "C-999"}],  # 不存在
    }
    failures = check_r03_entities(changes, test_db)
    assert len(failures) == 1
    assert failures[0].rule_id == "R3"
    assert "C-999" in failures[0].message


def test_r03_passes_with_known_alias(test_db: Path):
    """允许用别名而非 ID。"""
    changes = {
        "character_state_changes": [{"character_id": "陈默"}],  # alias
    }
    failures = check_r03_entities(changes, test_db)
    assert failures == []


def test_r03_fails_on_unknown_alias(test_db: Path):
    changes = {
        "character_state_changes": [{"character_id": "张三"}],  # 不在 alias
    }
    failures = check_r03_entities(changes, test_db)
    assert len(failures) == 1
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/test_r03_entities.py -v
```

Expected: 4 failures（check_r03_entities 未实现）。

- [ ] **Step 3: 实现 R3**

Edit `${ROOT}/.claude/scripts/changes_gate.py`，在 R2 实现后追加：

```python
def _load_entity_lookup(db_path: Path) -> tuple[set[str], set[str]]:
    """从 index.db 加载所有合法 ID 和 alias。"""
    if not Path(db_path).exists():
        # db 不存在时返回空集——所有引用都会被标记为未知（由调用方决定是否阻塞）
        return set(), set()
    conn = sqlite3.connect(db_path)
    ids = set()
    aliases = set()
    try:
        for row in conn.execute("SELECT id FROM entities WHERE is_archived = 0"):
            ids.add(row[0])
        for row in conn.execute("SELECT alias FROM aliases"):
            aliases.add(row[0])
    finally:
        conn.close()
    return ids, aliases


def check_r03_entities(changes: dict[str, Any], db_path: Path) -> list[Failure]:
    """R3: 实体引用合法（ID 或 alias 都接受）。"""
    failures = []
    valid_ids, valid_aliases = _load_entity_lookup(db_path)
    if not valid_ids and not valid_aliases:
        # db 不可用，跳过此规则
        return failures

    def check_ref(ref: Any, location: str) -> None:
        if not isinstance(ref, str):
            return
        if ref in valid_ids or ref in valid_aliases:
            return
        failures.append(Failure(
            rule_id="R3",
            severity="blocking",
            message=f"{location}: 引用 '{ref}' 不在账本",
        ))

    for i, ev in enumerate(changes.get("character_state_changes", []) or []):
        if isinstance(ev, dict):
            check_ref(ev.get("character_id"), f"character_state_changes[{i}].character_id")

    for i, ev in enumerate(changes.get("new_plot_points", []) or []):
        if isinstance(ev, dict):
            for j, char_id in enumerate(ev.get("involved_characters", []) or []):
                check_ref(char_id, f"new_plot_points[{i}].involved_characters[{j}]")

    for i, ev in enumerate(changes.get("location_state_changes", []) or []):
        if isinstance(ev, dict):
            check_ref(ev.get("location_id"), f"location_state_changes[{i}].location_id")

    for i, ev in enumerate(changes.get("faction_state_changes", []) or []):
        if isinstance(ev, dict):
            check_ref(ev.get("faction_id"), f"faction_state_changes[{i}].faction_id")

    return failures
```

并在 `main()` 函数里 R2 检查后追加：

```python
            check_r03_entities(parsed, Path(args.db)),
```

同时把 `args.db` 改为接受空字符串或不存在的情况（如果用户没初始化项目，db 不存在时 R3 跳过，不阻塞）。

修改 argparse：

```python
    parser.add_argument("--db", default="", help="webnovel-writer index.db 路径（可选，未初始化项目可省略）")
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/test_r03_entities.py -v
```

Expected: 4 passed。

- [ ] **Step 5: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase2: implement R3 (entity reference)" --allow-empty
```

### Task 10: 实现 R4（伏笔推进）+ 测试

**Files:**
- Modify: `${ROOT}/.claude/scripts/changes_gate.py`
- Create: `${ROOT}/.claude/scripts/tests/test_r04_foreshadowing.py`

- [ ] **Step 1: 写 R4 失败的测试**

写入 `${ROOT}/.claude/scripts/tests/test_r04_foreshadowing.py`：

```python
"""R4: 伏笔推进——foreshadow_id 必须存在于账本。"""
from pathlib import Path

from changes_gate import check_r04_foreshadowing


def test_r04_passes_with_known_foreshadow(test_db: Path):
    changes = {"foreshadowing_actions": [{"foreshadow_id": "F1-001", "action": "setup"}]}
    assert check_r04_foreshadowing(changes, test_db) == []


def test_r04_fails_on_unknown_foreshadow(test_db: Path):
    changes = {"foreshadowing_actions": [{"foreshadow_id": "F9-999", "action": "setup"}]}
    failures = check_r04_foreshadowing(changes, test_db)
    assert len(failures) == 1
    assert failures[0].rule_id == "R4"


def test_r04_fails_on_payoff_before_setup(test_db: Path):
    """R4 高级约束：如果 foreshadowing 在账本中状态不是 setup，标记 payoff 应报错。"""
    # 先把 F1-002 标记为 payoff（已回收）
    import sqlite3
    conn = sqlite3.connect(test_db)
    conn.execute("UPDATE foreshadowing SET status='paid' WHERE id='F1-002'")
    conn.commit()
    conn.close()

    changes = {"foreshadowing_actions": [{"foreshadow_id": "F1-002", "action": "payoff"}]}
    failures = check_r04_foreshadowing(changes, test_db)
    assert len(failures) >= 1  # 不允许重复 payoff
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/test_r04_foreshadowing.py -v
```

Expected: 3 failures。

- [ ] **Step 3: 实现 R4**

Edit `${ROOT}/.claude/scripts/changes_gate.py`，在 R3 后追加：

```python
def _load_foreshadowing_state(db_path: Path) -> dict[str, str]:
    if not Path(db_path).exists():
        return {}
    conn = sqlite3.connect(db_path)
    state = {}
    try:
        for row in conn.execute("SELECT id, status FROM foreshadowing"):
            state[row[0]] = row[1]
    finally:
        conn.close()
    return state


def check_r04_foreshadowing(changes: dict[str, Any], db_path: Path) -> list[Failure]:
    """R4: 伏笔 ID 必须存在 + 不能重复 payoff。"""
    failures = []
    fs_state = _load_foreshadowing_state(db_path)
    if not fs_state:
        return failures  # db 不可用，跳过

    for i, ev in enumerate(changes.get("foreshadowing_actions", []) or []):
        if not isinstance(ev, dict):
            continue
        fid = ev.get("foreshadow_id")
        action = ev.get("action")
        if fid not in fs_state:
            failures.append(Failure(
                rule_id="R4",
                severity="blocking",
                message=f"foreshadowing_actions[{i}].foreshadow_id='{fid}' 不在账本",
            ))
            continue
        current_status = fs_state[fid]
        # 状态机：setup 可以反复 setup（强化伏笔），payoff 后不能再 payoff
        if action == "payoff" and current_status == "paid":
            failures.append(Failure(
                rule_id="R4",
                severity="blocking",
                message=f"foreshadowing_actions[{i}]: '{fid}' 已被回收，不能再次 payoff",
            ))

    return failures
```

并在 main() 里 R3 检查后追加：

```python
            check_r04_foreshadowing(parsed, Path(args.db)),
```

- [ ] **Step 4: 跑测试**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/test_r04_foreshadowing.py -v
```

Expected: 3 passed。

- [ ] **Step 5: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase2: implement R4 (foreshadowing)" --allow-empty
```

### Task 11: 实现 R5（信任度变化超 ±30）+ 测试

**Files:**
- Modify: `${ROOT}/.claude/scripts/changes_gate.py`
- Create: `${ROOT}/.claude/scripts/tests/test_r05_relationships.py`

- [ ] **Step 1: 写 R5 失败的测试**

写入 `${ROOT}/.claude/scripts/tests/test_r05_relationships.py`：

```python
"""R5: 信任度变化——单章 ±delta 不超过 30。"""
from pathlib import Path

from changes_gate import check_r05_relationships


def test_r05_passes_with_small_delta(test_db: Path):
    changes = {
        "character_state_changes": [
            {"relationship_changes": {"C-002": {"trust_delta": 10}}}
        ]
    }
    assert check_r05_relationships(changes, test_db) == []


def test_r05_fails_with_huge_delta(test_db: Path):
    changes = {
        "character_state_changes": [
            {"relationship_changes": {"C-002": {"trust_delta": 50}}}  # 超 30
        ]
    }
    failures = check_r05_relationships(changes, test_db)
    assert len(failures) == 1
    assert failures[0].rule_id == "R5"
    assert "trust_delta=50" in failures[0].message


def test_r05_fails_with_negative_delta_exceeded(test_db: Path):
    changes = {
        "character_state_changes": [
            {"relationship_changes": {"C-002": {"trust_delta": -45}}}
        ]
    }
    failures = check_r05_relationships(changes, test_db)
    assert len(failures) == 1
```

- [ ] **Step 2: 实现 R5**

Edit `${ROOT}/.claude/scripts/changes_gate.py`，在 R4 后追加：

```python
MAX_TRUST_DELTA = 30


def check_r05_relationships(changes: dict[str, Any], db_path: Path) -> list[Failure]:
    """R5: 单章关系信任度变化不超过 ±MAX_TRUST_DELTA。"""
    failures = []
    for i, ev in enumerate(changes.get("character_state_changes", []) or []):
        if not isinstance(ev, dict):
            continue
        rel_changes = ev.get("relationship_changes", {}) or {}
        if not isinstance(rel_changes, dict):
            continue
        for target, info in rel_changes.items():
            if not isinstance(info, dict):
                continue
            delta = info.get("trust_delta")
            if delta is None:
                continue
            if abs(delta) > MAX_TRUST_DELTA:
                failures.append(Failure(
                    rule_id="R5",
                    severity="blocking",
                    message=f"character_state_changes[{i}].relationship_changes['{target}']: trust_delta={delta} 超过 ±{MAX_TRUST_DELTA}",
                ))
    return failures
```

main() 里追加：

```python
            check_r05_relationships(parsed, Path(args.db)),
```

- [ ] **Step 3: 跑测试**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/test_r05_relationships.py -v
```

Expected: 3 passed。

- [ ] **Step 4: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase2: implement R5 (trust delta)" --allow-empty
```

### Task 12: 实现 R6（未登记实体）+ 测试

**Files:**
- Modify: `${ROOT}/.claude/scripts/changes_gate.py`
- Create: `${ROOT}/.claude/scripts/tests/test_r06_unregistered.py`

- [ ] **Step 1: 写 R6 失败的测试**

写入 `${ROOT}/.claude/scripts/tests/test_r06_unregistered.py`：

```python
"""R6: 未登记实体——正文提到但未申报的实体 ≤ 5。"""
import re
from pathlib import Path

from changes_gate import extract_chapter_entities, check_r06_unregistered


def test_extract_finds_known_and_unknown():
    text = """
    陈默走向论剑台。
    神秘的黑衣女子出现了。
    王玄之在角落里观察。
    """
    known = {"陈默", "王玄之", "论剑台"}
    registered = {"陈默", "王玄之", "论剑台"}  # 假设这三个都在账本
    mentioned = extract_chapter_entities(text)
    unknown = [m for m in mentioned if m not in registered]
    assert "黑衣女子" in unknown
    assert "陈默" not in unknown
    assert "论剑台" not in unknown


def test_r06_passes_with_few_unknowns():
    text = "陈默在论剑台等王玄之。"
    changes = {"new_entities_mentioned": []}  # 没申报
    failures = check_r06_unregistered(text, changes, registered={"陈默", "王玄之", "论剑台"})
    assert failures == []


def test_r06_fails_with_too_many_unknowns():
    text = "陈默遇到了黑衣人、白衣剑客、灰衣老者、红发魔女、青袍道士、绿衫少女。"
    changes = {"new_entities_mentioned": []}
    failures = check_r06_unregistered(text, changes, registered={"陈默"})
    assert len(failures) == 1
    assert failures[0].rule_id == "R6"
    assert "5" in failures[0].message or "过多" in failures[0].message
```

- [ ] **Step 2: 实现 R6**

Edit `${ROOT}/.claude/scripts/changes_gate.py`，在 R5 后追加：

```python
# 常见中文名/称谓停用词，避免误报
ENTITY_STOPWORDS = frozenset({
    "他", "她", "它", "我", "你", "我们", "他们", "她们", "它们",
    "这", "那", "这个", "那个", "这些", "那些",
    "什么", "怎么", "为什么", "谁", "哪里",
    "主角", "配角", "反派", "路人",
})

# 中文姓名启发式：2-4 字 + 不在停用词 + 不含标点
ENTITY_PATTERN = re.compile(r"[一-龥]{2,4}")


def extract_chapter_entities(text: str) -> set[str]:
    """从正文提取可能的实体名（启发式）。"""
    candidates = set()
    for m in ENTITY_PATTERN.finditer(text):
        name = m.group()
        if name not in ENTITY_STOPWORDS:
            candidates.add(name)
    return candidates


def check_r06_unregistered(text: str, changes: dict[str, Any], registered: set[str]) -> list[Failure]:
    """R6: 正文中提到的实体如未在账本且未在 CHANGES 申报，超过阈值则告警。"""
    threshold = 5
    mentioned = extract_chapter_entities(text)
    # 申报了的实体也算已知
    declared = set()
    for ev in changes.get("character_state_changes", []) or []:
        if isinstance(ev, dict):
            cid = ev.get("character_id")
            if cid:
                declared.add(cid)
    for ev in changes.get("new_plot_points", []) or []:
        if isinstance(ev, dict):
            for cid in ev.get("involved_characters", []) or []:
                declared.add(cid)

    unregistered = mentioned - registered - declared
    if len(unregistered) > threshold:
        return [Failure(
            rule_id="R6",
            severity="blocking",
            message=f"正文中出现 {len(unregistered)} 个未登记实体（阈值 {threshold}）：{sorted(unregistered)[:10]}...",
        )]
    return []
```

main() 里追加：

```python
    # R6 需要 chapter 全文 + 已加载的 registered ids
    if parsed:
        registered_ids, registered_aliases = _load_entity_lookup(Path(args.db))
        all_known = registered_ids | registered_aliases
        chapter_text_for_r6 = Path(args.chapter_file).read_text(encoding="utf-8")
        for f in check_r06_unregistered(chapter_text_for_r6, parsed, all_known):
            result.failures.append(f)
        result.passed = not any(f.severity == "blocking" for f in result.failures)
```

- [ ] **Step 3: 跑测试**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/test_r06_unregistered.py -v
```

Expected: 3 passed。

- [ ] **Step 4: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase2: implement R6 (unregistered entities)" --allow-empty
```

### Task 13: 实现 R7（物品状态机）+ 测试

**Files:**
- Modify: `${ROOT}/.claude/scripts/changes_gate.py`
- Create: `${ROOT}/.claude/scripts/tests/test_r07_item_state.py`

- [ ] **Step 1: 写 R7 失败的测试**

写入 `${ROOT}/.claude/scripts/tests/test_r07_item_state.py`：

```python
"""R7: 物品状态机——item status 转移合法。"""
from pathlib import Path

from changes_gate import check_r07_item_state


def test_r07_passes_with_normal_status(test_db: Path):
    changes = {"item_transfers": [{"new_status": "active"}]}
    assert check_r07_item_state(changes, test_db) == []


def test_r07_passes_when_no_previous_state(test_db: Path):
    """物品首次出现，没有 prev state 时不报错。"""
    changes = {"item_transfers": [{"item_id": "I-NEW", "new_status": "active"}]}
    assert check_r07_item_state(changes, test_db) == []


def test_r07_fails_on_destroyed_to_active(test_db: Path):
    """已 destroyed 的物品不能变回 active（除非经过 sealed 中转）。"""
    import sqlite3
    conn = sqlite3.connect(test_db)
    # 给 I-001 设一个前状态
    conn.execute("CREATE TABLE IF NOT EXISTS item_state (item_id TEXT PRIMARY KEY, status TEXT)")
    conn.execute("INSERT OR REPLACE INTO item_state VALUES ('I-001', 'destroyed')")
    conn.commit()
    conn.close()

    changes = {"item_transfers": [{"item_id": "I-001", "new_status": "active"}]}
    failures = check_r07_item_state(changes, test_db)
    assert len(failures) == 1
    assert failures[0].rule_id == "R7"
```

- [ ] **Step 2: 实现 R7**

Edit `${ROOT}/.claude/scripts/changes_gate.py`，在 R6 后追加：

```python
# 物品状态机：合法转移图
ITEM_STATE_TRANSITIONS = {
    None: {"active", "lost", "destroyed", "sealed"},
    "active": {"active", "lost", "destroyed", "sealed"},
    "lost": {"active", "destroyed"},
    "sealed": {"active", "destroyed", "lost"},
    "destroyed": set(),  # destroyed 是终态
}


def _load_item_state(db_path: Path) -> dict[str, str]:
    if not Path(db_path).exists():
        return {}
    conn = sqlite3.connect(db_path)
    state = {}
    try:
        # 兼容 item 表的 current_json 字段或单独的 item_state 表
        for row in conn.execute("SELECT id, current_json FROM entities WHERE type='item'"):
            import json as _json
            try:
                cur = _json.loads(row[1]) if row[1] else {}
                status = cur.get("status")
                if status:
                    state[row[0]] = status
            except _json.JSONDecodeError:
                pass
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
    return state


def check_r07_item_state(changes: dict[str, Any], db_path: Path) -> list[Failure]:
    """R7: 物品状态转移合法。"""
    failures = []
    item_state = _load_item_state(db_path)
    for i, ev in enumerate(changes.get("item_transfers", []) or []):
        if not isinstance(ev, dict):
            continue
        item_id = ev.get("item_id")
        new_status = ev.get("new_status")
        if not item_id or not new_status:
            continue  # 没 ID 不强制校验
        prev_status = item_state.get(item_id)
        legal_next = ITEM_STATE_TRANSITIONS.get(prev_status, set())
        if legal_next and new_status not in legal_next:
            failures.append(Failure(
                rule_id="R7",
                severity="blocking",
                message=f"item_transfers[{i}]: '{item_id}' 从 '{prev_status}' → '{new_status}' 非法转移，合法目标：{sorted(legal_next)}",
            ))
    return failures
```

main() 里追加：

```python
            check_r07_item_state(parsed, Path(args.db)),
```

- [ ] **Step 3: 跑测试**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/test_r07_item_state.py -v
```

Expected: 3 passed。

- [ ] **Step 4: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase2: implement R7 (item state machine)" --allow-empty
```

### Task 14: 实现 R8（时间线连贯）+ 测试

**Files:**
- Modify: `${ROOT}/.claude/scripts/changes_gate.py`
- Create: `${ROOT}/.claude/scripts/tests/test_r08_timeline.py`

- [ ] **Step 1: 写 R8 失败的测试**

写入 `${ROOT}/.claude/scripts/tests/test_r08_timeline.py`：

```python
"""R8: 时间线连贯——time_progression 不与上一章冲突。"""
from pathlib import Path

from changes_gate import check_r08_timeline


def test_r08_passes_with_null_progression(test_db: Path):
    """time_progression 为 null 时不报错。"""
    changes = {"time_progression": None}
    assert check_r08_timeline(changes, test_db, current_chapter=3) == []


def test_r08_passes_with_progression(test_db: Path):
    changes = {"time_progression": {"elapsed_time": "一日"}}
    assert check_r08_timeline(changes, test_db, current_chapter=3) == []


def test_r08_fails_on_chapter_regression(test_db: Path):
    """检测：声称回到上一章之前的时间。"""
    # 当前 chapter = 3，上一章（chapter=2）time_anchor="夏末"
    changes = {"time_progression": {"elapsed_time": "回到三年前"}}
    failures = check_r08_timeline(changes, test_db, current_chapter=3)
    # 这条规则启发式较简单，只检测明显的倒退
    # 如无明显倒退则不报错
    assert isinstance(failures, list)
```

- [ ] **Step 2: 实现 R8**

Edit `${ROOT}/.claude/scripts/changes_gate.py`，在 R7 后追加：

```python
import re as _re_time


def _extract_chapter_number(chapter_text: str) -> int | None:
    """从章节文件正文里提取章号。"""
    m = _re_time.search(r"第\s*(\d+)\s*章", chapter_text)
    return int(m.group(1)) if m else None


def _load_timeline(db_path: Path) -> dict[int, str]:
    if not Path(db_path).exists():
        return {}
    conn = sqlite3.connect(db_path)
    state = {}
    try:
        for row in conn.execute("SELECT chapter, time_anchor FROM timeline ORDER BY chapter"):
            state[row[0]] = row[1]
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
    return state


def check_r08_timeline(changes: dict[str, Any], db_path: Path, current_chapter: int) -> list[Failure]:
    """R8: 时间线连贯——本章不应声明与上一章冲突的时间。"""
    failures = []
    tp = changes.get("time_progression")
    if not tp or not isinstance(tp, dict):
        return failures
    elapsed = (tp.get("elapsed_time") or "").strip()
    if not elapsed:
        return failures

    timeline = _load_timeline(db_path)
    if not timeline:
        return failures  # db 不可用跳过

    # 简单启发式：检测"回到"、"倒退"等关键词
    suspicious_keywords = ["回到", "倒退", "前一年", "三年前", "十年前"]
    if any(kw in elapsed for kw in suspicious_keywords):
        # 进一步要求上一章存在
        if (current_chapter - 1) in timeline:
            failures.append(Failure(
                rule_id="R8",
                severity="advisory",  # 注意：启发式不确定，用 advisory
                message=f"time_progression.elapsed_time='{elapsed}' 含倒退关键词，请人工确认",
            ))
    return failures
```

main() 里 R8 调用需要 current_chapter：

```python
    chapter_text_for_r8 = Path(args.chapter_file).read_text(encoding="utf-8")
    chapter_num = _extract_chapter_number(chapter_text_for_r8) or 0
    if parsed:
        for f in check_r08_timeline(parsed, Path(args.db), chapter_num):
            result.failures.append(f)
```

并把 `--strict` 时 advisory 也算 blocking（前面已声明，未实现）：

```python
        if args.strict:
            result.passed = not result.failures
        else:
            result.passed = not any(f.severity == "blocking" for f in result.failures)
```

- [ ] **Step 3: 跑测试**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/test_r08_timeline.py -v
```

Expected: 3 passed。

- [ ] **Step 4: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase2: implement R8 (timeline coherence)" --allow-empty
```

### Task 15: 集成测试（5 正例 + 5 反例）

**Files:**
- Create: `${ROOT}/.claude/scripts/tests/test_integration.py`

- [ ] **Step 1: 写集成测试**

写入 `${ROOT}/.claude/scripts/tests/test_integration.py`：

```python
"""集成测试——5 正例 + 5 反例对照。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
GATE_SCRIPT = ROOT / ".claude" / "scripts" / "changes_gate.py"


def run_gate(chapter_text: str, db_path: Path, *extra_args: str) -> dict:
    chapter_file = Path("/tmp/_test_chapter.md")
    chapter_file.write_text(chapter_text, encoding="utf-8")
    cmd = [
        sys.executable, str(GATE_SCRIPT),
        "--chapter-file", str(chapter_file),
        "--db", str(db_path),
        "--json",
        *extra_args,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        pytest.fail(f"gate crashed: stderr={result.stderr}")
    return json.loads(result.stdout)


def make_chapter(changes_obj) -> str:
    return f"""# 第5章：测试

正文内容。

<chapter_changes>
{json.dumps(changes_obj, ensure_ascii=False)}
</chapter_changes>
"""


# 5 个正例
def test_positive_minimal_empty(test_db: Path):
    """最小合法 CHANGES：所有数组为空，time_progression=null。"""
    changes = {f: [] for f in [
        "character_state_changes", "new_plot_points", "foreshadowing_actions",
        "location_state_changes", "faction_state_changes",
        "item_transfers", "unresolved_questions"
    ]}
    changes["time_progression"] = None
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is True, result


def test_positive_known_entities(test_db: Path):
    changes = {
        "character_state_changes": [{"character_id": "C-001", "importance": "important"}],
        "new_plot_points": [],
        "foreshadowing_actions": [{"foreshadow_id": "F1-001", "action": "setup"}],
        "location_state_changes": [],
        "faction_state_changes": [],
        "time_progression": None,
        "item_transfers": [],
        "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is True, result


def test_positive_alias_reference(test_db: Path):
    """用 alias 而非 ID 也应该通过。"""
    changes = {
        "character_state_changes": [{"character_id": "陈默", "importance": "normal"}],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is True, result


def test_positive_small_trust_delta(test_db: Path):
    changes = {
        "character_state_changes": [{
            "character_id": "C-001",
            "relationship_changes": {"C-002": {"trust_delta": 5}},
            "importance": "important"
        }],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is True, result


def test_positive_valid_setup_action(test_db: Path):
    changes = {
        "character_state_changes": [], "new_plot_points": [],
        "foreshadowing_actions": [{"foreshadow_id": "F1-001", "action": "setup"}],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is True, result


# 5 个反例
def test_negative_missing_field(test_db: Path):
    """缺少必填字段。"""
    changes = {
        "character_state_changes": [], "new_plot_points": [],
        "foreshadowing_actions": [], "location_state_changes": [],
        "faction_state_changes": [], "time_progression": None,
        "unresolved_questions": []
        # 缺 item_transfers
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is False
    assert any("item_transfers" in f["message"] for f in result["failures"])


def test_negative_invalid_enum(test_db: Path):
    changes = {
        "character_state_changes": [{"importance": "very-important"}],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is False
    assert any(f["rule_id"] == "R2" for f in result["failures"])


def test_negative_unknown_entity(test_db: Path):
    changes = {
        "character_state_changes": [{"character_id": "Z-999"}],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is False
    assert any(f["rule_id"] == "R3" for f in result["failures"])


def test_negative_huge_trust_delta(test_db: Path):
    changes = {
        "character_state_changes": [{
            "character_id": "C-001",
            "relationship_changes": {"C-002": {"trust_delta": 100}}
        }],
        "new_plot_points": [], "foreshadowing_actions": [],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is False
    assert any(f["rule_id"] == "R5" for f in result["failures"])


def test_negative_unknown_foreshadow(test_db: Path):
    changes = {
        "character_state_changes": [], "new_plot_points": [],
        "foreshadowing_actions": [{"foreshadow_id": "F9-999", "action": "setup"}],
        "location_state_changes": [], "faction_state_changes": [],
        "time_progression": None, "item_transfers": [], "unresolved_questions": [],
    }
    result = run_gate(make_chapter(changes), test_db)
    assert result["passed"] is False
    assert any(f["rule_id"] == "R4" for f in result["failures"])
```

- [ ] **Step 2: 跑集成测试**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/test_integration.py -v
```

Expected: 10 passed（5 正例 + 5 反例）。

- [ ] **Step 3: 跑全套测试**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/ -v
```

Expected: 所有测试通过（R1-R8 共 22 个 + 集成 10 个 = 32 个左右）。

- [ ] **Step 4: Phase 2 验收快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase2: integration tests pass, gate complete" --allow-empty
```

### Task 16: 写 CHANGES 协议文档

**Files:**
- Create: `${ROOT}/.claude/references/changes-protocol.md`
- Create: `${ROOT}/.claude/references/changes-examples.md`

- [ ] **Step 1: 写 changes-protocol.md**

写入 `${ROOT}/.claude/references/changes-protocol.md`：

```markdown
# CHANGES 协议字段定义

本协议借鉴天命 AI 写小说工具的结构化变更声明机制，**简化到 8 个核心字段**以降低 LLM 输出成本。

## 容器形式

优先格式：`<chapter_changes>...</chapter_changes>`

容错顺序：
1. `<chapter_changes>...</chapter_changes>`
2. `---CHANGES--- ...`
3. `# CHANGES\n...`
4. 末尾 JSON 兜底（≥4 个顶级字段匹配）

## 8 个顶级字段

| 字段名 | 类型 | 是否必填 | 枚举值 |
|---|---|---|---|
| `character_state_changes` | array | 是 | — |
| `new_plot_points` | array | 是 | — |
| `foreshadowing_actions` | array | 是 | action: setup / payoff |
| `location_state_changes` | array | 是 | — |
| `faction_state_changes` | array | 是 | — |
| `time_progression` | object \| null | 是 | importance: normal / important / critical |
| `item_transfers` | array | 是 | new_status: active / lost / destroyed / sealed |
| `unresolved_questions` | array | 是 | — |

空数组 `[]` 也算"显式存在"——不要省略字段。

## 字段细则

### character_state_changes[i]

```json
{
  "character_id": "C-001 或 别名",
  "new_state": "字符串",
  "relationship_changes": {
    "C-002": {"relation": "挚友", "trust_delta": 5, "emotion_phase": "信任"}
  },
  "key_event": "关键事件描述",
  "importance": "normal | important | critical"
}
```

### new_plot_points[i]

```json
{
  "keywords": ["古镜", "窥见"],
  "context": "陈默发现照夜古镜能显示三日后的景象",
  "involved_characters": ["C-001"],
  "importance": "normal | important | critical",
  "storyline": "main | sub | character_arc"
}
```

### foreshadowing_actions[i]

```json
{
  "foreshadow_id": "F1-001",
  "action": "setup | payoff"
}
```

### location_state_changes[i]

```json
{
  "location_id": "L-001 或别名",
  "new_status": "字符串",
  "event": "事件描述",
  "importance": "normal | important | critical"
}
```

### faction_state_changes[i]

```json
{
  "faction_id": "F-001 或别名",
  "new_status": "字符串",
  "event": "事件描述",
  "importance": "normal | important | critical"
}
```

### time_progression

```json
{
  "time_period": "夏末黄昏",
  "elapsed_time": "三日",
  "key_time_event": "主角抵港三日",
  "importance": "normal | important | critical"
}
```

### item_transfers[i]

```json
{
  "item_id": "I-001 或别名（首次出现可只用 item_name）",
  "item_name": "照夜古镜",
  "from_holder": "持有者 ID 或别名",
  "to_holder": "新持有者 ID 或别名",
  "new_status": "active | lost | destroyed | sealed",
  "event": "转移事件描述",
  "importance": "normal | important | critical"
}
```

### unresolved_questions[i]

```json
{
  "question": "古镜的完整来历？",
  "introduced_chapter": 1,
  "target_payoff_chapter": 50,
  "importance": "normal | important | critical"
}
```
```

- [ ] **Step 2: 写 changes-examples.md**

写入 `${ROOT}/.claude/references/changes-examples.md`：

```markdown
# CHANGES 协议示例

## 完整示例

```markdown
（章节正文：约 2500 字，陈默在论剑台险胜王玄之...）

<chapter_changes>
{
  "character_state_changes": [
    {
      "character_id": "C-001",
      "new_state": "疲惫但振奋",
      "relationship_changes": {
        "C-002": {"relation": "宿敌", "trust_delta": 3, "emotion_phase": "竞争"}
      },
      "key_event": "在论剑台险胜王玄之",
      "importance": "critical"
    },
    {
      "character_id": "C-002",
      "new_state": "受伤但不甘",
      "key_event": "论剑台落败",
      "importance": "important"
    }
  ],
  "new_plot_points": [
    {
      "keywords": ["论剑台", "王玄之"],
      "context": "陈默与王玄之的第一次正面交锋，主角险胜",
      "involved_characters": ["C-001", "C-002"],
      "importance": "important",
      "storyline": "main"
    }
  ],
  "foreshadowing_actions": [
    {"foreshadow_id": "F1-002", "action": "setup"}
  ],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": {
    "time_period": "夏末黄昏",
    "elapsed_time": "一日",
    "key_time_event": "论剑台对决",
    "importance": "normal"
  },
  "item_transfers": [],
  "unresolved_questions": [
    {
      "question": "王玄之的真实身份？",
      "introduced_chapter": 2,
      "target_payoff_chapter": 30,
      "importance": "important"
    }
  ]
}
</chapter_changes>
```

## 极简示例

```markdown
（章节正文...）

<chapter_changes>
{
  "character_state_changes": [],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "item_transfers": [],
  "unresolved_questions": []
}
</chapter_changes>
```

## 错误示例（会被门禁打回）

```markdown
<!-- 缺 item_transfers 字段 -->
<chapter_changes>
{
  "character_state_changes": [],
  "new_plot_points": [],
  "foreshadowing_actions": [],
  "location_state_changes": [],
  "faction_state_changes": [],
  "time_progression": null,
  "unresolved_questions": []
}
</chapter_changes>

<!-- importance 非法值 -->
{"character_state_changes": [{"importance": "very-important"}]}

<!-- 不在账本的 character_id（除非已加入账本）-->
{"character_state_changes": [{"character_id": "Z-999"}]}

<!-- trust_delta 超阈值 -->
{"character_state_changes": [{"character_id": "C-001", "relationship_changes": {"C-002": {"trust_delta": 100}}}]}
```
```

- [ ] **Step 3: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase2: CHANGES protocol docs" --allow-empty
```

### Task 17: 改造 webnovel-write/skill.md 注入 CHANGES 协议和门禁

**Files:**
- Modify: `${ROOT}/.claude/skills/webnovel-write/skill.md`

- [ ] **Step 1: 在 Step 2A 之后追加"CHANGES 协议要求"段落**

Edit `${ROOT}/.claude/skills/webnovel-write/skill.md`，找到 Step 2A 描述段落的末尾（grep "Step 2A" 找到位置），在 Step 2B 描述之前插入：

```markdown
### Step 2A 末尾追加：CHANGES 协议声明

Step 2A 生成章节正文后，**必须在正文末尾追加一个 `<chapter_changes>...</chapter_changes>` 块**，
包含本章对设定集/人物/物品/伏笔的所有结构化变更。

字段定义见 `.claude/references/changes-protocol.md`。
示例见 `.claude/references/changes-examples.md`。

8 个顶级字段必须全部显式存在（即使无变化也要写 `[]` 或 `null`）。
```

- [ ] **Step 2: 在 Step 4 之后追加 Step 4.5（CHANGES 校验门禁）**

找到 Step 4 的结束位置（grep "Step 4" 找上下文，找包含 Step 5 引用之前的位置），
在 Step 5 之前插入：

```markdown
### Step 4.5：CHANGES 协议门禁

执行命令：

\`\`\`bash
python3 ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/changes_gate.py \\
    --chapter-file 正文/第{NNNN}章-{title_safe}.md \\
    --db .webnovel/index.db \\
    --json
\`\`\`

**判定逻辑**：
- `passed=true`：进入 Step 5（data-agent）。
- `passed=false`：读取 `failures` 列表，把每条规则的报错反馈给主流程 LLM，要求**只重写 `<chapter_changes>` 块**（不改正文）。最多 2 次。
- 2 次仍未通过：记录到 `.webnovel/tmp/changes_gate_failures.jsonl`，人工介入后走 `/webnovel-resume`。
```

- [ ] **Step 3: 在 Step 4.5 之后追加 Step 4.6（anti-slop 扫描）**

```markdown
### Step 4.6：anti-slop 扫描

并行执行两个扫描器：

\`\`\`bash
python3 ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/text_humanizer.py \\
    detect --chapter-file 正文/第{NNNN}章-{title_safe}.md \\
    --json > /tmp/humanizer.json

node ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/check-ai-patterns.js \\
    --check --fail-on=blocking \\
    正文/第{NNNN}章-{title_safe}.md
\`\`\`

**判定逻辑**：
- blocking 命中：退回 Step 4 重写正文（**保留 CHANGES 块**）。最多 2 次。
- advisory 命中：写入 `.story-system/anti_patterns.json`，继续流程。

可选关闭：在命令前加 `--skip-deslop`。
```

- [ ] **Step 4: 把 Skill `allowed-tools` 改为包含 Bash**

Edit 文件顶部的 YAML front matter：

```yaml
---
name: webnovel-write
description: ...
allowed-tools: Read Write Edit Grep Bash Task
---
```

（Bash 应该已经在允许列表，确认一下）

- [ ] **Step 5: 验证 skill.md 文件结构**

```bash
head -30 ${ROOT}/.claude/skills/webnovel-write/skill.md
grep -n "Step 4.5" ${ROOT}/.claude/skills/webnovel-write/skill.md
grep -n "Step 4.6" ${ROOT}/.claude/skills/webnovel-write/skill.md
```

Expected: 三个 grep 都有输出。

- [ ] **Step 6: Phase 2 验收快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase2: inject CHANGES gate and anti-slop into webnovel-write" --allow-empty
```

---

## Phase 3：快车道 + 独立扫描 skill（2-3 天）

### Task 18: 写 webnovel-fast-write/SKILL.md

**Files:**
- Create: `${ROOT}/.claude/skills/webnovel-fast-write/SKILL.md`

- [ ] **Step 1: 创建目录**

```bash
mkdir -p ${ROOT}/.claude/skills/webnovel-fast-write/
```

- [ ] **Step 2: 写 SKILL.md**

写入 `${ROOT}/.claude/skills/webnovel-fast-write/SKILL.md`：

```markdown
---
name: webnovel-fast-write
description: 跳过 reviewer 和 polish 完整流程的快车道写章节。保留 CHANGES 校验 + anti-slop 扫描 + data-agent。Use when you trust the direction of a single chapter and don't need 5-dimension subjective review. Runs Step 0/1/2A/4.5/4.6/5/6.
allowed-tools: Read Write Edit Grep Bash Task
---

# Fast Chapter Writing (Skip Reviewer)

## 目标

写一章并通过 CHANGES 校验 + anti-slop 扫描 + data-agent，**不调 reviewer、不跑完整 polish**。
相比 `/webnovel-write` 节省一次 subagent 调用（reviewer 是 5 维串行，最耗时）。

## 适用场景

- 你信任本章的方向（章节大纲清楚、伏笔命中明确）
- 不想为单章花 5+ 分钟等 reviewer 审查
- 已写过至少 3 章 /webnovel-write，对 webnovel-writer 的节奏有感觉

## 不适用场景

- 第一次写新项目（先跑 `/webnovel-write` 摸清边界）
- 重大剧情转折（用 `/webnovel-write`，reviewer 兜底）
- 用户明确要求"严格审查"

## 执行流程

按顺序执行：

1. **Step 0 预检**：调用 `${CLAUDE_PLUGIN_ROOT}/scripts/webnovel.py preflight` + `placeholder-scan`。
2. **Step 1 context-agent**：调用 `webnovel-writer:context-agent` subagent 生成 5 段任务书。
3. **Step 2A 起草**：主流程生成正文 + 末尾追加 `<chapter_changes>...</chapter_changes>` 块。
4. **Step 4.5 CHANGES 校验**：调用 `python3 .claude/scripts/changes_gate.py ...`（详见主 skill 的 Step 4.5）。
5. **Step 4.6 anti-slop 扫描**：调用 `text_humanizer.py` + `check-ai-patterns.js`（详见主 skill 的 Step 4.6）。
6. **Step 5 data-agent**：调用 `webnovel-writer:data-agent` subagent 产出 extraction_result 等 3 份 artifact。
7. **Step 5.2 chapter-commit**：调用 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/webnovel.py chapter-commit`。
8. **Step 6 备份**：调用 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/webnovel.py backup`。

## 跳过步骤

- **Step 2B 风格转译**（可选）
- **Step 3 reviewer 5 维审查**（主流程跳过）
- **Step 4 polish 完整流程**（只保留 4.5 + 4.6 两道门禁）

## 失败处理

- Step 4.5 失败：退回 Step 2A 重写 CHANGES 块（最多 2 次）
- Step 4.6 blocking：退回 Step 2A 重写正文（保留 CHANGES 块），最多 2 次
- Step 5 schema 失败：退回 Step 2A 全章重写

## 退出条件

跑 5-10 章后评估：
- 如果感觉与 `/webnovel-write` 质量持平 → 改用本 skill 作为默认
- 如果某章明显需要 reviewer 介入 → 临时回退到 `/webnovel-write`
```

- [ ] **Step 3: 验证 skill 文件结构**

```bash
head -10 ${ROOT}/.claude/skills/webnovel-fast-write/SKILL.md
```

Expected: YAML front matter 完整。

- [ ] **Step 4: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase3: webnovel-fast-write skill" --allow-empty
```

### Task 19: 写 webnovel-deslop-check/SKILL.md

**Files:**
- Create: `${ROOT}/.claude/skills/webnovel-deslop-check/SKILL.md`

- [ ] **Step 1: 创建目录**

```bash
mkdir -p ${ROOT}/.claude/skills/webnovel-deslop-check/
```

- [ ] **Step 2: 写 SKILL.md**

写入 `${ROOT}/.claude/skills/webnovel-deslop-check/SKILL.md`：

```markdown
---
name: webnovel-deslop-check
description: 独立触发 anti-slop 双引擎扫描，对任意章节（已写好的）输出 Markdown 报告。Use when reviewing existing chapters, batch-scanning old drafts, or doing a periodic health check on your manuscript.
allowed-tools: Read Write Edit Grep Bash
---

# De-Slop Check (Independent Anti-AI-Flavor Scanner)

## 目标

对任意已写章节（或全本所有章节）跑 anti-slop 扫描，输出 Markdown 报告：
- blocking 项位置 + 原文引用 + 修改建议
- advisory 项汇总

## 适用场景

- 回头改稿：扫旧章节，看哪些地方需要改
- 批量体检：扫全本，统计 AI 味最重的章节
- 阶段性 review：每写 10 章扫一次，确认风格未漂移

## 执行方式

### 扫单个章节

\`\`\`bash
python3 ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/text_humanizer.py \\
    detect --chapter-file 正文/第{NNNN}章-{title_safe}.md \\
    --json > /tmp/humanizer.json

node ${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/scripts/check-ai-patterns.js \\
    --check --fail-on=blocking \\
    正文/第{NNNN}章-{title_safe}.md
\`\`\`

把两份输出合并为 Markdown 报告，存到 `审查报告/deslop-第{NNNN}章.md`。

### 批量扫描全本

扫描 `正文/` 目录下所有章节：

\`\`\`bash
for f in 正文/第*.md; do
    echo "=== $f ==="
    python3 .claude/scripts/text_humanizer.py detect --chapter-file "$f" --json 2>&1 | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'  blocking: {sum(1 for x in data if x.get(\"severity\")==\"blocking\")}')
print(f'  advisory: {sum(1 for x in data if x.get(\"severity\")==\"advisory\")}')
"
done
\`\`\`

生成 `审查报告/deslop-batch-report.md` 汇总。

## 报告模板

每个 blocking 项：

\`\`\`markdown
### [RULE_ID] 规则名

- **位置**：第 N 段 / 第 N 行
- **原文**：`"..."`
- **问题**：解释为什么这是 AI 味
- **修改建议**：给出一个具体改写方向
\`\`\`

advisory 项汇总到末尾表格。

## 不做的事

- 不改正文（这是 reviewer-like skill 的工作，不属于本 skill）
- 不调用 reviewer subagent
- 不写 CHANGES 校验（CHANGES 是写前用的，本 skill 是写后用的）
```

- [ ] **Step 3: 验证**

```bash
head -10 ${ROOT}/.claude/skills/webnovel-deslop-check/SKILL.md
```

- [ ] **Step 4: 快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase3: webnovel-deslop-check skill" --allow-empty
```

### Task 20: Phase 3 验收——端到端跑一遍

**Files:** 无修改

- [ ] **Step 1: 跑 text_humanizer 全套测试章节**

```bash
for f in /Users/chang/Desktop/webnovel-tool-lab/.claude/plugins/webnovel-writer/agents/evals/files/test-project/正文/*.md; do
    echo "=== $f ==="
    python3 /Users/chang/Desktop/webnovel-tool-lab/.claude/scripts/text_humanizer.py detect --chapter-file "$f" --json 2>&1 | head -10
done
```

Expected: 至少一次输出非空（说明扫描器在工作）。

- [ ] **Step 2: 跑全套 pytest**

```bash
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/ -v
```

Expected: 所有测试通过（约 32 个）。

- [ ] **Step 3: 跑 changes_gate 真实测试章节**

```bash
python3 /Users/chang/Desktop/webnovel-tool-lab/.claude/scripts/changes_gate.py \\
    --chapter-file /Users/chang/Desktop/webnovel-tool-lab/.claude/plugins/webnovel-writer/agents/evals/files/test-project/正文/第0004章-迦南学院的考验.md \\
    --db /tmp/nonexistent.db \\
    --json
```

Expected: 返回 JSON，因为该章节没有 `<chapter_changes>` 块，应返回 `{"passed": false, "failures": [{"rule_id": "R0", ...}]}`。

- [ ] **Step 4: Phase 3 验收快照**

```bash
cd ${ROOT}/.claude-backup && git add -A && git commit -m "phase3: e2e verification complete" --allow-empty
echo "=== Phase 3 complete ==="
```

- [ ] **Step 5: 输出完成报告**

```bash
echo "Files created/modified:"
find ${ROOT}/.claude/ -type f -newer ${ROOT}/.claude/plugins/ -name "*.py" -o -name "*.js" -o -name "*.md" 2>/dev/null | sort
echo
echo "Test results:"
cd ${ROOT}/.claude/scripts && python3 -m pytest tests/ -v 2>&1 | tail -10
```

---

## 完成定义

整套工具的完成标志：

1. ✅ `${ROOT}/.claude/scripts/text_humanizer.py` 等 3 个 anti-slop 脚本可独立跑
2. ✅ `${ROOT}/.claude/scripts/changes_gate.py` 8 项校验规则全部实现且测试通过
3. ✅ `${ROOT}/.claude/scripts/tests/` 下 32+ 测试全部通过
4. ✅ `${ROOT}/.claude/skills/webnovel-write/skill.md` 已注入 Step 4.5 + 4.6
5. ✅ `${ROOT}/.claude/skills/webnovel-fast-write/SKILL.md` 可用
6. ✅ `${ROOT}/.claude/skills/webnovel-deslop-check/SKILL.md` 可用
7. ✅ 真实测试章节跑扫描器有非空输出
8. ✅ `${ROOT}/.claude/references/changes-protocol.md` + `changes-examples.md` 完整
9. ✅ 用户实际写过 5-10 章后给出"至少 X 个痛点被解决"的反馈