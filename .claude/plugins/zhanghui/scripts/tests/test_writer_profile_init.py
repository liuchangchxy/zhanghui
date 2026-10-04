"""测试 init 把 templates/个人语料.md 与 写作宪法.md copy 到 <book>/.webnovel/writer-profile/。

Phase E：webnovel-init 完成后，书项目根目录下应有：
  - .webnovel/writer-profile/个人语料.md
  - .webnovel/writer-profile/写作宪法.md

且重新运行 init 不会覆盖已存在的副本。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
WEBNOVEL_PY = SCRIPTS_DIR / "webnovel.py"
PLUGIN_ROOT = SCRIPTS_DIR.parent
TEMPLATE_DIR = PLUGIN_ROOT / "templates"


def _have_required_templates() -> bool:
    """如果 plugin templates 缺失对应文件，跳过整个模块（避免假阳性）。"""
    return (TEMPLATE_DIR / "个人语料.md").exists() and (TEMPLATE_DIR / "写作宪法.md").exists()


pytestmark = pytest.mark.skipif(
    not _have_required_templates(),
    reason="plugin templates/个人语料.md 或 写作宪法.md 缺失",
)


@pytest.fixture
def book_dir() -> Path:
    """创建书项目临时目录。

    注意：不能用默认的 tmp_path 夹具，因为 init_project.py 显式拒绝
    ".claude" 路径下的项目（防止误把书项目写到 plugin 工作树）。
    """
    base = Path("/tmp/webnovel_writer_profile_tests")
    base.mkdir(parents=True, exist_ok=True)
    book = base / f"book-{uuid.uuid4().hex}"
    book.mkdir()
    try:
        yield book
    finally:
        if os.environ.get("WEBNOVEL_KEEP_TEST_TMP") != "1":
            shutil.rmtree(book, ignore_errors=True)


def _run_init(book: Path) -> subprocess.CompletedProcess:
    """调用 webnovel.py init 生成书项目骨架。"""
    return subprocess.run(
        ["python3", str(WEBNOVEL_PY), "--project-root", str(book), "init",
         str(book), "pytest-book", "玄幻", "--target-chapters", "100"],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_init_creates_writer_profile(book_dir: Path) -> None:
    """运行 init 后，.webnovel/writer-profile/{个人语料,写作宪法}.md 应被创建。"""
    result = _run_init(book_dir)

    writer_profile = book_dir / ".webnovel" / "writer-profile"
    assert writer_profile.exists(), (
        f"writer-profile 未创建: {writer_profile}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert (writer_profile / "个人语料.md").exists(), "个人语料.md 未 copy"
    assert (writer_profile / "写作宪法.md").exists(), "写作宪法.md 未 copy"


def test_init_writer_profile_content_matches_template(book_dir: Path) -> None:
    """writer-profile 副本内容应与 plugin templates/ 源一致（首次 copy 时）。"""
    _run_init(book_dir)

    expected_personal = (TEMPLATE_DIR / "个人语料.md").read_text(encoding="utf-8")
    expected_constitution = (TEMPLATE_DIR / "写作宪法.md").read_text(encoding="utf-8")

    actual_personal = (book_dir / ".webnovel" / "writer-profile" / "个人语料.md").read_text(encoding="utf-8")
    actual_constitution = (book_dir / ".webnovel" / "writer-profile" / "写作宪法.md").read_text(encoding="utf-8")

    assert actual_personal == expected_personal, "个人语料.md 内容与 plugin 模板不一致"
    assert actual_constitution == expected_constitution, "写作宪法.md 内容与 plugin 模板不一致"


def test_init_does_not_overwrite_existing_writer_profile(book_dir: Path) -> None:
    """二次 init 不应覆盖用户在 .webnovel/writer-profile/ 已编辑的内容。"""
    # 首次 init：触发 copy
    first = _run_init(book_dir)
    assert first.returncode == 0, f"首次 init 失败: {first.stderr}"

    # 用户编辑副本
    personal_dst = book_dir / ".webnovel" / "writer-profile" / "个人语料.md"
    user_marker = "# USER OVERRIDE MARKER - DO NOT OVERWRITE"
    personal_dst.write_text(user_marker, encoding="utf-8")

    # 再次 init：应保留用户内容
    second = _run_init(book_dir)
    assert second.returncode == 0, f"二次 init 失败: {second.stderr}"

    assert personal_dst.read_text(encoding="utf-8") == user_marker, (
        "二次 init 覆盖了用户已编辑的个人语料.md（应当 only-if-missing）"
    )

