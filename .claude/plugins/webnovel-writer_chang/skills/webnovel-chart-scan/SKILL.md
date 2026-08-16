---
name: webnovel-chart-scan
description: 扫起点/番茄/纵横/七猫/刺猬猫五个网文平台的分类榜单，提取元数据（书名/作者/分类/简介/字数/状态/标签/排名），输出 JSON + Markdown 报告到当前项目目录。写新书前手动调用，调研题材和找对标书。
allowed-tools: Read Write Edit Grep Bash Task WebFetch
---

# /webnovel-chart-scan — 扫网文平台分类榜单

## 目标

一键扫 5 个网文平台（起点 / 番茄 / 纵横 / 七猫 / 刺猬猫）的分类榜单，提取明面元数据，生成报告和 JSON。

## 适用场景

- 写新书前手动调用，调研当前热门题材
- 找 3-5 本对标书做差异化分析
- 跟踪某题材的设定/金手指变化趋势

## 不适用场景

- 抓正文（合规边界）
- 抓会员/付费章节
- 实时监控（这是手动工具）

## CLI 调用

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/webnovel-chart-scan/scripts/scan.py [options]
```

或者：

```bash
cd /path/to/novel-project
chart-scan --platform=qidian --category=玄幻 --top=20 --period=monthly
```

## CLI 参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--platform` | `all` | 逗号分隔，例 `qidian,fanqie` 或 `all` |
| `--category` | `all` | 分类名，例 `玄幻` 或 `all` |
| `--top` | `50` | 每榜前 N 本，限制 ≤100 |
| `--period` | `weekly` | `daily` / `weekly` / `monthly`（逗号分隔多值） |
| `--output-dir` | `./chart-scan` | 输出目录（相对 cwd） |
| `--verbose` | false | 打印每个 adapter 执行细节 |

## 输出

调用时所在项目目录下生成 `./chart-scan/`：

```
chart-scan/
├── report.md          # 人读报告（概览 + 字数分布 + 标签云 + 完整榜单 + 失败记录）
├── books.json         # 机读：所有 BookItem + ScanMeta + errors
└── scan_<timestamp>.log
```

## 失败行为

- 单个 adapter 失败 → 写入 `books.json` 的 `errors` 字段，主流程继续
- 全部 adapter 失败 → 退出码 1
- 部分失败 → 退出码 0，报告里显眼标记

## 平台覆盖

| 平台 | Strategy | 说明 |
|------|----------|------|
| 起点 | HYBRID | parser + URL 模板 + 分类 ID（reference-only vendor） |
| 番茄 | DIRECT_DUMP | fetch GitHub raw daily dump（无需 chromium，最多 24h 数据延迟，取决于用户时区） |
| 纵横 | DIRECT_API | 自写 httpx 调公开 API |
| 七猫 | VENDOR | clone WebCrawler（个人自用） |
| 刺猬猫 | WEBFETCH (vendored CDP) | shell-out to vendored Node scraper（SessionStart 钩子引导装 agent-browser + Chrome @ 9222） |

详见 `references/upstream-survey.md`。

## 依赖

- Python 3.11+
- pydantic, httpx, beautifulsoup4, lxml
- （可选）playwright + chromium for 番茄

## 安装

```bash
cd ${CLAUDE_PLUGIN_ROOT}/skills/webnovel-chart-scan
pip install -e ".[fanqie,dev]"
playwright install chromium  # 番茄需要
```

### 刺猬猫额外设置

ciweimao adapter 需要 Chrome @ 9222 + `agent-browser`。SessionStart 钩子会
在你第一次进入项目时弹 y/N 提示；接受即可一键装好。

手动运行：
```bash
webnovel-chart-scan-setup-ciweimao
```

或自定义端口：
```bash
WEBNOVEL_CIWEIMAO_CDP_PORT=9333 webnovel-chart-scan-setup-ciweimao --port 9333
```

### 标记对标书（联动 /webnovel-deconstruct）

读完 `report.md` 后，可以告诉 Claude "标记对标：《A》《B》《C》"（书名列表）。Claude 会把标记清单写到 `./chart-scan/marked-references.json`。

之后运行 `/webnovel-deconstruct --from-scan` 会读取这个清单，批量拆解所有标记的书。

`marked-references.json` schema：

```json
{
  "schema_version": 1,
  "marked_at": "<ISO8601>",
  "from_scan": "./chart-scan/books.json",
  "references": [
    {"platform": "qidian", "title": "凡人修仙传", "author": "忘语", "category": "仙侠"}
  ]
}
```

查看当前标记清单：直接读 `./chart-scan/marked-references.json`（如果有）。

**注意**：chart-scan 自身**不会**自动写 `marked-references.json`——用户必须明确告诉 Claude "标记对标"。这是有意的设计：保持 chart-scan 的 hermetic 性质，避免自动行为带来的认知负担。