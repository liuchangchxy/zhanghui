#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
import sys
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List

from .chapter_commit_schema import normalize_accepted_events
from .durable_projection import DurableCommitError, read_durable_commit, require_durable_commit_match
from .story_contracts import StoryContractPaths, read_json_if_exists, write_json


class EventLogStore:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).expanduser().resolve()
        self.paths = StoryContractPaths.from_project_root(self.project_root)

    @contextmanager
    def _connect(self, *, row_factory: bool = False) -> Iterator[sqlite3.Connection]:
        """统一 SQLite 连接管理，确保连接始终关闭。"""
        db_path = self.project_root / ".webnovel" / "index.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        if row_factory:
            conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def write_events(self, commit_or_chapter: Dict[str, Any] | int, events: Any = None) -> Path:
        from .projection_generation import ProjectionGeneration
        if ProjectionGeneration(self.project_root).enrollment_path.exists():
            raise DurableCommitError("activation-managed event writes require an effective generation")
        if isinstance(commit_or_chapter, dict):
            payload = commit_or_chapter
            commit = require_durable_commit_match(self.project_root, payload)
            chapter = int((payload.get("meta") or {}).get("chapter") or 0)
            raw_events = ((payload.get("extraction_result") or {}).get("accepted_events") or [])
            normalized = self.normalize_events(chapter, raw_events)
        else:
            chapter = int(commit_or_chapter)
            # Normalize before checking provenance so malformed event input keeps
            # its useful schema error and cannot trigger any write.
            normalized = self.normalize_events(chapter, events)
            commit = read_durable_commit(self.project_root, chapter)
            payload = deepcopy(commit)
            extraction = payload.setdefault("extraction_result", {})
            if not isinstance(extraction, dict):
                raise DurableCommitError("Durable chapter commit extraction_result is not an object")
            extraction["accepted_events"] = normalized
            require_durable_commit_match(self.project_root, payload)

        if str((commit.get("meta") or {}).get("status") or "") != "accepted":
            raise DurableCommitError(
                f"Event projection requires a matching accepted chapter commit: {self.paths.commit_json(chapter)}"
            )
        path = self.paths.event_json(chapter)
        write_json(path, normalized)
        self._write_sqlite_mirror(chapter, normalized)
        return path

    def read_events(self, chapter: int) -> List[Dict[str, Any]]:
        from .owned_project_view import OwnedProjectView

        view = OwnedProjectView.pin_active(self.project_root)
        if view is not None:
            result = view.canon_chapter(chapter)
            events = result["domains"].get("events", {}).get("accepted_events", [])
            return events if result["effective_status"] == "accepted" and isinstance(events, list) else []
        return list(read_json_if_exists(self.paths.event_json(chapter)) or [])

    def list_recent(self, chapter: int | None = None, limit: int = 200) -> List[Dict[str, Any]]:
        from .owned_project_view import OwnedProjectView

        view = OwnedProjectView.pin_active(self.project_root)
        if view is not None:
            rows = []
            for doc in sorted((view.pinned.generation_root / "events").glob("chapter_*.json")):
                number = int(doc.stem.removeprefix("chapter_"))
                if chapter is not None and chapter != number:
                    continue
                payload = json.loads(doc.read_text(encoding="utf-8"))
                events = payload.get("projection", {}).get("accepted_events", [])
                rows.extend({**event, "chapter": number} for event in events if isinstance(event, dict))
            rows.sort(key=lambda row: (int(row.get("chapter") or 0), str(row.get("event_id") or "")), reverse=True)
            return rows[:limit]
        db_path = self.project_root / ".webnovel" / "index.db"
        if not db_path.is_file():
            return []
        with self._connect(row_factory=True) as conn:
            try:
                if chapter is not None:
                    rows = conn.execute(
                        """
                        SELECT event_id, chapter, event_type, subject, payload_json
                        FROM story_events
                        WHERE chapter = ?
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (chapter, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT event_id, chapter, event_type, subject, payload_json
                        FROM story_events
                        ORDER BY chapter DESC, id DESC
                        LIMIT ?
                        """,
                        (limit,),
                    ).fetchall()
            except sqlite3.OperationalError:
                return []

        result: List[Dict[str, Any]] = []
        for row in rows:
            payload = {}
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except json.JSONDecodeError:
                payload = {}
            result.append(
                {
                    "event_id": row["event_id"],
                    "chapter": row["chapter"],
                    "event_type": row["event_type"],
                    "subject": row["subject"],
                    "payload": payload,
                }
            )
        return result

    def health(self) -> Dict[str, Any]:
        db_path = self.project_root / ".webnovel" / "index.db"
        file_count = len(list(self.paths.events_dir.glob("chapter_*.events.json")))
        sqlite_rows = 0
        if db_path.is_file():
            with self._connect() as conn:
                try:
                    sqlite_rows = int(
                        conn.execute("SELECT COUNT(*) FROM story_events").fetchone()[0]
                    )
                except sqlite3.OperationalError:
                    sqlite_rows = 0
        return {"ok": True, "sqlite_rows": sqlite_rows, "event_files": file_count}

    def normalize_events(self, chapter: int, events: Any) -> List[Dict[str, Any]]:
        return normalize_accepted_events(chapter, events)

    def _write_sqlite_mirror(self, chapter: int, events: List[Dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS story_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    chapter INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_story_events_chapter ON story_events(chapter)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_story_events_type ON story_events(event_type)"
            )
            conn.execute("DELETE FROM story_events WHERE chapter = ?", (chapter,))
            conn.executemany(
                """
                INSERT OR REPLACE INTO story_events(event_id, chapter, event_type, subject, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        event["event_id"],
                        int(event["chapter"]),
                        event["event_type"],
                        event["subject"],
                        json.dumps(event.get("payload") or {}, ensure_ascii=False),
                    )
                    for event in events
                ],
            )
            conn.commit()

    def apply_effective(self, effective_input, build_handle) -> dict:
        from .effective_history import EffectiveProjectionInput, write_effective_projection
        if not isinstance(effective_input, EffectiveProjectionInput):
            raise TypeError("apply_effective requires EffectiveProjectionInput")
        entry = effective_input.effective_entry
        extraction = entry.extraction_result or {}
        return write_effective_projection(
            self.project_root, effective_input, build_handle, "events", "events",
            {"tombstone": entry.status != "accepted",
             "accepted_events": extraction.get("accepted_events", [])
             if entry.status == "accepted" else []},
        )
