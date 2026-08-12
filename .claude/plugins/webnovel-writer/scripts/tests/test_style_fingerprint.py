"""
style_fingerprint 落盘路径的原子性与正确性（M-H17）。

两份副本（.claude/scripts 与插件 scripts/）必须保持一致，本文件同时守护
这一点 —— 只改其中一份是历史上反复出现的漏改。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import style_fingerprint as sf

PLUGIN_COPY = Path(sf.__file__).resolve()
STANDALONE_COPY = PLUGIN_COPY.parents[3] / "scripts" / "style_fingerprint.py"


def _fp(chapter: int = 1, **kw) -> sf.Fingerprint:
    base = dict(chapter=chapter, chapter_file=f"ch{chapter}.md", char_count=1200, avg_len=18)
    base.update(kw)
    return sf.Fingerprint(**base)


# ---------------------------------------------------------------------------
# 落盘正确性
# ---------------------------------------------------------------------------

def test_save_fingerprint_writes_valid_json(tmp_path):
    path = sf.save_fingerprint(tmp_path, 1, _fp(1, avg_len=23))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["chapter"] == 1
    assert data["avg_len"] == 23


def test_save_fingerprint_leaves_no_temp_files(tmp_path):
    """原子写入的临时文件必须清理干净，不能污染 style-profile 目录。"""
    sf.save_fingerprint(tmp_path, 1, _fp(1))
    profile_dir = tmp_path / ".webnovel" / "style-profile"
    assert not list(profile_dir.glob("*.tmp"))
    assert [p.name for p in profile_dir.iterdir()] == ["ch0001.json"]


def test_save_fingerprint_overwrite_is_clean(tmp_path):
    """覆盖写不得残留旧内容尾巴（长 → 短）。"""
    sf.save_fingerprint(tmp_path, 1, _fp(1, chapter_file="x" * 5000))
    path = sf.save_fingerprint(tmp_path, 1, _fp(1, chapter_file="s.md"))

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["chapter_file"] == "s.md"
    assert "xxxx" not in path.read_text(encoding="utf-8")


def test_save_fingerprint_roundtrips_through_reader(tmp_path):
    sf.save_fingerprint(tmp_path, 4, _fp(4, dialogue_ratio=42))
    loaded = sf._read_fingerprint(tmp_path / ".webnovel" / "style-profile" / "ch0004.json")
    assert loaded is not None
    assert loaded.dialogue_ratio == 42


def test_generate_baseline_writes_atomic_json(tmp_path):
    for ch in (1, 2, 3):
        sf.save_fingerprint(tmp_path, ch, _fp(ch, avg_len=20 + ch))

    payload = sf.generate_baseline(tmp_path, [1, 2, 3])
    baseline_file = tmp_path / ".webnovel" / "style-profile" / "baseline.json"

    assert json.loads(baseline_file.read_text(encoding="utf-8")) == payload
    assert payload["baseline_chapters"] == [1, 2, 3]
    assert not list(baseline_file.parent.glob("*.tmp"))


def test_load_baseline_roundtrip(tmp_path):
    for ch in (1, 2, 3):
        sf.save_fingerprint(tmp_path, ch, _fp(ch))
    written = sf.generate_baseline(tmp_path, [1, 2, 3])
    assert sf.load_baseline(tmp_path) == written


def test_save_fingerprint_unicode_is_not_escaped(tmp_path):
    """中文按原样写入（ensure_ascii=False），保持人工可读。"""
    path = sf.save_fingerprint(tmp_path, 2, _fp(2, chapter_file="第二章 觉醒.md"))
    assert "第二章 觉醒.md" in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 双副本一致性
# ---------------------------------------------------------------------------

def test_two_copies_stay_identical():
    """.claude/scripts 与插件下的副本必须逐字节一致（防止只改一份）。"""
    if not STANDALONE_COPY.exists():  # pragma: no cover - 布局变化时跳过
        pytest.skip(f"未找到独立副本: {STANDALONE_COPY}")

    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(PLUGIN_COPY) == digest(STANDALONE_COPY), (
        f"两份 style_fingerprint.py 不一致：\n  {PLUGIN_COPY}\n  {STANDALONE_COPY}"
    )


def test_no_bare_write_text_remains():
    """回归保护：所有落盘都必须走原子写入，不得回退到裸 write_text。"""
    src = PLUGIN_COPY.read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in src.splitlines()
        if ".write_text(" in line and "def " not in line
    ]
    assert not offenders, f"发现未原子化的写入: {offenders}"
