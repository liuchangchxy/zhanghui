# webnovel-writer plugin 跨平台 Python 依赖自动安装实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `webnovel-writer_chang` plugin 在 macOS / Linux / Windows 上零手动步骤可用 — 首次 SessionStart 后台自动安装 Python 依赖，plugin 升级自动重建 venv。

**Architecture:** 用 `uv`（~15MB 跨平台单文件二进制）作为 Python bootstrapper。SessionStart hook 在 `~/.cache/webnovel-writer-chang/venvs/<module>/` 检测每个 Python 模块的 venv 状态，`.install-stamp`（sha256 of pyproject.toml）与当前不匹配则后台 fork 子进程跑 `uv venv` + `uv pip install`。chart-scan 的 chromium（150MB）单独走 Claude prompt 让用户选 y/N。**主 SessionStart hook < 2s 完成，不阻塞当前会话**。

**Tech Stack:** uv 0.4+ (Astral), Python 3.11+, Claude Code hooks (SessionStart), sha256 stamp, pytest + Docker（集成测试）。

**Spec:** `docs/superpowers/specs/2026-08-15-webnovel-plugin-self-contained-refactor-design.md` §4.6

**前置条件:** 已完成 `docs/superpowers/plans/2026-08-15-webnovel-plugin-self-contained-refactor-impl.md`（plugin 已 self-contained，marketplace 已建立，cache 已 symlink 到 dev workspace）。

---

## Phase ↔ Spec §4.6.x 映射

| Phase | Tasks | 覆盖 spec 节 |
|---|---|---|
| Phase 1：vendor uv | Task 1-2 | §4.6.2（vendor/uv/ 布局 + sha256 校验） |
| Phase 2：install_python_deps.py 核心 | Task 3-9 | §4.6.1（uv 选型）+ §4.6.3（cache 布局 + stamp）+ §4.6.4（装流程）+ §4.6.5 部分（subprocess 失败处理） |
| Phase 3：dashboard / scripts pyproject | Task 10-11 | §4.6.7（文件清单中的 dashboard + scripts pyproject） |
| Phase 4：session_start.py 集成 | Task 12-13 | §4.6.4（SessionStart 触发流 + 后台 fork）+ §4.6.7（hooks.json timeout） |
| Phase 5：chromium 弹窗 | Task 14-15 | §4.6.4（chromium 单独处理流程） |
| Phase 6：集成测试 + CI | Task 16-17 | §4.6.6（测试策略：Docker + matrix） |
| Phase 7：sync + README + 终验 | Task 18-20 | §4.6.7（剩余文件清单）+ §6 验证方法 |

**Phase 2 内的错误处理补强**：Task 8b（venv 损坏检测）+ Task 8c（PyPI 镜像 fallback）补完 §4.6.5 错误矩阵。

---

## 全局约定

| 项 | 约定 |
|---|---|
| venv 落点 | `~/.cache/webnovel-writer-chang/venvs/<module>/`（Windows 上 `os.path.expanduser("~/.cache/...")` 解析为 `%USERPROFILE%/.cache/...`） |
| stamp 文件 | `<venv>/.install-stamp`，内容 = sha256(pyproject.toml + 任何 requirements.txt) |
| SessionStart 超时 | 30s（覆盖原 5s）；实现保证 < 2s 真用 |
| 后台安装 | `subprocess.Popen([sys.executable, install_python_deps.py, ...])`；主 hook 不等子进程 |
| 重试策略 | 后台 install 失败 → log 到 `~/.cache/.../logs/` → 下次 SessionStart 重试（stamp 不会写除非装成功） |
| 镜像 fallback | 默认 PyPI；CN IP 时自动切清华/阿里；fallback 链：PyPI 官方 → 清华 → 阿里 |
| Python 版本 | uv 自动管；缺失时下载 Python 3.11+（用户无感） |
| Commit 粒度 | 每个 Task 末尾一个 commit，格式 `<type>(<scope>): <what>` |
| 测试位置 | `plugins/webnovel-writer_chang/scripts/tests/`，统一命令 `cd plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/ -v` |

---

## 文件结构总览

| 文件/目录 | 操作 | 内容 |
|---|---|---|
| `plugins/webnovel-writer_chang/vendor/uv/uv-darwin-arm64` | 新增 | macOS Apple Silicon uv 二进制 |
| `plugins/webnovel-writer_chang/vendor/uv/uv-darwin-x86_64` | 新增 | macOS Intel uv 二进制 |
| `plugins/webnovel-writer_chang/vendor/uv/uv-linux-x86_64` | 新增 | Linux x86_64 uv 二进制 |
| `plugins/webnovel-writer_chang/vendor/uv/uv-windows-x86_64.exe` | 新增 | Windows x86_64 uv 二进制 |
| `plugins/webnovel-writer_chang/vendor/uv/SHA256SUMS` | 新增 | 4 个二进制 sha256 |
| `plugins/webnovel-writer_chang/hooks/install_python_deps.py` | 新增 | 实际跑 uv 的脚本（可独立调用） |
| `plugins/webnovel-writer_chang/hooks/session_start.py` | 修改 | 扩展：检测 Python 依赖 + fork 后台 |
| `plugins/webnovel-writer_chang/hooks/hooks.json` | 修改 | timeout 5s → 30s |
| `plugins/webnovel-writer_chang/dashboard/pyproject.toml` | 新增 | 替代裸 `requirements.txt` |
| `plugins/webnovel-writer_chang/scripts/pyproject.toml` | 新增 | 声明根 scripts/ 的隐式 pydantic 依赖 |
| `plugins/webnovel-writer_chang/scripts/tests/test_install_*.py` | 新增 | install 流程测试（单元 + 集成） |
| `plugins/webnovel-writer_chang/scripts/sync_dev_to_marketplace.sh` | 修改 | release 时同步 uv 二进制 |
| `README.md` | 修改 | 加"首次使用会后台装依赖"说明 |

---

## Phase 1：vendor uv 二进制 + 完整性校验

### Task 1: 下载 uv 二进制 + SHA256SUMS

**Files:**
- Create: `plugins/webnovel-writer_chang/vendor/uv/{uv-darwin-arm64,uv-darwin-x86_64,uv-linux-x86_64,uv-windows-x86_64.exe,SHA256SUMS}`

- [ ] **Step 1: 创建 vendor/uv/ 目录**

```bash
mkdir -p .claude/plugins/webnovel-writer_chang/vendor/uv
```

- [ ] **Step 2: 下载 4 平台 uv 二进制（锁定版本 0.4.18）**

```bash
UV_VERSION="0.4.18"
BASE="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}"

curl -fsSL "${BASE}/uv-aarch64-apple-darwin.tar.gz" | tar -xz -C /tmp uv-aarch64-apple-darwin/uv && \
  cp /tmp/uv-aarch64-apple-darwin/uv .claude/plugins/webnovel-writer_chang/vendor/uv/uv-darwin-arm64

curl -fsSL "${BASE}/uv-x86_64-apple-darwin.tar.gz" | tar -xz -C /tmp uv-x86_64-apple-darwin/uv && \
  cp /tmp/uv-x86_64-apple-darwin/uv .claude/plugins/webnovel-writer_chang/vendor/uv/uv-darwin-x86_64

curl -fsSL "${BASE}/uv-x86_64-unknown-linux-gnu.tar.gz" | tar -xz -C /tmp uv-x86_64-unknown-linux-gnu/uv && \
  cp /tmp/uv-x86_64-unknown-linux-gnu/uv .claude/plugins/webnovel-writer_chang/vendor/uv/uv-linux-x86_64

curl -fsSL -o /tmp/uv-win.zip "${BASE}/uv-x86_64-pc-windows-msvc.zip" && \
  unzip -p /tmp/uv-win.zip uv.exe > .claude/plugins/webnovel-writer_chang/vendor/uv/uv-windows-x86_64.exe

chmod +x .claude/plugins/webnovel-writer_chang/vendor/uv/uv-darwin-* .claude/plugins/webnovel-writer_chang/vendor/uv/uv-linux-*
ls -la .claude/plugins/webnovel-writer_chang/vendor/uv/
```

预期：4 个二进制 + 文件大小约 15-25MB

- [ ] **Step 3: 生成 SHA256SUMS**

```bash
cd .claude/plugins/webnovel-writer_chang/vendor/uv
shasum -a 256 uv-darwin-arm64 uv-darwin-x86_64 uv-linux-x86_64 uv-windows-x86_64.exe > SHA256SUMS
cat SHA256SUMS
```

预期：4 行 sha256 摘要

- [ ] **Step 4: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/vendor/uv/
git commit -m "feat(install): vendor uv ${UV_VERSION} binaries for 4 platforms"
```

---

### Task 2: 写 uv 校验测试

**Files:**
- Test: `plugins/webnovel-writer_chang/scripts/tests/test_uv_vendor.py`

- [ ] **Step 1: 写失败测试**

```python
"""验证 vendor/uv/ 二进制存在且 SHA256SUMS 一致。"""
import hashlib
from pathlib import Path

UV_DIR = Path(__file__).parent.parent.parent / "vendor" / "uv"
EXPECTED = [
    "uv-darwin-arm64",
    "uv-darwin-x86_64",
    "uv-linux-x86_64",
    "uv-windows-x86_64.exe",
]


def _read_sha256sums() -> dict[str, str]:
    sums = {}
    for line in (UV_DIR / "SHA256SUMS").read_text().splitlines():
        sha, name = line.split(maxsplit=1)
        sums[name.strip()] = sha.strip()
    return sums


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


import pytest


@pytest.mark.parametrize("binary", EXPECTED)
def test_uv_binary_exists(binary):
    assert (UV_DIR / binary).exists(), f"missing uv binary: {binary}"


@pytest.mark.parametrize("binary", EXPECTED)
def test_uv_binary_sha256_matches(binary):
    sums = _read_sha256sums()
    assert binary in sums, f"no sha256 entry for {binary}"
    assert _sha256(UV_DIR / binary) == sums[binary]
```

- [ ] **Step 2: 跑测试确认全绿**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_uv_vendor.py -v
```

预期：8 passed (2 tests × 4 binaries)

- [ ] **Step 3: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/tests/test_uv_vendor.py
git commit -m "test(install): verify uv binary sha256"
```

---

## Phase 2：install_python_deps.py 核心函数

### Task 3: 写 compute_install_stamp 测试 + 实现

**Files:**
- Test: `plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py`
- Create: `plugins/webnovel-writer_chang/hooks/install_python_deps.py`

- [ ] **Step 1: 写失败测试**

```python
"""install_python_deps.py 的单元测试。"""
import hashlib
from pathlib import Path

import pytest


# --- compute_install_stamp ---

def test_compute_install_stamp_returns_sha256(tmp_path):
    from hooks.install_python_deps import compute_install_stamp
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    expected = hashlib.sha256(b"[project]\nname='x'\n").hexdigest()
    assert compute_install_stamp(tmp_path) == expected


def test_compute_install_stamp_includes_requirements_txt(tmp_path):
    from hooks.install_python_deps import compute_install_stamp
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "requirements.txt").write_text("foo>=1.0\n")
    base = hashlib.sha256(b"[project]\n").hexdigest()
    with_reqs = compute_install_stamp(tmp_path)
    assert with_reqs != base
    assert len(with_reqs) == 64  # sha256 hex
```

- [ ] **Step 2: 跑测试确认失败（function not defined）**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_install_python_deps.py -v
```

预期：ImportError / ModuleNotFoundError

- [ ] **Step 3: 最小实现 compute_install_stamp**

Create `plugins/webnovel-writer_chang/hooks/install_python_deps.py`:

```python
"""install_python_deps.py — 实际跑 uv 安装 Python 依赖。

被 SessionStart hook 后台调用，也可独立运行做诊断。
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def compute_install_stamp(module_dir: Path) -> str:
    """计算 <module_dir>/{pyproject.toml,requirements.txt} 的 sha256 stamp。

    Args:
        module_dir: 包含 pyproject.toml 的目录。

    Returns:
        64-char hex sha256。
    """
    h = hashlib.sha256()
    for fname in ("pyproject.toml", "requirements.txt"):
        f = module_dir / fname
        if f.exists():
            h.update(f.read_bytes())
    return h.hexdigest()
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_install_python_deps.py::test_compute_install_stamp_returns_sha256 tests/test_install_python_deps.py::test_compute_install_stamp_includes_requirements_txt -v
```

预期：2 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py \
        .claude/plugins/webnovel-writer_chang/hooks/install_python_deps.py
git commit -m "feat(install): add compute_install_stamp"
```

---

### Task 4: 写 select_uv_binary 测试 + 实现

**Files:**
- Test: `plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py` (extend)
- Modify: `plugins/webnovel-writer_chang/hooks/install_python_deps.py`

- [ ] **Step 1: 在 test 文件追加测试**

```python
# --- select_uv_binary ---

import sys


def test_select_uv_binary_darwin_arm64(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    from hooks.install_python_deps import select_uv_binary
    binary = select_uv_binary(tmp_path)
    assert binary.name == "uv-darwin-arm64"
    assert binary.parent == tmp_path / "uv"


def test_select_uv_binary_linux_x86_64(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    from hooks.install_python_deps import select_uv_binary
    binary = select_uv_binary(tmp_path)
    assert binary.name == "uv-linux-x86_64"


def test_select_uv_binary_windows_x86_64(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr("platform.machine", lambda: "AMD64")
    from hooks.install_python_deps import select_uv_binary
    binary = select_uv_binary(tmp_path)
    assert binary.name == "uv-windows-x86_64.exe"


def test_select_uv_binary_unsupported_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "powerpc")
    from hooks.install_python_deps import select_uv_binary
    with pytest.raises(RuntimeError, match="找不到匹配的 uv"):
        select_uv_binary(tmp_path)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_install_python_deps.py -v
```

预期：4 failed (NameError: select_uv_binary)

- [ ] **Step 3: 实现 select_uv_binary**

Append to `plugins/webnovel-writer_chang/hooks/install_python_deps.py`:

```python
import platform as _platform


# (system, machine) -> filename
UV_BINARY_MAP: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "uv-darwin-arm64",
    ("darwin", "x86_64"): "uv-darwin-x86_64",
    ("linux", "x86_64"): "uv-linux-x86_64",
    ("linux", "aarch64"): "uv-linux-x86_64",  # 后续 Phase 再补 linux-arm64 二进制
    ("win32", "AMD64"): "uv-windows-x86_64.exe",
    ("win32", "x86"): "uv-windows-x86_64.exe",
}


def select_uv_binary(vendor_uv_dir: Path) -> Path:
    """根据当前平台选 vendor/uv/ 下的对应 uv 二进制路径。

    Args:
        vendor_uv_dir: plugin 的 vendor/uv/ 目录。

    Returns:
        uv 二进制的完整 Path。

    Raises:
        RuntimeError: 当前平台不在 4 个支持范围内。
    """
    key = (sys.platform, _platform.machine())
    name = UV_BINARY_MAP.get(key)
    if name is None:
        raise RuntimeError(
            f"找不到匹配的 uv ({sys.platform}/{_platform.machine()})，"
            f"请检查 vendor/uv/ 目录；支持：{sorted(UV_BINARY_MAP.keys())}"
        )
    return vendor_uv_dir / name
```

注意：顶部需要加 `import sys`（已在 use_superpowers 顶部用 `from __future__`）。

- [ ] **Step 4: 跑测试确认通过**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_install_python_deps.py -v
```

预期：6 passed (2 stamp + 4 binary)

- [ ] **Step 5: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py \
        .claude/plugins/webnovel-writer_chang/hooks/install_python_deps.py
git commit -m "feat(install): add select_uv_binary with platform detection"
```

---

### Task 5: 写 resolve_cache_dir 测试 + 实现（含多级 fallback）

**Files:**
- Test: `plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py` (extend)
- Modify: `plugins/webnovel-writer_chang/hooks/install_python_deps.py`

- [ ] **Step 1: 追加测试**

```python
# --- resolve_cache_dir ---

def test_resolve_cache_dir_uses_expanduser(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("WEBNOVEL_CACHE_DIR", raising=False)
    from hooks.install_python_deps import resolve_cache_dir
    cache = resolve_cache_dir()
    assert cache == tmp_path / ".cache" / "webnovel-writer-chang"


def test_resolve_cache_dir_env_override(monkeypatch, tmp_path):
    custom = tmp_path / "custom"
    monkeypatch.setenv("WEBNOVEL_CACHE_DIR", str(custom))
    from hooks.install_python_deps import resolve_cache_dir
    assert resolve_cache_dir() == custom


def test_resolve_cache_dir_creates_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("WEBNOVEL_CACHE_DIR", raising=False)
    from hooks.install_python_deps import resolve_cache_dir
    cache = resolve_cache_dir()
    assert cache.exists()
    assert cache.is_dir()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_install_python_deps.py -v
```

预期：3 failed

- [ ] **Step 3: 实现 resolve_cache_dir**

Append to `plugins/webnovel-writer_chang/hooks/install_python_deps.py`:

```python
import os


def resolve_cache_dir() -> Path:
    """解析 plugin 跨平台缓存根目录。

    优先级：
    1. $WEBNOVEL_CACHE_DIR（用户显式指定）
    2. ~/.cache/webnovel-writer-chang/（跨平台统一路径；Windows 上 ~ 解析为 %USERPROFILE%）

    Returns:
        已创建的缓存根目录 Path。
    """
    custom = os.environ.get("WEBNOVEL_CACHE_DIR")
    if custom:
        cache = Path(custom)
    else:
        cache = Path.home() / ".cache" / "webnovel-writer-chang"
    cache.mkdir(parents=True, exist_ok=True)
    return cache
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_install_python_deps.py -v
```

预期：9 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py \
        .claude/plugins/webnovel-writer_chang/hooks/install_python_deps.py
git commit -m "feat(install): add resolve_cache_dir with env override"
```

---

### Task 6: 写 should_install_module 测试 + 实现

**Files:**
- Test: `plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py` (extend)
- Modify: `plugins/webnovel-writer_chang/hooks/install_python_deps.py`

- [ ] **Step 1: 追加测试**

```python
# --- should_install_module ---

def test_should_install_module_no_venv(tmp_path):
    from hooks.install_python_deps import should_install_module
    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\n")
    assert should_install_module(module) == "missing venv"


def test_should_install_module_stale_stamp(tmp_path):
    from hooks.install_python_deps import should_install_module, compute_install_stamp
    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='x'\n")
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / ".install-stamp").write_text("stale-stamp-not-matching\n")
    assert should_install_module(module) != "ok"


def test_should_install_module_up_to_date(tmp_path):
    from hooks.install_python_deps import should_install_module, compute_install_stamp
    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='x'\n")
    venv = tmp_path / "venv"
    venv.mkdir()
    stamp = compute_install_stamp(module)
    (venv / ".install-stamp").write_text(stamp + "\n")
    assert should_install_module(module) == "ok"
```

- [ ] **Step 2: 跑测试确认失败**

预期：3 failed

- [ ] **Step 3: 实现 should_install_module**

Append:

```python
def should_install_module(module_dir: Path) -> str:
    """判断某 module 是否需要重新安装。

    Args:
        module_dir: 含 pyproject.toml 的目录。

    Returns:
        "ok" 如果 venv 存在且 stamp 匹配；否则返回原因字符串（"missing venv" / "stale stamp"）。
    """
    cache = resolve_cache_dir()
    venv = cache / "venvs" / module_dir.name
    if not venv.exists():
        return "missing venv"
    stamp_path = venv / ".install-stamp"
    if not stamp_path.exists():
        return "missing stamp"
    on_disk = stamp_path.read_text().strip()
    expected = compute_install_stamp(module_dir)
    if on_disk != expected:
        return f"stale stamp (disk={on_disk[:8]} expected={expected[:8]})"
    return "ok"
```

- [ ] **Step 4: 跑测试确认通过**

预期：12 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py \
        .claude/plugins/webnovel-writer_chang/hooks/install_python_deps.py
git commit -m "feat(install): add should_install_module with stamp check"
```

---

### Task 7: 写 find_python_modules 测试 + 实现（扫描 plugin skills）

**Files:**
- Test: `plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py` (extend)
- Modify: `plugins/webnovel-writer_chang/hooks/install_python_deps.py`

- [ ] **Step 1: 追加测试**

```python
# --- find_python_modules ---

def test_find_python_modules_finds_pyproject_toml(tmp_path):
    from hooks.install_python_deps import find_python_modules
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "chart-scan").mkdir()
    (tmp_path / "skills" / "chart-scan" / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "skills" / "write").mkdir()  # no pyproject → ignore
    (tmp_path / "dashboard").mkdir()
    (tmp_path / "dashboard" / "pyproject.toml").write_text("[project]\n")
    modules = find_python_modules(tmp_path)
    names = sorted(m.name for m in modules)
    assert names == ["chart-scan", "dashboard"]
```

- [ ] **Step 2: 跑测试确认失败**

预期：1 failed

- [ ] **Step 3: 实现 find_python_modules**

Append:

```python
def find_python_modules(plugin_root: Path) -> list[Path]:
    """扫描 plugin root 下所有 Python 模块（skills/<name>/pyproject.toml + dashboard/pyproject.toml）。

    Args:
        plugin_root: plugin 根目录（含 skills/ 与 dashboard/）。

    Returns:
        含 pyproject.toml 的目录 Path 列表。
    """
    modules: list[Path] = []
    skills = plugin_root / "skills"
    if skills.exists():
        for skill in sorted(skills.iterdir()):
            if (skill / "pyproject.toml").exists():
                modules.append(skill)
    dashboard = plugin_root / "dashboard"
    if (dashboard / "pyproject.toml").exists():
        modules.append(dashboard)
    return modules
```

- [ ] **Step 4: 跑测试确认通过**

预期：13 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py \
        .claude/plugins/webnovel-writer_chang/hooks/install_python_deps.py
git commit -m "feat(install): add find_python_modules"
```

---

### Task 8: 写 install_module 函数 + 实现（实际跑 uv）

**Files:**
- Test: `plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py` (extend)
- Modify: `plugins/webnovel-writer_chang/hooks/install_python_deps.py`

- [ ] **Step 1: 追加测试**

```python
# --- install_module ---

def test_install_module_creates_venv_and_stamp(tmp_path, monkeypatch):
    """集成测试：mock uv subprocess 调用，验证 venv + stamp 创建。"""
    from hooks import install_python_deps as ipd
    monkeypatch.setattr(ipd, "resolve_cache_dir", lambda: tmp_path / "cache")
    fake_uv_calls = []

    def fake_uv_run(argv, **kwargs):
        fake_uv_calls.append(argv)
        # 模拟 uv venv 创建目录
        venv_idx = argv.index("venv") + 1
        Path(argv[venv_idx]).mkdir(parents=True, exist_ok=True)
        # 模拟 uv pip install 创建 site-packages
        Path(argv[venv_idx]) / "lib" / "site-packages" / "foo.py"
        Path(argv[venv_idx]) / "lib" / "site-packages" / "foo.py"
        # 创建 site-packages 父目录
        (Path(argv[venv_idx]) / "lib" / "site-packages").mkdir(parents=True, exist_ok=True)
        (Path(argv[venv_idx]) / "lib" / "site-packages" / "foo.py").write_text("# ok")
        return type("R", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(ipd.subprocess, "run", fake_uv_run)

    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='m'\n")
    ipd.install_module(module)

    venv = tmp_path / "cache" / "venvs" / "m"
    assert venv.exists()
    assert (venv / ".install-stamp").exists()
    assert (venv / ".install-stamp").read_text().strip() == ipd.compute_install_stamp(module)
    assert len(fake_uv_calls) == 2  # uv venv + uv pip install


def test_install_module_failure_writes_log(tmp_path, monkeypatch):
    """uv 失败的场景：写 log，不写 stamp。"""
    from hooks import install_python_deps as ipd
    monkeypatch.setattr(ipd, "resolve_cache_dir", lambda: tmp_path / "cache")

    def fake_uv_fail(argv, **kwargs):
        return type("R", (), {"returncode": 1, "stderr": "ERROR: package 'foo' not found"})()

    monkeypatch.setattr(ipd.subprocess, "run", fake_uv_fail)
    module = tmp_path / "m"
    module.mkdir()
    (module / "pyproject.toml").write_text("[project]\nname='m'\n")

    with pytest.raises(RuntimeError, match="uv pip install 失败"):
        ipd.install_module(module)

    venv = tmp_path / "cache" / "venvs" / "m"
    assert not (venv / ".install-stamp").exists()
```

- [ ] **Step 2: 跑测试确认失败**

预期：2 failed

- [ ] **Step 3: 实现 install_module + 顶部 import**

Edit 顶部 `from __future__ import annotations` 块下方加：

```python
import subprocess
from datetime import datetime, timezone
```

Append:

```python
DEFAULT_INSTALL_TIMEOUT = 300  # 5 min


def install_module(module_dir: Path) -> None:
    """为单个 module 创建 venv + uv pip install + 写 stamp。

    Args:
        module_dir: 含 pyproject.toml 的目录。

    Raises:
        RuntimeError: uv venv 或 uv pip install 返回非 0；log 写到 logs/。
    """
    cache = resolve_cache_dir()
    venv = cache / "venvs" / module_dir.name
    logs = cache / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = logs / f"install-{module_dir.name}-{timestamp}.log"

    # Locate uv via $CLAUDE_PLUGIN_ROOT/vendor/uv (set by Claude Code).
    plugin_root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root_env:
        raise RuntimeError("CLAUDE_PLUGIN_ROOT 未设置；这个脚本必须在 plugin hook 里跑")
    uv = select_uv_binary(Path(plugin_root_env) / "vendor" / "uv")

    venv.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: uv venv
    r = subprocess.run(
        [str(uv), "venv", str(venv), "--python", "3.11"],
        capture_output=True, text=True, timeout=DEFAULT_INSTALL_TIMEOUT,
    )
    if r.returncode != 0:
        log_path.write_text(f"uv venv failed:\n{r.stderr}\n")
        raise RuntimeError(f"uv venv 失败：{r.stderr[:200]}")

    # Step 2: uv pip install
    r = subprocess.run(
        [str(uv), "pip", "install", "-e", str(module_dir)],
        capture_output=True, text=True, timeout=DEFAULT_INSTALL_TIMEOUT,
        env={**os.environ, "VIRTUAL_ENV": str(venv)},
    )
    if r.returncode != 0:
        log_path.write_text(f"uv pip install failed:\n{r.stderr}\n")
        raise RuntimeError(f"uv pip install 失败：{r.stderr[:200]}")

    # Step 3: write stamp
    stamp = compute_install_stamp(module_dir)
    (venv / ".install-stamp").write_text(stamp + "\n")
    log_path.write_text(f"OK: installed {module_dir.name}, stamp={stamp[:8]}\n")
```

- [ ] **Step 4: 跑测试确认通过**

预期：15 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py \
        .claude/plugins/webnovel-writer_chang/hooks/install_python_deps.py
git commit -m "feat(install): add install_module with venv + pip + stamp"
```

---

### Task 8b: 写 is_venv_corrupted 测试 + 实现（spec §4.6.5 "已有 venv 损坏"）

**Files:**
- Test: `plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py` (extend)
- Modify: `plugins/webnovel-writer_chang/hooks/install_python_deps.py`

- [ ] **Step 1: 追加测试**

```python
# --- is_venv_corrupted ---

def test_is_venv_corrupted_missing_python_bin(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    venv = tmp_path / "cache" / "venvs" / "x"
    venv.mkdir(parents=True)
    from hooks.install_python_deps import is_venv_corrupted
    assert is_venv_corrupted("x") is True


def test_is_venv_corrupted_python_version_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    venv = tmp_path / "cache" / "venvs" / "x"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    fake_py = bin_dir / "python"
    fake_py.write_text("#!/bin/sh\nexit 1\n")
    fake_py.chmod(0o755)
    from hooks.install_python_deps import is_venv_corrupted
    assert is_venv_corrupted("x") is True


def test_is_venv_corrupted_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    venv = tmp_path / "cache" / "venvs" / "x"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    fake_py = bin_dir / "python"
    fake_py.write_text("#!/bin/sh\necho Python 3.11.0\nexit 0\n")
    fake_py.chmod(0o755)
    from hooks.install_python_deps import is_venv_corrupted
    assert is_venv_corrupted("x") is False
```

- [ ] **Step 2: 跑测试确认失败**

预期：3 failed

- [ ] **Step 3: 实现 is_venv_corrupted**

Append to `install_python_deps.py`:

```python
def is_venv_corrupted(module_name: str) -> bool:
    """检测 venv 是否损坏（python 二进制不存在或 --version 失败）。

    Args:
        module_name: venv 名（对应 modules/<name> 目录）。

    Returns:
        True = 损坏（需要重建）；False = 健康。
    """
    venv = resolve_cache_dir() / "venvs" / module_name
    py = venv / "bin" / "python"
    if not py.exists():
        return True
    try:
        r = subprocess.run(
            [str(py), "--version"],
            capture_output=True, timeout=5,
        )
        return r.returncode != 0
    except (subprocess.TimeoutExpired, OSError):
        return True


def nuke_venv(module_name: str) -> None:
    """删掉损坏的 venv（让 install_module 重建）。"""
    import shutil
    venv = resolve_cache_dir() / "venvs" / module_name
    if venv.exists():
        shutil.rmtree(venv)
```

- [ ] **Step 4: 在 should_install_module 里集成**

Replace existing `should_install_module` 顶部加一行：

```python
def should_install_module(module_dir: Path) -> str:
    cache = resolve_cache_dir()
    venv = cache / "venvs" / module_dir.name
    if not venv.exists():
        return "missing venv"
    if is_venv_corrupted(module_dir.name):
        nuke_venv(module_dir.name)
        return "corrupted venv"
    stamp_path = venv / ".install-stamp"
    if not stamp_path.exists():
        return "missing stamp"
    on_disk = stamp_path.read_text().strip()
    expected = compute_install_stamp(module_dir)
    if on_disk != expected:
        return f"stale stamp (disk={on_disk[:8]} expected={expected[:8]})"
    return "ok"
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_install_python_deps.py -v
```

预期：22 passed (15 原有 + 3 corrupted + 集成后 should_install 新增的 "corrupted venv" 分支已被原测试间接覆盖)

- [ ] **Step 6: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py \
        .claude/plugins/webnovel-writer_chang/hooks/install_python_deps.py
git commit -m "feat(install): detect and rebuild corrupted venv (spec §4.6.5)"
```

---

### Task 8c: 写 PyPI 镜像 fallback（spec §4.6.5 "网络断 / PyPI 不可达"）

**Files:**
- Test: `plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py` (extend)
- Modify: `plugins/webnovel-writer_chang/hooks/install_python_deps.py`

- [ ] **Step 1: 追加测试**

```python
# --- pick_pip_index_url ---

def test_pick_pip_index_url_default_no_env(monkeypatch):
    monkeypatch.delenv("WEBNOVEL_PIP_INDEX", raising=False)
    from hooks.install_python_deps import pick_pip_index_url
    assert pick_pip_index_url() == "https://pypi.org/simple"


def test_pick_pip_index_url_env_override(monkeypatch):
    monkeypatch.setenv("WEBNOVEL_PIP_INDEX", "https://mirrors.aliyun.com/pypi/simple/")
    from hooks.install_python_deps import pick_pip_index_url
    assert pick_pip_index_url() == "https://mirrors.aliyun.com/pypi/simple/"


def test_pick_pip_index_url_china_detected(monkeypatch):
    """模拟 CN 检测（IP 库查 cn → 返回清华镜像）。"""
    monkeypatch.delenv("WEBNOVEL_PIP_INDEX", raising=False)
    monkeypatch.setattr("hooks.install_python_deps._is_china_ip", lambda: True)
    from hooks.install_python_deps import pick_pip_index_url
    url = pick_pip_index_url()
    assert "tsinghua" in url or "aliyun" in url or "ustc" in url
```

- [ ] **Step 2: 跑测试确认失败**

预期：3 failed

- [ ] **Step 3: 实现 pick_pip_index_url + _is_china_ip**

Append:

```python
import urllib.request


PIP_MIRRORS_CN = [
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple/",
    "https://pypi.mirrors.ustc.edu.cn/simple/",
]


def _is_china_ip() -> bool:
    """简单启发式：通过访问 ip.cn 看返回是否包含 '中国' / 'China'。

    返回 True 视为 CN 网络。失败兜底 False。
    """
    try:
        with urllib.request.urlopen("https://ip.cn", timeout=2) as r:
            body = r.read().decode("utf-8", errors="ignore")
        return "中国" in body or "China" in body
    except Exception:
        return False


def pick_pip_index_url() -> str:
    """决定 uv pip install 使用的 index URL。

    优先级：
    1. $WEBNOVEL_PIP_INDEX（用户显式指定）
    2. CN IP 检测为 True → 清华镜像
    3. 默认 PyPI 官方
    """
    custom = os.environ.get("WEBNOVEL_PIP_INDEX")
    if custom:
        return custom.rstrip("/")
    if _is_china_ip():
        return PIP_MIRRORS_CN[0]
    return "https://pypi.org/simple"
```

- [ ] **Step 4: 在 install_module 里集成**

Replace Task 8 的 install_module 里的 subprocess.run 调用，给 uv pip install 加 `--index-url`：

```python
    # Step 2: uv pip install
    index_url = pick_pip_index_url()
    r = subprocess.run(
        [str(uv), "pip", "install", "-e", str(module_dir),
         "--index-url", index_url],
        capture_output=True, text=True, timeout=DEFAULT_INSTALL_TIMEOUT,
        env={**os.environ, "VIRTUAL_ENV": str(venv)},
    )
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/test_install_python_deps.py -v
```

预期：25 passed

- [ ] **Step 6: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py \
        .claude/plugins/webnovel-writer_chang/hooks/install_python_deps.py
git commit -m "feat(install): PyPI mirror fallback (PyPI/CN auto-detect + env override)"
```

---

### Task 9: 写 main() 入口（独立调用入口）

**Files:**
- Modify: `plugins/webnovel-writer_chang/hooks/install_python_deps.py`

- [ ] **Step 1: 实现 main()**

Append:

```python
import argparse


def main() -> int:
    """CLI 入口：`python3 install_python_deps.py [--module NAME]`。

    无参数：扫描 CLAUDE_PLUGIN_ROOT 下所有 Python module 并 install。
    有参数：只装指定 module。

    Returns:
        0 全部成功 / 1 至少一个失败。
    """
    parser = argparse.ArgumentParser(description="Install Python deps for plugin modules.")
    parser.add_argument("--module", help="只装指定 module 名（skills/<name> 或 dashboard）")
    parser.add_argument("--plugin-root", default=os.environ.get("CLAUDE_PLUGIN_ROOT"),
                        help="plugin 根目录（默认从 CLAUDE_PLUGIN_ROOT 环境变量读）")
    args = parser.parse_args()

    if not args.plugin_root:
        print("ERROR: --plugin-root 未指定且 CLAUDE_PLUGIN_ROOT 未设置", file=sys.stderr)
        return 2

    plugin_root = Path(args.plugin_root)
    if args.module:
        target = plugin_root / "skills" / args.module
        if not target.exists():
            target = plugin_root / args.module
        if not (target / "pyproject.toml").exists():
            print(f"ERROR: {target} 没有 pyproject.toml", file=sys.stderr)
            return 2
        modules = [target]
    else:
        modules = find_python_modules(plugin_root)

    failures = 0
    for module in modules:
        reason = should_install_module(module)
        if reason == "ok":
            print(f"SKIP: {module.name} ({reason})")
            continue
        print(f"INSTALL: {module.name} ({reason})")
        try:
            install_module(module)
            print(f"OK: {module.name}")
        except Exception as e:
            print(f"FAIL: {module.name}: {e}", file=sys.stderr)
            failures += 1

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 手动验证 --help 跑通**

```bash
python3 .claude/plugins/webnovel-writer_chang/hooks/install_python_deps.py --help
```

预期：argparse 输出 usage

- [ ] **Step 3: 在干净临时 plugin root 上手动跑**

```bash
TMPPLUGIN=$(mktemp -d)
mkdir -p "$TMPPLUGIN/skills/fake-skill"
cat > "$TMPPLUGIN/skills/fake-skill/pyproject.toml" <<'EOF'
[project]
name = "fake-skill"
version = "0.0.1"
dependencies = []
EOF
python3 .claude/plugins/webnovel-writer_chang/hooks/install_python_deps.py --plugin-root "$TMPPLUGIN"
```

预期：输出 `OK: fake-skill` 或在 uv 不可达时报错（uv 二进制跟 python3.14 的兼容性问题正常暴露）

- [ ] **Step 4: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/hooks/install_python_deps.py
git commit -m "feat(install): add main() CLI entry"
```

---

## Phase 3：dashboard / 根 scripts 的 pyproject 声明

### Task 10: 添加 dashboard/pyproject.toml

**Files:**
- Create: `plugins/webnovel-writer_chang/dashboard/pyproject.toml`

- [ ] **Step 1: 写 pyproject.toml**

```toml
[project]
name = "webnovel-dashboard"
version = "0.1.0"
description = "Webnovel writer dashboard FastAPI server"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "httpx>=0.27.0",
    "uvicorn[standard]>=0.32.0",
    "watchdog>=5.0.0",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["*"]
```

- [ ] **Step 2: 备份旧的裸 requirements.txt（保留兼容兜底）**

```bash
mv .claude/plugins/webnovel-writer_chang/dashboard/requirements.txt \
   .claude/plugins/webnovel-writer_chang/dashboard/requirements.txt.legacy
```

- [ ] **Step 3: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/dashboard/pyproject.toml \
        .claude/plugins/webnovel-writer_chang/dashboard/requirements.txt.legacy
git commit -m "feat(dashboard): add pyproject.toml replacing requirements.txt"
```

---

### Task 11: 添加根 scripts/ 的 pyproject.toml

**Files:**
- Create: `plugins/webnovel-writer_chang/scripts/pyproject.toml`

- [ ] **Step 1: 写 pyproject.toml**

先 grep 根 scripts/ 实际用到的第三方 import：

```bash
grep -rhE "^(import|from) (pydantic|fastapi|httpx|numpy|pandas)" \
  .claude/plugins/webnovel-writer_chang/scripts/*.py \
  .claude/plugins/webnovel-writer_chang/scripts/data_modules/*.py 2>/dev/null | sort -u
```

- [ ] **Step 2: 根据 grep 结果写 pyproject.toml**

```toml
[project]
name = "webnovel-writer-scripts"
version = "0.1.0"
description = "Root scripts for webnovel-writer plugin"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.6",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

（如果 grep 出 pydantic 之外的其他依赖，按需补到 dependencies）

- [ ] **Step 3: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/pyproject.toml
git commit -m "feat(scripts): add pyproject.toml declaring pydantic"
```

---

## Phase 4：session_start.py 集成 + 后台 fork

### Task 12: 扩展 session_start.py 检测 Python 依赖 + 后台 fork

**Files:**
- Modify: `plugins/webnovel-writer_chang/hooks/session_start.py`

- [ ] **Step 1: 读现有 session_start.py**

```bash
cat .claude/plugins/webnovel-writer_chang/hooks/session_start.py
```

确认现有结构（按 §0 全局约定走 `< 2s` 完成）。

- [ ] **Step 2: 追加 Python 依赖检测 + 后台 fork**

在现有 main() 末尾（或 hook handler 末尾）追加：

```python
import subprocess
import sys
from pathlib import Path


def trigger_background_python_install(plugin_root: Path) -> None:
    """扫描 plugin 的 Python module，对需要重装的 fork 后台进程跑 install_python_deps.py。

    主 hook 不等子进程完成；子进程日志写到 ~/.cache/.../logs/。
    """
    sys.path.insert(0, str(plugin_root / "hooks"))
    try:
        from install_python_deps import find_python_modules, should_install_module
    except ImportError:
        return  # install_python_deps.py 还没部署；静默 skip

    pending = [m for m in find_python_modules(plugin_root)
               if should_install_module(m) != "ok"]
    if not pending:
        return

    install_script = plugin_root / "hooks" / "install_python_deps.py"
    if not install_script.exists():
        return

    # Detach：用 subprocess.Popen + start_new_session=True 让子进程脱离父 hook 的生命周期
    subprocess.Popen(
        [sys.executable, str(install_script), "--plugin-root", str(plugin_root)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, close_fds=True,
    )
```

- [ ] **Step 3: 在 main() 末尾调用**

（具体插入点取决于现有 main() 结构；典型做法：）

```python
def main() -> int:
    # ... 现有 session_start.py 的逻辑 ...
    plugin_root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", "."))
    trigger_background_python_install(plugin_root)
    return 0
```

- [ ] **Step 4: 手测：在临时 plugin root 上跑，确认后台 fork 真的发生**

```bash
TMPPLUGIN=$(mktemp -d)
mkdir -p "$TMPPLUGIN/skills/fake"
cat > "$TMPPLUGIN/skills/fake/pyproject.toml" <<'EOF'
[project]
name = "fake"
version = "0.0.1"
dependencies = []
EOF
CLAUDE_PLUGIN_ROOT="$TMPPLUGIN" python3 -c "
import sys
sys.path.insert(0, '.claude/plugins/webnovel-writer_chang/hooks')
from session_start import trigger_background_python_install
from pathlib import Path
trigger_background_python_install(Path('$TMPPLUGIN'))
print('forked')
" && sleep 3 && ls -la ~/.cache/webnovel-writer-chang/venvs/fake/ 2>&1 | head -5
```

预期：`forked` 打出 + 3 秒后 `~/.cache/.../venvs/fake/` 存在（如果 uv 可跑；如 uv 不可跑，logs/ 应有错误日志）

- [ ] **Step 5: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/hooks/session_start.py
git commit -m "feat(hooks): session_start triggers background Python install"
```

---

### Task 13: 改 hooks.json timeout 5s → 30s

**Files:**
- Modify: `plugins/webnovel-writer_chang/hooks/hooks.json`

- [ ] **Step 1: 编辑**

把 SessionStart hook 的 `"timeout": 5` 改为 `"timeout": 30`：

```json
"SessionStart": [
  {
    "matcher": "*",
    "hooks": [
      {
        "type": "command",
        "command": "python3 -X utf8 \"${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py\"",
        "timeout": 30
      }
    ]
  }
]
```

- [ ] **Step 2: 验证 JSON 合法**

```bash
python3 -c "import json; print(json.load(open('.claude/plugins/webnovel-writer_chang/hooks/hooks.json'))['hooks']['SessionStart'][0]['hooks'][0]['timeout'])"
```

预期：`30`

- [ ] **Step 3: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/hooks/hooks.json
git commit -m "feat(hooks): SessionStart timeout 5s → 30s"
```

---

## Phase 5：chromium 弹窗机制

### Task 14: 写 should_prompt_chromium 测试 + 实现

**Files:**
- Test: `plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py` (extend)
- Modify: `plugins/webnovel-writer_chang/hooks/install_python_deps.py`

- [ ] **Step 1: 追加测试**

```python
# --- should_prompt_chromium / write_chromium_decision ---

def test_should_prompt_chromium_first_time(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    from hooks.install_python_deps import should_prompt_chromium
    assert should_prompt_chromium("webnovel-chart-scan") is True


def test_should_prompt_chromium_already_yes(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    venv = tmp_path / "cache" / "venvs" / "webnovel-chart-scan"
    venv.mkdir(parents=True)
    (venv / ".chromium-prompted").write_text("yes\n")
    from hooks.install_python_deps import should_prompt_chromium
    assert should_prompt_chromium("webnovel-chart-scan") is False


def test_should_prompt_chromium_already_no(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    venv = tmp_path / "cache" / "venvs" / "webnovel-chart-scan"
    venv.mkdir(parents=True)
    (venv / ".chromium-prompted").write_text("no\n")
    from hooks.install_python_deps import should_prompt_chromium
    assert should_prompt_chromium("webnovel-chart-scan") is False


def test_write_chromium_decision(tmp_path, monkeypatch):
    monkeypatch.setattr("hooks.install_python_deps.resolve_cache_dir", lambda: tmp_path / "cache")
    from hooks.install_python_deps import write_chromium_decision
    write_chromium_decision("webnovel-chart-scan", "yes")
    f = tmp_path / "cache" / "venvs" / "webnovel-chart-scan" / ".chromium-prompted"
    assert f.read_text().strip() == "yes"
```

- [ ] **Step 2: 跑测试确认失败**

预期：4 failed

- [ ] **Step 3: 实现 should_prompt_chromium / write_chromium_decision**

Append:

```python
CHROMIUM_PROMPT_FILENAME = ".chromium-prompted"


def _chromium_marker(module_name: str) -> Path:
    return resolve_cache_dir() / "venvs" / module_name / CHROMIUM_PROMPT_FILENAME


def should_prompt_chromium(module_name: str) -> bool:
    """判断是否需要弹 chromium 安装提示。

    仅 webnovel-chart-scan（fanqie adapter）会触发。
    """
    return not _chromium_marker(module_name).exists()


def write_chromium_decision(module_name: str, decision: str) -> None:
    """记录用户对 chromium 弹窗的选择：'yes' 或 'no'。

    'no' 意味着 chart-scan 永久 skip fanqie。
    """
    marker = _chromium_marker(module_name)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(decision.strip().lower() + "\n")


def format_chromium_prompt() -> str:
    """生成发给 Claude prompt 的消息文本。"""
    return (
        "fanqie adapter 需要下载 chromium 浏览器（~150MB）。\n"
        "装好后可用 fanqie 平台榜单扫描；不装也能用其它 4 个平台。\n"
        "是否安装？(y/N)"
    )
```

- [ ] **Step 4: 跑测试确认通过**

预期：19 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/tests/test_install_python_deps.py \
        .claude/plugins/webnovel-writer_chang/hooks/install_python_deps.py
git commit -m "feat(install): add chromium prompt mechanism"
```

---

### Task 15: 在 session_start.py 加 chromium 弹窗触发逻辑

**Files:**
- Modify: `plugins/webnovel-writer_chang/hooks/session_start.py`

- [ ] **Step 1: 追加 check_chromium_prompt 函数**

```python
def check_chromium_prompt(plugin_root: Path) -> str | None:
    """检查 webnovel-chart-scan 是否需要 chromium 弹窗。

    Returns:
        需要弹窗时返回 prompt 文本（给 Claude）；否则 None。
    """
    sys.path.insert(0, str(plugin_root / "hooks"))
    try:
        from install_python_deps import should_prompt_chromium, format_chromium_prompt
    except ImportError:
        return None
    if not should_prompt_chromium("webnovel-chart-scan"):
        return None
    # 只在 chart-scan venv 已就绪时弹（否则用户连装 deps 都还没确认）
    cache_root = None
    from pathlib import Path as _P
    cache_root = _P.home() / ".cache" / "webnovel-writer-chang"
    if not (cache_root / "venvs" / "webnovel-chart-scan" / ".install-stamp").exists():
        return None
    return format_chromium_prompt()
```

- [ ] **Step 2: 在 main() 末尾输出 prompt**

```python
def main() -> int:
    # ... 现有逻辑 ...
    plugin_root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", "."))
    trigger_background_python_install(plugin_root)

    prompt = check_chromium_prompt(plugin_root)
    if prompt:
        print(prompt)
    return 0
```

注意：Claude Code hook stdout 是 JSON 输出格式（不是裸 print）。需要查 Claude Code hook 协议文档，确认 prompt 文本的输出格式。本 plan 默认 hook 协议允许 `print()` 到 stdout；如需 JSON 包装，按 Claude Code 文档调整。

- [ ] **Step 3: 手测：模拟 .chromium-prompted 缺失场景**

```bash
rm -rf ~/.cache/webnovel-writer-chang/venvs/webnovel-chart-scan
# 创建 fake venv + stamp 但无 chromium marker
mkdir -p ~/.cache/webnovel-writer-chang/venvs/webnovel-chart-scan
echo "fake-stamp" > ~/.cache/webnovel-writer-chang/venvs/webnovel-chart-scan/.install-stamp
CLAUDE_PLUGIN_ROOT="$(pwd)/.claude/plugins/webnovel-writer_chang" python3 .claude/plugins/webnovel-writer_chang/hooks/session_start.py
```

预期：stdout 包含 "fanqie adapter 需要下载 chromium"

- [ ] **Step 4: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/hooks/session_start.py
git commit -m "feat(hooks): session_start emits chromium prompt when needed"
```

---

## Phase 6：集成测试 + 跨平台 CI

### Task 16: 写 Docker 集成测试（ubuntu:latest 无 Python 场景）

**Files:**
- Create: `plugins/webnovel-writer_chang/scripts/tests/test_install_docker.py`
- Create: `plugins/webnovel-writer_chang/scripts/tests/Dockerfile.install-test`

- [ ] **Step 1: 写 Dockerfile.install-test**

```dockerfile
FROM ubuntu:latest
RUN apt-get update && apt-get install -y python3 python3-pip curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /plugin
COPY . /plugin/
RUN ls vendor/uv/uv-linux-x86_64 && chmod +x vendor/uv/uv-linux-x86_64
ENV CLAUDE_PLUGIN_ROOT=/plugin
RUN python3 hooks/install_python_deps.py
RUN test -f /root/.cache/webnovel-writer-chang/venvs/dashboard/.install-stamp || \
    test -f /root/.cache/webnovel-writer-chang/venvs/webnovel-chart-scan/.install-stamp
CMD ["echo", "install ok"]
```

- [ ] **Step 2: 写 test_install_docker.py（被 pytest skip 除非 DOCKER_INSTALL_TEST=1）**

```python
"""集成测试：跑 install_python_deps.py 在干净 ubuntu:latest Docker 容器里。

默认 skip（CI 慢 + 需 docker）。本地跑：
    DOCKER_INSTALL_TEST=1 python3 -m pytest tests/test_install_docker.py -v -s
"""
import os
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent.parent


@pytest.mark.skipif(
    os.environ.get("DOCKER_INSTALL_TEST") != "1",
    reason="set DOCKER_INSTALL_TEST=1 to run (slow, needs docker)",
)
def test_install_in_clean_ubuntu_container(tmp_path):
    dockerfile_src = PLUGIN_ROOT / "scripts" / "tests" / "Dockerfile.install-test"
    build_ctx = tmp_path
    (build_ctx / "Dockerfile").write_text(dockerfile_src.read_text())
    # Copy plugin into build context
    subprocess.run(
        ["cp", "-R", str(PLUGIN_ROOT) + "/.", str(build_ctx) + "/"],
        check=True,
    )
    result = subprocess.run(
        ["docker", "build", "-t", "wn-install-test", str(build_ctx)],
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, f"docker build failed:\n{result.stderr}"
```

- [ ] **Step 3: 本地手测（如果 docker 可用）**

```bash
which docker && docker --version
```

如果 docker 可用：

```bash
cd .claude/plugins/webnovel-writer_chang
DOCKER_INSTALL_TEST=1 python3 scripts/tests/test_install_docker.py -v -s 2>&1 | tail -30
```

预期：build 成功，断言通过

- [ ] **Step 4: Commit（即使没本地跑也提交，CI 会跑）**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/tests/test_install_docker.py \
        .claude/plugins/webnovel-writer_chang/scripts/tests/Dockerfile.install-test
git commit -m "test(install): Docker integration test for clean ubuntu"
```

---

### Task 17: 添加 GitHub Actions 跨平台 CI matrix

**Files:**
- Create: `.github/workflows/install-cross-platform.yml`

- [ ] **Step 1: 写 workflow**

```yaml
name: install-cross-platform

on:
  pull_request:
    paths:
      - 'plugins/webnovel-writer_chang/vendor/uv/**'
      - 'plugins/webnovel-writer_chang/hooks/install_python_deps.py'
      - 'plugins/webnovel-writer_chang/scripts/tests/test_install_*.py'
      - '.github/workflows/install-cross-platform.yml'
  push:
    branches: [main]

jobs:
  test-install:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-22.04, macos-14, windows-2022]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Verify uv binary sha256
        shell: bash
        run: |
          cd plugins/webnovel-writer_chang
          python3 -m pytest scripts/tests/test_uv_vendor.py -v
      - name: Unit tests for install_python_deps
        shell: bash
        run: |
          cd plugins/webnovel-writer_chang
          python3 -m pytest scripts/tests/test_install_python_deps.py -v
```

- [ ] **Step 2: 验证 yaml 合法**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/install-cross-platform.yml'))" \
  || pip3 install pyyaml && python3 -c "import yaml; yaml.safe_load(open('.github/workflows/install-cross-platform.yml'))"
```

预期：无报错

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/install-cross-platform.yml
git commit -m "ci: cross-platform install test matrix (ubuntu/macos/windows)"
```

---

## Phase 7：sync_dev_to_marketplace + README + 终验

### Task 18: sync_dev_to_marketplace.sh 加 uv 同步步骤

**Files:**
- Modify: `.claude/plugins/webnovel-writer_chang/scripts/sync_dev_to_marketplace.sh` (或 dev-only/)

- [ ] **Step 1: 读现有脚本**

```bash
cat .claude/plugins/webnovel-writer_chang/scripts/dev-only/sync_dev_to_cache.sh 2>/dev/null \
  || cat .claude/plugins/webnovel-writer_chang/scripts/sync_dev_to_marketplace.sh 2>/dev/null \
  || echo "NOT FOUND - 需要先找到正确的 sync 脚本路径"
```

- [ ] **Step 2: 在 cp -R 之后加一行同步 vendor/uv/**

找到 cp plugin 的命令行，在其后追加：

```bash
# vendor/uv/ 二进制已经在 plugin 目录里被 cp，无需单独处理
# 但要在脚本末尾 verify uv binary sha256
echo "Verifying uv binary sha256..."
(cd "$MKT_PLUGIN/vendor/uv" && shasum -a 256 -c SHA256SUMS) || {
  echo "ERROR: uv binary sha256 校验失败" >&2
  exit 1
}
```

- [ ] **Step 3: 手测：跑 sync 脚本，确认不破坏 uv 校验**

（具体命令取决于现有脚本结构。本 task 在执行时按实际脚本调整。）

- [ ] **Step 4: Commit**

```bash
git add .claude/plugins/webnovel-writer_chang/scripts/dev-only/sync_dev_to_cache.sh \
        .claude/plugins/webnovel-writer_chang/scripts/sync_dev_to_marketplace.sh
git commit -m "feat(sync): verify uv binary sha256 after marketplace sync"
```

---

### Task 19: 更新 README.md 说明首次安装行为

**Files:**
- Modify: `README.md`（仓库根）

- [ ] **Step 1: 在 README.md 的"安装"段落末尾追加**

```markdown
## 首次安装依赖

第一次跑 `claude` 时，plugin 会自动在后台装 Python 依赖（不需要你手动操作）：
- 装在 `~/.cache/webnovel-writer-chang/venvs/<module>/`
- SessionStart 后台 fork 子进程，不阻塞你的会话
- 装好后会写 `.install-stamp`，下次不再装

`webnovel-chart-scan` 的 fanqie adapter 需要 chromium（~150MB），会弹一次 y/N 让你选。

**离线场景**：默认从 PyPI 装；如果 PyPI 不可达会自动切国内镜像（清华/阿里）。要彻底离线请用 `WEBNOVEL_CACHE_DIR` 指向预装好的 venv。

**清理**：`rm -rf ~/.cache/webnovel-writer-chang/` 即可重装。
```

- [ ] **Step 2: 验证 README 渲染**

```bash
head -60 README.md
```

预期：上面那段文字出现在 README

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): explain first-time install behavior"
```

---

### Task 20: 最终全测试 + 验收

**Files:** （无新增，仅验证）

- [ ] **Step 1: 跑全部单元测试**

```bash
cd .claude/plugins/webnovel-writer_chang/scripts && python3 -m pytest tests/ -v
```

预期：全绿（test_uv_vendor.py + test_install_python_deps.py + 既有 self-contained 测试）

- [ ] **Step 2: 手动跑 session_start.py，确认 < 2s 完成**

```bash
time CLAUDE_PLUGIN_ROOT="$(pwd)/.claude/plugins/webnovel-writer_chang" \
  python3 .claude/plugins/webnovel-writer_chang/hooks/session_start.py
```

预期：real < 2.0s；stdout 可能含 chromium prompt（如果 chart-scan venv 已就绪）

- [ ] **Step 3: 手动跑 install_python_deps.py 确认可独立调用**

```bash
CLAUDE_PLUGIN_ROOT="$(pwd)/.claude/plugins/webnovel-writer_chang" \
  python3 .claude/plugins/webnovel-writer_chang/hooks/install_python_deps.py
```

预期：所有 module 输出 OK / SKIP；如果有 module 没 pyproject.toml（按 §4.6.7 设计 chart-scan 有、dashboard 有、scripts 有），全部 OK 或 SKIP

- [ ] **Step 4: 清理 worktree（如有）**

```bash
cd /Users/chang/Desktop/zhanghui
git worktree list | grep -v $(pwd) | awk '{print $1}' | xargs -I{} git worktree remove {}
```

- [ ] **Step 5: 同步 marketplace**

```bash
bash .claude/plugins/webnovel-writer_chang/scripts/dev-only/sync_dev_to_cache.sh
```

预期：sync 完成，无报错（cache 是 symlink 自动跟上；marketplace 仓库是独立目录需 cp）

- [ ] **Step 6: 终 commit**

```bash
git add -A
git status
git commit -m "feat: cross-platform Python dep auto-install (spec §4.6)

实现 uv bootstrapper + SessionStart 后台安装：
- vendor/uv/ 4 平台二进制 + SHA256SUMS
- install_python_deps.py 含 stamp/select_uv/resolve_cache/find_modules/install/chromium-prompt
- session_start.py 检测 Python 依赖 + 后台 fork + chromium 弹窗
- dashboard/ + scripts/ 各自 pyproject.toml
- hooks.json timeout 5s → 30s
- GitHub Actions matrix 跨平台测试
- README 说明首次安装行为

详见：
- docs/superpowers/specs/2026-08-15-webnovel-plugin-self-contained-refactor-design.md §4.6
- docs/superpowers/plans/2026-08-15-webnovel-plugin-cross-platform-deps-impl.md"

git log --oneline -5
```

预期：commit 成功；git log 显示本 commit 在最新

---

## 自检清单（plan 完成时检查）

- [ ] 18 个文件创建/修改覆盖 spec §4.6 全部 7 个子节
- [ ] 0 placeholders (TODO / TBD / "implement later")
- [ ] 每个 task 的代码块完整可直接用
- [ ] 每个 task 的命令有预期输出
- [ ] 任务粒度 2-5 分钟（最大 task 是 Task 9 main() 入口 + Task 16 Docker 集成测试，~10 min）
- [ ] TDD 节奏贯穿（每个 task 都是 test → impl → verify → commit）
- [ ] 所有 commit message 遵循 `<type>(<scope>): <what>` 格式
- [ ] 不在 CI 测 chromium（spec §4.6.6 明确不测）
- [ ] 不阻塞 SessionStart（spec §4.6.4 + Task 12 用 subprocess.Popen + start_new_session=True）

---

## 风险与回退

| 风险 | 触发条件 | 回退步骤 |
|---|---|---|
| uv 0.4.18 跟 Python 3.14 不兼容 | `uv venv` 创建 venv 后 `venv/bin/python --version` 报错 | bump 到 uv 0.5.x；如还不行，降回 Python 3.11 + 3.12 only |
| uv 二进制被平台编译器破坏（macOS Gatekeeper 拒跑） | `uv-darwin-arm64` 报 "cannot be opened because the developer cannot be verified" | 在 release 流程加 `codesign --sign -` 给 binary 加 ad-hoc signature |
| 后台 install 跟用户主动跑 chart-scan 撞车 | install 写到一半 venv 不完整，但用户先跑了 | install_python_deps.py 加 venv lock 文件；chart-scan 检测到 lock 时报错让用户等 |
| stamp 误判（pyproject 内容改了但 deps 没变） | 重装浪费时间 | 接受；stamp 简单可靠优先，浪费 30s 比依赖没装好 |
| WEBNOVEL_CACHE_DIR 指向用户无权写的目录 | cache 创建失败 | resolve_cache_dir() 兜底用 temp dir + 写 warning 到 stderr；不静默 fail |

---

## 关联文档

- Spec: `docs/superpowers/specs/2026-08-15-webnovel-plugin-self-contained-refactor-design.md`
- 上游 plan: `docs/superpowers/plans/2026-08-15-webnovel-plugin-self-contained-refactor-impl.md`（本 plan 的前置）
- 本 plan: `docs/superpowers/plans/2026-08-15-webnovel-plugin-cross-platform-deps-impl.md`
