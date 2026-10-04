# `/webnovel-chart-scan` 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 Claude Code skill，一键扫描起点/番茄/纵横/七猫/刺猬猫 五个网文平台的分类榜单，提取明面元数据（书名/作者/分类/简介/字数/状态/标签/封面/排名位置），归一化输出 JSON + Markdown 报告到调用时所在项目目录。

**Architecture:** 胖客户端 + 统一 adapter 抽象。每个平台一个 `adapters/{platform}.py`，声明自己的 Strategy（VENDOR / DIRECT_API / WEBFETCH），主控 `scan.py` 解析 CLI、路由、归一化、渲染报告。失败降级四级链：首选 strategy → 下一级 strategy → WebFetch + BS4 → 报错不崩主流程。

**Tech Stack:** Python 3.11+（pydantic + httpx + beautifulsoup4 + pytest）、vendored 上游代码（部分平台）、Playwright（仅番茄 adapter 冷启动）。

**Spec:** `docs/superpowers/specs/2026-08-12-webnovel-chart-scan-design.md`

---

## 文件总览

### 新建文件
```
.claude/skills/webnovel-chart-scan/
├── SKILL.md                                ← Phase 5 Task 13
├── pyproject.toml                          ← Phase 1 Task 1
├── README.md                               ← Phase 5 Task 13
├── scripts/
│   ├── scan.py                             ← Phase 4 Task 12
│   ├── schema.py                           ← Phase 1 Task 2
│   ├── normalize.py                        ← Phase 1 Task 3
│   ├── output.py                           ← Phase 4 Task 10
│   ├── report.py                           ← Phase 4 Task 11
│   └── adapters/
│       ├── __init__.py
│       ├── base.py                         ← Phase 1 Task 4
│       ├── zongheng.py                     ← Phase 2 Task 5（DIRECT_API）
│       ├── ciweimao.py                     ← Phase 2 Task 6（WEBFETCH）
│       ├── qidian.py                       ← Phase 3 Task 7（VENDOR）
│       ├── fanqie.py                       ← Phase 3 Task 8（VENDOR）
│       └── qimao.py                        ← Phase 3 Task 9（VENDOR）
├── vendor/                                 ← Phase 3 各 vendor task 创建
│   ├── novel-downloader/                    ← Task 7 起点
│   ├── fanqie-rank-tracker/                ← Task 8 番茄
│   └── qimao-web-crawler/                  ← Task 9 七猫
├── references/
│   ├── upstream-survey.md                  ← Phase 5 Task 14
│   ├── category-mapping.md                 ← Phase 5 Task 15
│   └── adapter-strategies.md               ← Phase 5 Task 15
└── tests/
    ├── __init__.py
    ├── conftest.py                         ← Phase 1 Task 1
    ├── test_schema.py                      ← Task 2
    ├── test_normalize.py                   ← Task 3
    ├── test_base.py                        ← Task 4
    ├── test_zongheng_adapter.py            ← Task 5
    ├── test_ciweimao_adapter.py            ← Task 6
    ├── test_qidian_adapter.py              ← Task 7
    ├── test_fanqie_adapter.py              ← Task 8
    ├── test_qimao_adapter.py               ← Task 9
    ├── test_output.py                      ← Task 10
    ├── test_report.py                      ← Task 11
    └── test_scan_integration.py            ← Task 12
```

### 不修改任何现有文件

本 skill 完全独立，无外部依赖修改。

---

## 工作约定

- **工作目录**：`${ROOT}` = `/Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/`
- **Python**：3.11+（pyproject.toml 强制声明）
- **测试**：pytest，在 `${ROOT}` 下执行 `pytest tests/ -v`
- **提交**：每完成一个 task 一次 commit；commit message 用 `<type>: <subject>` 前缀（`feat:` / `test:` / `docs:` / `chore:`）

---

## Phase 1：基础骨架（4 个 task，~30 min）

### Task 1: 项目骨架 + pyproject.toml + conftest.py

**Files:**
- Create: `${ROOT}/pyproject.toml`
- Create: `${ROOT}/scripts/__init__.py`
- Create: `${ROOT}/scripts/adapters/__init__.py`
- Create: `${ROOT}/tests/__init__.py`
- Create: `${ROOT}/tests/conftest.py`

- [ ] **Step 1: 创建目录骨架**

```bash
mkdir -p /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/{scripts/adapters,tests,references,vendor}
```

- [ ] **Step 2: 写 pyproject.toml**

```toml
# /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/pyproject.toml
[project]
name = "webnovel-chart-scan"
version = "0.1.0"
description = "扫 5 个网文平台分类榜单的 Claude Code skill"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "pydantic>=2.6",
    "lxml>=5.0",
]

[project.optional-dependencies]
fanqie = ["playwright>=1.41"]
dev = ["pytest>=7.4", "pytest-cov>=4.1"]

[project.scripts]
chart-scan = "scripts.scan:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["scripts*"]
```

- [ ] **Step 3: 写空 __init__.py 和 conftest.py**

```python
# ${ROOT}/scripts/__init__.py
# (empty)
```
```python
# ${ROOT}/scripts/adapters/__init__.py
# (empty)
```
```python
# ${ROOT}/tests/__init__.py
# (empty)
```
```python
# ${ROOT}/tests/conftest.py
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pytest

@pytest.fixture
def fixtures_dir() -> Path:
    return ROOT / "tests" / "fixtures"
```

- [ ] **Step 4: 验证骨架可导入**

```bash
cd /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan
python -c "import scripts; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/webnovel-chart-scan/
git commit -m "chore: project skeleton for webnovel-chart-scan"
```

---

### Task 2: schema.py + tests（BookItem / RawBook / AdapterError / ScanMeta / ScanResult）

**Files:**
- Create: `${ROOT}/scripts/schema.py`
- Create: `${ROOT}/tests/test_schema.py`

- [ ] **Step 1: 写失败的测试**

```python
# ${ROOT}/tests/test_schema.py
from datetime import datetime, timezone
from scripts.schema import BookItem, RawBook, AdapterError, ScanMeta, ScanResult

def test_bookitem_minimal_required_fields():
    b = BookItem(
        id="qidian-12345",
        platform="qidian",
        title="凡人修仙传",
        author="忘语",
        category="仙侠",
        category_normalized="仙侠",
        period="weekly",
        fetched_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    assert b.id == "qidian-12345"
    assert b.tags == []
    assert b.intro == ""
    assert b.word_count is None
    assert b.status is None

def test_bookitem_full_fields():
    b = BookItem(
        id="fanqie-67890",
        platform="fanqie",
        title="xxx",
        author="yyy",
        category="都市",
        category_normalized="都市",
        tags=["系统流", "穿越"],
        intro="简介内容",
        word_count=1500000,
        status="serial",
        cover_url="https://example.com/cover.jpg",
        detail_url="https://fanqie.com/book/67890",
        rank_position=1,
        period="monthly",
        fetched_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    assert b.word_count == 1500000
    assert b.rank_position == 1

def test_bookitem_rejects_invalid_platform():
    import pytest
    with pytest.raises(ValueError):
        BookItem(
            id="x-1", platform="unknown", title="t", author="a",
            category="c", category_normalized="c", period="weekly",
            fetched_at=datetime.now(timezone.utc),
        )

def test_rawbook_required_fields():
    r = RawBook(platform_book_id="123", title="t", author="a", category="玄幻")
    assert r.tags == []
    assert r.raw_payload == {}

def test_adapter_error_required_fields():
    e = AdapterError(
        platform="qidian", category="玄幻", period="weekly",
        stage="vendor", message="connection refused",
        occurred_at=datetime.now(timezone.utc),
    )
    assert e.stage == "vendor"

def test_scan_meta_aggregates():
    m = ScanMeta(
        platforms=["qidian", "fanqie"],
        categories=["玄幻", "都市"],
        periods=["weekly"],
        top=50,
        scanned_at=datetime.now(timezone.utc),
        duration_seconds=120.5,
        total_books=200,
        total_errors=3,
    )
    assert m.total_books == 200

def test_scan_result_holds_books_and_errors():
    r = ScanResult(
        meta=ScanMeta(
            platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
            top=10, scanned_at=datetime.now(timezone.utc),
            duration_seconds=10.0, total_books=10, total_errors=0,
        ),
        books=[],
        errors=[],
    )
    assert r.errors == []
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan
pytest tests/test_schema.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.schema'`

- [ ] **Step 3: 实现 schema.py**

```python
# ${ROOT}/scripts/schema.py
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

PLATFORMS = Literal["qidian", "fanqie", "zongheng", "qimao", "ciweimao"]
PERIODS = Literal["daily", "weekly", "monthly"]
STATUSES = Literal["serial", "completed"]
ERROR_STAGES = Literal["vendor", "direct_api", "webfetch", "normalize"]


class RawBook(BaseModel):
    """平台原始数据，由各 adapter 的 fetch() 返回。"""
    platform_book_id: str
    title: str
    author: str
    category: str
    tags: list[str] = Field(default_factory=list)
    intro: str = ""
    word_count: Optional[int] = None
    status: Optional[STATUSES] = None
    cover_url: Optional[str] = None
    detail_url: Optional[str] = None
    rank_position: Optional[int] = None
    raw_payload: dict = Field(default_factory=dict)


class BookItem(BaseModel):
    """归一化后的书籍元数据。"""
    id: str
    platform: PLATFORMS
    title: str
    author: str
    category: str
    category_normalized: str
    tags: list[str] = Field(default_factory=list)
    intro: str = ""
    word_count: Optional[int] = None
    status: Optional[STATUSES] = None
    cover_url: Optional[str] = None
    detail_url: Optional[str] = None
    rank_position: Optional[int] = None
    period: PERIODS
    fetched_at: datetime


class AdapterError(BaseModel):
    platform: str
    category: str
    period: str
    stage: ERROR_STAGES
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
    errors: list[AdapterError] = Field(default_factory=list)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_schema.py -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/schema.py tests/test_schema.py
git commit -m "feat: schema.py with BookItem/RawBook/AdapterError/ScanMeta/ScanResult"
```

---

### Task 3: normalize.py + tests

**Files:**
- Create: `${ROOT}/scripts/normalize.py`
- Create: `${ROOT}/tests/test_normalize.py`

- [ ] **Step 1: 写失败的测试**

```python
# ${ROOT}/tests/test_normalize.py
from datetime import datetime, timezone
from scripts.schema import RawBook
from scripts.normalize import raw_to_bookitem, normalize_category, build_book_id

def test_build_book_id_format():
    assert build_book_id("qidian", "12345") == "qidian-12345"
    assert build_book_id("fanqie", "abc") == "fanqie-abc"

def test_normalize_category_qidian_xuanhuan():
    assert normalize_category("qidian", "玄幻") == "玄幻"
    assert normalize_category("qidian", "东方玄幻") == "玄幻"

def test_normalize_category_unknown_platform_passthrough():
    assert normalize_category("ciweimao", "奇幻") == "奇幻"  # 不强行映射

def test_raw_to_bookitem_basic():
    raw = RawBook(
        platform_book_id="12345",
        title="凡人修仙传",
        author="忘语",
        category="仙侠",
        tags=["修真", "凡人"],
        intro="一个普通凡人...",
        word_count=3500000,
        status="completed",
        cover_url="https://example.com/c.jpg",
        detail_url="https://book.qidian.com/info/12345",
        rank_position=1,
    )
    book = raw_to_bookitem(raw, platform="qidian", period="weekly")
    assert book.id == "qidian-12345"
    assert book.platform == "qidian"
    assert book.category == "仙侠"
    assert book.category_normalized == "仙侠"
    assert book.tags == ["修真", "凡人"]
    assert book.word_count == 3500000
    assert book.status == "completed"
    assert book.rank_position == 1
    assert book.period == "weekly"
    assert isinstance(book.fetched_at, datetime)

def test_raw_to_bookitem_truncates_long_intro():
    raw = RawBook(
        platform_book_id="x", title="t", author="a", category="c",
        intro="x" * 1000,
    )
    book = raw_to_bookitem(raw, platform="fanqie", period="daily")
    assert len(book.intro) == 500

def test_raw_to_bookitem_handles_missing_optional():
    raw = RawBook(platform_book_id="1", title="t", author="a", category="玄幻")
    book = raw_to_bookitem(raw, platform="qidian", period="monthly")
    assert book.word_count is None
    assert book.tags == []
    assert book.intro == ""
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_normalize.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.normalize'`

- [ ] **Step 3: 实现 normalize.py**

```python
# ${ROOT}/scripts/normalize.py
from datetime import datetime, timezone
from scripts.schema import RawBook, BookItem

INTRO_MAX_LEN = 500

# 起点分类映射：子分类 -> 主分类
_QIDIAN_SUBCATEGORY_MAP = {
    "东方玄幻": "玄幻", "异世大陆": "玄幻", "高武": "玄幻",
    "都市生活": "都市", "职场": "都市", "现实题材": "现实",
    "古典仙侠": "仙侠", "修真文明": "仙侠", "现代修真": "仙侠",
}

# 番茄分类映射
_FANQIE_SUBCATEGORY_MAP = {
    "男频-玄幻": "玄幻", "女频-古言": "古言",
    "男频-都市": "都市", "女频-现言": "现言",
}


def build_book_id(platform: str, platform_book_id: str) -> str:
    return f"{platform}-{platform_book_id}"


def normalize_category(platform: str, category: str) -> str:
    """把平台原始分类归一化到统一分类。"""
    if platform == "qidian":
        return _QIDIAN_SUBCATEGORY_MAP.get(category, category)
    if platform == "fanqie":
        return _FANQIE_SUBCATEGORY_MAP.get(category, category)
    # zongheng/qimao/ciweimao 暂不强制映射，原样返回
    return category


def raw_to_bookitem(raw: RawBook, platform: str, period: str) -> BookItem:
    intro = raw.intro[:INTRO_MAX_LEN] if raw.intro else ""
    return BookItem(
        id=build_book_id(platform, raw.platform_book_id),
        platform=platform,  # type: ignore[arg-type]
        title=raw.title,
        author=raw.author,
        category=raw.category,
        category_normalized=normalize_category(platform, raw.category),
        tags=list(raw.tags),
        intro=intro,
        word_count=raw.word_count,
        status=raw.status,
        cover_url=raw.cover_url,
        detail_url=raw.detail_url,
        rank_position=raw.rank_position,
        period=period,  # type: ignore[arg-type]
        fetched_at=datetime.now(timezone.utc),
    )
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_normalize.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/normalize.py tests/test_normalize.py
git commit -m "feat: normalize.py with raw_to_bookitem + category mapping"
```

---

### Task 4: base.py + tests（Adapter 抽象 + Strategy 枚举）

**Files:**
- Create: `${ROOT}/scripts/adapters/base.py`
- Create: `${ROOT}/tests/test_base.py`

- [ ] **Step 1: 写失败的测试**

```python
# ${ROOT}/tests/test_base.py
import pytest
from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook


class FakeAdapter(BaseAdapter):
    platform = "fake"
    strategy = Strategy.DIRECT_API

    def fetch(self, category, period, top):
        return [
            RawBook(platform_book_id=str(i), title=f"book-{i}", author="a", category=category)
            for i in range(top)
        ]


def test_strategy_enum_values():
    assert Strategy.VENDOR.value == "vendor"
    assert Strategy.DIRECT_API.value == "direct_api"
    assert Strategy.WEBFETCH.value == "webfetch"


def test_adapter_subclass_must_implement_fetch():
    class IncompleteAdapter(BaseAdapter):
        platform = "x"
        strategy = Strategy.WEBFETCH

    with pytest.raises(TypeError):
        IncompleteAdapter()  # 不能实例化抽象类


def test_adapter_fetch_returns_list_of_rawbook():
    a = FakeAdapter()
    result = a.fetch("玄幻", "weekly", 3)
    assert len(result) == 3
    assert all(isinstance(r, RawBook) for r in result)
    assert all(r.category == "玄幻" for r in result)


def test_adapter_normalize_defaults_to_module_function(monkeypatch):
    """默认 normalize 应该调用 scripts.normalize.raw_to_bookitem"""
    from scripts import normalize
    called = []
    original = normalize.raw_to_bookitem

    def spy(raw, platform, period):
        called.append((platform, period))
        return original(raw, platform, period)

    monkeypatch.setattr(normalize, "raw_to_bookitem", spy)

    a = FakeAdapter()
    raw = RawBook(platform_book_id="1", title="t", author="a", category="玄幻")
    a.normalize(raw, period="weekly")

    assert called == [("fake", "weekly")]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_base.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.adapters.base'`

- [ ] **Step 3: 实现 base.py**

```python
# ${ROOT}/scripts/adapters/base.py
from abc import ABC, abstractmethod
from enum import Enum

from scripts.schema import RawBook, BookItem
from scripts.normalize import raw_to_bookitem


class Strategy(str, Enum):
    VENDOR = "vendor"
    DIRECT_API = "direct_api"
    WEBFETCH = "webfetch"


class BaseAdapter(ABC):
    """所有平台 adapter 必须继承。"""
    platform: str = ""
    strategy: Strategy = Strategy.WEBFETCH

    @abstractmethod
    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        """按平台策略抓取榜单，返回平台原始数据。"""

    def normalize(self, raw: RawBook, period: str) -> BookItem:
        """默认调用 normalize.raw_to_bookitem；adapter 可重写。"""
        return raw_to_bookitem(raw, platform=self.platform, period=period)
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_base.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/adapters/base.py tests/test_base.py
git commit -m "feat: adapter BaseAdapter ABC with Strategy enum"
```

---

## Phase 2：简单 adapter（2 个 task，~45 min）

### Task 5: zongheng adapter（DIRECT_API）

**Files:**
- Create: `${ROOT}/scripts/adapters/zongheng.py`
- Create: `${ROOT}/tests/fixtures/zongheng_rank_details.json`
- Create: `${ROOT}/tests/test_zongheng_adapter.py`

- [ ] **Step 1: 抓真实样本存 fixture**

```bash
mkdir -p /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/tests/fixtures
curl -s -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
  "https://www.zongheng.com/api/rank/details?rankType=4&pageSize=10&pageNum=1" \
  -o /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/tests/fixtures/zongheng_rank_details.json
head -50 /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/tests/fixtures/zongheng_rank_details.json
```

Expected: JSON 输出含 `data.bookList` 数组，每项有 `bookName / authorName / cateFineName / orderNo` 等字段。**记录真实字段名**——后续代码用真实字段名。

如果该 endpoint 当前返回非 200 或结构变了，记录错误日志后跳到 Step 6（用合成 fixture）。

- [ ] **Step 2: 写失败的测试（基于真实 fixture 字段）**

```python
# ${ROOT}/tests/test_zongheng_adapter.py
import json
from pathlib import Path
import httpx

from scripts.adapters.zongheng import ZonghengAdapter, parse_rank_response


def test_parse_rank_response_extracts_basic_fields():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "zongheng_rank_details.json").read_text()
    )
    books = parse_rank_response(fixture, top=5)
    assert len(books) == 5
    assert all(b.platform_book_id for b in books)
    assert all(b.title for b in books)
    assert all(b.author for b in books)
    assert all(b.rank_position is not None for b in books)


def test_zongheng_adapter_metadata():
    a = ZonghengAdapter()
    assert a.platform == "zongheng"
    assert a.strategy.value == "direct_api"


def test_zongheng_adapter_fetch_uses_httpx(monkeypatch):
    """mock httpx.get，验证 URL 和 headers 正确。"""
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        captured["params"] = kwargs.get("params", {})

        class Resp:
            def __init__(self):
                self.status_code = 200

            def json(self):
                return {"data": {"bookList": []}}

            def raise_for_status(self):
                pass

        return Resp()

    monkeypatch.setattr(httpx, "get", fake_get)
    a = ZonghengAdapter()
    a.fetch("玄幻", "weekly", 10)

    assert "zongheng.com" in captured["url"]
    assert captured["headers"].get("User-Agent", "").startswith("Mozilla")
    assert captured["params"].get("pageSize") == 10
```

- [ ] **Step 3: 跑测试确认失败**

```bash
pytest tests/test_zongheng_adapter.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.adapters.zongheng'`

- [ ] **Step 4: 实现 zongheng adapter（用真实 API 字段名）**

> **重要**：字段名以 Step 1 抓到的真实响应为准。下方是**示例字段**，按实际抓到的调整：

```python
# ${ROOT}/scripts/adapters/zongheng.py
import httpx
from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook

ZONGHENG_API = "https://www.zongheng.com/api/rank/details"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# rankType: 2=热销 4=新书 9=推荐
RANK_TYPE_MAP = {"monthly": 2, "daily": 4, "weekly": 9}


def parse_rank_response(payload: dict, top: int) -> list[RawBook]:
    """把 zongheng API 的 JSON 响应解析为 RawBook 列表。"""
    book_list = payload.get("data", {}).get("bookList", [])
    books = []
    for i, item in enumerate(book_list[:top]):
        # 字段名以真实 API 为准（Step 1 抓到为准）
        books.append(RawBook(
            platform_book_id=str(item.get("bookId", "")),
            title=item.get("bookName", ""),
            author=item.get("authorName", ""),
            category=item.get("cateFineName", ""),
            rank_position=item.get("orderNo", i + 1),
            raw_payload=item,
        ))
    return books


class ZonghengAdapter(BaseAdapter):
    platform = "zongheng"
    strategy = Strategy.DIRECT_API

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        rank_type = RANK_TYPE_MAP.get(period, 4)
        url = ZONGHENG_API
        headers = {"User-Agent": USER_AGENT, "Referer": "https://www.zongheng.com/"}
        params = {"rankType": rank_type, "pageSize": min(top, 100), "pageNum": 1}

        # 暂不处理 category 过滤（公开 API 不直接支持 category 参数）
        # category 参数留作 v0.2 增强
        resp = httpx.get(url, headers=headers, params=params, timeout=30.0)
        resp.raise_for_status()
        return parse_rank_response(resp.json(), top=top)
```

- [ ] **Step 5: 跑测试确认通过**

```bash
pytest tests/test_zongheng_adapter.py -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/adapters/zongheng.py tests/test_zongheng_adapter.py tests/fixtures/zongheng_rank_details.json
git commit -m "feat: zongheng adapter (DIRECT_API via httpx)"
```

---

### Task 6: ciweimao adapter（WEBFETCH）

**Files:**
- Create: `${ROOT}/scripts/adapters/ciweimao.py`
- Create: `${ROOT}/tests/fixtures/ciweimao_category_xuanhuan.html`
- Create: `${ROOT}/tests/test_ciweimao_adapter.py`

- [ ] **Step 1: 抓真实样本存 fixture**

```bash
curl -s -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
  "https://www.ciweimao.com/category/%E5%B7%A8%E9%AD%94%E5%B0%91%E5%A5%B3%E7%9A%84%E5%8F%B2%E5%8F%99%E4%BA%8B" \
  -o /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/tests/fixtures/ciweimao_category_xuanhuan.html
wc -l /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/tests/fixtures/ciweimao_category_xuanhuan.html
```

Expected: HTML 文件，几十到几百行。如果失败（非 200），记录错误，跳到 Step 6 用合成 fixture。

- [ ] **Step 2: 写失败的测试**

```python
# ${ROOT}/tests/test_ciweimao_adapter.py
from pathlib import Path
from scripts.adapters.ciweimao import CiweimaoAdapter, parse_category_html


def test_parse_category_html_extracts_basic_fields():
    html = (Path(__file__).parent / "fixtures" / "ciweimao_category_xuanhuan.html").read_text()
    books = parse_category_html(html, top=10)
    assert all(b.platform_book_id for b in books)
    assert all(b.title for b in books)
    assert all(b.author for b in books)


def test_ciweimao_adapter_metadata():
    a = CiweimaoAdapter()
    assert a.platform == "ciweimao"
    assert a.strategy.value == "webfetch"


def test_ciweimao_fetch_calls_correct_url():
    """只验证 URL 构造逻辑（不真发请求）。"""
    from scripts.adapters import ciweimao as mod
    captured = []

    def fake_fetch(url, **kwargs):
        captured.append(url)
        return _FakeResp("")

    mod.httpx.get = fake_fetch
    a = CiweimaoAdapter()
    a.fetch("玄幻", "weekly", 5)
    assert any("ciweimao.com" in u for u in captured)


class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        pass
```

- [ ] **Step 3: 跑测试确认失败**

```bash
pytest tests/test_ciweimao_adapter.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.adapters.ciweimao'`

- [ ] **Step 4: 实现 ciweimao adapter（字段以 Step 1 真实 HTML 为准）**

```python
# ${ROOT}/scripts/adapters/ciweimao.py
import httpx
from bs4 import BeautifulSoup

from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook

CIWEIMAO_BASE = "https://www.ciweimao.com"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def parse_category_html(html: str, top: int) -> list[RawBook]:
    """解析刺猬猫分类榜 HTML。字段以真实页面为准。"""
    soup = BeautifulSoup(html, "lxml")
    books = []

    # 占位选择器：以真实页面结构为准
    # 常见模式：每本书一个 .book-item 或 .rank-item 容器
    for i, item in enumerate(soup.select(".book-item, .rank-item, .novel-item")[:top]):
        title_el = item.select_one(".title, .book-title, h3 a")
        author_el = item.select_one(".author, .book-author")
        link_el = item.select_one("a[href*='/book/']")
        book_id = ""
        if link_el and link_el.get("href"):
            # 从 URL 抽取 bookId
            href = link_el["href"]
            if "/book/" in href:
                book_id = href.split("/book/")[-1].split("/")[0].split(".")[0]

        if not title_el:
            continue

        books.append(RawBook(
            platform_book_id=book_id,
            title=title_el.get_text(strip=True),
            author=author_el.get_text(strip=True) if author_el else "",
            category="",  # 详情页才有
            detail_url=CIWEIMAO_BASE + link_el["href"] if link_el and link_el.get("href") else None,
            rank_position=i + 1,
            raw_payload={"html_snippet": str(item)[:500]},
        ))
    return books


class CiweimaoAdapter(BaseAdapter):
    platform = "ciweimao"
    strategy = Strategy.WEBFETCH

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        # 刺猬猫分类页 URL 模板（按 category 编码）
        # 暂走"全部分类"路径，等 Step 1 抓到的真实 URL 调整
        url = f"{CIWEIMAO_BASE}/rank/"
        headers = {"User-Agent": USER_AGENT, "Referer": CIWEIMAO_BASE}

        resp = httpx.get(url, headers=headers, timeout=30.0)
        resp.raise_for_status()
        return parse_category_html(resp.text, top=top)
```

- [ ] **Step 5: 跑测试确认通过**

```bash
pytest tests/test_ciweimao_adapter.py -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/adapters/ciweimao.py tests/test_ciweimao_adapter.py tests/fixtures/ciweimao_category_xuanhuan.html
git commit -m "feat: ciweimao adapter (WEBFETCH + BeautifulSoup)"
```

---

## Phase 3：Vendor adapter（3 个 task，~75 min）

> 这些 task 涉及 vendoring 上游代码。模式相同：clone → 摘出需要的模块 → 写薄壳 wrapper → 用 fixture 测试。

### Task 7: qidian adapter（VENDOR parser）

**Files:**
- Create: `${ROOT}/vendor/novel-downloader/`（git clone 自 saudadez21/novel-downloader）
- Create: `${ROOT}/scripts/adapters/qidian.py`
- Create: `${ROOT}/tests/test_qidian_adapter.py`

- [ ] **Step 1: clone 上游**

```bash
cd /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/vendor
git clone --depth 1 https://github.com/saudadez21/novel-downloader.git
ls novel-downloader/
```

Expected: 看到 `novel_downloader/` 或 `src/`、`qidian/`、`requirements.txt` 等。**记录真实目录结构**。

- [ ] **Step 2: 摘出起点模块**

```bash
# 把起点相关目录/文件复制到 vendor 根（避免 import 整库）
# 具体路径按 Step 1 看到的真实结构
# 示例（按需调整）：
cp -r novel-downloader/src/novel_downloader/sources/qidian ./novel-downloader/qidian_subset
ls novel-downloader/qidian_subset/
```

Expected: 看到 `parser.py` 或类似文件。**记录实际文件名**。

- [ ] **Step 3: 写失败的测试**

```python
# ${ROOT}/tests/test_qidian_adapter.py
from scripts.adapters.qidian import QidianAdapter, parse_qidian_list_json

# 起点公开榜 JSON 片段示例（真实抓取后再调整）
SAMPLE_QIDIAN_LIST = {
    "code": 0,
    "data": {
        "books": [
            {
                "bookId": "12345",
                "bookName": "凡人修仙传",
                "authorName": "忘语",
                "categoryName": "仙侠",
                "coverUrl": "https://example.com/c.jpg",
            }
        ]
    }
}


def test_parse_qidian_list_json_extracts_fields():
    books = parse_qidian_list_json(SAMPLE_QIDIAN_LIST, top=10)
    assert len(books) == 1
    assert books[0].title == "凡人修仙传"
    assert books[0].author == "忘语"
    assert books[0].category == "仙侠"


def test_qidian_adapter_metadata():
    a = QidianAdapter()
    assert a.platform == "qidian"
    assert a.strategy.value == "vendor"
```

- [ ] **Step 4: 跑测试确认失败**

```bash
pytest tests/test_qidian_adapter.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.adapters.qidian'`

- [ ] **Step 5: 实现 qidian adapter**

```python
# ${ROOT}/scripts/adapters/qidian.py
import httpx
from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook

QIDIAN_LIST_API = "https://www.qidian.com/all"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 起点分类 ID（来自 owllook/qidian_ranking.py）
QIDIAN_CATEGORY_IDS = {
    "玄幻": 21, "奇幻": 1, "武侠": 2, "仙侠": 22,
    "都市": 4, "职场": 15, "军事": 6, "历史": 5,
    "游戏": 7, "体育": 8, "科幻": 9, "灵异": 10, "二次元": 12,
}


def parse_qidian_list_json(payload: dict, top: int) -> list[RawBook]:
    """解析起点分类页 JSON 响应。字段以真实响应为准。"""
    # 占位解析逻辑 - 按 Step 1-2 看到的真实结构调整
    books_data = payload.get("data", {}).get("books", [])
    books = []
    for i, item in enumerate(books_data[:top]):
        books.append(RawBook(
            platform_book_id=str(item.get("bookId", "")),
            title=item.get("bookName", ""),
            author=item.get("authorName", ""),
            category=item.get("categoryName", ""),
            cover_url=item.get("coverUrl"),
            rank_position=i + 1,
            raw_payload=item,
        ))
    return books


class QidianAdapter(BaseAdapter):
    platform = "qidian"
    strategy = Strategy.VENDOR

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        chan_id = QIDIAN_CATEGORY_IDS.get(category, -1)  # -1 = 全部
        url = QIDIAN_LIST_API
        headers = {"User-Agent": USER_AGENT, "Referer": "https://www.qidian.com/"}
        params = {
            "chanId": chan_id,
            "subCateId": -1,
            "pageSize": min(top, 100),
            "page": 1,
        }

        resp = httpx.get(url, headers=headers, params=params, timeout=30.0)
        resp.raise_for_status()
        return parse_qidian_list_json(resp.json(), top=top)
```

- [ ] **Step 6: 跑测试确认通过**

```bash
pytest tests/test_qidian_adapter.py -v
```

Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add scripts/adapters/qidian.py tests/test_qidian_adapter.py vendor/novel-downloader/
git commit -m "feat: qidian adapter (VENDOR + parse_qidian_list_json)"
```

---

### Task 8: fanqie adapter（VENDOR fork）

**Files:**
- Create: `${ROOT}/vendor/fanqie-rank-tracker/`（git clone）
- Create: `${ROOT}/scripts/adapters/fanqie.py`
- Create: `${ROOT}/tests/test_fanqie_adapter.py`

- [ ] **Step 1: clone 上游**

```bash
cd /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/vendor
git clone --depth 1 https://github.com/Despacito0o/FanqieRankTracker.git
ls FanqieRankTracker/
```

Expected: 看到 `scrape_fanqie_ranks.py`、`requirements.txt`、`README.md` 等。**记录实际文件**。

- [ ] **Step 2: 确认 Playwright 是必需依赖**

```bash
cat FanqieRankTracker/requirements.txt
```

Expected: 含 `playwright`。**这是 MVP 唯一需要 Playwright 的 adapter**。

- [ ] **Step 3: 写失败的测试**

```python
# ${ROOT}/tests/test_fanqie_adapter.py
from scripts.adapters.fanqie import FanqieAdapter, parse_fanqie_rank_list


SAMPLE_FANQIE_RANK = [
    {"bookName": "xxx", "author": "yyy", "intro": "...", "category": "玄幻",
     "bookId": "abc", "rank": 1, "cover": "https://..."},
]


def test_parse_fanqie_rank_list():
    books = parse_fanqie_rank_list(SAMPLE_FANQIE_RANK, top=10)
    assert len(books) == 1
    assert books[0].title == "xxx"
    assert books[0].author == "yyy"


def test_fanqie_adapter_metadata():
    a = FanqieAdapter()
    assert a.platform == "fanqie"
    assert a.strategy.value == "vendor"
```

- [ ] **Step 4: 跑测试确认失败**

```bash
pytest tests/test_fanqie_adapter.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.adapters.fanqie'`

- [ ] **Step 5: 实现 fanqie adapter（包装上游代码）**

```python
# ${ROOT}/scripts/adapters/fanqie.py
"""番茄 adapter。

包装 vendored FanqieRankTracker 的核心抓取函数。
需要 Playwright（首次冷启动 Chromium）。
"""
from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook


def parse_fanqie_rank_list(raw_list: list[dict], top: int) -> list[RawBook]:
    """把 FanqieRankTracker 的内部数据结构转为 RawBook。"""
    books = []
    for i, item in enumerate(raw_list[:top]):
        books.append(RawBook(
            platform_book_id=str(item.get("bookId", "")),
            title=item.get("bookName", ""),
            author=item.get("author", ""),
            category=item.get("category", ""),
            intro=item.get("intro", ""),
            cover_url=item.get("cover"),
            rank_position=item.get("rank", i + 1),
            raw_payload=item,
        ))
    return books


class FanqieAdapter(BaseAdapter):
    platform = "fanqie"
    strategy = Strategy.VENDOR

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        # 懒导入：避免未装 Playwright 时 import 报错
        try:
            from vendor.fanqie_rank_tracker.scrape_fanqie_ranks import (
                scrape_fanqie_ranks,
            )
        except ImportError as e:
            raise RuntimeError(
                "fanqie adapter requires Playwright. Install: pip install playwright && playwright install chromium"
            ) from e

        raw = scrape_fanqie_ranks(category=category, top=top)
        return parse_fanqie_rank_list(raw, top=top)
```

**注**：实际 import 路径以 Step 1 看到的真实目录结构为准。如果上游是单文件 `scrape_fanqie_ranks.py`，需要写 `vendor/fanqie_rank_tracker/__init__.py` 让它可被 import。

- [ ] **Step 6: 跑测试确认通过**

```bash
pytest tests/test_fanqie_adapter.py -v
```

Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add scripts/adapters/fanqie.py tests/test_fanqie_adapter.py vendor/fanqie-rank-tracker/
git commit -m "feat: fanqie adapter (VENDOR + parse_fanqie_rank_list)"
```

---

### Task 9: qimao adapter（VENDOR clone）

**Files:**
- Create: `${ROOT}/vendor/qimao-web-crawler/`（git clone）
- Create: `${ROOT}/scripts/adapters/qimao.py`
- Create: `${ROOT}/tests/test_qimao_adapter.py`

- [ ] **Step 1: clone 上游**

```bash
cd /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/vendor
git clone --depth 1 https://github.com/staysharp1104/WebCrawler.git qimao-web-crawler
ls qimao-web-crawler/
```

Expected: 看到 Python 源码文件。**记录实际目录**。

- [ ] **Step 2: 摘出七猫模块**

按 Step 1 看到的实际结构，复制七猫相关文件到 `qimao-web-crawler/qimao_subset/`。

- [ ] **Step 3: 写失败的测试**

```python
# ${ROOT}/tests/test_qimao_adapter.py
from scripts.adapters.qimao import QimaoAdapter, parse_qimao_rank


SAMPLE_QIMAO_RANK = [
    {"bookName": "yyy", "authorName": "zzz", "categoryName": "玄幻",
     "bookId": "q123", "rankNo": 1},
]


def test_parse_qimao_rank():
    books = parse_qimao_rank(SAMPLE_QIMAO_RANK, top=10)
    assert len(books) == 1
    assert books[0].title == "yyy"


def test_qimao_adapter_metadata():
    a = QimaoAdapter()
    assert a.platform == "qimao"
    assert a.strategy.value == "vendor"
```

- [ ] **Step 4: 跑测试确认失败**

```bash
pytest tests/test_qimao_adapter.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.adapters.qimao'`

- [ ] **Step 5: 实现 qimao adapter**

```python
# ${ROOT}/scripts/adapters/qimao.py
from scripts.adapters.base import BaseAdapter, Strategy
from scripts.schema import RawBook


def parse_qimao_rank(raw_list: list[dict], top: int) -> list[RawBook]:
    """把七猫榜单元数据转为 RawBook。字段以 vendored 上游实际产出为准。"""
    books = []
    for i, item in enumerate(raw_list[:top]):
        books.append(RawBook(
            platform_book_id=str(item.get("bookId", "")),
            title=item.get("bookName", ""),
            author=item.get("authorName", ""),
            category=item.get("categoryName", ""),
            rank_position=item.get("rankNo", i + 1),
            raw_payload=item,
        ))
    return books


class QimaoAdapter(BaseAdapter):
    platform = "qimao"
    strategy = Strategy.VENDOR

    def fetch(self, category: str, period: str, top: int) -> list[RawBook]:
        # 懒导入：上游可能需要 selenium 或额外依赖
        try:
            from vendor.qimao_web_crawler.qimao_subset import fetch_qimao_rank
        except ImportError as e:
            raise RuntimeError(
                "qimao adapter requires vendored WebCrawler module. Check vendor/qimao-web-crawler/"
            ) from e

        raw = fetch_qimao_rank(category=category, top=top)
        return parse_qimao_rank(raw, top=top)
```

**注**：import 路径以 Step 1-2 实际结构为准。

- [ ] **Step 6: 跑测试确认通过**

```bash
pytest tests/test_qimao_adapter.py -v
```

Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add scripts/adapters/qimao.py tests/test_qimao_adapter.py vendor/qimao-web-crawler/
git commit -m "feat: qimao adapter (VENDOR + parse_qimao_rank)"
```

---

## Phase 4：编排 + 输出 + 报告（3 个 task，~50 min）

### Task 10: output.py + tests

**Files:**
- Create: `${ROOT}/scripts/output.py`
- Create: `${ROOT}/tests/test_output.py`

- [ ] **Step 1: 写失败的测试**

```python
# ${ROOT}/tests/test_output.py
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.schema import ScanResult, ScanMeta, BookItem
from scripts.output import write_scan_result, slug_timestamp


def test_slug_timestamp_format():
    ts = slug_timestamp(datetime(2026, 8, 12, 14, 30, 45, tzinfo=timezone.utc))
    assert ts == "20260812T143045Z"


def test_write_scan_result_creates_files(tmp_path: Path):
    meta = ScanMeta(
        platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
        top=10, scanned_at=datetime.now(timezone.utc),
        duration_seconds=10.0, total_books=1, total_errors=0,
    )
    book = BookItem(
        id="qidian-1", platform="qidian", title="t", author="a",
        category="玄幻", category_normalized="玄幻",
        period="weekly", fetched_at=datetime.now(timezone.utc),
    )
    result = ScanResult(meta=meta, books=[book])

    written = write_scan_result(result, output_dir=tmp_path)

    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "books.json").exists()
    assert len(written) >= 2

    payload = json.loads((tmp_path / "books.json").read_text())
    assert "meta" in payload
    assert "books" in payload
    assert len(payload["books"]) == 1


def test_write_scan_result_creates_log_file(tmp_path: Path):
    meta = ScanMeta(
        platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
        top=10, scanned_at=datetime.now(timezone.utc),
        duration_seconds=10.0, total_books=0, total_errors=0,
    )
    result = ScanResult(meta=meta, books=[])

    write_scan_result(result, output_dir=tmp_path)

    log_files = list(tmp_path.glob("scan_*.log"))
    assert len(log_files) == 1
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_output.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.output'`

- [ ] **Step 3: 实现 output.py**

```python
# ${ROOT}/scripts/output.py
import json
from datetime import datetime
from pathlib import Path

from scripts.schema import ScanResult


def slug_timestamp(dt: datetime) -> str:
    """UTC ISO 时间戳转文件友好字符串。"""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def write_scan_result(result: ScanResult, output_dir: Path) -> list[Path]:
    """把 ScanResult 写到 output_dir，返回写入的文件列表。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    # books.json
    json_path = output_dir / "books.json"
    json_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
    )
    written.append(json_path)

    # report.md（占位 - Task 11 由 report.py 真正生成）
    report_path = output_dir / "report.md"
    from scripts.report import render_report_markdown  # 延迟 import
    report_path.write_text(render_report_markdown(result), encoding="utf-8")
    written.append(report_path)

    # scan_<ts>.log
    log_path = output_dir / f"scan_{slug_timestamp(result.meta.scanned_at)}.log"
    log_path.write_text(
        f"webnovel-chart-scan run at {result.meta.scanned_at.isoformat()}\n"
        f"platforms: {result.meta.platforms}\n"
        f"categories: {result.meta.categories}\n"
        f"periods: {result.meta.periods}\n"
        f"top: {result.meta.top}\n"
        f"total_books: {result.meta.total_books}\n"
        f"total_errors: {result.meta.total_errors}\n",
        encoding="utf-8",
    )
    written.append(log_path)

    return written
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_output.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/output.py tests/test_output.py
git commit -m "feat: output.py with write_scan_result"
```

---

### Task 11: report.py + tests

**Files:**
- Create: `${ROOT}/scripts/report.py`
- Create: `${ROOT}/tests/test_report.py`

- [ ] **Step 1: 写失败的测试**

```python
# ${ROOT}/tests/test_report.py
from datetime import datetime, timezone
from scripts.schema import ScanResult, ScanMeta, BookItem
from scripts.report import render_report_markdown


def _make_book(title, author, category, platform="qidian", word_count=None,
               status=None, rank=None, tags=None):
    return BookItem(
        id=f"{platform}-1", platform=platform, title=title, author=author,
        category=category, category_normalized=category,
        tags=tags or [], word_count=word_count, status=status,
        rank_position=rank, period="weekly",
        fetched_at=datetime.now(timezone.utc),
    )


def test_render_report_includes_overview():
    meta = ScanMeta(
        platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
        top=10, scanned_at=datetime.now(timezone.utc),
        duration_seconds=10.0, total_books=2, total_errors=0,
    )
    books = [
        _make_book("凡人修仙传", "忘语", "仙侠", word_count=3500000, status="completed", rank=1),
        _make_book("xxx", "yyy", "玄幻", word_count=500000, status="serial", rank=2),
    ]
    result = ScanResult(meta=meta, books=books)
    md = render_report_markdown(result)
    assert "# 扫描报告" in md
    assert "凡人修仙传" in md
    assert "总本数" in md


def test_render_report_includes_error_section():
    meta = ScanMeta(
        platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
        top=10, scanned_at=datetime.now(timezone.utc),
        duration_seconds=10.0, total_books=0, total_errors=1,
    )
    from scripts.schema import AdapterError
    err = AdapterError(
        platform="qidian", category="玄幻", period="weekly",
        stage="vendor", message="connection refused",
        occurred_at=datetime.now(timezone.utc),
    )
    result = ScanResult(meta=meta, books=[], errors=[err])
    md = render_report_markdown(result)
    assert "失败" in md or "错误" in md


def test_render_report_includes_table():
    meta = ScanMeta(
        platforms=["qidian"], categories=["玄幻"], periods=["weekly"],
        top=10, scanned_at=datetime.now(timezone.utc),
        duration_seconds=10.0, total_books=1, total_errors=0,
    )
    result = ScanResult(meta=meta, books=[_make_book("t", "a", "玄幻", rank=1)])
    md = render_report_markdown(result)
    assert "| # |" in md or "| 书名 |" in md
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_report.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.report'`

- [ ] **Step 3: 实现 report.py**

```python
# ${ROOT}/scripts/report.py
from collections import Counter
from scripts.schema import ScanResult


def _tag_cloud(tags_flat: list[str]) -> str:
    """生成简单标签云（按出现次数排序的 Markdown 列表）。"""
    if not tags_flat:
        return "_（无标签数据）_"
    counter = Counter(tags_flat)
    lines = [f"- {tag} ({count})" for tag, count in counter.most_common(20)]
    return "\n".join(lines)


def _word_count_buckets(books) -> dict[str, int]:
    buckets = {"<100万": 0, "100-300万": 0, ">300万": 0, "未知": 0}
    for b in books:
        if b.word_count is None:
            buckets["未知"] += 1
        elif b.word_count < 1_000_000:
            buckets["<100万"] += 1
        elif b.word_count < 3_000_000:
            buckets["100-300万"] += 1
        else:
            buckets[">300万"] += 1
    return buckets


def render_report_markdown(result: ScanResult) -> str:
    meta = result.meta
    books = result.books

    lines: list[str] = []
    lines.append(f"# 扫描报告：{', '.join(meta.platforms)} - {', '.join(meta.categories)} - {', '.join(meta.periods)}（TOP {meta.top}）")
    lines.append("")
    lines.append(f"扫描时间：{meta.scanned_at.isoformat()}")
    lines.append(f"耗时：{meta.duration_seconds:.1f}s")
    lines.append("")
    lines.append("## 概览")
    lines.append(f"- 总本数：**{meta.total_books}**")
    lines.append(f"- 失败次数：{meta.total_errors}")
    serial_count = sum(1 for b in books if b.status == "serial")
    completed_count = sum(1 for b in books if b.status == "completed")
    lines.append(f"- 连载中：{serial_count} | 已完结：{completed_count}")
    lines.append("")
    lines.append("### 字数分布")
    for k, v in _word_count_buckets(books).items():
        lines.append(f"- {k}: {v} 本")
    lines.append("")
    lines.append("### 标签云（TOP 20）")
    all_tags = [t for b in books for t in b.tags]
    lines.append(_tag_cloud(all_tags))
    lines.append("")

    if result.errors:
        lines.append("## 失败记录")
        for e in result.errors:
            lines.append(f"- [{e.platform}/{e.period}/{e.category}] {e.stage}: {e.message}")
        lines.append("")

    lines.append("## 完整榜单")
    lines.append("")
    lines.append("| # | 书名 | 作者 | 平台 | 分类 | 字数 | 状态 | 标签 |")
    lines.append("|---|------|------|------|------|------|------|------|")
    for b in sorted(books, key=lambda x: (x.platform, x.rank_position or 9999)):
        wc = f"{b.word_count // 10000}万" if b.word_count else "-"
        status = {"serial": "连载", "completed": "完结"}.get(b.status or "", "-")
        tags = ", ".join(b.tags[:3]) if b.tags else "-"
        lines.append(f"| {b.rank_position or '-'} | {b.title} | {b.author} | {b.platform} | {b.category} | {wc} | {status} | {tags} |")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_report.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/report.py tests/test_report.py
git commit -m "feat: report.py with render_report_markdown"
```

---

### Task 12: scan.py 主控 + adapter 注册 + 集成测试

**Files:**
- Create: `${ROOT}/scripts/scan.py`
- Create: `${ROOT}/tests/test_scan_integration.py`

- [ ] **Step 1: 写失败的测试（集成测试）**

```python
# ${ROOT}/tests/test_scan_integration.py
from datetime import datetime, timezone
from pathlib import Path

from scripts.schema import RawBook
from scripts.adapters.base import BaseAdapter, Strategy
from scripts.scan import build_parser, run_scan, ADAPTER_REGISTRY


class FakeAdapter(BaseAdapter):
    platform = "fake"
    strategy = Strategy.DIRECT_API

    def fetch(self, category, period, top):
        return [
            RawBook(
                platform_book_id=str(i),
                title=f"book-{i}",
                author=f"author-{i}",
                category=category,
                rank_position=i + 1,
            )
            for i in range(top)
        ]


def test_build_parser_defaults():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.platform == "all"
    assert args.category == "all"
    assert args.top == 50
    assert args.period == "weekly"
    assert args.output_dir == Path("./chart-scan")


def test_run_scan_collects_books_and_writes_files(tmp_path: Path, monkeypatch):
    # 替换 adapter 注册表
    from scripts.scan import ADAPTER_REGISTRY
    monkeypatch.setitem(ADAPTER_REGISTRY, "fake", FakeAdapter)

    parser = build_parser()
    args = parser.parse_args(["--platform", "fake", "--category", "玄幻", "--top", "3", "--output-dir", str(tmp_path)])

    rc = run_scan(args)
    assert rc == 0

    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "books.json").exists()

    import json
    payload = json.loads((tmp_path / "books.json").read_text())
    assert payload["meta"]["total_books"] == 3
    assert all(b["title"].startswith("book-") for b in payload["books"])


def test_run_scan_returns_zero_on_partial_failure(tmp_path: Path, monkeypatch):
    """一个 adapter 失败不应让整体退出码非零。"""
    class BrokenAdapter(BaseAdapter):
        platform = "broken"
        strategy = Strategy.DIRECT_API

        def fetch(self, category, period, top):
            raise RuntimeError("simulated upstream failure")

    from scripts.scan import ADAPTER_REGISTRY
    monkeypatch.setitem(ADAPTER_REGISTRY, "broken", BrokenAdapter)
    monkeypatch.setitem(ADAPTER_REGISTRY, "fake", FakeAdapter)

    parser = build_parser()
    args = parser.parse_args(["--platform", "broken,fake", "--category", "玄幻", "--top", "2", "--output-dir", str(tmp_path)])

    rc = run_scan(args)
    assert rc == 0  # 部分失败不算失败

    import json
    payload = json.loads((tmp_path / "books.json").read_text())
    assert payload["meta"]["total_errors"] >= 1
    assert payload["meta"]["total_books"] == 2
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_scan_integration.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.scan'`

- [ ] **Step 3: 实现 scan.py**

```python
# ${ROOT}/scripts/scan.py
"""webnovel-chart-scan 主控。

CLI 入口：解析参数 -> 路由到 adapter -> 归一化 -> 渲染报告 -> 写文件。
"""
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.adapters.base import BaseAdapter
from scripts.adapters.zongheng import ZonghengAdapter
from scripts.adapters.ciweimao import CiweimaoAdapter
from scripts.adapters.qidian import QidianAdapter
from scripts.adapters.fanqie import FanqieAdapter
from scripts.adapters.qimao import QimaoAdapter
from scripts.schema import ScanResult, ScanMeta, AdapterError
from scripts.normalize import raw_to_bookitem
from scripts.output import write_scan_result

ALL_PLATFORMS = ["qidian", "fanqie", "zongheng", "qimao", "ciweimao"]
ALL_CATEGORIES = ["玄幻", "都市", "仙侠", "历史", "科幻", "游戏", "同人", "军事", "灵异", "二次元", "轻小说", "体育", "现实"]
ALL_PERIODS = ["daily", "weekly", "monthly"]

ADAPTER_REGISTRY: dict[str, BaseAdapter] = {
    "qidian": QidianAdapter(),
    "fanqie": FanqieAdapter(),
    "zongheng": ZonghengAdapter(),
    "qimao": QimaoAdapter(),
    "ciweimao": CiweimaoAdapter(),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chart-scan",
        description="扫网文平台分类榜单（起点/番茄/纵横/七猫/刺猬猫）",
    )
    parser.add_argument("--platform", default="all", help="逗号分隔，例 qidian,fanqie 或 all")
    parser.add_argument("--category", default="all", help="分类名或 all（多分类用逗号）")
    parser.add_argument("--top", type=int, default=50, help="每榜前 N 本，≤100")
    parser.add_argument("--period", default="weekly", help="daily,weekly,monthly（多值用逗号）")
    parser.add_argument("--output-dir", type=Path, default=Path("./chart-scan"))
    parser.add_argument("--verbose", action="store_true")
    return parser


def _parse_list(value: str, all_values: list[str], label: str) -> list[str]:
    if value == "all":
        return list(all_values)
    items = [v.strip() for v in value.split(",") if v.strip()]
    invalid = [i for i in items if i not in all_values]
    if invalid:
        raise ValueError(f"{label} 包含无效值 {invalid}; 有效: {all_values}")
    return items


def run_scan(args: argparse.Namespace) -> int:
    started = time.monotonic()
    scanned_at = datetime.now(timezone.utc)

    platforms = _parse_list(args.platform, ALL_PLATFORMS, "platform")
    categories = _parse_list(args.category, ALL_CATEGORIES, "category")
    periods = _parse_list(args.period, ALL_PERIODS, "period")

    books = []
    errors: list[AdapterError] = []

    for platform in platforms:
        adapter = ADAPTER_REGISTRY.get(platform)
        if adapter is None:
            errors.append(AdapterError(
                platform=platform, category="*", period="*",
                stage="normalize", message=f"unknown platform: {platform}",
                occurred_at=datetime.now(timezone.utc),
            ))
            continue

        for category in categories:
            for period in periods:
                try:
                    if args.verbose:
                        print(f"[{platform}/{category}/{period}] fetching top {args.top}...", file=sys.stderr)
                    raw_books = adapter.fetch(category, period, top=args.top)
                    for raw in raw_books:
                        books.append(raw_to_bookitem(raw, platform=platform, period=period))
                except Exception as e:
                    if args.verbose:
                        print(f"[{platform}/{category}/{period}] FAILED: {e}", file=sys.stderr)
                    errors.append(AdapterError(
                        platform=platform, category=category, period=period,
                        stage=adapter.strategy.value,
                        message=str(e),
                        occurred_at=datetime.now(timezone.utc),
                    ))

    duration = time.monotonic() - started

    result = ScanResult(
        meta=ScanMeta(
            platforms=platforms,
            categories=categories,
            periods=periods,
            top=args.top,
            scanned_at=scanned_at,
            duration_seconds=duration,
            total_books=len(books),
            total_errors=len(errors),
        ),
        books=books,
        errors=errors,
    )

    written = write_scan_result(result, output_dir=args.output_dir)

    if args.verbose:
        print(f"\n✓ 写入 {len(written)} 个文件到 {args.output_dir}", file=sys.stderr)
        print(f"  总本数：{len(books)} | 失败次数：{len(errors)}", file=sys.stderr)

    # 全部失败时退出码 1
    if len(books) == 0 and len(errors) > 0:
        return 1
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run_scan(args)
    except ValueError as e:
        print(f"参数错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/test_scan_integration.py -v
```

Expected: 3 passed

- [ ] **Step 5: 跑全套测试确认整体通过**

```bash
pytest tests/ -v
```

Expected: 全部通过

- [ ] **Step 6: Commit**

```bash
git add scripts/scan.py tests/test_scan_integration.py
git commit -m "feat: scan.py main controller + adapter registry + CLI"
```

---

## Phase 5：文档 + 参考（3 个 task，~30 min）

### Task 13: SKILL.md + README.md

**Files:**
- Create: `${ROOT}/SKILL.md`
- Create: `${ROOT}/README.md`

- [ ] **Step 1: 写 SKILL.md**

```markdown
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
python /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/scripts/scan.py [options]
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
| 起点 | VENDOR | parser + URL 模板 + 分类 ID |
| 番茄 | VENDOR | fork FanqieRankTracker（需 chromium） |
| 纵横 | DIRECT_API | 自写 httpx 调公开 API |
| 七猫 | VENDOR | clone WebCrawler（个人自用） |
| 刺猬猫 | WEBFETCH | 自写 httpx + BS4 |

详见 `references/upstream-survey.md`。

## 依赖

- Python 3.11+
- pydantic, httpx, beautifulsoup4, lxml
- （可选）playwright + chromium for 番茄

## 安装

```bash
cd /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan
pip install -e ".[fanqie,dev]"
playwright install chromium  # 番茄需要
```
```

- [ ] **Step 2: 写 README.md**

```markdown
# webnovel-chart-scan

扫起点/番茄/纵横/七猫/刺猬猫五个网文平台分类榜单的 Claude Code skill。

## 快速开始

```bash
cd /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan
pip install -e ".[fanqie,dev]"
playwright install chromium  # 仅番茄需要

# 跑一次扫描
cd /path/to/your-novel-project
python /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/scripts/scan.py \
    --platform=qidian,fanqie \
    --category=玄幻,都市 \
    --top=30 \
    --period=weekly
```

输出落在 `./chart-scan/`。

## 架构

详见 `docs/superpowers/specs/2026-08-12-webnovel-chart-scan-design.md`。

## 开发

```bash
pytest tests/ -v
pytest tests/ --cov=scripts --cov-report=term-missing
```

## License

个人自用，未明确开源协议。vendored 上游代码遵循各自协议（见 `references/upstream-survey.md`）。
```

- [ ] **Step 3: Commit**

```bash
git add SKILL.md README.md
git commit -m "docs: SKILL.md + README.md"
```

---

### Task 14: references/upstream-survey.md

**Files:**
- Create: `${ROOT}/references/upstream-survey.md`

- [ ] **Step 1: 写上游选型调研记录**

```markdown
# 上游项目选型调研

调研日期：2026-08-12
调研者：与 Claude 对话产出

## 起点中文网 (qidian.com)

### 首选：`saudadez21/novel-downloader`
- URL: https://github.com/saudadez21/novel-downloader
- Stars: 135 / License: MIT
- 最近 commit: 2025-12-02
- 价值：`qidian/parser.py` 完整抽取元数据（书名/作者/分类/简介/字数/状态/标签）
- 风险：Python 3.11+ 要求；macOS 上有 issue #173 可选依赖安装问题

### 参考：`xuduogui/QiDianAPI` (DEAD)
- 仓库已 3 年无活动，但 README 列出的 URL 模板是金矿
- `/all?chanId=21&subCateId=73&tag=...&pageSize=50&page=1` 是真实可用的 AJAX 端点

### 参考：`howie6879/owllook` (Apache-2.0)
- 仓库活跃但 demo 已挂；价值在于 `qidian_ranking.py` 里的分类 ID 映射表
- `21=玄幻 22=仙侠 4=都市 ...` 等

### 集成方式：VENDOR
- 把 `novel-downloader` 的 `qidian/parser.py` 子集复制到 `vendor/`
- 自写 `category_browser.py` 调公开 AJAX
- 分类 ID 表从 `owllook` 抄

## 番茄小说 (fanqie.com)

### 首选：`Despacito0o/FanqieRankTracker`
- URL: https://github.com/Despacito0o/FanqieRankTracker
- Stars: 0（新仓库，68 commits）/ License: MIT
- 最近 commit: 2026-08-12（今天还在更新）
- 价值：4 个 tab（男频/女频 × 阅读/新书）全遍历 + Playwright 处理 a_bogus 签名 + 字体解密
- 依赖：playwright + chromium

### 辅助：`mhkz/fanqie-novels-skills` (Node.js, MIT)
- 仅用作知识库参考：分类竞争程度表 + URL 格式 `/rank/{gender}_{type}_{category_id}`
- 不集成

### 集成方式：VENDOR（fork）
- 把整个 `FanqieRankTracker` 仓库克隆到 `vendor/fanqie-rank-tracker/`
- 主循环用它的 `scrape_fanqie_ranks.py`
- 扩展 `get_book_detail()` 函数拿字数/标签

## 纵横中文网 (zongheng.com)

### 首选：无候选（GitHub 上无活跃 zongheng 分类榜项目）
- 大多数候选要么不支持 zongheng，要么已 dead，要么 Go/Node.js 而非 Python

### Fallback：直接调公开 API
- `https://www.zongheng.com/api/rank/details?rankType={N}&pageSize=50&pageNum=1`
- `rankType`: 2=热销 4=新书 9=推荐
- 返回 JSON 含 `bookName / authorName / cateFineName / orderNo`
- 字段补全需单书详情页（v0.2）

### 集成方式：DIRECT_API（自写 50 行 httpx）

## 七猫小说 (qimao.com)

### 首选：`staysharp1104/WebCrawler`
- URL: https://github.com/staysharp1104/WebCrawler
- Stars: 3 / License: ⚠ 未声明（个人自用容差）
- 最近 commit: 2026-07-02
- 价值：完全对齐需求（榜单爬取 + 元数据），Nuxt.js SSR `__NUXT__` 解析
- 缺点：License 不清，自用 OK；商业场景需重写

### 备选：`qisumi/fanqie-qimao-downloader` (MIT, 13 stars)
- 定位是个人书架 + 章节下载，不是榜单工具；fallback

### 集成方式：VENDOR（clone 七猫模块到子目录）

## 刺猬猫 (ciweimao.com)

### 首选：无候选
- 唯一 Python 候选 `saudadez21/novel-downloader` 的刺猬猫插件 issue #157 已失效 9 个月
- `AlexiaAshford/HedgehogCatAppNovelDownload` 已 17 个月 dead
- `guohuiyuan/go-novel-dl` 是 Go 且 AGPL-3.0

### Fallback：自写 httpx + BeautifulSoup
- `https://www.ciweimao.com/category/{分类}/` + 详情页
- 反爬绕过需自己分析

### 集成方式：WEBFETCH（自写 200 行）

## 架构模板（学谁的）

### `NanmiCoder/NewsCrawler` (GPL-3.0, 549 stars)
- URL: https://github.com/NanmiCoder/NewsCrawler
- 价值：SKILL.md + detector.py URL 识别 + adapters/ 目录 + 归一化 schema 模式
- 直接借鉴架构，不 fork 代码（GPL 传染）

## 关键风险

1. **七猫 `WebCrawler` License 不清**：自用 OK；二次分发前需联系作者
2. **番茄反爬严**：必须 Playwright + 字体解密
3. **所有平台分类口径不一致**：见 `category-mapping.md`
4. **上游 API 失效是常态**：每个 adapter 内部有四级降级链

## License 矩阵

| 平台 | 上游 License | 集成方式 | 风险 |
|------|-------------|----------|------|
| 起点 | MIT + Apache-2.0 | VENDOR 子集 | 低 |
| 番茄 | MIT | VENDOR 完整 | 低 |
| 纵横 | —（直接调 API）| DIRECT_API | 无 |
| 七猫 | 未声明 | VENDOR 完整 | 中（个人用 OK）|
| 刺猬猫 | — | WEBFETCH 自写 | 无 |
```

- [ ] **Step 2: Commit**

```bash
git add references/upstream-survey.md
git commit -m "docs: upstream survey reference"
```

---

### Task 15: references/category-mapping.md + adapter-strategies.md

**Files:**
- Create: `${ROOT}/references/category-mapping.md`
- Create: `${ROOT}/references/adapter-strategies.md`

- [ ] **Step 1: 写 category-mapping.md**

```markdown
# 分类映射表（5 平台 → 统一分类）

更新日期：2026-08-12

## 起点分类 ID

```python
QIDIAN_CATEGORY_IDS = {
    "玄幻": 21, "奇幻": 1, "武侠": 2, "仙侠": 22,
    "都市": 4, "职场": 15, "军事": 6, "历史": 5,
    "游戏": 7, "体育": 8, "科幻": 9, "灵异": 10, "二次元": 12,
}
```

来源：`howie6879/owllook/spiders/qidian_ranking.py`

## 番茄分类

男频：玄幻、都市、仙侠、历史、军事、游戏、体育、科幻、灵异、二次元
女频：古言、现言、玄幻言情、浪漫青春、悬疑、仙侠奇缘

## 纵横分类

玄幻、奇幻、武侠、仙侠、都市、职场、历史、军事、游戏、体育、科幻、灵异、二次元

## 七猫分类

男频：玄幻、都市、仙侠、历史、军事、游戏、科幻、灵异
女频：古言、现言、校园、悬疑

## 刺猬猫分类

轻小说主站：奇幻、玄幻、科幻、都市、悬疑、游戏、同人、二次元、历史、言情

## 归一化映射（不完整，按需扩充）

```python
NORMALIZED_CATEGORIES = {
    "玄幻": ["东方玄幻", "异世大陆", "高武", "男频-玄幻", "玄幻奇缘"],
    "都市": ["都市生活", "职场", "男频-都市"],
    "仙侠": ["古典仙侠", "修真文明", "现代修真", "男频-仙侠", "仙侠奇缘"],
    "古言": ["女频-古言", "古言"],
    "现言": ["女频-现言", "现言", "浪漫青春"],
}
```

实现见 `scripts/normalize.py:_QIDIAN_SUBCATEGORY_MAP` 等。
```

- [ ] **Step 2: 写 adapter-strategies.md**

```markdown
# Adapter 策略详解

更新日期：2026-08-12

## Strategy 枚举

```python
class Strategy(str, Enum):
    VENDOR = "vendor"           # vendored 完整上游代码
    DIRECT_API = "direct_api"   # 自写薄壳调平台公开 API
    WEBFETCH = "webfetch"       # 自写 httpx + BeautifulSoup 兜底
```

## 各 adapter 详解

### 起点（VENDOR）

**vendored 子集**：`vendor/novel-downloader/qidian_subset/parser.py`

**fetch() 流程**：
1. 构造 URL：`https://www.qidian.com/all?chanId={id}&pageSize={top}&page=1`
2. httpx.get 带 UA + Referer
3. JSON 解析为 RawBook 列表

**已知缺口**：
- intro / word_count / tags 需单书详情页（v0.2 增强）
- 起点反爬近年来加强，部分 IP 段会触发验证（届时降级 WebFetch）

### 番茄（VENDOR）

**vendored 仓库**：`vendor/fanqie-rank-tracker/`

**fetch() 流程**：
1. 懒导入 `scrape_fanqie_ranks` 函数
2. Playwright + Chromium 渲染榜单页
3. 字体解密（CHAR_SEQUENCE 映射表）
4. 解析为 RawBook 列表

**已知缺口**：
- 字段在 rank 阶段只有 6 个（书名/作者/简介/在读数/封面/详情 URL）
- 字数/状态/标签需 `get_book_detail()`（MVP 后扩展）

### 纵横（DIRECT_API）

**端点**：`https://www.zongheng.com/api/rank/details`

**fetch() 流程**：
1. 构造 URL：`?rankType={N}&pageSize={top}&pageNum=1`
2. httpx.get 带 UA + Referer
3. JSON 解析为 RawBook 列表

**已知缺口**：
- `rankType` 与 period 映射：daily=4, weekly=9, monthly=2
- 字段：bookName/authorName/cateFineName/number/orderNo
- intro/word_count/status/tags 需详情页（v0.2）

### 七猫（VENDOR）

**vendored 仓库**：`vendor/qimao-web-crawler/qimao_subset/`

**fetch() 流程**：
1. 懒导入七猫 fetch 函数
2. 解析 Nuxt.js SSR `__NUXT__` JSON
3. 字段映射到 RawBook

**已知缺口**：
- 七猫 License 未声明（自用 OK；商业分发需重写）
- 字段以 vendored 上游实际产出为准

### 刺猬猫（WEBFETCH）

**端点**：`https://www.ciweimao.com/category/{分类}/` + 详情页

**fetch() 流程**：
1. httpx.get 榜单页
2. BeautifulSoup + lxml 解析 HTML
3. 提取 title/author/bookId/rank_position
4. （可选）详情页拿 intro/word_count

**已知缺口**：
- 反爬绕过需自己分析，可能触发 403/429
- 字段以真实页面为准（HTML 结构变化时 adapter 需更新）

## 失败降级链

每个 adapter 内部：

```
首选 strategy → 下一级 strategy → WebFetch + BS4 → 抛 AdapterError
```

例：起点 VENDOR 失败 → 降级 WebFetch 公开榜 → 仍失败 → AdapterError
```

- [ ] **Step 3: Commit**

```bash
git add references/category-mapping.md references/adapter-strategies.md
git commit -m "docs: category-mapping + adapter-strategies references"
```

---

## 验收（最后一步）

完成所有 Phase 后，跑：

```bash
cd /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan
pip install -e ".[dev]"
pytest tests/ -v
pytest tests/ --cov=scripts --cov-report=term-missing
```

预期：全部测试通过，覆盖率 ≥ 60%。

跑一次真实扫描验证：

```bash
cd /tmp  # 或任何小说项目目录
python /Users/chang/Desktop/zhanghui/.claude/skills/webnovel-chart-scan/scripts/scan.py \
    --platform=qidian --category=玄幻 --top=5 --period=weekly --verbose
```

预期：`./chart-scan/report.md` 和 `./chart-scan/books.json` 被创建。

---

## Self-Review 检查清单

执行计划写完后，对照 spec 自审：

- [ ] §1.2 目标（5 平台 + 元数据 + 输出）→ Task 5/6/7/8/9（5 个 adapter）+ Task 12（scan.py 编排）
- [ ] §3 核心原则（混合集成策略）→ Task 5-9 + `references/adapter-strategies.md`
- [ ] §4.1 MVP（5 平台 + 默认 top=50 + 三周期 + 8 字段 + JSON+MD + 默认输出）→ Task 2-12 + Task 10-11
- [ ] §5.1 目录结构 → 文件总览已列出所有新建路径
- [ ] §6.1 schema（BookItem/RawBook/AdapterError/ScanMeta/ScanResult）→ Task 2
- [ ] §6.2 CLI 参数（--platform, --category, --top, --period, --output-dir, --verbose）→ Task 12
- [ ] §7.2 各平台策略 → Task 5-9
- [ ] §8 失败降级（adapter 失败不崩 + 四级链）→ Task 12（run_scan 异常捕获）+ Task 14（文档化）
- [ ] §9 测试（pytest + fixtures）→ Task 2-12 每个 adapter 都有测试
- [ ] §9.3 验收标准（CLI 跑通 + 5 adapter 通过 + 覆盖 ≥ 60% + references 文档）→ Phase 5 全部