# 🏆 番茄风向标 · Fanqie Rank Tracker

> 专注于**番茄小说女频新书榜**，每日自动追踪排行数据并结合 AI 生成趋势分析，部署为精美的在线看板。

[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-在线看板-brightgreen)](https://despacito0o.github.io/FanqieRankTracker/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

---

## ✨ 功能概览

| 功能 | 说明 |
|------|------|
| 🕷️ 自动爬取 | 每日定时抓取番茄女性频道各个分类的新书榜 Top 30 |
| 📊 趋势对比 | 自动对比相邻两天数据：新上榜 / 掉榜 / 排名变化 / 阅读量增长 |
| 🤖 AI 风向分析 | 接入 OpenAI 兼容 API，按分类生成市场趋势速评 |
| 🖥️ 精美看板 | 暗色编辑风格仪表盘，带打字机动画和瀑布流书籍卡片 |
| 📱 移动适配 | 完整的移动端适配，侧边栏抽屉式菜单 |
| ⚡ 全自动化 | GitHub Actions + GitHub Pages，零服务器运维 |

---

## 🌐 在线看板

**https://despacito0o.github.io/FanqieRankTracker/**

每天北京时间 08:00 自动更新数据。

---

## 🔧 本地开发

```bash
# 1. 克隆仓库
git clone https://github.com/Despacito0o/FanqieRankTracker.git
cd FanqieRankTracker

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 4. 运行爬虫（每个分类抓取 Top 30）
python scrape_fanqie_ranks.py

# 5. 构建看板数据（可选，带 AI 分析需设置环境变量）
pip install openai
export API_BASE_URL="https://your-api-endpoint/v1"
export API_KEY="your-api-key"
export API_MODEL="your-model-name"
python scripts/build_latest.py

# 6. 本地预览前端
python -m http.server 8000
# 打开 http://localhost:8000
```

---

## ⚙️ 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│                   GitHub Actions (每日 08:00)               │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  Playwright   │───▶│  build_latest │───▶│  git commit  │  │
│  │  爬取榜单数据  │    │  趋势对比      │    │  自动提交     │  │
│  │              │    │  + AI 分析     │    │  到 master   │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                                                             │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
                    GitHub Pages 自动部署
                    用户访问在线看板 🌐
```

---

## 📁 项目结构

```
FanqieRankTracker/
├── .github/workflows/
│   ├── scrape.yml          # 每日自动爬取工作流
│   ├── pages.yml          # GitHub Pages 部署
│   └── force_update.yml   # 强制更新工作流
├── css/
│   └── style.css          # 暗色编辑风格主题样式
├── js/
│   └── app.js             # 前端渲染逻辑（瀑布流 + 打字机动画）
├── scripts/
│   └── build_latest.py    # 趋势对比 + AI 分析构建脚本
├── data/
│   ├── fanqie_female_new_ranks_YYYYMMDD.json  # 每日原始快照
│   ├── latest_ranks.json    # 最新聚合数据（看板数据源）
│   └── trends/              # 趋势归档
├── index.html              # 仪表盘入口页
├── scrape_fanqie_ranks.py  # 番茄小说爬虫（Playwright）
└── requirements.txt        # Python 依赖
```

---

## 🤖 AI 分析配置（可选）

进入仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**，添加：

| Secret 名称 | 说明 | 示例 |
|---|---|---|
| `API_BASE_URL` | OpenAI 兼容 API 地址 | `https://api.openai.com/v1` |
| `API_KEY` | API 密钥 | `***` |
| `API_MODEL` | 模型名称 | `gpt-4o-mini` |

> 💡 不配置也能用，系统会自动 fallback 到基于规则的摘要。

---

## 📜 License

MIT
