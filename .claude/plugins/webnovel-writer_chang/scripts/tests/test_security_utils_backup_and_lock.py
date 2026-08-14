"""
M-H21：时间戳备份（不再用单个 .bak 互相覆盖）
M-H26：filelock 缺失时回退到 SQLite 全局锁，保证跨进程互斥
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

import security_utils
from security_utils import (
    BACKUP_RETENTION,
    atomic_write_json,
    latest_backup,
    read_json_safe,
    restore_from_backup,
)

SCRIPTS_DIR = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# M-H21 时间戳备份
# ---------------------------------------------------------------------------

def test_backup_goes_to_timestamped_file_not_bak(tmp_path):
    target = tmp_path / "state.json"
    atomic_write_json(target, {"v": 1}, use_lock=False, backup=False)
    atomic_write_json(target, {"v": 2}, use_lock=False, backup=True)

    backups = list((tmp_path / "backups").glob("state.backup_*.json"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == {"v": 1}
    assert not (tmp_path / "state.json.bak").exists(), "不应再写死 .bak"


def test_consecutive_writes_do_not_overwrite_each_other(tmp_path):
    """
    M-H21 的核心：连续两次写入后，倒数第二份好数据仍然可恢复。
    旧实现固定写 .bak，第二次写入会把唯一一份好备份覆盖掉。
    """
    target = tmp_path / "state.json"
    atomic_write_json(target, {"gen": "good"}, use_lock=False, backup=False)
    atomic_write_json(target, {"gen": "bad1"}, use_lock=False, backup=True)
    atomic_write_json(target, {"gen": "bad2"}, use_lock=False, backup=True)

    saved = sorted(
        json.loads(p.read_text(encoding="utf-8"))["gen"]
        for p in (tmp_path / "backups").glob("state.backup_*.json")
    )
    assert saved == ["bad1", "good"], "历史备份被覆盖，M-H21 未修复"


def test_backup_retention_keeps_newest_20(tmp_path):
    target = tmp_path / "state.json"
    atomic_write_json(target, {"n": -1}, use_lock=False, backup=False)
    for i in range(30):
        atomic_write_json(target, {"n": i}, use_lock=False, backup=True)

    backups = sorted((tmp_path / "backups").glob("state.backup_*.json"))
    assert len(backups) == BACKUP_RETENTION

    # 保留的是最新的 20 份（最旧的被裁掉）
    kept = sorted(json.loads(p.read_text(encoding="utf-8"))["n"] for p in backups)
    assert kept == list(range(9, 29))


def test_restore_uses_latest_backup(tmp_path):
    target = tmp_path / "state.json"
    atomic_write_json(target, {"v": "first"}, use_lock=False, backup=False)
    atomic_write_json(target, {"v": "second"}, use_lock=False, backup=True)
    atomic_write_json(target, {"v": "third"}, use_lock=False, backup=True)

    assert restore_from_backup(target) is True
    assert read_json_safe(target) == {"v": "second"}, "应恢复最近一份备份"


def test_restore_falls_back_to_legacy_bak(tmp_path):
    """升级前留下的 <file>.bak 仍然可用（不破坏已有项目的恢复路径）。"""
    target = tmp_path / "state.json"
    target.write_text('{"v": "corrupt"}', encoding="utf-8")
    (tmp_path / "state.json.bak").write_text('{"v": "legacy"}', encoding="utf-8")

    assert restore_from_backup(target) is True
    assert read_json_safe(target) == {"v": "legacy"}


def test_restore_returns_false_without_any_backup(tmp_path):
    target = tmp_path / "state.json"
    target.write_text("{}", encoding="utf-8")
    assert restore_from_backup(target) is False


def test_latest_backup_none_when_absent(tmp_path):
    assert latest_backup(tmp_path / "nope.json") is None


def test_backup_filename_with_glob_metacharacters(tmp_path):
    """文件名含 [ ] 等 glob 元字符时仍能正确匹配自己的备份。"""
    target = tmp_path / "state[v1].json"
    atomic_write_json(target, {"v": 1}, use_lock=False, backup=False)
    atomic_write_json(target, {"v": 2}, use_lock=False, backup=True)

    assert latest_backup(target) is not None
    assert json.loads(latest_backup(target).read_text(encoding="utf-8")) == {"v": 1}


def test_backups_are_isolated_per_file(tmp_path):
    """同目录下不同文件的备份互不干扰、互不裁剪。"""
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    atomic_write_json(a, {"x": 0}, use_lock=False, backup=False)
    atomic_write_json(b, {"y": 0}, use_lock=False, backup=False)
    for i in range(25):
        atomic_write_json(a, {"x": i}, use_lock=False, backup=True)
    atomic_write_json(b, {"y": 1}, use_lock=False, backup=True)

    assert len(list((tmp_path / "backups").glob("a.backup_*.json"))) == BACKUP_RETENTION
    assert len(list((tmp_path / "backups").glob("b.backup_*.json"))) == 1


# ---------------------------------------------------------------------------
# M-H26 filelock 回退到 SQLite 锁
# ---------------------------------------------------------------------------

def test_sqlite_lock_used_when_filelock_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(security_utils, "HAS_FILELOCK", False)
    monkeypatch.setenv("WEBNOVEL_LOCK_DIR", str(tmp_path / "lockdir"))

    target = tmp_path / "state.json"
    atomic_write_json(target, {"v": 1}, use_lock=True, backup=False)

    assert read_json_safe(target) == {"v": 1}
    assert (tmp_path / "lockdir" / "writer.lock").exists(), "未创建 SQLite 锁库"


def test_sqlite_lock_is_reentrant_across_sequential_acquires(tmp_path, monkeypatch):
    monkeypatch.setattr(security_utils, "HAS_FILELOCK", False)
    monkeypatch.setenv("WEBNOVEL_LOCK_DIR", str(tmp_path / "lockdir"))

    for i in range(3):
        with security_utils.cross_process_lock(tmp_path / "x.lock", timeout=5):
            pass


def test_sqlite_lock_releases_on_exception(tmp_path, monkeypatch):
    """持锁体内抛异常必须释放锁，否则后续写入全部超时。"""
    monkeypatch.setattr(security_utils, "HAS_FILELOCK", False)
    monkeypatch.setenv("WEBNOVEL_LOCK_DIR", str(tmp_path / "lockdir"))

    with pytest.raises(RuntimeError):
        with security_utils.cross_process_lock(tmp_path / "x.lock", timeout=5):
            raise RuntimeError("boom")

    # 仍可再次获取
    with security_utils.cross_process_lock(tmp_path / "x.lock", timeout=5):
        pass


@pytest.mark.skipif(sys.platform == "win32", reason="依赖 POSIX 进程语义")
def test_sqlite_lock_mutual_exclusion_across_processes(tmp_path):
    """
    M-H26 核心：filelock 缺失时，多个**进程**不得同时进入临界区。
    修复前该分支完全无锁，并发写会丢更新。
    """
    lock_dir = tmp_path / "lockdir"
    marker = tmp_path / "marker.txt"

    child = tmp_path / "child.py"
    child.write_text(
        textwrap.dedent(
            f"""
            import os, sys, time
            sys.path.insert(0, {str(SCRIPTS_DIR)!r})
            os.environ["WEBNOVEL_LOCK_DIR"] = {str(lock_dir)!r}
            import security_utils
            security_utils.HAS_FILELOCK = False
            with security_utils.cross_process_lock("x.lock", timeout=60):
                with open({str(marker)!r}, "a") as fh:
                    fh.write("ENTER %d\\n" % os.getpid()); fh.flush()
                time.sleep(0.8)
                with open({str(marker)!r}, "a") as fh:
                    fh.write("EXIT %d\\n" % os.getpid())
            """
        ),
        encoding="utf-8",
    )

    procs = [subprocess.Popen([sys.executable, str(child)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for _ in range(3)]
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, f"子进程失败: {err}"

    lines = [l.split()[0] for l in marker.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 6
    # 严格交替 ENTER/EXIT 说明临界区互斥；出现 ENTER,ENTER 即为并发进入
    assert lines == ["ENTER", "EXIT"] * 3, f"临界区未互斥: {lines}"
