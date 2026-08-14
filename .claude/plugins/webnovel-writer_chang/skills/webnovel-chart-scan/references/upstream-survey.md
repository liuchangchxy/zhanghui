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

### 集成方式：HYBRID
- 把 `novel-downloader` 的 `qidian/parser.py` 子集复制到 `vendor/` 作参考
- 自写 `category_browser.py` 调公开 AJAX
- 分类 ID 表从 `owllook` 抄
- 当前 endpoint 被 probe.js 反爬挡住，需 port RC4 cookie 计算（未来 follow-up）

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

### 集成方式：VENDOR
- 把整个 `FanqieRankTracker` 仓库克隆到 `vendor/fanqie_rank_tracker/`（注意：下划线命名以避免 Python import 失败）
- 主循环用它的 `run_scraper(limit, sleep_sec)`（注意：不是 spec 假设的 `scrape_fanqie_ranks`）
- 扩展 `get_book_detail()` 函数拿字数/标签

## 纵横中文网 (zongheng.com)

### 首选：无候选（GitHub 上无活跃 zongheng 分类榜项目）
- 大多数候选要么不支持 zongheng，要么已 dead，要么 Go/Node.js 而非 Python

### Fallback：直接调公开 API
- `https://www.zongheng.com/api/rank/details?rankType={N}&pageSize=50&pageNum=1`
- `rankType`: 2=热销 4=新书 9=推荐
- 返回 JSON 含 `bookName / authorName / cateFineName / orderNo`
- 字段补全需单书详情页（v0.2）

**注意**：spec 假设的 endpoint 实际上 404，需用 Nuxt SSR 抓真实字段名
- 真实字段：`rankNo` / `bookId` / `bookName` / `authorName` / `cateFineName` / `description` / `totalWords` / `serialStatus` / `imageUrl`

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

### 集成方式：VENDOR
- clone 七猫模块到子目录 `vendor/qimao_web_crawler_subset/qimao_subset/`（下划线命名）
- 用纯 Python 替换上游的 Node.js 子进程解析 Nuxt payload
- 真实字段：`book_id / title / author / category_label / cover_url / description / status / reader_count / source`

## 刺猬猫 (ciweimao.com)

### 首选：无候选
- 唯一 Python 候选 `saudadez21/novel-downloader` 的刺猬猫插件 issue #157 已失效 9 个月
- `AlexiaAshford/HedgehogCatAppNovelDownload` 已 17 个月 dead
- `guohuiyuan/go-novel-dl` 是 Go 且 AGPL-3.0

### Fallback：自写 httpx + BeautifulSoup
- `https://www.ciweimao.com/book_list/{category_slug}/` + 详情页
- 反爬绕过需自己分析
- 真实字段：`name / author / type / num / date / chapter`（来自 book-list-table 容器）

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
5. **起点 probe.js 反爬**：当前实现只能拿到 202 + probe.js 响应，需 port RC4 cookie 计算
6. **纵横 API endpoint 404**：spec 假设的 URL 实际不存在；用 Nuxt SSR 正确路径

## License 矩阵

| 平台 | 上游 License | 集成方式 | 风险 |
|------|-------------|----------|------|
| 起点 | MIT + Apache-2.0 | HYBRID 子集 | 需 Python 3.11+ |
| 番茄 | MIT | VENDOR 完整 | 需 chromium |
| 纵横 | —（直接调 API）| DIRECT_API | endpoint 404 |
| 七猫 | 未声明 | VENDOR 完整 | 限自用 |
| 刺猬猫 | — | WEBFETCH 自写 | 反爬需自处理 |
