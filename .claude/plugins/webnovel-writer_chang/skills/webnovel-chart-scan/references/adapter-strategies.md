# Adapter 策略详解

更新日期：2026-08-12

## Strategy 枚举

```python
class Strategy(str, Enum):
    VENDOR = "vendor"           # 真实 import vendored 上游代码
    HYBRID = "hybrid"           # 用 httpx + 参考 vendored 子集（reference-only）
    DIRECT_API = "direct_api"   # 自写薄壳调平台公开 API
    WEBFETCH = "webfetch"       # 自写 httpx + BeautifulSoup 兜底
```

## 各 adapter 详解

### 起点（HYBRID）

**vendored 子集**：`vendor/novel-downloader/qidian_subset/`（仅参考）

**fetch() 流程**：
1. 构造 URL：`https://www.qidian.com/all?chanId={id}&pageSize={top}&page=1`
2. httpx.get 带 UA + Referer
3. JSON 解析为 RawBook 列表

**已知缺口**：
- 端点被 probe.js 反爬挡住（HTTP 202），需 port RC4 cookie 计算（v0.2）
- intro / word_count / tags 需单书详情页（v0.2 增强）
- 当前 adapter 不 import vendored 子集（避免引入上游 lxml/async/registry 全套依赖）

### 番茄（VENDOR）

**vendored 仓库**：`vendor/fanqie_rank_tracker/`（下划线命名）

**fetch() 流程**：
1. 懒导入 `from vendor.fanqie_rank_tracker.scrape_fanqie_ranks import run_scraper`
2. Playwright + Chromium 渲染榜单页
3. 字体解密（CHAR_SEQUENCE 映射表）
4. 解析为 RawBook 列表

**已知缺口**：
- 字段在 rank 阶段只有 6 个（书名/作者/简介/在读数/封面/详情 URL）
- 字数/状态/标签需 `get_book_detail()`（v0.2）
- `run_scraper` 一次抓所有分类不可中断；category/period 参数被忽略（category=!="all" 抛 NotImplementedError）

### 纵横（DIRECT_API）

**端点**：`https://www.zongheng.com/api/rank/details`

**fetch() 流程**：
1. 构造 URL：`?rankType={N}&pageSize={top}&pageNum=1`
2. httpx.get 带 UA + Referer
3. JSON 解析为 RawBook 列表

**已知缺口**：
- spec 假设的 endpoint 实际 404；当前用 Nuxt SSR 找到的真实字段名（rankNo 等）
- `rankType` 与 period 映射：daily=3, weekly=5, monthly=1（基于观察到的页面导航）
- category 参数不支持（=!="all" 抛 NotImplementedError）
- intro/word_count/status/tags 需详情页（v0.2）

### 七猫（VENDOR）

**vendored 仓库**：`vendor/qimao_web_crawler_subset/`（下划线命名）

**fetch() 流程**：
1. 懒导入 `from vendor.qimao_web_crawler_subset.qimao_subset import fetch_qimao_rank`
2. httpx + 纯 Python 替换上游的 Node.js 子进程解析 Nuxt SSR `__NUXT__`
3. 字段映射到 RawBook

**已知缺口**：
- 七猫 License 未声明（自用 OK；商业分发需重写）
- 分两个 channel（boy / girl）各跑一次，rank_position 全局连续
- category 参数不支持（=!="all" 抛 NotImplementedError）
- 字段以 vendored 上游实际产出为准

### 刺猬猫（WEBFETCH）

**端点**：`https://www.ciweimao.com/book_list/{category_slug}/` + 详情页

**fetch() 流程**：
1. httpx.get 榜单页
2. BeautifulSoup + lxml 解析 HTML（table.book-list-table）
3. 提取 title/author/bookId/rank_position
4. （可选）详情页拿 intro/word_count

**已知缺口**：
- 反爬绕过需自己分析，可能触发 403/429
- 字段以真实页面为准（HTML 结构变化时 adapter 需更新）
- 真实 URL 不是 spec 假设的 `/category/{分类}/` 而是 `/book_list/{slug}/`

## 失败降级链

每个 adapter 内部：

```
首选 strategy → 下一级 strategy → WebFetch + BS4 → 抛 AdapterError
```

**当前实现状况**：
- ✅ 起点 / 番茄 / 七猫 / 刺猬猫 都支持迁到 WebFetch + BS4（adapter 内 fallback 未实现，留 v0.2）
- ✅ 单 adapter 失败 → AdapterError（Task 12 已在主循环实现）
- ❌ 完整 4 级降级链尚未实现（v0.2 增强）
