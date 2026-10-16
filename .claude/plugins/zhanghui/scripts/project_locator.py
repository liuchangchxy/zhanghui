#!/usr/bin/env python3
"""
Project location helpers for webnovel-writer scripts.

Problem this solves:
- Many scripts assumed CWD is the project root and used relative paths like `.webnovel/state.json`.
- In this repo, commands/scripts are often invoked from the repo root, while the actual project lives
  in a subdirectory (default: `webnovel-project/`).

These helpers provide a single, consistent way to locate the active project root.

Resolution priority (single contract shared by `where`, `preflight`, runtime and Skills):

1. explicit project root argument (validated)
2. `WEBNOVEL_PROJECT_ROOT` environment binding
3. a project root at cwd or one of its ancestors (including `<dir>/webnovel-project/`)
4. an unambiguous workspace binding inside the current workspace scope:
   workspace pointer file, unique child project, user-level workspace registry
5. otherwise fail loudly

Scope rule: bindings from step 4 only apply inside the *current workspace scope* — the nearest
ancestor containing `.claude/`, excluding the user-level Claude home (`~/.claude`). A pointer or
registry entry that resolves outside that scope is ignored instead of silently hijacking the
resolution. This is what previously let a stale global pointer (e.g. pointing at a benchmark run
directory) capture `webnovel.py where` / `preflight` while the user was standing inside a
perfectly valid book project.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from runtime_compat import normalize_windows_path


DEFAULT_PROJECT_DIR_NAMES: tuple[str, ...] = ("webnovel-project",)
CURRENT_PROJECT_POINTER_REL: Path = Path(".claude") / ".webnovel-current-project"

# 用户级全局映射（当 skills/agents 安装在 ~/.claude 时，项目目录可能在任意盘符）
# 该文件用于在“空上下文 + CWD 不在项目内”的情况下仍能定位到正确 project_root。
GLOBAL_REGISTRY_REL: Path = Path("zhanghui") / "workspaces.json"

# Claude Code 常见环境变量（存在时优先作为“工作区根目录”提示）
ENV_CLAUDE_PROJECT_DIR = "CLAUDE_PROJECT_DIR"
ENV_CLAUDE_HOME = "CLAUDE_HOME"
ENV_WEBNOVEL_CLAUDE_HOME = "WEBNOVEL_CLAUDE_HOME"


def _find_git_root(cwd: Path) -> Optional[Path]:
    """Return nearest git root for cwd, if any."""
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _path_is_within(child: Path, parent: Path) -> bool:
    """True when `child` is `parent` itself or lives underneath it (Windows + POSIX safe)."""
    try:
        child_norm = os.path.normcase(str(child.expanduser().resolve()))
        parent_norm = os.path.normcase(str(parent.expanduser().resolve()))
    except Exception:
        return False
    if child_norm == parent_norm:
        return True
    return child_norm.startswith(parent_norm.rstrip("/\\") + os.sep)


def _workspace_scope_root(start: Path) -> Optional[Path]:
    """
    Nearest ancestor (or self) carrying a real workspace `.claude/` directory.

    The user-level Claude home (`~/.claude`, or `$WEBNOVEL_CLAUDE_HOME`) is explicitly NOT a
    workspace: treating it as one is exactly how a single global pointer file ended up governing
    every project on the machine. When the walk reaches (or would pass through) the user home it
    stops and returns None.
    """
    try:
        user_claude_root = _get_user_claude_root()
    except Exception:
        user_claude_root = None

    for candidate in (start, *start.parents):
        claude_dir = candidate / ".claude"
        if not claude_dir.is_dir():
            continue
        if user_claude_root is not None and _path_is_within(claude_dir, user_claude_root):
            # 这一层就是用户级 Claude home：它之上共享同一个全局 home，继续向上没有意义。
            return None
        return candidate
    return None


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normcase_path_key(p: Path) -> str:
    """
    生成稳定的路径 key（Windows 下大小写/分隔符不敏感）。

    注意：key 仅用于映射表索引，实际路径仍以原始绝对路径字符串存储。
    """
    try:
        resolved = p.expanduser().resolve()
    except Exception:
        resolved = p.expanduser()
    return os.path.normcase(str(resolved))


def _get_user_claude_root() -> Path:
    raw = os.environ.get(ENV_WEBNOVEL_CLAUDE_HOME) or os.environ.get(ENV_CLAUDE_HOME)
    if raw:
        try:
            return normalize_windows_path(raw).expanduser().resolve()
        except Exception:
            return normalize_windows_path(raw).expanduser()
    return (Path.home() / ".claude").resolve()


def _global_registry_path() -> Path:
    return _get_user_claude_root() / GLOBAL_REGISTRY_REL


def _default_registry() -> dict:
    return {
        "schema_version": 1,
        "workspaces": {},
        "last_used_project_root": "",
        "updated_at": _now_iso(),
    }


def _load_global_registry(path: Path) -> dict:
    if not path.is_file():
        return _default_registry()
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return _default_registry()
    if not isinstance(data, dict):
        return _default_registry()

    if data.get("schema_version") != 1:
        data["schema_version"] = 1
    if not isinstance(data.get("workspaces"), dict):
        data["workspaces"] = {}
    if not isinstance(data.get("last_used_project_root"), str):
        data["last_used_project_root"] = ""
    if not isinstance(data.get("updated_at"), str):
        data["updated_at"] = _now_iso()
    return data


def _save_global_registry(path: Path, data: dict) -> None:
    # 写入是 best-effort：用户目录权限/只读盘符等情况不应阻断主流程。
    try:
        from security_utils import atomic_write_json

        data["updated_at"] = _now_iso()
        atomic_write_json(path, data, backup=False)
    except Exception:
        # 非阻断
        return


def _resolve_project_root_from_global_registry(
    base: Path,
    *,
    workspace_hint: Optional[Path] = None,
) -> Optional[Path]:
    """
    从用户级 registry 中解析 project_root（严格作用域）。

    安全策略：
    - 只在「registry 里记录的 workspace 确实包含 base（cwd）」时启用，并且解析出的项目必须
      落在该 workspace 内部；跨工作区的记录一律忽略。
    - 不使用 `last_used_project_root` 兜底：一个与当前目录无关的全局「上次用过」记录，
      正是过去把 `where` / `preflight` 劫持到 benchmark 运行目录的原因。
    - Windows 与 POSIX 路径都按真实路径包含关系判断（旧实现用 `\\` 前缀匹配，在 POSIX 上失效）。
    """
    reg_path = _global_registry_path()
    reg = _load_global_registry(reg_path)
    workspaces = reg.get("workspaces") or {}
    if not isinstance(workspaces, dict) or not workspaces:
        return None

    hints: list[Path] = []
    env_ws = os.environ.get(ENV_CLAUDE_PROJECT_DIR)
    if env_ws:
        hints.append(normalize_windows_path(env_ws).expanduser())
    if workspace_hint is not None:
        hints.append(workspace_hint)
    hints.append(base)

    def _target_of(entry: object, workspace_root: Path) -> Optional[Path]:
        if not isinstance(entry, dict):
            return None
        raw = entry.get("current_project_root")
        if not isinstance(raw, str) or not raw.strip():
            return None
        target = normalize_windows_path(raw).expanduser()
        if not target.is_absolute() or not _is_project_root(target):
            return None
        if not _path_is_within(target, workspace_root):
            # 跨工作区绑定 —— 必须由显式 `webnovel use` 完成，不在这里静默生效。
            return None
        return target.resolve()

    # 1) 精确匹配：hint 就是某个已记录的 workspace 根
    for hint in hints:
        entry = workspaces.get(_normcase_path_key(hint))
        if entry is None:
            continue
        workspace_root = normalize_windows_path(
            str((entry or {}).get("workspace_root") or hint)
        ).expanduser()
        resolved = _target_of(entry, workspace_root)
        if resolved is not None:
            return resolved

    # 2) 前缀匹配：base 位于某个已记录 workspace 内部（从工作区子目录运行时）
    for hint in hints:
        best: tuple[int, Path, object] | None = None
        for ws_key, entry in workspaces.items():
            if not isinstance(ws_key, str) or not ws_key:
                continue
            if not isinstance(entry, dict):
                continue
            workspace_root = Path(str(entry.get("workspace_root") or ws_key)).expanduser()
            if not _path_is_within(hint, workspace_root):
                continue
            resolved = _target_of(entry, workspace_root)
            if resolved is None:
                continue
            depth = len(workspace_root.resolve().parts)
            if best is None or depth > best[0]:
                best = (depth, workspace_root, entry)
        if best is not None:
            entry = best[2]
            workspace_root = best[1]
            resolved = _target_of(entry, workspace_root)
            if resolved is not None:
                return resolved

    return None


def update_global_registry_current_project(
    *,
    workspace_root: Optional[Path],
    project_root: Path,
) -> Optional[Path]:
    """
    更新用户级 registry：workspace -> current_project_root 映射。

    返回：registry 文件路径（写入失败则返回 None）。
    """
    root = normalize_windows_path(project_root).expanduser()
    try:
        root = root.resolve()
    except Exception:
        root = root
    if not _is_project_root(root):
        raise FileNotFoundError(f"Not a webnovel project root (missing .webnovel/state.json): {root}")

    ws = workspace_root
    if ws is None:
        env_ws = os.environ.get(ENV_CLAUDE_PROJECT_DIR)
        if env_ws:
            ws = normalize_windows_path(env_ws).expanduser()
    if ws is None:
        return None

    try:
        ws = ws.expanduser().resolve()
    except Exception:
        ws = ws.expanduser()

    reg_path = _global_registry_path()
    reg = _load_global_registry(reg_path)
    workspaces = reg.get("workspaces")
    if not isinstance(workspaces, dict):
        workspaces = {}
        reg["workspaces"] = workspaces

    workspaces[_normcase_path_key(ws)] = {
        "workspace_root": str(ws),
        "current_project_root": str(root),
        "updated_at": _now_iso(),
    }
    reg["last_used_project_root"] = str(root)
    _save_global_registry(reg_path, reg)
    return reg_path


def _candidate_roots(cwd: Path, *, stop_at: Optional[Path] = None) -> Iterable[Path]:
    yield cwd
    for name in DEFAULT_PROJECT_DIR_NAMES:
        yield cwd / name

    for parent in cwd.parents:
        yield parent
        for name in DEFAULT_PROJECT_DIR_NAMES:
            yield parent / name
        if stop_at is not None and parent == stop_at:
            break


def _is_project_root(path: Path) -> bool:
    return (path / ".webnovel" / "state.json").is_file()


def _pointer_candidates(cwd: Path, *, stop_at: Optional[Path] = None) -> Iterable[Path]:
    """
    Yield candidate workspace pointer files from cwd up to (and including) the workspace scope root.

    The walk is deliberately bounded to the current workspace scope. Walking all the way up to the
    user-level `~/.claude/.webnovel-current-project` is what let one global pointer override every
    project on the machine.
    """
    scope_root = _workspace_scope_root(cwd)
    if scope_root is None:
        return
    for candidate in (cwd, *cwd.parents):
        yield candidate / CURRENT_PROJECT_POINTER_REL
        if candidate == scope_root:
            return
        if stop_at is not None and candidate == stop_at:
            return


def _resolve_project_root_from_pointer(cwd: Path, *, stop_at: Optional[Path] = None) -> Optional[Path]:
    """
    Resolve project root from the workspace pointer file, scoped to the current workspace.

    Pointer file format:
    - plain text absolute path, one line.
    - relative path is also supported (resolved relative to pointer's `.claude/` dir).

    A pointer whose target falls outside the workspace scope is ignored: that is a cross-workspace
    binding, which must be requested explicitly (`webnovel use <path>`), not inferred.
    """
    scope_root = _workspace_scope_root(cwd)
    if scope_root is None:
        return None
    for pointer_file in _pointer_candidates(cwd, stop_at=stop_at):
        if not pointer_file.is_file():
            continue
        raw = pointer_file.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        target = normalize_windows_path(raw).expanduser()
        if not target.is_absolute():
            target = (pointer_file.parent / target).resolve()
        if not _is_project_root(target):
            continue
        if not _path_is_within(target, scope_root):
            continue
        return target.resolve()
    return None


def _resolve_unique_child_project_root(root: Path) -> Optional[Path]:
    """
    Resolve a workspace root that contains exactly one direct child book project.

    This supports commands invoked with a parent workspace path while keeping
    ambiguous multi-book workspaces explicit.
    """
    try:
        children = [child.resolve() for child in root.iterdir() if child.is_dir() and _is_project_root(child)]
    except OSError:
        return None
    if len(children) == 1:
        return children[0]
    return None


def _find_workspace_root_with_claude(start: Path) -> Optional[Path]:
    """Find nearest ancestor containing a workspace `.claude/` (never the user-level home)."""
    return _workspace_scope_root(start)


def write_current_project_pointer(project_root: Path, *, workspace_root: Optional[Path] = None) -> Optional[Path]:
    """
    Write workspace-level current project pointer and return pointer file path.

    If no workspace root with `.claude/` can be found, returns None (non-fatal).
    """
    root = normalize_windows_path(project_root).expanduser().resolve()
    if not _is_project_root(root):
        raise FileNotFoundError(f"Not a webnovel project root (missing .webnovel/state.json): {root}")

    ws_root = Path(workspace_root).expanduser().resolve() if workspace_root else _find_workspace_root_with_claude(root)
    if ws_root is None:
        ws_root = _find_workspace_root_with_claude(Path.cwd().resolve())
    if ws_root is None:
        # 兜底：若无法找到 `.claude/`，将项目父目录视为“工作区”候选，
        # 仅用于写入用户级 registry（不创建 `.claude/` 目录，不写 pointer 文件）。
        ws_root = root.parent if root.parent != root else None
    # 注意：ws_root 可能为 None（例如全局安装的 skills/agents，工作区内没有 `.claude/`）。
    # 这类情况仍然需要写入用户级 registry，以支持后续“空上下文”定位。

    pointer_file: Optional[Path] = None
    if ws_root is not None:
        # 仅当工作区内已经存在 `.claude/` 时才写入指针，避免在任意目录下“凭空创建 .claude/”。
        if (ws_root / ".claude").is_dir():
            try:
                pointer_file = ws_root / CURRENT_PROJECT_POINTER_REL
                pointer_file.write_text(str(root), encoding="utf-8")
            except Exception:
                pointer_file = None

    # best-effort 更新用户级 registry（不阻断）
    try:
        update_global_registry_current_project(workspace_root=ws_root, project_root=root)
    except Exception:
        pass

    return pointer_file


def resolve_project_root_with_source(
    explicit_project_root: Optional[str] = None,
    *,
    cwd: Optional[Path] = None,
) -> tuple[Path, str]:
    """
    Resolve the project root and report which rule matched.

    Returns `(project_root, source)` where `source` is one of:
    `explicit`, `explicit_workspace`, `env`, `cwd`, `pointer`, `unique_child`, `registry`.

    Resolution order (the single contract shared by `where`, `preflight`, runtime and Skills):

    1) explicit project root argument (or explicit workspace root)
    2) `WEBNOVEL_PROJECT_ROOT`
    3) a book project at cwd or one of its ancestors — this runs *before* any pointer or registry
       lookup, so a stale global binding can never override the project the user is standing in
    4) workspace-scoped bindings: pointer file, unambiguous child project, user-level registry
    5) otherwise raise FileNotFoundError

    Search safety:
    - If cwd is inside a Git repo, the ancestor search stops at the repo root.
    - Bindings from step 4 must resolve *inside* the current workspace scope, otherwise they are
      ignored (never "silently succeed" into an unrelated project).

    Raises:
        FileNotFoundError: if no valid project root can be found.
    """
    if explicit_project_root:
        root = normalize_windows_path(explicit_project_root).expanduser().resolve()
        if _is_project_root(root):
            return root, "explicit"

        # 兼容：显式传入“工作区根目录”（含 `.claude/.webnovel-current-project` 指针）
        # 例如：D:\wk\xiaoshuo 不是项目根，但其指针指向 D:\wk\xiaoshuo\<书名>
        pointer_root = _resolve_project_root_from_pointer(root, stop_at=_find_git_root(root))
        if pointer_root is not None:
            return pointer_root, "explicit_workspace"

        child_root = _resolve_unique_child_project_root(root)
        if child_root is not None:
            return child_root, "explicit_workspace"

        # 兼容：显式传入“工作区根目录”但其 `.claude/` 在用户目录（全局安装）时，
        # workspace 内部可能没有指针文件。此时从用户级 registry 查找。
        reg_root = _resolve_project_root_from_global_registry(root, workspace_hint=root)
        if reg_root is not None:
            return reg_root, "explicit_workspace"

        raise FileNotFoundError(f"Not a webnovel project root (missing .webnovel/state.json): {root}")

    env_root = os.environ.get("WEBNOVEL_PROJECT_ROOT")
    if env_root:
        root = normalize_windows_path(env_root).expanduser().resolve()
        if _is_project_root(root):
            return root, "env"
        raise FileNotFoundError(f"WEBNOVEL_PROJECT_ROOT is set but invalid (missing .webnovel/state.json): {root}")

    base = (cwd or Path.cwd()).resolve()
    git_root = _find_git_root(base)

    # 3) 当前目录（及其有效祖先）中的书项目 —— 优先于任何历史绑定。
    for candidate in _candidate_roots(base, stop_at=git_root):
        if _is_project_root(candidate):
            return candidate.resolve(), "cwd"

    # 4a) 工作区指针（仅限当前工作区作用域，且目标必须在作用域内）
    pointer_root = _resolve_project_root_from_pointer(base, stop_at=git_root)
    if pointer_root is not None:
        return pointer_root, "pointer"

    # 4b) 无歧义的唯一子项目（`cd <workspace>` 且工作区里只有一本书）
    scope_root = _workspace_scope_root(base)
    for candidate in (base, scope_root):
        if candidate is None:
            continue
        child_root = _resolve_unique_child_project_root(candidate)
        if child_root is not None:
            return child_root, "unique_child"

    # 4c) 用户级 registry（仅在 base 位于某个已记录 workspace 内部时启用；不使用 last_used）
    reg_root = _resolve_project_root_from_global_registry(base, workspace_hint=None)
    if reg_root is not None:
        return reg_root, "registry"

    raise FileNotFoundError(
        "Unable to locate webnovel project root. Expected `.webnovel/state.json` under the current directory, "
        "a parent directory, or `webnovel-project/`. Run /webnovel-init first, or bind explicitly with "
        "`webnovel use <project_root>`, or pass --project-root / set WEBNOVEL_PROJECT_ROOT."
    )


def resolve_project_root(explicit_project_root: Optional[str] = None, *, cwd: Optional[Path] = None) -> Path:
    """Resolve the project root. See `resolve_project_root_with_source` for the resolution contract."""
    return resolve_project_root_with_source(explicit_project_root, cwd=cwd)[0]


def resolve_state_file(
    explicit_state_file: Optional[str] = None,
    *,
    explicit_project_root: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> Path:
    """
    Resolve `.webnovel/state.json` path.

    If explicit_state_file is provided, returns it as-is (resolved to absolute if relative).
    Otherwise derives it from resolve_project_root().
    """
    base = (cwd or Path.cwd()).resolve()
    if explicit_state_file:
        p = Path(explicit_state_file).expanduser()
        return (base / p).resolve() if not p.is_absolute() else p.resolve()

    root = resolve_project_root(explicit_project_root, cwd=base)
    return root / ".webnovel" / "state.json"

