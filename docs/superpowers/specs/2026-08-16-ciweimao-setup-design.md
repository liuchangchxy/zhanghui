# ciweimao setup 自动化设计文档

> **状态**：设计稿，待用户审批
> **日期**：2026-08-16
> **作者**：与 Claude 对话产出
> **代码归属**：`/Users/chang/Desktop/zhanghui/.claude/plugins/webnovel-writer_chang/`

---

## 1. 背景与目标

### 1.1 痛点

v0.2 (commit `03ad302`) 把 ciweimao adapter 标成 `LIVE_WITH_SETUP`，但 SETUP 的实际内容从未实现：
- 适配器依赖外部 Chrome 进程监听 9222 端口 + `agent-browser` 在 `$PATH` 上
- 用户**没有任何文档、提示、或自动化机制**被告知这件事
- 对照：fanqie adapter 的 chromium 下载由 SessionStart 钩子在 y/N 提示后自动完成；ciweimao 完全没对等机制

实际后果：用户（开发者本人）第一次跑 ciweimao scan 撞到 "Connection refused at 127.0.0.1:9222"，且**该错误信息没有可操作的指引**。排查需要看 vendored JS 的 `cdp-utils.js` 源码才知道发生了什么。

### 1.2 目标

把 ciweimao 的 "SETUP" 从假标签变成真的自动化：
1. 用户第一次用 ciweimao 时，SessionStart 钩子 y/N 提示，自动起 Chrome 在 9222 + 自动装 agent-browser
2. 决策持久化，下次 SessionStart 不再打扰
3. 运行时如果环境异常，错误信息指向可执行命令
4. 端到端测试在 Chrome 可用时跑通，缺失时干净 skip

### 1.3 非目标

- 不重写 vendored JS（用 agent-browser 是上游设计选择，本轮接受）
- 不替换为 playwright 自管路径（已在 review 中讨论，列为未来重构）
- 不改 fanqie 路径（独立生命周期）
- 不新增 Windows 平台特殊处理（agent-browser Windows shim 已在 cdp-utils.js 处理）

---

## 2. 触发与用户故事

### 2.1 触发

**A. SessionStart 时**（新增）
钩子检测 ciweimao adapter 是否需要 SETUP → 需要则打印 y/N 提示给 Claude。

**B. 用户主动**（新增）
```bash
python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao
# 或带自定义端口
python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao --port 9223
```

### 2.2 用户故事

| # | 我作为 | 想要 | 以便 |
|---|--------|------|------|
| 1 | 网文作者 | 第一次跑 ciweimao scan 前被明确提示需要装什么 | 不会被 "Connection refused" 卡住 |
| 2 | 网文作者 | 接受 y 后所有依赖自动装好 | 不需要手动 `npm install` 或启 Chrome |
| 3 | 网文作者 | 拒绝 N 后下次 SessionStart 永不再问 | 不被打扰 |
| 4 | 工具维护者 | ciweimao 错误信息直接告诉我跑哪条命令 | 不用看 vendored JS 源码 |
| 5 | 工具维护者 | 同一台机器能跑多个 v0.2 worktree 而 9222 不冲突 | 通过 `WEBNOVEL_CIWEIMAO_CDP_PORT` env 覆盖 |

---

## 3. 架构

### 3.1 两条独立 lifecycle 路径

```
fanqie 路径（已存在）                  ciweimao 路径（本设计）
─────────────────────                  ────────────────────
SessionStart hook                      SessionStart hook (扩展)
  ↓ 检测 chromium                         ↓ 检测 agent-browser + Chrome @ port
  ↓ y/N 提示                              ↓ y/N 提示
  ↓ yes → playwright install chromium     ↓ yes → setup-ciweimao 脚本
.chromium-prompted                    .ciweimao-prompted (独立标记)
                                         ↓
                                         setup_ciweimao.py 干三件事：
                                           1. 检测/安装 agent-browser
                                           2. 启动 Chrome @ port
                                           3. 验证 CDP 可达

运行时（adapter.fetch）
─────────────────────
ciweimao_runner.run_scraper(rank_type, output_dir)
  → 读 env: WEBNOVEL_CIWEIMAO_CDP_PORT (默认 9222)
  → 错误信息 humanized
```

### 3.2 架构原则

- **独立子目录**：`scripts/ciweimao_setup/` 隔离 ciweimao lifecycle 代码，不污染 fanqie 路径
- **adapter 层只读环境**：adapter 不做自检不自启，依赖 hook 已完成 SETUP
- **错误信息归 adapter 层**：因为 adapter 是第一个报错点；hook 层只负责"引导用户装"
- **决策文件独立**：`.ciweimao-prompted` 不复用 `.chromium-prompted`，避免决策串台

---

## 4. 组件

### 4.1 新增组件

#### C1. `scripts/ciweimao_setup/__init__.py`
空 package 标记文件。

#### C2. `scripts/ciweimao_setup/setup_ciweimao.py`
独立可运行的 setup 脚本。

**公开函数**：
| 函数 | 签名 | 职责 |
|------|------|------|
| `check_agent_browser` | `() -> bool` | `shutil.which("agent-browser")` 检测 |
| `install_agent_browser` | `() -> None` | subprocess `npm install -g agent-browser`, timeout 120s |
| `check_chrome_running` | `(port: int) -> bool` | HTTP GET `/json/version`, 2xx + body 含 `"Browser"` 字段 |
| `find_chrome_binary` | `() -> Optional[Path]` | 见下方 5 级优先级 |
| `launch_chrome` | `(port: int, user_data_dir: Path) -> subprocess.Popen` | `start_new_session=True` 后台启动 |
| `verify_cdp_ready` | `(port: int, retries: int = 10, delay: float = 0.5) -> None` | 轮询 check_chrome_running |
| `setup_ciweimao` | `(port: int = 9222) -> None` | orchestrator |

**`find_chrome_binary` 5 级优先级**：
1. `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`（macOS）
2. `shutil.which("google-chrome")`（Linux）
3. `shutil.which("chrome")`（Linux alt）
4. `~/Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium`（复用 playwright 已装的）
5. 都找不到 → `RuntimeError("找不到 Chrome 二进制。请安装 Chrome 或运行 `playwright install chromium`")`

**CLI 入口**：`argparse` 接 `--port`（默认 9222），exit code 反映成功/失败。

#### C3. `scripts/ciweimao_setup/sessionstart_integration.py`
**镜像** `install_python_deps.py` 的 chromium 模式（`_chromium_marker` / `should_prompt_chromium` / `write_chromium_decision` / `format_chromium_prompt`）。

**公开函数**：
| 函数 | 签名 | 职责 |
|------|------|------|
| `_ciweimao_marker` | `(module_name: str) -> Path` | 标记文件路径 |
| `should_prompt_ciweimao` | `(module_name: str) -> bool` | 决策文件不存在 → True |
| `write_ciweimao_decision` | `(module_name: str, decision: str) -> None` | 写 'yes' 或 'no' |
| `format_ciweimao_prompt` | `() -> str` | 给 Claude 的提示文本 |

**关键差异 vs chromium 模式**：
- 标记文件名：`.ciweimao-prompted`（不复用 `.chromium-prompted`）
- 提示文本不同（针对 Chrome + agent-browser，不针对 playwright chromium）
- 决策 yes 后**不**自动跑 setup（铬模式是 Claude 自己跑 `playwright install chromium`；ciweimao 需要先确认端口、检查 binary、后台启 Chrome，逻辑更复杂，单独做成脚本由 Claude 调用）

#### C4. 修改 `hooks/session_start.py`
加新函数 `check_ciweimao_prompt(plugin_root: Path) -> str | None`，与 `check_chromium_prompt` 并列。`main()` 在 `check_chromium_prompt` 之后调一次 `check_ciweimao_prompt`。两次输出用 `print` 顺序拼接。

**修改函数**：
- `main()`: 新增 `prompt2 = check_ciweimao_prompt(plugin_root); if prompt2: print(prompt2)` 一段

#### C5. `tests/test_ciweimao_e2e.py`（新增）
**与现有 `test_ciweimao_live.py` 并存**——新文件覆盖自动化 setup 路径，旧文件保留手动 live 验证。

**装饰器**：
```python
pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not _chrome_listening(), reason="no Chrome on configured port"),
    pytest.mark.skipif(not _agent_browser_on_path(), reason="no agent-browser"),
]
```

**测试函数**：
| 名称 | 验证什么 |
|------|---------|
| `test_adapter_returns_books_when_chrome_available` | 调 `fetch("all", "daily", top=10)` → 断言 ≥1 本书 + title/detail_url 非空 |
| `test_setup_is_idempotent` | 连跑两次 `setup_ciweimao()` 不抛错、不重启 Chrome |
| `test_check_chrome_running_returns_false_for_closed_port` | unit-level |
| `test_find_chrome_binary_finds_at_least_one_on_dev_machine` | skip-if-not-(mac/linux) |
| `test_setup_writes_ciweimao_decision_yes_on_success(tmp_path)` | mock check_chrome_running=True, 调 setup, 断言标记内容 |

### 4.2 修改的组件

#### M1. `scripts/adapters/ciweimao_runner.py`

**改动 1**：port 来自 env
```python
# 原：硬编码
cmd = [..., "--port", "9222"]
# 新：
port = int(os.environ.get("WEBNOVEL_CIWEIMAO_CDP_PORT", "9222"))
cmd = [..., "--port", str(port)]
```

**改动 2**：错误信息 humanize
```python
# 原 RuntimeError 模板：
# "ciweimao scraper failed (exit N): stderr=..."
# 新模板：
# "ciweimao scraper 启动失败：
#  - Chrome 没在 {port} 监听？→ python -m webnovel_chart_scan.ciweimao_setup.setup_ciweimao
#  - agent-browser 不在 PATH？→ npm install -g agent-browser
#  - node 没装？→ brew install node 或 https://nodejs.org
#  原始错误：{stderr[:300]}"
```

**改动 3**：node 缺失信息 humanize
```python
# 原：透传 FileNotFoundError
# 新：明确 RuntimeError
# "找不到 node 可执行文件。请安装 Node.js ≥18（brew install node 或 https://nodejs.org），ciweimao adapter 才能用。"
```

#### M2. `scripts/adapters/ciweimao.py`

**改动 1**：删死代码
- 删 `parse_category_html`（91-166 行）
- 删 `_extract_book_id`（83-88 行）
- 删 `CATEGORY_SLUG_MAP`（57-72 行）
- 删 `PERIOD_SORT_MAP`（76-80 行）
- 删 `import re`、`import httpx`、`from bs4 import BeautifulSoup`（如不再被用）

**改动 2**：`PERIOD_TO_RANK_TYPE["weekly"]` 加注释
```python
PERIOD_TO_RANK_TYPE = {
    "daily": "click",
    # 注意：ciweimao 没有 weekly 榜，weekly 复用 click 榜（最近 24h 数据）。
    "weekly": "click",
    "monthly": "monthly",
}
```

**改动 3**：adapter docstring 重写
- 删 "BLOCKED_EXTERNAL" 历史段
- 删 "WEBFETCH strategy via httpx + BeautifulSoup" 段
- 替换为引用 setup 脚本的简短段落

#### M3. `pyproject.toml`（chart-scan）

新增 entry point（如适用）：
```toml
[project.scripts]
webnovel-chart-scan-setup-ciweimao = "webnovel_chart_scan.ciweimao_setup.setup_ciweimao:main"
```

#### M4. `scripts/adapters/ciweimao_runner.py` 删除
- `parse_category_html` 不在 runner 里，无需改

---

## 5. 数据流

```
[SessionStart 钩子触发]
    ↓
check_ciweimao_prompt(plugin_root)
    ↓
should_prompt_ciweimao("webnovel-chart-scan")?
    ├─ False → 静默退出
    └─ True
        ↓
        format_ciweimao_prompt() → 输出到 stdout
        ↓
        Claude 收到提示，转给用户 y/N
        ↓
        ├─ y/Y → Claude 调 setup_ciweimao.setup_ciweimao(port)
        │           ├─ check_agent_browser()?
        │           │   ├─ True → skip
        │           │   └─ False → install_agent_browser()
        │           │                  ↓ npm install -g agent-browser (timeout 120s)
        │           │                  ↓ 失败 raise RuntimeError
        │           ├─ check_chrome_running(port)?
        │           │   ├─ True → skip
        │           │   └─ False → find_chrome_binary()
        │           │                  ↓ 找不到 raise RuntimeError
        │           │                  ↓ 找到 → launch_chrome(port, user_data_dir)
        │           │                              ↓ subprocess.Popen(start_new_session=True)
        │           │                  ↓ verify_cdp_ready(port) [10 × 0.5s]
        │           │                              ↓ 失败 raise RuntimeError
        │           └─ 成功 → write_ciweimao_decision("webnovel-chart-scan", "yes")
        └─ n/N/其他 → write_ciweimao_decision("webnovel-chart-scan", "no")

[运行时：scan 触发]
    ↓
scan.py → CiweimaoAdapter.fetch("玄幻", "weekly", 10)
    ↓
ciweimao_runner.run_scraper("click", output_dir)
    ↓ 读 env: WEBNOVEL_CIWEIMAO_CDP_PORT (默认 9222)
subprocess.run(["node", JS_SCRAPER, "--type", "click",
                "--outdir", output_dir, "--port", port])
    ├─ returncode 0 → read .md → parse_rank_markdown → filter by category → 返回
    └─ FileNotFoundError("node") → RuntimeError(humanized)
    └─ returncode ≠ 0 → RuntimeError(humanized, 引用 setup 脚本)
    └─ TimeoutExpired → RuntimeError(原有模板)
```

---

## 6. 错误处理

| 错误源 | 检测点 | 处理 |
|--------|--------|------|
| `agent-browser` 不在 PATH | setup 入口 | 自动 npm install -g |
| `npm install -g` 失败 | install_agent_browser | raise + 原始 stderr |
| 找不到 Chrome 二进制 | find_chrome_binary | raise + 列出常见路径 |
| Chrome 启动后 CDP 不可达 | verify_cdp_ready | raise + 提示检查 Chrome 进程 |
| `node` 不在 PATH | subprocess FileNotFoundError | RuntimeError humanized |
| `node` subprocess timeout | subprocess.TimeoutExpired | 现有 RuntimeError |
| `cdp-utils.js` 缺失 | stderr 含 MODULE_NOT_FOUND | RuntimeError 提示 vendor 损坏 |
| 决策文件 yes 后 Chrome 中途死 | 下次 scan 时 check_chrome_running 失败 | 透传到 user：提示重新跑 setup |
| **新**：setup 进程半途崩 | Popen 后台 Chrome 进程 | `start_new_session=True` 脱离父进程；user_data_dir 让下次能识别 |
| **新**：port 已被占用 | launch_chrome | 当前实现不检测，subprocess 会失败 → humanize 提示换 WEBNOVEL_CIWEIMAO_CDP_PORT |

---

## 7. 测试策略

### 7.1 新增 tests/test_ciweimao_e2e.py
（见 §4.1 C5）

### 7.2 新增 unit tests（test_ciweimao_runner.py 内新增函数）
- `test_run_scraper_uses_env_var_port(monkeypatch)`: monkeypatch `WEBNOVEL_CIWEIMAO_CDP_PORT=9223`，mock subprocess.run，断言 cmd 含 `"--port"` `"9223"`
- `test_run_scraper_humanizes_node_not_found_error`: mock subprocess.run 抛 FileNotFoundError("node")，断言 RuntimeError message 含 "brew install node"
- `test_run_scraper_humanizes_chrome_not_running_error`: mock subprocess.run 返回 returncode=1, stderr 含 "CDP", 断言 RuntimeError 引用 setup_ciweimao 命令

### 7.3 保留（不动）
- `tests/test_ciweimao_runner_integration.py`：C1/C2 回归保护
- `tests/test_ciweimao_live.py`：手动 live 验证（更激进）
- `tests/test_ciweimao_adapter.py` / `test_ciweimao_runner.py`：现有 parser unit tests

### 7.4 pyproject.toml
新增 `[tool.pytest.ini_options] markers = ["slow: end-to-end tests requiring Chrome"]` （如已存在则跳过）

---

## 8. 验收标准

- [ ] 新 clone 此 plugin → 重启 Claude → 第一次 SessionStart 看到 ciweimao y/N 提示
- [ ] 接受 y → agent-browser + Chrome @ 9222 自动就绪 → 标记文件写入
- [ ] 下次 SessionStart 不再问
- [ ] 拒绝 N → 标记文件写入 → 下次 SessionStart 不再问
- [ ] 故意杀掉 Chrome → 跑 scan → 错误信息明确指向 setup_ciweimao 命令
- [ ] 设置 `WEBNOVEL_CIWEIMAO_CDP_PORT=9333` → setup 用 9333 启 Chrome → adapter 透传 9333 给 JS scraper
- [ ] `pytest -m slow` 在 Chrome 可用环境跑通；在不可用环境干净 skip（不 fail）
- [ ] `parse_category_html` 等死代码从 ciweimao.py 消失
- [ ] `pytest tests/` 全绿（不含 slow）

---

## 9. 风险与回退

| 风险 | 缓解 |
|------|------|
| Chrome `--headless=new` 与 agent-browser CDP 不兼容 | 先跑 `--headless=new`，如果 e2e 测试在常见环境失败，改用无 `--headless` 启动 |
| 后台 Chrome 进程泄漏（关 Claude 时未退出） | `start_new_session=True` 让 Chrome 独立于 Claude session；user_data_dir 在 cache 下，可手动清 |
| `npm install -g` 需要 sudo | 文档说明，失败信息指引用户手动 `sudo npm install -g agent-browser` |
| macOS Chrome 路径因系统版本变 | `find_chrome_binary` 第 4 级 fallback 复用 playwright chromium，覆盖 95% 场景 |
| agent-browser npm 包已废弃或改名 | 这是上游依赖，不在本 spec 控制范围；CI 测试若发现，列入未来 spec |
| 删除 parse_category_html 影响其他模块 | 已 grep 全仓，仅 ciweimao.py 使用，安全删除 |

---

## 10. 不在本 spec 范围（未来工作）

- 重写 ciweimao adapter 用 playwright 自管 chromium（替换 vendored CDP）
- Windows 平台 setup 脚本（agent-browser Windows shim 已在 cdp-utils.js 处理，但 launch_chrome 的 Chrome 路径检测需扩展）
- end-to-end CI 关卡在 GitHub Actions nightly 跑
- `word_count` 字段对 ciweimao 的语义修正（当前塞点击数/月票数，下游消费者已知）
- 跨 worktree port 冲突检测（目前靠用户手动设 env var）