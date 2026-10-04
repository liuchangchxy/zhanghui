"""Validate Canon, reset owned read models, and replay in canonical order."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .chapter_commit_service import ChapterCommitService
from .chapter_commit_schema import (
    DisambiguationResult,
    ExtractionResult,
    FulfillmentResult,
    ReviewResult,
)
from .durable_projection import read_commit_file
from .event_projection_router import EventProjectionRouter
from .commit_artifacts import extraction_list, extraction_text
from .event_log_store import EventLogStore
from .projection_rebuild_context import _controlled_rebuild


_COMMIT_NAME = re.compile(r"^chapter_(\d+)\.commit\.json$")
_MEMORY_EVIDENCE_PREFIXES = (
    "state_change:", "entity_new:", "relationship:", "chapter_meta:hook:",
    "memory_facts:timeline:", "memory_facts:world_rule:",
    "memory_facts:open_loop:", "memory_facts:reader_promise:",
)


class ProjectionRebuildError(RuntimeError):
    def __init__(self, message: str, *, chapter: int | None = None, projection: str = "canon"):
        super().__init__(message)
        self.chapter = chapter
        self.projection = projection


def discover_and_validate_commits(project_root: str | Path) -> list[dict[str, Any]]:
    root = Path(project_root).expanduser().resolve()
    directory = root / ".story-system" / "commits"
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ProjectionRebuildError(f"commit path is not a directory: {directory}")
    files = sorted(path for path in directory.iterdir() if path.is_file())
    commits: list[tuple[int, Path, dict[str, Any]]] = []
    seen: set[int] = set()
    for path in files:
        if path.name.endswith(".lock") and _COMMIT_NAME.fullmatch(path.name[:-5]):
            continue
        match = _COMMIT_NAME.fullmatch(path.name)
        if not match:
            raise ProjectionRebuildError(f"unexpected file in canonical commit directory: {path}")
        chapter = int(match.group(1))
        if chapter < 1:
            raise ProjectionRebuildError(f"invalid chapter number in commit filename: {path}")
        if path.name != f"chapter_{chapter:03d}.commit.json":
            raise ProjectionRebuildError(
                f"non-canonical durable commit filename: {path}", chapter=chapter
            )
        if chapter in seen:
            raise ProjectionRebuildError(f"duplicate durable commit for chapter {chapter}: {path}", chapter=chapter)
        seen.add(chapter)
        try:
            payload = read_commit_file(path)
            meta = payload.get("meta")
            if not isinstance(meta, dict):
                raise ValueError("meta must be an object")
            if int(meta.get("chapter") or 0) != chapter:
                raise ValueError(f"meta.chapter does not match filename chapter {chapter}")
            if meta.get("schema_version") != "story-system/v1":
                raise ValueError(f"unsupported schema version: {meta.get('schema_version')!r}")
            if meta.get("status") not in {"accepted", "rejected"}:
                raise ValueError(f"unsupported commit status: {meta.get('status')!r}")
            # Projection execution status is mutable and never participates in Canon validation.
            payload.pop("projection_status", None)
            ReviewResult.model_validate(payload.get("review_result"))
            FulfillmentResult.model_validate(payload.get("fulfillment_result"))
            DisambiguationResult.model_validate(payload.get("disambiguation_result"))
            ExtractionResult.model_validate(payload.get("extraction_result"))
        except Exception as exc:
            raise ProjectionRebuildError(
                f"invalid durable commit {path}: {exc}", chapter=chapter
            ) from exc
        commits.append((chapter, path, payload))
    commits.sort(key=lambda item: item[0])
    return [{"chapter": chapter, "path": path, "payload": payload} for chapter, path, payload in commits]


def _reset_events(root: Path) -> None:
    events = root / ".story-system" / "events"
    if events.is_dir():
        for path in events.glob("chapter_*.events.json"):
            path.unlink()
    db_path = root / ".webnovel" / "index.db"
    if db_path.is_file():
        with sqlite3.connect(db_path) as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='story_events'").fetchone()
            if exists:
                conn.execute("DELETE FROM story_events")
                seq_exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'").fetchone()
                if seq_exists:
                    conn.execute("DELETE FROM sqlite_sequence WHERE name='story_events'")


def _remove_path(target: dict[str, Any], path: str) -> None:
    parts = [part for part in path.split(".") if part]
    cursor: Any = target
    for part in parts[:-1]:
        if not isinstance(cursor, dict) or not isinstance(cursor.get(part), dict):
            return
        cursor = cursor[part]
    if isinstance(cursor, dict) and parts:
        cursor.pop(parts[-1], None)


def _reset_state(root: Path, commits: list[dict[str, Any]]) -> None:
    from .state_projection_writer import StateProjectionWriter
    from .story_contracts import write_json

    writer = StateProjectionWriter(root)
    state = json.loads(writer.state_path.read_text(encoding="utf-8")) if writer.state_path.is_file() else {}
    if not isinstance(state, dict):
        raise ValueError("state.json must contain an object")
    protagonist_ids = set()
    canonical_loops: set[str] = set()
    protagonist = state.get("protagonist_state")
    protagonist_name = str((protagonist or {}).get("name") or "") if isinstance(protagonist, dict) else ""
    for item in commits:
        payload = item["payload"]
        if payload["meta"]["status"] != "accepted":
            continue
        for event in extraction_list(payload, "accepted_events"):
            if isinstance(event, dict) and str(event.get("event_type") or "") in {"open_loop_created", "open_loop_closed"}:
                event_payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                content = str(event_payload.get("content") or event_payload.get("description") or event.get("subject") or "").strip()
                if content:
                    canonical_loops.add(content)
        protagonist_ids.update(writer._collect_protagonist_ids(payload, state))
        for delta in writer._collect_state_deltas(payload):
            if str(delta.get("entity_id") or "").strip() in protagonist_ids:
                _remove_path(state.setdefault("protagonist_state", {}), str(delta.get("field") or ""))
    state["entity_state"] = {}
    progress = state.setdefault("progress", {})
    for key in ("current_chapter", "total_words", "chapter_status", "last_updated"):
        progress.pop(key, None)
    tracker = state.get("strand_tracker")
    if isinstance(tracker, dict):
        for key in ("last_quest_chapter", "last_fire_chapter", "last_constellation_chapter", "current_dominant", "chapters_since_switch", "history"):
            tracker.pop(key, None)
    plot_threads = state.get("plot_threads")
    if isinstance(plot_threads, dict):
        rows = plot_threads.get("foreshadowing")
        if isinstance(rows, list):
            canonical_fields = ("status", "planted_chapter", "resolved_chapter", "target_chapter", "tier")
            for row in rows:
                if isinstance(row, dict) and str(row.get("content") or "").strip() in canonical_loops:
                    for key in canonical_fields:
                        row.pop(key, None)
    state["protagonist_state"] = state.get("protagonist_state") or {}
    write_json(writer.state_path, state)


def _reset_index(root: Path) -> None:
    from .config import DataModulesConfig
    from .index_manager import IndexManager

    config = DataModulesConfig.from_project_root(root)
    IndexManager(config)  # ensure tables exist before targeted clearing
    with sqlite3.connect(config.index_db) as conn:
        for table in ("chapters", "scenes", "appearances", "state_changes"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('scenes', 'appearances', 'state_changes')"
        )


def _reset_summaries(root: Path) -> None:
    directory = root / ".webnovel" / "summaries"
    if directory.is_dir():
        for path in directory.glob("ch[0-9]*.md"):
            if re.fullmatch(r"ch\d+\.md", path.name):
                path.unlink()


def _reset_memory(root: Path) -> None:
    from .config import DataModulesConfig
    from .memory.schema import BUCKET_TO_CATEGORY
    from .memory.store import ScratchpadManager

    store = ScratchpadManager(DataModulesConfig.from_project_root(root))
    with store._lock:
        data = store.load()
        for bucket in BUCKET_TO_CATEGORY:
            rows = getattr(data, bucket)
            setattr(data, bucket, [
                row for row in rows
                if not any(str(evidence).startswith(_MEMORY_EVIDENCE_PREFIXES) for evidence in row.evidence)
            ])
        store.save(data, _use_lock=False)


def _reset_vectors(root: Path, commits: list[dict[str, Any]]) -> None:
    from .config import DataModulesConfig
    from .rag_adapter import RAGAdapter

    config = DataModulesConfig.from_project_root(root)
    adapter = RAGAdapter(config)
    from .vector_projection_writer import VectorProjectionWriter

    canonical_chunk_ids = {
        chunk["chunk_id"]
        for item in commits if item["payload"]["meta"]["status"] == "accepted"
        for chunk in VectorProjectionWriter(root)._collect_chunks(item["payload"])
    }
    with adapter._get_conn() as conn:
        ids = {row[0] for row in conn.execute("SELECT chunk_id FROM vectors WHERE source_file LIKE 'commit:%'")}
        ids.update(canonical_chunk_ids)
        conn.execute("DELETE FROM vectors WHERE source_file LIKE 'commit:%'")
        if ids:
            values = sorted(ids)
            placeholders = ",".join("?" for _ in values)
            conn.execute(f"DELETE FROM bm25_index WHERE chunk_id IN ({placeholders})", values)
            conn.execute(f"DELETE FROM doc_stats WHERE chunk_id IN ({placeholders})", values)


def _prepare_targets(root: Path, commits: list[dict[str, Any]]) -> None:
    # Validate shared JSON stores before any projection target is changed.
    state_path = root / ".webnovel" / "state.json"
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("state.json must contain an object")
    memory_path = root / ".webnovel" / "memory_scratchpad.json"
    if memory_path.is_file():
        memory = json.loads(memory_path.read_text(encoding="utf-8"))
        if not isinstance(memory, dict):
            raise ValueError("memory_scratchpad.json must contain an object")
        for bucket in ("character_state", "story_facts", "world_rules", "timeline", "open_loops", "reader_promises", "relationships"):
            rows = memory.get(bucket, [])
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError(f"memory_scratchpad.json.{bucket} must be a list of objects")
    resetters = {
        "events": lambda: _reset_events(root),
        "state": lambda: _reset_state(root, commits),
        "index": lambda: _reset_index(root),
        "summary": lambda: _reset_summaries(root),
        "memory": lambda: _reset_memory(root),
        "vector": lambda: _reset_vectors(root, commits),
    }
    for name in EventProjectionRouter.PROJECTION_ORDER:
        try:
            resetters[EventProjectionRouter.PROJECTION_MANIFEST[name]["reset"]]()
        except Exception as exc:
            raise ProjectionRebuildError(
                f"failed to reset projection target: {exc}", projection=name
            ) from exc


def _validate_outputs(root: Path, commits: list[dict[str, Any]]) -> None:
    store = EventLogStore(root)
    db_path = root / ".webnovel" / "index.db"
    for item in commits:
        chapter = item["chapter"]
        payload = item["payload"]
        accepted = payload["meta"]["status"] == "accepted"
        expected_events = (
            store.normalize_events(chapter, extraction_list(payload, "accepted_events"))
            if accepted else []
        )
        event_path = root / ".story-system" / "events" / f"chapter_{chapter:03d}.events.json"
        if accepted and not event_path.is_file():
            raise ProjectionRebuildError("chapter event JSON mirror is missing", chapter=chapter, projection="events")
        actual_events = store.read_events(chapter)
        if actual_events != expected_events:
            raise ProjectionRebuildError("chapter JSON event mirror differs from Canon", chapter=chapter, projection="events")
        sqlite_events: list[dict[str, Any]] = []
        sqlite_table_present = False
        if db_path.is_file():
            with sqlite3.connect(db_path) as conn:
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "story_events" in tables:
                    sqlite_table_present = True
                    rows = conn.execute(
                        "SELECT event_id, chapter, event_type, subject, payload_json FROM story_events WHERE chapter=? ORDER BY event_id",
                        (chapter,),
                    ).fetchall()
                    sqlite_events = [
                        {"event_id": row[0], "chapter": row[1], "event_type": row[2], "subject": row[3], "payload": json.loads(row[4] or "{}")}
                        for row in rows
                    ]
        if accepted and not sqlite_table_present:
            raise ProjectionRebuildError("SQLite story_events mirror table is missing", chapter=chapter, projection="events")
        if sorted(sqlite_events, key=lambda row: row["event_id"]) != sorted(expected_events, key=lambda row: row["event_id"]):
            raise ProjectionRebuildError("SQLite story_events mirror differs from Canon", chapter=chapter, projection="events")

        summary = extraction_text(payload, "summary_text") if accepted else ""
        summary_path = root / ".webnovel" / "summaries" / f"ch{chapter:04d}.md"
        expected_summary = f"## 剧情摘要\n{summary}\n" if summary and "## 剧情摘要" not in summary else summary
        if summary and (not summary_path.is_file() or summary_path.read_text(encoding="utf-8") != expected_summary):
            raise ProjectionRebuildError("summary projection differs from Canon", chapter=chapter, projection="summary")
        if not summary and summary_path.exists():
            raise ProjectionRebuildError("unexpected summary projection without canonical summary", chapter=chapter, projection="summary")

        with sqlite3.connect(db_path) as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chapters'").fetchone()
            if exists:
                indexed = conn.execute("SELECT 1 FROM chapters WHERE chapter=?", (chapter,)).fetchone()
                if bool(indexed) != accepted:
                    raise ProjectionRebuildError("chapter index membership differs from commit status", chapter=chapter, projection="index")

    state_path = root / ".webnovel" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    status_map = ((state.get("progress") or {}).get("chapter_status") or {})
    for item in commits:
        chapter = item["chapter"]
        expected = "chapter_committed" if item["payload"]["meta"]["status"] == "accepted" else "chapter_rejected"
        if status_map.get(str(chapter)) != expected:
            raise ProjectionRebuildError("state chapter status differs from Canon", chapter=chapter, projection="state")


def rebuild_projections(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    try:
        commits = discover_and_validate_commits(root)
        if not commits:
            raise ProjectionRebuildError("no durable commits found; refusing to reset projections")
        _prepare_targets(root, commits)
    except Exception as exc:
        return {
            "schema_version": "webnovel-projections/v1",
            "action": "rebuild",
            "ok": False,
            "project_root": str(root),
            "chapters": [],
            "error": {"projection": getattr(exc, "projection", "prepare"), "chapter": getattr(exc, "chapter", None), "message": str(exc)},
            "results": [],
        }

    results = []
    service = ChapterCommitService(root)
    with _controlled_rebuild(root):
        for item in commits:
            chapter = item["chapter"]
            payload = item["payload"]
            try:
                projected = service.apply_projection_writers(payload)
                statuses = dict(projected.get("projection_status") or {})
                failures = {name: value for name, value in statuses.items() if str(value).startswith("failed")}
                results.append({"chapter": chapter, "ok": not failures, "projection_status": statuses})
                if failures:
                    name = next(iter(failures))
                    return {
                        "schema_version": "webnovel-projections/v1", "action": "rebuild", "ok": False,
                        "project_root": str(root), "chapters": [row["chapter"] for row in commits],
                        "error": {"projection": name, "chapter": chapter, "message": failures[name]},
                        "results": results,
                    }
            except Exception as exc:
                return {
                    "schema_version": "webnovel-projections/v1", "action": "rebuild", "ok": False,
                    "project_root": str(root), "chapters": [row["chapter"] for row in commits],
                    "error": {"projection": "coordinator", "chapter": chapter, "message": str(exc)},
                    "results": results,
                }
    try:
        _validate_outputs(root, commits)
    except Exception as exc:
        return {
            "schema_version": "webnovel-projections/v1", "action": "rebuild", "ok": False,
            "project_root": str(root), "chapters": [row["chapter"] for row in commits],
            "error": {"projection": getattr(exc, "projection", "validation"), "chapter": getattr(exc, "chapter", None), "message": str(exc)},
            "results": results,
        }
    return {
        "schema_version": "webnovel-projections/v1", "action": "rebuild", "ok": True,
        "project_root": str(root), "chapters": [row["chapter"] for row in commits],
        "error": None, "results": results,
    }
