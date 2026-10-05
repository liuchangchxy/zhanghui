"""Validate Canon, reset owned read models, and replay in canonical order."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .chapter_commit_service import ChapterCommitService
from .durable_projection import DurableCommitError, discover_validated_chapter_commits
from .event_projection_router import EventProjectionRouter
from .commit_artifacts import extraction_dict, extraction_list, extraction_text
from .event_log_store import EventLogStore
from .intent_reconciliation import intent_event_content_candidates, reconcile_intent_events
from .projection_rebuild_context import _controlled_rebuild


class ProjectionRebuildError(RuntimeError):
    def __init__(self, message: str, *, chapter: int | None = None, projection: str = "canon"):
        super().__init__(message)
        self.chapter = chapter
        self.projection = projection


def discover_and_validate_commits(project_root: str | Path) -> list[dict[str, Any]]:
    try:
        commits = discover_validated_chapter_commits(project_root)
    except DurableCommitError as exc:
        raise ProjectionRebuildError(str(exc), chapter=exc.chapter) from exc
    # Projection execution status is mutable and never participates in Canon validation.
    for item in commits:
        item["payload"].pop("projection_status", None)
    return commits


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
    canonical_loop_creates: list[dict[str, Any]] = []
    protagonist = state.get("protagonist_state")
    protagonist_name = str((protagonist or {}).get("name") or "") if isinstance(protagonist, dict) else ""
    for item in commits:
        payload = item["payload"]
        if payload["meta"]["status"] != "accepted":
            continue
        for event in extraction_list(payload, "accepted_events"):
            if isinstance(event, dict) and str(event.get("event_type") or "") == "open_loop_created":
                canonical_loop_creates.append(event)
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
            canonical_by_id = {
                str(event.get("event_id") or ""): event
                for event in canonical_loop_creates
                if str(event.get("event_id") or "").strip()
            }
            replay_rows = []
            for row in rows:
                if not isinstance(row, dict):
                    replay_rows.append(row)
                    continue
                row_id = str(row.get("loop_id") or row.get("source_event_id") or "").strip()
                if row_id and row_id in canonical_by_id:
                    # Canon-owned rows are regenerated by replay from the persisted event ID.
                    continue
                content = str(row.get("content") or "").strip()
                planted = writer._safe_int(row.get("source_chapter") or row.get("planted_chapter"))
                exact = [
                    event for event in canonical_loop_creates
                    if content in intent_event_content_candidates(event)
                ] if content else []
                exact_chapter = [event for event in exact if writer._safe_int(event.get("chapter")) == planted]
                if len(exact_chapter) == 1:
                    # Uniquely attributable legacy row is removed and replayed with identity/provenance.
                    continue
                if exact:
                    # Ambiguous or chapter-mismatched content remains visible as legacy, not active authority.
                    row["status"] = "legacy_unlinked"
                    row["link_status"] = "unlinked"
                replay_rows.append(row)
            plot_threads["foreshadowing"] = replay_rows
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


def _intent_diagnostics_path(root: Path) -> Path:
    return root / ".story-system" / "projections" / "intent-diagnostics.json"


def _reset_intent_diagnostics(root: Path) -> None:
    path = _intent_diagnostics_path(root)
    if path.exists():
        path.unlink()


def _expected_intent_diagnostics(commits: list[dict[str, Any]]) -> dict[str, Any]:
    events = [
        event
        for item in commits
        if item["payload"]["meta"]["status"] == "accepted"
        for event in extraction_list(item["payload"], "accepted_events")
        if isinstance(event, dict)
    ]
    result = reconcile_intent_events(events)
    diagnostics = sorted(
        result["diagnostics"],
        key=lambda row: (int(row.get("chapter") or 0), str(row.get("event_id") or ""), str(row.get("reason") or "")),
    )
    return {"schema_version": "intent-diagnostics/v1", "diagnostics": diagnostics}


def _write_intent_diagnostics(root: Path, commits: list[dict[str, Any]]) -> None:
    from .story_contracts import write_json

    path = _intent_diagnostics_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, _expected_intent_diagnostics(commits))


def _reset_memory(root: Path, commits: list[dict[str, Any]] | None = None) -> None:
    from .config import DataModulesConfig
    from .memory.schema import BUCKET_TO_CATEGORY, COMMIT_PROJECTION_EVIDENCE_PREFIXES
    from .memory.store import ScratchpadManager

    store = ScratchpadManager(DataModulesConfig.from_project_root(root))
    canonical_events = [
        event
        for item in (commits or [])
        if item["payload"]["meta"]["status"] == "accepted"
        for event in extraction_list(item["payload"], "accepted_events")
        if isinstance(event, dict)
    ]
    canonical_intent = reconcile_intent_events(canonical_events)
    canonical_by_category = {
        "open_loop": canonical_intent["open_loops"],
        "reader_promise": canonical_intent["reader_promises"],
    }
    create_types = {
        "open_loop_created": "open_loop",
        "promise_created": "reader_promise",
    }
    legacy_aliases: dict[str, dict[str, dict[str, Any]]] = {
        "open_loop": {},
        "reader_promise": {},
    }
    for event in canonical_events:
        category = create_types.get(str(event.get("event_type") or ""))
        event_id = str(event.get("event_id") or "").strip()
        if category and event_id:
            legacy_aliases[category].setdefault(event_id, {
                "source_chapter": int(event.get("chapter") or 0),
                "aliases": set(intent_event_content_candidates(event)),
            })
    from .memory.writer import MemoryWriter
    memory_writer = MemoryWriter(DataModulesConfig.from_project_root(root))
    with store._lock:
        data = store.load()
        for bucket in BUCKET_TO_CATEGORY:
            rows = getattr(data, bucket)
            retained = []
            for row in rows:
                evidence = [
                    value for value in row.evidence
                    if not str(value).startswith(COMMIT_PROJECTION_EVIDENCE_PREFIXES)
                ]
                if not evidence and row.evidence:
                    continue
                row.evidence = evidence
                category = BUCKET_TO_CATEGORY[bucket]
                has_identity = bool(
                    row.payload.get("loop_id") or row.payload.get("promise_event_id")
                    or row.payload.get("source_event_id")
                )
                if category in canonical_by_category and not has_identity:
                    row_contents = {
                        str(value or "").strip()
                        for value in (row.subject, row.value)
                        if str(value or "").strip()
                    }
                    candidate_ids = {
                        identity_id
                        for identity_id, source in legacy_aliases[category].items()
                        if row_contents.intersection(source["aliases"])
                    }
                    source_chapter = int(
                        row.payload.get("source_chapter")
                        or row.payload.get("planted_chapter")
                        or row.source_chapter
                        or 0
                    )
                    chapter_ids = {
                        identity_id
                        for identity_id in candidate_ids
                        if legacy_aliases[category][identity_id]["source_chapter"] == source_chapter
                    }
                    identities = {
                        str(item.get("identity_id") or ""): item
                        for item in canonical_by_category[category]
                    }
                    exact_chapter = [
                        identities[identity_id]
                        for identity_id in chapter_ids
                        if identity_id in identities
                    ]
                    if len(exact_chapter) == 1:
                        identity = exact_chapter[0]
                        identity_id = str(identity.get("identity_id") or "")
                        row.id = memory_writer._item_id(category, identity_id, "event", source_chapter)
                        row.payload.update({
                            "loop_id" if category == "open_loop" else "promise_event_id": identity_id,
                            "source_event_id": identity.get("source_event_id"),
                            "source_chapter": source_chapter,
                            "link_status": "legacy_exact_unique",
                        })
                    elif candidate_ids:
                        row.status = "outdated"
                        row.payload["lifecycle_status"] = "legacy_shadowed"
                        row.payload["link_status"] = "unlinked"
                retained.append(row)
            setattr(data, bucket, retained)
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
        "memory": lambda: _reset_memory(root, commits),
        "vector": lambda: _reset_vectors(root, commits),
        "intent_diagnostics": lambda: _reset_intent_diagnostics(root),
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

    from .index_projection_writer import IndexProjectionWriter

    index_writer = IndexProjectionWriter(root)
    expected_chapters: set[int] = set()
    expected_chapters_full: dict[int, tuple[str, str, int, str, str]] = {}
    expected_scenes: set[tuple[int, int, int, int, str, str, str]] = set()
    expected_appearances: set[tuple[str, int, str, float]] = set()
    expected_state_changes: set[tuple[str, str, str, str, str, int]] = set()
    for item in commits:
        chapter = item["chapter"]
        payload = item["payload"]
        if payload["meta"]["status"] != "accepted":
            continue
        expected_chapters.add(chapter)
        meta = extraction_dict(payload, "chapter_meta")
        title = str(meta.get("title") or payload.get("chapter_title") or index_writer._title_from_chapter_file(chapter) or "").strip()
        location = str(meta.get("location") or payload.get("location") or "").strip()
        summary = str(extraction_text(payload, "summary_text") or meta.get("summary") or "").strip()
        word_count = index_writer._safe_int(meta.get("word_count") or payload.get("word_count"))
        if word_count <= 0:
            word_count = index_writer._chapter_word_count(chapter)
        characters = meta.get("characters") or index_writer._collect_character_ids(payload)
        if not isinstance(characters, list):
            characters = []
        expected_chapters_full[chapter] = (
            title, location, word_count,
            json.dumps([str(c) for c in characters if str(c).strip()], ensure_ascii=False), summary,
        )
        for idx, scene in enumerate(extraction_list(payload, "scenes"), start=1):
            if isinstance(scene, dict):
                scene_index = index_writer._safe_int(scene.get("scene_index") or scene.get("index") or idx)
                scene_chars = scene.get("characters") or scene.get("character_ids") or []
                if not isinstance(scene_chars, list):
                    scene_chars = []
                expected_scenes.add((
                    chapter, scene_index, index_writer._safe_int(scene.get("start_line")),
                    index_writer._safe_int(scene.get("end_line")), str(scene.get("location") or "").strip(),
                    str(scene.get("summary") or scene.get("content") or "").strip(),
                    json.dumps([str(c) for c in scene_chars if str(c).strip()], ensure_ascii=False),
                ))
        for entity in extraction_list(payload, "entities_appeared"):
            if not isinstance(entity, dict):
                continue
            entity_id = str(entity.get("id") or entity.get("entity_id") or "").strip()
            if entity_id and entity_id != "NEW":
                mentions = entity.get("mentions") or []
                if isinstance(mentions, str):
                    mentions = [mentions]
                if not isinstance(mentions, list):
                    mentions = []
                expected_appearances.add((
                    entity_id, chapter,
                    json.dumps([str(m) for m in mentions if str(m).strip()], ensure_ascii=False),
                    index_writer._safe_float(entity.get("confidence"), 1.0),
                ))
        for change in index_writer._collect_state_changes(payload):
            entity_id = str(change.get("entity_id") or "").strip()
            field = str(change.get("field") or "").strip()
            change_chapter = index_writer._safe_int(change.get("chapter") or chapter)
            if not entity_id or not field or change_chapter <= 0:
                continue
            expected_state_changes.add((
                entity_id, field, index_writer._stringify(change.get("old")),
                index_writer._stringify(change.get("new")),
                str(change.get("reason") or "").strip(), change_chapter,
            ))
    with sqlite3.connect(db_path) as conn:
        actual_chapters_full = {
            row[0]: (row[1] or "", row[2] or "", row[3] or 0, row[4] or "[]", row[5] or "")
            for row in conn.execute("SELECT chapter, title, location, word_count, characters, summary FROM chapters")
        }
        actual_chapters = set(actual_chapters_full)
        actual_scenes = {
            (row[0], row[1], row[2] or 0, row[3] or 0, row[4] or "", row[5] or "", row[6] or "[]")
            for row in conn.execute("SELECT chapter, scene_index, start_line, end_line, location, summary, characters FROM scenes")
        }
        actual_appearances = {
            (row[0], row[1], row[2] or "[]", row[3] if row[3] is not None else 1.0)
            for row in conn.execute("SELECT entity_id, chapter, mentions, confidence FROM appearances")
        }
        actual_state_changes = {
            (row[0], row[1], row[2] or "", row[3] or "", row[4] or "", row[5])
            for row in conn.execute("SELECT entity_id, field, old_value, new_value, reason, chapter FROM state_changes")
        }
        state_change_row_count = conn.execute("SELECT COUNT(*) FROM state_changes").fetchone()[0]
    if state_change_row_count != len(actual_state_changes):
        raise ProjectionRebuildError("state_changes contains duplicate projection rows", projection="index")
    for chapter, expected_fields in expected_chapters_full.items():
        if actual_chapters_full.get(chapter) != expected_fields:
            raise ProjectionRebuildError("chapter index fields differ from canonical commit", chapter=chapter, projection="index")
    for name, actual, expected in (
        ("chapters", actual_chapters, expected_chapters),
        ("scenes", actual_scenes, expected_scenes),
        ("appearances", actual_appearances, expected_appearances),
        ("state_changes", actual_state_changes, expected_state_changes),
    ):
        if actual != expected:
            difference = actual.symmetric_difference(expected)
            sample = next(iter(difference), None)
            chapter_for_row = (
                sample if name == "chapters" and isinstance(sample, int)
                else sample[0] if isinstance(sample, tuple) and name == "scenes"
                else sample[1] if isinstance(sample, tuple) and name == "appearances"
                else sample[5] if isinstance(sample, tuple) and name == "state_changes"
                else None
            )
            raise ProjectionRebuildError(
                f"{name} index rows differ from canonical commits (expected {len(expected)}, found {len(actual)})",
                chapter=chapter_for_row, projection="index",
            )

    state_path = root / ".webnovel" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    status_map = ((state.get("progress") or {}).get("chapter_status") or {})
    for item in commits:
        chapter = item["chapter"]
        expected = "chapter_committed" if item["payload"]["meta"]["status"] == "accepted" else "chapter_rejected"
        if status_map.get(str(chapter)) != expected:
            raise ProjectionRebuildError("state chapter status differs from Canon", chapter=chapter, projection="state")

    diagnostics_path = _intent_diagnostics_path(root)
    if not diagnostics_path.is_file():
        raise ProjectionRebuildError("intent diagnostics projection is missing", projection="intent_diagnostics")
    try:
        actual_diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ProjectionRebuildError("intent diagnostics projection is invalid JSON", projection="intent_diagnostics") from exc
    if actual_diagnostics != _expected_intent_diagnostics(commits):
        raise ProjectionRebuildError("intent diagnostics projection differs from accepted commits", projection="intent_diagnostics")


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
        _write_intent_diagnostics(root, commits)
    except Exception as exc:
        return {
            "schema_version": "webnovel-projections/v1", "action": "rebuild", "ok": False,
            "project_root": str(root), "chapters": [row["chapter"] for row in commits],
            "error": {"projection": "intent_diagnostics", "chapter": None, "message": str(exc)},
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
