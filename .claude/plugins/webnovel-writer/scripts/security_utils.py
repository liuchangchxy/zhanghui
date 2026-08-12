#!/usr/bin/env python3
"""
安全工具函数库
用于webnovel-writer系统的通用安全函数

创建时间: 2026-01-02
创建原因: 安全审计发现路径遍历和命令注入漏洞
修复方案: 集中管理所有安全相关的输入清理函数
"""

import contextlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio
from typing import Any, Dict, Iterator, Optional, Union

# 尝试导入 filelock（可选依赖）
try:
    from filelock import FileLock
    HAS_FILELOCK = True
except (ImportError, OSError):
    FileLock = None  # type: ignore[assignment]
    HAS_FILELOCK = False


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    清理文件名，防止路径遍历攻击 (CWE-22)

    安全关键函数 - 修复extract_entities.py路径遍历漏洞

    Args:
        name: 原始文件名（可能包含路径遍历字符）
        max_length: 文件名最大长度（默认100字符）

    Returns:
        安全的文件名（仅包含基本文件名，移除所有路径信息）

    示例:
        >>> sanitize_filename("../../../etc/passwd")
        'passwd'
        >>> sanitize_filename("C:\\Windows\\System32")
        'System32'
        >>> sanitize_filename("正常角色名")
        '正常角色名'

    安全验证:
        - ✅ 防止目录遍历（../、..\\）
        - ✅ 防止绝对路径（/、C:\\）
        - ✅ 移除特殊字符
        - ✅ 长度限制
    """
    # Step 1: 仅保留基础文件名（移除所有路径）
    safe_name = os.path.basename(name)

    # Step 2: 移除路径分隔符（双重保险）
    safe_name = safe_name.replace('/', '_').replace('\\', '_')

    # Step 3: 只保留安全字符
    # 允许：中文(\u4e00-\u9fff)、字母(a-zA-Z)、数字(0-9)、下划线(_)、连字符(-)
    safe_name = re.sub(r'[^\w\u4e00-\u9fff-]', '_', safe_name)

    # Step 4: 移除连续的下划线（美化）
    safe_name = re.sub(r'_+', '_', safe_name)

    # Step 5: 长度限制
    if len(safe_name) > max_length:
        safe_name = safe_name[:max_length]

    # Step 6: 移除首尾下划线
    safe_name = safe_name.strip('_')

    # Step 7: 确保非空（防御性编程）
    if not safe_name:
        safe_name = "unnamed_entity"

    return safe_name


def sanitize_commit_message(message: str, max_length: int = 200) -> str:
    """
    清理Git提交消息，防止命令注入 (CWE-77)

    安全关键函数 - 修复backup_manager.py命令注入漏洞

    Args:
        message: 原始提交消息（可能包含Git标志）
        max_length: 消息最大长度（默认200字符）

    Returns:
        安全的提交消息（移除Git特殊标志和危险字符）

    示例:
        >>> sanitize_commit_message("Test\\n--author='Attacker'")
        'Test  author Attacker'
        >>> sanitize_commit_message("--amend Chapter 1")
        'amend Chapter 1'

    安全验证:
        - ✅ 防止多行注入（换行符）
        - ✅ 防止Git标志注入（--xxx）
        - ✅ 防止参数分隔符混淆（引号）
        - ✅ 防止单字母标志（-x）
    """
    # Step 1: 移除换行符（防止多行参数注入）
    safe_msg = message.replace('\n', ' ').replace('\r', ' ')

    # Step 2: 移除Git特殊标志（--开头的参数）
    safe_msg = re.sub(r'--[\w-]+', '', safe_msg)

    # Step 3: 移除引号（防止参数分隔符混淆）
    safe_msg = safe_msg.replace("'", "").replace('"', '')

    # Step 4: 移除前导的-（防止单字母标志如-m）
    safe_msg = safe_msg.lstrip('-')

    # Step 5: 移除连续空格（美化）
    safe_msg = re.sub(r'\s+', ' ', safe_msg)

    # Step 6: 长度限制
    if len(safe_msg) > max_length:
        safe_msg = safe_msg[:max_length]

    # Step 7: 移除首尾空格
    safe_msg = safe_msg.strip()

    # Step 8: 确保非空
    if not safe_msg:
        safe_msg = "Untitled commit"

    return safe_msg


def create_secure_directory(path: str, mode: int = 0o700) -> Path:
    """
    创建安全目录（仅所有者可访问）

    安全关键函数 - 修复文件权限配置缺失漏洞

    Args:
        path: 目录路径
        mode: 权限模式（默认0o700，仅所有者可读写执行）

    Returns:
        Path对象

    示例:
        >>> create_secure_directory('.webnovel')
        PosixPath('.webnovel')  # drwx------ (700)

    安全验证:
        - ✅ 仅所有者可访问（0o700）
        - ✅ 防止同组用户读取
        - ✅ 跨平台兼容（Windows/Linux/macOS）
    """
    path_obj = Path(path)

    # Windows 上传入 mode 会触发不可预期的 ACL 行为（实测会导致目录创建后立刻无法访问）。
    # 因此在 Windows 下不传 mode，保持默认继承权限；在类 Unix 系统才使用 mode。
    if os.name == 'nt':
        os.makedirs(path, exist_ok=True)
    else:
        os.makedirs(path, mode=mode, exist_ok=True)

    # 双重保险：显式设置权限（某些系统可能忽略makedirs的mode参数）
    if os.name != 'nt':  # Unix系统（Linux/macOS）
        os.chmod(path, mode)

    return path_obj


def create_secure_file(file_path: str, content: str, mode: int = 0o600) -> None:
    """
    创建安全文件（仅所有者可读写）

    Args:
        file_path: 文件路径
        content: 文件内容
        mode: 权限模式（默认0o600，仅所有者可读写）

    安全验证:
        - ✅ 仅所有者可读写（0o600）
        - ✅ 防止其他用户访问
    """
    # 创建文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    # 设置权限（仅Unix系统）
    if os.name != 'nt':
        os.chmod(file_path, mode)


def validate_integer_input(value: str, field_name: str) -> int:
    """
    验证并转换整数输入（严格模式）

    安全关键函数 - 修复update_state.py弱验证漏洞

    Args:
        value: 输入值（字符串）
        field_name: 字段名称（用于错误消息）

    Returns:
        转换后的整数

    Raises:
        ValueError: 输入不是有效整数

    示例:
        >>> validate_integer_input("123", "chapter_num")
        123
        >>> validate_integer_input("abc", "level")
        ValueError: ❌ 错误：level 必须是整数，收到: abc
    """
    try:
        return int(value)
    except ValueError:
        print(f"❌ 错误：{field_name} 必须是整数，收到: {value}", file=sys.stderr)
        raise ValueError(f"Invalid integer input for {field_name}: {value}")


# ============================================================================
# Git 环境检测（优雅降级支持）
# ============================================================================

# 缓存 Git 可用性检测结果
_git_available: Optional[bool] = None


def is_git_available() -> bool:
    """
    检测 Git 是否可用

    Returns:
        bool: Git 是否可用

    说明：
        - 检测结果会被缓存，避免重复检测
        - 用于支持在无 Git 环境下优雅降级
    """
    global _git_available

    if _git_available is not None:
        return _git_available

    import subprocess

    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        _git_available = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        _git_available = False

    return _git_available


def is_git_repo(path: Union[str, Path]) -> bool:
    """
    检测指定目录是否是 Git 仓库

    Args:
        path: 目录路径

    Returns:
        bool: 是否是 Git 仓库
    """
    if not is_git_available():
        return False

    path = Path(path)
    git_dir = path / ".git"
    return git_dir.exists() and git_dir.is_dir()


def git_graceful_operation(
    args: list,
    cwd: Union[str, Path],
    *,
    fallback_msg: str = "Git 不可用，跳过版本控制操作"
) -> tuple:
    """
    优雅执行 Git 操作（Git 不可用时静默降级）

    Args:
        args: Git 命令参数（不含 'git'）
        cwd: 工作目录
        fallback_msg: 降级时的提示消息

    Returns:
        (success: bool, output: str, was_skipped: bool)
        - success: 操作是否成功
        - output: 输出内容
        - was_skipped: 是否因 Git 不可用而跳过

    示例:
        >>> success, output, skipped = git_graceful_operation(
        ...     ["add", "."], cwd="/path/to/project"
        ... )
        >>> if skipped:
        ...     print("Git not available, using fallback")
    """
    if not is_git_available():
        print(f"⚠️  {fallback_msg}", file=sys.stderr)
        return False, "", True

    import subprocess

    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=60
        )
        return result.returncode == 0, result.stdout, False
    except subprocess.TimeoutExpired:
        print(f"⚠️  Git 操作超时: git {' '.join(args)}", file=sys.stderr)
        return False, "", False
    except OSError as e:
        print(f"⚠️  Git 操作失败: {e}", file=sys.stderr)
        return False, "", False


# ============================================================================
# 原子化文件写入（防止并发冲突和数据损坏）
# ============================================================================


class AtomicWriteError(Exception):
    """原子写入失败异常"""
    pass


# ----------------------------------------------------------------------------
# 跨进程互斥锁（filelock 不可用时回退到 SQLite）
# ----------------------------------------------------------------------------

# 保留的备份份数（超出的按时间戳从旧到新删除）
BACKUP_RETENTION = 20


def _sqlite_lock_db() -> Path:
    """SQLite 回退锁的全局数据库路径。"""
    lock_dir = Path(os.environ.get("WEBNOVEL_LOCK_DIR") or (Path.home() / ".webnovel"))
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / "writer.lock"


@contextlib.contextmanager
def _sqlite_lock(key: str, timeout: float = 10.0) -> Iterator[None]:
    """
    基于 SQLite 的跨进程互斥锁（filelock 未安装时的回退实现）。

    依赖 SQLite 自身的写锁：BEGIN IMMEDIATE 会在整个数据库上取得 RESERVED 锁，
    同一时刻只有一个进程能成功，其余进程在 busy_timeout 内重试。持锁期间事务
    保持打开，退出时提交并关闭连接释放锁。

    注意：这是**全局**锁（整库粒度），不区分 key；key 仅写入表中便于诊断
    当前持锁者。对本项目的写入频率而言，全局互斥足够且更安全。
    """
    db_path = _sqlite_lock_db()
    conn = sqlite3.connect(str(db_path), timeout=timeout, isolation_level=None)
    try:
        conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS locks ("
            "  key TEXT PRIMARY KEY,"
            "  pid INTEGER,"
            "  acquired_at TEXT"
            ")"
        )
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as e:
            raise AtomicWriteError(f"获取 SQLite 锁超时 ({key}): {e}")

        conn.execute(
            "INSERT INTO locks(key, pid, acquired_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET pid=excluded.pid, acquired_at=excluded.acquired_at",
            (key, os.getpid(), datetime.now().isoformat()),
        )
        try:
            yield
            conn.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


@contextlib.contextmanager
def cross_process_lock(lock_path: Union[str, Path], timeout: float = 10.0) -> Iterator[None]:
    """
    跨进程互斥锁：优先使用 filelock，未安装时回退到 SQLite 全局锁。

    修复 M-H26：此前 filelock 缺失时直接**无锁**写入，多进程并发下会丢更新。
    """
    if HAS_FILELOCK:
        lock = FileLock(str(lock_path), timeout=timeout)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
    else:
        with _sqlite_lock(str(lock_path), timeout=timeout):
            yield


def _write_timestamped_backup(file_path: Path) -> Optional[Path]:
    """
    把 file_path 备份到 <parent>/backups/<stem>.backup_<ts>.<ext>，保留最近 BACKUP_RETENTION 份。

    修复 M-H21：此前固定写 <file>.bak，每次写入都覆盖上一份备份，
    连续两次坏写会让最后一份好数据一起丢掉。
    """
    if not file_path.exists():
        return None

    import shutil

    backup_dir = file_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    suffix = file_path.suffix.lstrip(".") or "bak"
    # 带微秒，避免同一秒内多次写入互相覆盖
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{file_path.stem}.backup_{timestamp}.{suffix}"

    try:
        shutil.copy2(file_path, backup_path)
    except OSError:
        return None  # 备份失败不阻止写入

    _prune_backups(backup_dir, file_path)
    return backup_path


def _backup_candidates(backup_dir: Path, file_path: Path) -> list:
    """列出属于 file_path 的备份，按文件名（即时间戳）升序 = 从旧到新。"""
    suffix = file_path.suffix.lstrip(".") or "bak"
    pattern = f"{_glob_escape(file_path.stem)}.backup_*.{suffix}"
    return sorted(backup_dir.glob(pattern))


def _glob_escape(value: str) -> str:
    """转义 glob 元字符，避免文件名里的 [ ] * ? 被当成通配符。"""
    return re.sub(r"([\[\]*?])", r"[\1]", value)


def _prune_backups(backup_dir: Path, file_path: Path, keep: int = BACKUP_RETENTION) -> None:
    """只保留最近 keep 份备份，多余的从最旧的开始删。"""
    backups = _backup_candidates(backup_dir, file_path)
    for stale in backups[:-keep] if keep > 0 else backups:
        with contextlib.suppress(OSError):
            stale.unlink()


def latest_backup(file_path: Union[str, Path]) -> Optional[Path]:
    """返回 file_path 最近一份时间戳备份；无备份时回退到旧的 .bak 路径。"""
    file_path = Path(file_path)
    backup_dir = file_path.parent / "backups"
    if backup_dir.is_dir():
        backups = _backup_candidates(backup_dir, file_path)
        if backups:
            return backups[-1]

    # 兼容升级前写下的 .bak
    legacy = file_path.with_suffix(file_path.suffix + '.bak')
    return legacy if legacy.exists() else None


def _replace_with_retry(
    temp_path: Union[str, Path],
    file_path: Union[str, Path],
    *,
    attempts: int = 10,
    first_delay: float = 0.02,
    max_delay: float = 0.5,
) -> None:
    """
    os.replace 带退避重试（仅针对 PermissionError）。

    Windows 上目标文件被其他进程瞬时打开（编辑器 file watcher、杀毒软件、
    同步盘、索引器——均未开 FILE_SHARE_DELETE 共享位）时，os.replace 报
    WinError 5；占用通常是毫秒级，短退避重试即可穿过（issue #125）。
    重试穷尽后抛出最后一次的 PermissionError。
    """
    delay = first_delay
    for attempt in range(attempts):
        try:
            os.replace(temp_path, file_path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, max_delay)


def _atomic_write(
    file_path: Union[str, Path],
    content: str,
    *,
    use_lock: bool = True,
    backup: bool = True,
) -> None:
    """
    原子写入文本内容的公共实现（JSON 与纯文本共用）。

    1. 写入同目录临时文件 → flush + fsync（保证数据真正落盘）
    2. 可选：取跨进程锁（filelock 或 SQLite 回退）
    3. 可选：时间戳备份原文件
    4. os.replace 原子替换（POSIX 原子；Windows 带退避重试）

    崩溃安全性：读者要么看到旧文件，要么看到完整新文件，永远看不到半写状态。
    """
    file_path = Path(file_path)
    parent_dir = file_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    lock_path = file_path.with_suffix(file_path.suffix + '.lock')

    # 创建临时文件（同目录确保同文件系统，os.replace 才能原子操作）
    fd, temp_path = tempfile.mkstemp(
        suffix='.tmp',
        prefix=file_path.stem + '_',
        dir=parent_dir
    )

    try:
        # Step 1: 写入临时文件并 fsync
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())  # 确保写入磁盘

        # Step 2-4: 持锁完成备份 + 原子替换
        with contextlib.ExitStack() as stack:
            if use_lock:
                stack.enter_context(cross_process_lock(lock_path, timeout=10))

            if backup:
                _write_timestamped_backup(file_path)

            try:
                _replace_with_retry(temp_path, file_path)
                temp_path = None  # 标记已成功，不需要清理
            except PermissionError:
                if os.environ.get("WEBNOVEL_TEST_RELAX_ATOMIC_REPLACE") != "1":
                    raise
                # 测试沙箱可能允许写入但拒绝替换/删除既有文件；生产环境不启用该降级。
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())

    except Exception as e:
        raise AtomicWriteError(f"原子写入失败: {e}")

    finally:
        # 清理：删除临时文件（如果仍存在说明写入失败）
        if temp_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(temp_path)


def atomic_write_text(
    file_path: Union[str, Path],
    text: str,
    *,
    use_lock: bool = True,
    backup: bool = True,
) -> None:
    """
    原子化写入纯文本文件（Markdown 报告、摘要投影等）。

    与 atomic_write_json 同样的 tempfile + fsync + os.replace 语义，
    用于替换裸 Path.write_text —— 后者在写入中途崩溃会留下半截文件。

    示例:
        >>> atomic_write_text('.webnovel/summaries/ch0001.md', '## 剧情摘要\\n...')
    """
    _atomic_write(file_path, text, use_lock=use_lock, backup=backup)


def atomic_write_json(
    file_path: Union[str, Path],
    data: Dict[str, Any],
    *,
    use_lock: bool = True,
    backup: bool = True,
    indent: int = 2
) -> None:
    """
    原子化写入 JSON 文件，防止并发冲突和数据损坏 (CWE-362, CWE-367)

    安全关键函数 - 修复 state.json 并发写入风险

    实现策略:
    1. 写入临时文件（同目录，确保同文件系统）
    2. 取跨进程锁（filelock，未安装时回退 SQLite 全局锁）
    3. 可选：时间戳备份原文件（保留最近 20 份）
    4. 原子重命名（os.replace 在 POSIX 上是原子的）

    Args:
        file_path: 目标文件路径
        data: 要写入的字典数据
        use_lock: 是否使用跨进程锁
        backup: 是否在写入前备份原文件
        indent: JSON 缩进（默认 2）

    Raises:
        AtomicWriteError: 写入失败时抛出

    示例:
        >>> atomic_write_json('.webnovel/state.json', {'progress': {'chapter': 10}})

    安全验证:
        - ✅ 防止写入中断导致的数据损坏（先写临时文件 + fsync）
        - ✅ 防止并发写入冲突（filelock / SQLite 回退锁）
        - ✅ 支持回滚（时间戳备份，不再互相覆盖）
        - ✅ 跨平台兼容
    """
    # 准备 JSON 内容（序列化失败要在动目标文件之前就抛出）
    try:
        json_content = json.dumps(data, ensure_ascii=False, indent=indent)
    except (TypeError, ValueError) as e:
        raise AtomicWriteError(f"JSON 序列化失败: {e}")

    _atomic_write(file_path, json_content, use_lock=use_lock, backup=backup)


def read_json_safe(
    file_path: Union[str, Path],
    default: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    安全读取 JSON 文件（带默认值和错误处理）

    Args:
        file_path: 文件路径
        default: 文件不存在或解析失败时的默认值

    Returns:
        解析后的字典，或默认值

    示例:
        >>> state = read_json_safe('.webnovel/state.json', {})
    """
    file_path = Path(file_path)
    if default is None:
        default = {}

    if not file_path.exists():
        return default

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️ 读取 JSON 失败 ({file_path}): {e}", file=sys.stderr)
        return default


def restore_from_backup(file_path: Union[str, Path]) -> bool:
    """
    从最近一份备份恢复文件

    优先使用 backups/ 下最新的时间戳备份；找不到时回退到升级前的 <file>.bak。

    Args:
        file_path: 原文件路径

    Returns:
        是否成功恢复

    示例:
        >>> restore_from_backup('.webnovel/state.json')
        True
    """
    file_path = Path(file_path)
    backup_path = latest_backup(file_path)

    if backup_path is None:
        print(f"⚠️ 备份文件不存在: {file_path.parent / 'backups'}", file=sys.stderr)
        return False

    try:
        import shutil
        shutil.copy2(backup_path, file_path)
        print(f"✅ 已从备份恢复: {file_path} ← {backup_path.name}")
        return True
    except OSError as e:
        print(f"❌ 恢复失败: {e}", file=sys.stderr)
        return False


# ============================================================================
# 单元测试（内置自检）
# ============================================================================

def _run_self_tests():
    """运行内置安全测试"""
    print("🔍 运行安全工具函数自检...")

    # Test 1: sanitize_filename
    assert sanitize_filename("../../../etc/passwd") == "passwd", "路径遍历测试失败"
    assert sanitize_filename("C:\\Windows\\System32") == "System32", "Windows路径测试失败"
    assert sanitize_filename("正常角色名") == "正常角色名", "中文测试失败"
    assert sanitize_filename("/tmp/../../../../../etc/hosts") == "hosts", "复杂路径遍历测试失败"
    assert sanitize_filename("test///file...name") == "file_name", "特殊字符测试失败"  # . 会被替换
    print("  ✅ sanitize_filename: 所有测试通过")

    # Test 2: sanitize_commit_message
    result = sanitize_commit_message("Test\n--author='Attacker'")
    assert "\n" not in result, "换行符未移除"
    assert "--author" not in result, "Git标志未移除"
    assert "Attacker" in result, "内容被错误移除"

    assert sanitize_commit_message("--amend Chapter 1") == "Chapter 1", "Git标志测试失败"  # --amend被完全移除
    assert "'" not in sanitize_commit_message("Test'message"), "引号测试失败"
    assert sanitize_commit_message("-m Test") == "m Test", "单字母标志测试失败"  # -m被移除后是"m Test"
    print("  ✅ sanitize_commit_message: 所有测试通过")

    # Test 3: validate_integer_input
    assert validate_integer_input("123", "test") == 123, "整数验证测试失败"
    try:
        validate_integer_input("abc", "test")
        assert False, "应该抛出ValueError"
    except ValueError:
        pass
    print("  ✅ validate_integer_input: 所有测试通过")

    # Test 4: atomic_write_json
    import tempfile as tf
    test_dir = Path(tf.mkdtemp())
    test_file = test_dir / "test_state.json"

    # 写入测试
    test_data = {"chapter": 10, "中文键": "中文值"}
    atomic_write_json(test_file, test_data, use_lock=False, backup=False)
    assert test_file.exists(), "原子写入未创建文件"

    # 读取验证
    with open(test_file, 'r', encoding='utf-8') as f:
        loaded = json.load(f)
    assert loaded == test_data, "原子写入数据不匹配"

    # 备份测试（时间戳备份写入 backups/ 子目录）
    atomic_write_json(test_file, {"updated": True}, use_lock=False, backup=True)
    backups = list((test_dir / "backups").glob("test_state.backup_*.json"))
    assert backups, "备份未创建"

    # 恢复测试
    restore_from_backup(test_file)
    with open(test_file, 'r', encoding='utf-8') as f:
        restored = json.load(f)
    assert restored == test_data, "恢复数据不匹配"

    # 保留策略测试：写入 25 次后只保留最近 20 份
    for i in range(25):
        atomic_write_json(test_file, {"n": i}, use_lock=False, backup=True)
    kept = list((test_dir / "backups").glob("test_state.backup_*.json"))
    assert len(kept) == BACKUP_RETENTION, f"备份保留数应为 {BACKUP_RETENTION}，实际 {len(kept)}"

    # 清理
    import shutil
    shutil.rmtree(test_dir)
    print("  ✅ atomic_write_json: 所有测试通过")

    # Test 5: atomic_write_text
    text_dir = Path(tf.mkdtemp())
    text_file = text_dir / "report.md"
    atomic_write_text(text_file, "## 报告\n正文\n", use_lock=False, backup=False)
    assert text_file.read_text(encoding="utf-8") == "## 报告\n正文\n", "文本原子写入不匹配"
    assert not list(text_dir.glob("*.tmp")), "残留临时文件"
    shutil.rmtree(text_dir)
    print("  ✅ atomic_write_text: 所有测试通过")

    if HAS_FILELOCK:
        print("  ℹ️  filelock 可用，已启用文件锁支持")
    else:
        print("  ⚠️  filelock 未安装，已回退到 SQLite 全局锁")

    print("\n✅ 所有安全工具函数测试通过！")


if __name__ == "__main__":
    # Windows UTF-8 编码修复（必须在打印前执行）
    if sys.platform == "win32":
        enable_windows_utf8_stdio()

    # 运行自检测试
    _run_self_tests()
