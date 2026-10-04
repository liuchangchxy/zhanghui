# `/webnovel-chart-scan` 设计文档（v0.2 实施稿）

> **状态**：实施稿（覆盖 v0.1 初步稿，调研完成后重写）
> **日期**：2026-08-12
> **作者**：与 Claude 对话产出
> **代码归属**：`/Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/`

---

## 1. 背景与目标

### 1.1 痛点

网文作者在开新书前，需要做"市场调研 + 对标分析"：扫起点/番茄/纵横/七猫/刺猬猫的榜，看同类书在写什么、提炼可借鉴的设定/金手指/人物关系。

现有工具链缺这一环——`deconstruction-agent` 能拆本地文本，但不能"先找书，再拆"。

### 1.2 目标

提供 `/webnovel-chart-scan` skill，让作者能：

1. 一键拉取起点 + 番茄 + 纵横 + 七猫 + 刺猬猫 五个平台的分类榜单
2. 提取榜单明面信息（书名/作者/分类/简介/字数/状态/标签/封面/排名位置）
3. 生成人读报告（Markdown）和机读 JSON，输出到调用时所在项目目录
4. 优先复用 GitHub 上游现成项目，按平台适配混合集成策略（fork / vendor / direct API / WebFetch）

### 1.3 非目标

- 不做逐章深度拆解（沿用现有 `deconstruction-agent`）
- 不抓全本正文（合规与体量双约束）
- 不替代平台官方榜单 UI（这是给 AI 用的，不是给人看的）
- 不做内容生成/缝合/创作（留给 init 阶段用户决策）
- 不做账号管理/付费章节/会员内容

---

## 2. 触发与用户故事

### 2.1 触发

用户在任何写小说的项目目录下手动调用：

```
/webnovel-chart-scan
/webnovel-chart-scan --platform=qidian --category=玄幻 --top=50 --period=monthly
/webnovel-chart-scan --platform=fanqie,zongheng --category=都市 --top=30
/webnovel-chart-scan --all  # 5 平台全跑
```

### 2.2 用户故事

| # | 我作为 | 想要 | 以便 |
|---|--------|------|------|
| 1 | 网文作者 | 写新书前扫一眼当前热门题材在写什么 | 找准赛道和卖点 |
| 2 | 网文作者 | 拿到 3-5 本对标书的简介+标签+金手指类型 | 做差异化和借鉴缝合 |
| 3 | 网文作者 | 输出落在调用时所在项目目录，方便对比历史 | 多次扫描结果可对比 |
| 4 | 工具维护者 | 切换数据源（某个 API 挂了）只改对应 adapter | 不污染其他模块 |
| 5 | 工具维护者 | 个人自用环境，无需担心未声明 License 的小众仓库 | 提速 MVP |

---

## 3. 核心原则

1. **优先复用现成的**：GitHub 上扫榜项目多，按平台适配策略（fork / vendor / direct API / WebFetch），不自己造轮子
2. **统一归一化层**：上游怎么抓归各 adapter 管，schema 归一化由 `normalize.py` 单点负责
3. **轻量边界**：MVP 只做明面信息提取，不做正文抓取和逐章拆
4. **失败可降级**：adapter 失败 = 单条 `AdapterError` 写入 `errors`，主流程不崩；adapter 内部有"上游 → 平台公开 API → WebFetch + BS4 → 报错"四级降级链
5. **合规底线**：不抓付费章节正文；只拉公开可见的榜单元数据
6. **个人自用 License 容差**：未声明 License 的小众仓库（如 `staysharp1104/WebCrawler`）允许 clone 用于本地扫描，不做分发

---

## 4. 功能范围

### 4.1 MVP（v0.1，必须做）

- [ ] 拉取 5 个平台分类榜单（玄幻/都市/仙侠/历史/科幻/游戏/同人/军事/灵异/二次元/轻小说/体育/现实/其它）
- [ ] 每个榜单默认 top=50（可调 ≤100）
- [ ] 支持 daily / weekly / monthly 三种周期
- [ ] 提取每本书：书名 / 作者 / 分类 / 简介 / 字数 / 连载状态 / 标签 / 封面 URL / 详情 URL / 排名位置
- [ ] 5 平台各至少 1 个 adapter 上线
- [ ] 归一化到统一 JSON schema（见 §6.1）
- [ ] 生成 `chart-scan/report.md`（人读，含表格 + 概览 + 标签云）
- [ ] 生成 `chart-scan/books.json`（机读）
- [ ] 输出落在调用时所在项目根目录的 `chart-scan/` 下
- [ ] CLI 参数：`--platform`, `--category`, `--top`, `--period`, `--output-dir`
- [ ] 上游选型记录（`references/upstream-survey.md`）
- [ ] 单元测试覆盖率 ≥ 60%，关键 adapter 有 fixture 离线回归

### 4.2 v0.2（增强）

- [ ] 多书对比模式：选 2-5 本书，输出"异同表 + 缝合建议"
- [ ] 与 `/webnovel-init` 联动：`--feed-init`
- [ ] 增量缓存：避免每次全量拉
- [ ] SQLite 输出（`chart-scan.db`），便于历史对比和趋势查询

### 4.3 v0.3+（远期）

- [ ] 其他平台：飞卢、SFACG、ESJZone
- [ ] 调用现有 `deconstruction-agent` 做正文级拆（用户需自备文本）
- [ ] 趋势曲线：某题材近 30 天上榜变化

---

## 5. 架构概览

### 5.1 目录结构

```
.claude/skills/webnovel-chart-scan/
├── SKILL.md # Claude Code 入口 + CLI 参数说明
├── pyproject.toml                    # Python 项目元数据（依赖、entry_points）
├── README.md
├── scripts/
│   ├── scan.py                       # 主控：CLI 解析 / 调度 / 归一化 / 报告渲染
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py                   # BaseAdapter + Strategy enum + fetch/normalize 接口
│   │   ├── qidian.py                 # Strategy: VENDOR（mix parser + URL templates + cat ID）
│   │   ├── fanqie.py                 # Strategy: VENDOR（fork FanqieRankTracker 子目录）
│   │   ├── zongheng.py               # Strategy: DIRECT_API（httpx 调公开 JSON API）
│   │   ├── qimao.py                  # Strategy: VENDOR（clone WebCrawler 关键模块）
│   │   └── ciweimao.py               # Strategy: WEBFETCH（bs4 兜底）
│   ├── normalize.py                  # RawBook → BookItem 字段映射
│   ├── schema.py                     # pydantic BookItem + ScanResult + AdapterError
│   ├── report.py                     # Markdown 渲染（表格 + 概览 + 标签云）
│   └── output.py                     # 写文件逻辑（默认 ./chart-scan/）
├── vendor/                           # 实际 vendored 上游代码
│   ├── novel-downloader/             # 起点 parser（saudadez21，MIT）
│   ├── fanqie-rank-tracker/          # 番茄（Despacito0o，MIT）
│   └── qimao-web-crawler/            # 七猫（staysharp1104，未声明，自用）
├── references/
│   ├── upstream-survey.md            # 上游选型调研记录（5 平台详表）
│   ├── category-mapping.md           # 各平台分类 → 统一分类（玄幻/都市/...）
│   └── adapter-strategies.md         # 每个 adapter 的 strategy 详解
├── tests/
│   ├── test_normalize.py
│   ├── test_schema.py
│   ├── test_qidian_adapter.py
│   ├── test_fanqie_adapter.py
│   ├── test_zongheng_adapter.py
│   ├── test_qimao_adapter.py
│   ├── test_ciweimao_adapter.py
│   └── fixtures/                     # 离线样本 HTML/JSON（用于不上网的单元测试）
```

### 5.2 模块边界

- `scan.py` 只做编排：**不抓数据**
- 每个 adapter 实现 `BaseAdapter.fetch(category, period, top) -> list[RawBook]`
- `normalize.py` 把 `RawBook` 转 `BookItem`（统一 schema）
- `report.py` 只消费 `BookItem`，不知道上游存在
- `output.py` 只管写文件，不知道 schema 内容

### 5.3 数据流

```
CLI 参数
  ↓
scan.py 解析
  ↓
对每个 (platform, category, period, top) 组合：
  ↓
  路由到对应 adapter.fetch()
  ↓
  adapter 内部走四级降级链（vendor → direct API → WebFetch → 报错）
  ↓
  返回 list[RawBook]
  ↓
  normalize.raw_to_bookitem(raw, platform, period)
  ↓
  累积 list[BookItem] + list[AdapterError]
  ↓
report.render(books) → Markdown
output.write(report_md, books_json, output_dir)
  ↓
chart-scan/report.md + chart-scan/books.json
```

---

## 6. 数据契约

### 6.1 统一 schema（`schema.py`）

```python
class RawBook(BaseModel):
    """平台原始数据，由各 adapter 的 fetch() 返回。字段名是约定俗成的 snake_case。"""
    platform_book_id: str
    title: str
    author: str
    category: str                       # 平台原始分类
    tags: list[str] = []
    intro: str = ""
    word_count: int | None = None
    status: Literal["serial","completed"] | None = None
    cover_url: str | None = None
    detail_url: str | None = None
    rank_position: int | None = None
    raw_payload: dict = {}              # 平台原始 JSON/HTTP 响应，调试用

class BookItem(BaseModel):
    id: str                                  # "{platform}-{book_id}"
    platform: Literal["qidian","fanqie","zongheng","qimao","ciweimao"]
    title: str
    author: str
    category: str                            # 平台原始分类
    category_normalized: str                 # 映射后统一分类（玄幻/都市/...）
    tags: list[str] = []
    intro: str = ""                          # ≤500 字
    word_count: int | None = None
    status: Literal["serial","completed"] | None = None
    cover_url: str | None = None
    detail_url: str | None = None
    rank_position: int | None = None
    period: Literal["daily","weekly","monthly"]
    fetched_at: datetime

class AdapterError(BaseModel):
    platform: str
    category: str
    period: str
    stage: Literal["vendor","direct_api","webfetch","normalize"]
    message: str
    occurred_at: datetime

class ScanMeta(BaseModel):
    platforms: list[str]
    categories: list[str]
    periods: list[str]
    top: int
    scanned_at: datetime
    duration_seconds: float
    total_books: int
    total_errors: int

class ScanResult(BaseModel):
    meta: ScanMeta
    books: list[BookItem]
    errors: list[AdapterError] = []
```

### 6.2 CLI 参数

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `--platform` | string | `all` | 逗号分隔，例 `qidian,fanqie` 或 `all` |
| `--category` | string | `all` | 分类名，例 `玄幻` 或 `all`（逗号分隔多分类） |
| `--top` | int | `50` | 每榜拉取前 N 本，限制 ≤100 |
| `--period` | string | `weekly` | 逗号分隔，例 `daily,weekly,monthly` |
| `--output-dir` | path | `./chart-scan` | 输出目录（相对当前 cwd） |
| `--verbose` | flag | false | 打印每个 adapter 的执行细节 |

### 6.3 输出文件

调用时所在项目目录下生成：

```
<output-dir>/
├── report.md                          # 人读报告
├── books.json                         # 机读：所有 BookItem + ScanMeta + errors
└── scan_<timestamp>.log               # 运行日志（始终写入；--verbose 时内容更详细）
```

---

## 7. 平台 adapter 策略详解

### 7.1 策略枚举（`base.py`）

```python
class Strategy(str, Enum):
    VENDOR = "vendor"           # vendored 完整上游代码（fork or clone）
    DIRECT_API = "direct_api"   # 自写薄壳调平台公开 API
    WEBFETCH = "webfetch"       # 自写 httpx + BeautifulSoup 兜底
```

### 7.2 各平台策略详表

| 平台 | Strategy | 抓取路径 | 字段来源 | 失败降级链 |
|------|----------|----------|----------|------------|
| **起点** | VENDOR | vendored `novel-downloader` 的 `qidian/parser.py` + 自写 `category_browser.py` 调 `/all?chanId={id}` AJAX | 分类页 JSON 拿 80% 字段 + 单书详情页拿 tags/word_count | vendor → WebFetch 公开榜 → 报错 |
| **番茄** | VENDOR | fork `FanqieRankTracker`，主循环用它的 `scrape_fanqie_ranks.py`，扩展 `get_book_detail()` 拿字数/标签 | 榜单元数据 + 详情页补全 | vendor（Playwright）→ WebFetch + BS4 公开榜 → 报错 |
| **纵横** | DIRECT_API | `httpx.get("https://www.zongheng.com/api/rank/details?rankType={N}&pageSize=50&pageNum={P}")` | API 直接返回 bookName/author/cateFineName/number/orderNo（rank_position）；intro/word_count/status/tags 需单书详情页补全 | direct_api → WebFetch + BS4 榜单 HTML → 报错 |
| **七猫** | VENDOR | clone `WebCrawler` 的七猫模块（Nuxt.js SSR `__NUXT__` 解析） | 榜单页 + 单书详情页 | vendor → WebFetch 公开榜 → 报错 |
| **刺猬猫** | WEBFETCH | `httpx` + `BeautifulSoup` 直拉 `https://www.ciweimao.com/category/{分类}/` + 详情页 | 榜单页 HTML + 详情页 | webfetch → 提示用户手输 |

### 7.3 adapter 接口契约

```python
class BaseAdapter(ABC):
    platform: str
    strategy: Strategy

    @abstractmethod
    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        """按平台策略抓取榜单，返回平台原始数据。"""

    def normalize(self, raw: RawBook, period: str) -> BookItem:
        """默认调用 normalize.py 的 raw_to_bookitem；adapter 可重写。"""
```

每个 adapter 必须实现 `fetch()`；`normalize()` 默认走 `normalize.raw_to_bookitem()`，仅当字段映射特殊时重写。

---

## 8. 失败降级 + 错误处理

### 8.1 主流程容错

1. **adapter 失败不抛异常**：捕获所有异常，构造 `AdapterError` 写入 `errors`
2. **BookItem 字段缺失 = `None`**，不抛异常；intro 截断到 500 字
3. **跨平台独立**：一个平台挂了，其他平台继续；一个分类挂了，其他分类继续
4. **退出码**：有部分失败时 `exit 0` 但报告里显眼标记；有 *全部* 失败时 `exit 1`

### 8.2 adapter 内部四级降级链

```
1. 首选 strategy（VENDOR / DIRECT_API / WEBFETCH）
   ↓ 失败
2. 退到下一级（VENDOR → DIRECT_API → WEBFETCH）
   ↓ 失败
3. 退到 WebFetch + BS4 公开榜（任何 strategy 失败都兜底）
   ↓ 失败
4. 抛 AdapterError 到主流程，不静默吞掉
```

### 8.3 反爬与限流

- 默认请求间隔 1.5s（可调，CLI 参数 `--rate-limit`）
- 自带 `User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ...` + `Referer: https://{platform_host}/`
- `top` 硬限 ≤100（避免触发封号）
- 命中 HTTP 429/403 时自动 sleep 30s 重试一次；仍失败则降级
- 不使用 headless browser 跑默认扫描（仅番茄 adapter 首次 Playwright 冷启动）

---

## 9. 测试策略

### 9.1 测试层次

| 层级 | 内容 | 工具 | 网络 |
|------|------|------|------|
| 单元 | `normalize.py` 各种 RawBook → BookItem 映射 | pytest | 否 |
| 单元 | `schema.py` 字段验证（缺字段/类型错/枚举） | pytest | 否 |
| 单适配 | 各 adapter 在 `tests/fixtures/` 离线样本上跑通 | pytest | 否 |
| 集成 | 端到端 `--top 5 --category 玄幻` 不崩 | pytest（`@pytest.mark.slow`） | 是 |

### 9.2 fixtures 策略

- 首次成功运行某 adapter 时，把它的真实响应存到 `tests/fixtures/{platform}_{category}_{period}.json`
- 离线测试读取 fixture 验证 normalize 逻辑
- fixture 文件不超过 1MB/个（避免污染仓库）

### 9.3 验收标准（v0.1）

满足以下全部条件即视为 v0.1 可发布：

1. `python scripts/scan.py --platform=qidian --category=玄幻 --top=20 --period=weekly` 输出 JSON + MD 不崩
2. 5 平台各至少 1 个 adapter 单元测试通过
3. 单元测试覆盖率 ≥ 60%（关键路径：`normalize.py` + `schema.py` + `output.py` 必须 100%）
4. `references/upstream-survey.md` 记录 5 平台选型调研
5. `references/category-mapping.md` 覆盖 5 平台主分类（玄幻/都市/仙侠/历史/科幻/游戏/同人）
6. `SKILL.md` 写清 CLI 参数、输出位置、失败行为
7. 任意 adapter 失败时主流程返回 `errors` 列表而不是 `exit 1`
8. 跑一次全平台扫榜（5 平台 × 默认周期 × top=50）≤ 10 分钟，不触发封号

---

## 10. 上游选型记录（摘要）

详细版见 `references/upstream-survey.md`。摘要：

| 平台 | 首选上游 | License | 集成方式 | 关键风险 |
|------|----------|---------|----------|----------|
| 起点 | `saudadez21/novel-downloader` parser + `xuduogui/QiDianAPI` URL 模板 + `howie6879/owllook` 分类 ID 表 | MIT + Apache-2.0 | vendor parser + 抄 URL + 抄 ID 表 | 需 Python 3.11+ |
| 番茄 | `Despacito0o/FanqieRankTracker` | MIT | fork 完整代码（250 行） | Playwright + Chromium 冷启动 |
| 纵横 | **无候选**（GitHub 上无活跃 zongheng 分类榜项目） | — | DIRECT_API：自写 50 行 httpx 调 `zongheng.com/api/rank/details` | 字段需详情页补全 |
| 七猫 | `staysharp1104/WebCrawler` | ⚠ 未声明（个人自用容差） | clone 七猫模块 | License 不清（自用 OK） |
| 刺猬猫 | **无候选**（GitHub 上唯一 Python 项目 `saudadez21/novel-downloader` 的刺猬猫插件 issue #157 已失效 9 个月） | — | WEBFETCH：自写 httpx + BeautifulSoup | 需自己逆向反爬 |

**架构模板**（学谁的设计）：`NanmiCoder/NewsCrawler` 的 SKILL.md + detector + adapters/ + 归一化 schema 模式。

---

## 11. 风险与依赖

| 风险 | 影响 | 缓解 |
|------|------|------|
| 上游 API 失效/反爬加强 | 整个 adapter 不可用 | adapter 内部四级降级链 + `errors` 不静默 |
| 起点/番茄分类口径不一致 | normalize 复杂 | 维护 `category-mapping.md` 映射表 |
| 上游 License 不兼容 | 法律风险（分发场景） | MVP 自用，暂忽略；未来分发需重写 |
| 抓数据量过大触发封号 | IP 被 ban | top ≤ 100，间隔 1.5s/请求 |
| 番茄/七猫 JS 渲染 | httpx 拿不到 | 用 vendored Playwright/Selenium 方案 |
| 七猫 `WebCrawler` License 不清 | 二次分发风险 | MVP 自用 OK；商业场景需重写 |
| vendored 依赖体积 | skill 目录变大 | 每个 vendor 子目录记录 commit hash，便于后续同步上游 |
| Python 3.11+ 要求（起点 parser） | 环境兼容 | 在 `pyproject.toml` 明确声明 `requires-python = ">=3.11"` |

---

## 12. 不在范围内

- 任何与"创作/缝合"相关的逻辑（属于 `/webnovel-init` 的事）
- 任何对 `deconstruction-agent` 的修改（除非 v0.3 联动）
- 任何对 webnovel-writer 上游插件的 PR
- 计费/会员章节正文（合规底线）
- 5 平台以外的其他平台（飞卢、SFACG、ESJZone → v0.3+）
- 自动监控 / 趋势曲线 / 定时任务（→ v0.3+）

---

## 附录 A：参考

- 现有 webnovel-fast-write skill：`/Users/chang/Desktop/zhanghui/.claude/skills/webnovel-fast-write/SKILL.md`
- 现有 webnovel-writer 插件：`/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer/`
- 现有 deconstruction-agent：`/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer/agents/deconstruction-agent.md`
- 设计规范（参考前例）：`/Users/chang/Desktop/zhanghui/docs/superpowers/specs/2026-08-08-webnovel-writer-fork-design.md`
- 实施计划（参考前例）：`/Users/chang/Desktop/zhanghui/docs/superpowers/plans/2026-08-08-webnovel-writer-fork-impl.md`

## 附录 B：上游项目链接

- 起点：`https://github.com/saudadez21/novel-downloader`、`https://github.com/xuduogui/QiDianAPI`（DEAD，仅参考 URL）、`https://github.com/howie6879/owllook`
- 番茄：`https://github.com/Despacito0o/FanqieRankTracker`、`https://github.com/mhkz/fanqie-novels-skills`（仅参考分类知识库）
- 纵横：平台公开 API（`https://www.zongheng.com/api/rank/details?rankType={N}&pageSize={size}&pageNum={P}`）
- 七猫：`https://github.com/staysharp1104/WebCrawler`
- 刺猬猫：`https://github.com/saudadez21/novel-downloader`（刺猬猫插件已失效，仅作 fallback 起点）
- 架构模板：`https://github.com/NanmiCoder/NewsCrawler`