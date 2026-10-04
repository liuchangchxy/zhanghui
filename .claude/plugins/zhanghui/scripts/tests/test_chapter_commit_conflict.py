"""Tests for ChapterCommitService.persist_commit --on-conflict 守卫。

直接调 service（不通过 CLI）确保守卫真正被执行，避免上层 Pydantic 校验掩盖。
"""
import json
import sys
from pathlib import Path

import pytest

# 与 sibling 测试一致：把 scripts/ 加入 path（让 scripts.* 和 data_modules.* 都可解析）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_modules.chapter_commit_service import ChapterCommitService, ChapterCommitError  # noqa: E402
from scripts._shared.safe_overwrite import ConflictMode  # noqa: E402


def _make_payload(service: ChapterCommitService, chapter: int = 1) -> dict:
    """构造一个 minimal accepted payload。"""
    return service.build_commit(
        chapter=chapter,
        review_result={"blocking_count": 0},
        fulfillment_result={
            "planned_nodes": ["发现陷阱"],
            "covered_nodes": ["发现陷阱"],
            "missed_nodes": [],
            "extra_nodes": [],
        },
        disambiguation_result={"pending": []},
        extraction_result={
            "state_deltas": [],
            "entity_deltas": [],
            "accepted_events": [],
        },
    )


@pytest.fixture
def service_with_existing_commit(tmp_path):
    """预创建已存在的 chapter_001.commit.json 的 service。"""
    commits_dir = tmp_path / ".story-system" / "commits"
    commits_dir.mkdir(parents=True)
    existing = commits_dir / "chapter_001.commit.json"
    existing.write_text(
        json.dumps({"meta": {"chapter": 1, "status": "accepted"}, "old": True}),
        encoding="utf-8",
    )
    return ChapterCommitService(tmp_path), existing


class TestPersistCommitConflictGuard:
    def test_default_rejects_overwrite(self, service_with_existing_commit):
        """默认（mode=None）+ commit 已存在 → 抛 ChapterCommitError，文件不变。"""
        service, existing = service_with_existing_commit
        payload = _make_payload(service, chapter=1)
        with pytest.raises(ChapterCommitError, match="已存在"):
            service.persist_commit(payload, on_conflict=None)
        # 文件未被覆盖
        assert json.loads(existing.read_text()).get("old") is True

    def test_apply_projections_does_not_overwrite_existing_commit_by_default(self, service_with_existing_commit, monkeypatch):
        service, existing = service_with_existing_commit
        payload = _make_payload(service, chapter=1)
        monkeypatch.setattr(
            service,
            "_projection_writers",
            lambda: pytest.fail("projection ran before commit conflict was rejected"),
        )

        with pytest.raises(ChapterCommitError, match="已存在"):
            service.apply_projections(payload)

        assert json.loads(existing.read_text()).get("old") is True

    def test_overwrite_replaces_existing(self, service_with_existing_commit):
        """--on-conflict=overwrite + commit 已存在 → 文件被替换为新 payload。"""
        service, existing = service_with_existing_commit
        payload = _make_payload(service, chapter=1)
        result = service.persist_commit(
            payload, on_conflict=ConflictMode.OVERWRITE.value
        )
        assert result == existing
        new_content = json.loads(existing.read_text())
        assert "old" not in new_content
        assert new_content["meta"]["status"] == "accepted"

    def test_skip_keeps_existing(self, service_with_existing_commit):
        """--on-conflict=skip + commit 已存在 → 文件不变，return path。"""
        service, existing = service_with_existing_commit
        payload = _make_payload(service, chapter=1)
        result = service.persist_commit(
            payload, on_conflict=ConflictMode.SKIP.value
        )
        assert result == existing
        # 文件未变
        assert json.loads(existing.read_text()).get("old") is True

    def test_default_writes_when_no_existing(self, tmp_path):
        """默认 + commit 不存在 → 直接写入（正常路径）。"""
        service = ChapterCommitService(tmp_path)
        payload = _make_payload(service, chapter=1)
        result = service.persist_commit(payload)
        assert result.exists()
        content = json.loads(result.read_text())
        assert content["meta"]["status"] == "accepted"

    def test_append_mode_rejected_as_unsupported(self, service_with_existing_commit):
        """--on-conflict=append 在本脚本不支持 → ChapterCommitError。"""
        service, _ = service_with_existing_commit
        payload = _make_payload(service, chapter=1)
        with pytest.raises(ChapterCommitError, match="不支持 append"):
            service.persist_commit(
                payload, on_conflict=ConflictMode.APPEND.value
            )
