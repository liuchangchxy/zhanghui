"""
M-H17 崩溃安全性验证：真实 kill -9 中途打断写入，确认目标文件不会半写。

每个用例都会 fork 一个真实子进程，让它在「临时文件已写完、os.replace 尚未
执行」的瞬间挂起，然后用 SIGKILL 干掉它 —— 这是断电 / OOM kill 的最坏时点。
断言：目标文件要么保持旧内容，要么根本不存在，绝不出现半截内容。

对照组 test_naive_write_text_IS_corrupted_by_kill 用裸 write_text 复现损坏，
证明本文件的杀进程时机确实能捕捉到这类 bug（否则测试全绿毫无意义）。
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]

# 足够大，保证裸 write_text 无法在一次系统调用内写完（对照组需要它被截断）
BIG_LINE = "这是一段足够长的中文正文用来撑大文件体积。" * 200
BIG_TEXT = "\n".join(f"{i:06d} {BIG_LINE}" for i in range(400))

READY_MARKER = "ready.flag"


def _run_child_and_kill(tmp_path: Path, body: str, timeout: float = 20.0) -> None:
    """
    在子进程里执行 body，等它写下 ready 标记后 SIGKILL。

    body 约定：在进入「不可中断区」之前创建 READY_MARKER，然后永久阻塞。
    """
    script = tmp_path / "child.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import os, sys, time
            sys.path.insert(0, {str(SCRIPTS_DIR)!r})
            TMP = {str(tmp_path)!r}
            READY = os.path.join(TMP, {READY_MARKER!r})
            BIG_TEXT = {BIG_TEXT!r}

            {textwrap.indent(textwrap.dedent(body), "            ").lstrip()}
            """
        ),
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        [sys.executable, str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    marker = tmp_path / READY_MARKER
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            if marker.exists():
                break
            if proc.poll() is not None:
                out, err = proc.communicate()
                pytest.fail(f"子进程提前退出 rc={proc.returncode}\nstdout={out}\nstderr={err}")
            time.sleep(0.01)
        else:
            pytest.fail("子进程未在超时内到达 ready 点")

        # 到达不可中断区，立刻 kill -9
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:  # pragma: no cover - 兜底
            proc.kill()
            proc.wait(timeout=10)

    assert proc.returncode in (-signal.SIGKILL, 137), f"期望被 SIGKILL，实际 rc={proc.returncode}"


# ---------------------------------------------------------------------------
# 对照组：证明「kill 时机」确实能捕获损坏
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL 语义为 POSIX")
def test_naive_write_text_IS_corrupted_by_kill(tmp_path):
    """裸 Path.write_text 被 kill -9 打断 → 目标文件被截断（这正是 M-H17）。"""
    target = tmp_path / "naive.md"
    good = "GOOD-ORIGINAL-CONTENT\n"
    target.write_text(good, encoding="utf-8")

    _run_child_and_kill(
        tmp_path,
        f"""
        target = os.path.join(TMP, "naive.md")
        # 复现裸 write_text：先截断，再慢慢写
        f = open(target, "w", encoding="utf-8")
        f.write(BIG_TEXT[:500])
        f.flush()
        open(READY, "w").close()
        time.sleep(300)
        """,
    )

    survived = target.read_text(encoding="utf-8")
    assert survived != good, "对照组未复现损坏，说明 kill 时机无效，其余用例不可信"
    assert "GOOD-ORIGINAL" not in survived
    assert survived != BIG_TEXT  # 半写状态


# ---------------------------------------------------------------------------
# 实验组：4 个写入点在同一时机下均保持完整
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL 语义为 POSIX")
def test_atomic_write_text_survives_kill(tmp_path):
    """security_utils.atomic_write_text：kill 于 replace 前，旧内容完好。"""
    target = tmp_path / "report.md"
    good = "GOOD-ORIGINAL-CONTENT\n"
    target.write_text(good, encoding="utf-8")

    _run_child_and_kill(
        tmp_path,
        """
        import security_utils
        real_replace = os.replace

        def hang(src, dst):
            open(READY, "w").close()   # 临时文件此刻已 fsync 落盘
            time.sleep(300)            # 在 rename 前被 kill -9

        os.replace = hang
        security_utils.os.replace = hang
        security_utils.atomic_write_text(
            os.path.join(TMP, "report.md"), BIG_TEXT, use_lock=False, backup=False
        )
        """,
    )

    assert target.read_text(encoding="utf-8") == good, "原子写入被打断后目标文件仍应是旧内容"


@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL 语义为 POSIX")
def test_style_fingerprint_save_survives_kill(tmp_path):
    """style_fingerprint.save_fingerprint：kill 后 baseline/指纹 JSON 仍可解析。"""
    profile_dir = tmp_path / ".webnovel" / "style-profile"
    profile_dir.mkdir(parents=True)
    target = profile_dir / "ch0001.json"
    good = {"chapter": 1, "avg_len": 20}
    target.write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")

    _run_child_and_kill(
        tmp_path,
        """
        import style_fingerprint as sf

        def hang(src, dst):
            open(READY, "w").close()
            time.sleep(300)

        os.replace = hang
        try:
            import security_utils
            security_utils.os.replace = hang
        except ImportError:
            pass
        sf.os.replace = hang

        fp = sf.Fingerprint(chapter=1, chapter_file="ch1.md", char_count=99999, avg_len=77)
        sf.save_fingerprint(__import__("pathlib").Path(TMP), 1, fp)
        """,
    )

    assert json.loads(target.read_text(encoding="utf-8")) == good


@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL 语义为 POSIX")
def test_summary_projection_survives_kill(tmp_path):
    """summary_projection_writer：kill 后摘要 md 不出现半截。"""
    summaries = tmp_path / ".webnovel" / "summaries"
    summaries.mkdir(parents=True)
    target = summaries / "ch0003.md"
    good = "## 剧情摘要\n旧摘要内容\n"
    target.write_text(good, encoding="utf-8")

    _run_child_and_kill(
        tmp_path,
        """
        import security_utils
        from data_modules.summary_projection_writer import append_summary_projection

        def hang(src, dst):
            open(READY, "w").close()
            time.sleep(300)

        os.replace = hang
        security_utils.os.replace = hang

        payload = {
            "meta": {"status": "accepted", "chapter": 3},
            "extraction_result": {"summary_text": BIG_TEXT},
        }
        append_summary_projection(TMP, payload)
        """,
    )

    assert target.read_text(encoding="utf-8") == good


@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL 语义为 POSIX")
def test_review_report_survives_kill(tmp_path):
    """review_pipeline.write_review_report：kill 后报告 md 不出现半截。"""
    target = tmp_path / "review.md"
    good = "# 旧审查报告\n"
    target.write_text(good, encoding="utf-8")

    _run_child_and_kill(
        tmp_path,
        """
        import security_utils
        import review_pipeline

        def hang(src, dst):
            open(READY, "w").close()
            time.sleep(300)

        os.replace = hang
        security_utils.os.replace = hang

        review_pipeline.render_review_report = lambda payload: BIG_TEXT
        review_pipeline.write_review_report(__import__("pathlib").Path(TMP), "review.md", {})
        """,
    )

    assert target.read_text(encoding="utf-8") == good


@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL 语义为 POSIX")
def test_atomic_write_json_survives_kill(tmp_path):
    """atomic_write_json：kill 后 state.json 仍是合法 JSON（旧值）。"""
    target = tmp_path / "state.json"
    good = {"progress": {"chapter": 10}}
    target.write_text(json.dumps(good), encoding="utf-8")

    _run_child_and_kill(
        tmp_path,
        """
        import security_utils

        def hang(src, dst):
            open(READY, "w").close()
            time.sleep(300)

        os.replace = hang
        security_utils.os.replace = hang

        big = {"progress": {"chapter": 11}, "blob": [BIG_TEXT] * 20}
        security_utils.atomic_write_json(
            os.path.join(TMP, "state.json"), big, use_lock=False, backup=False
        )
        """,
    )

    assert json.loads(target.read_text(encoding="utf-8")) == good
