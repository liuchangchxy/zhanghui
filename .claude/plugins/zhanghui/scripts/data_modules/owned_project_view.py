"""Compose one pinned Canon generation with independently mutable owner stores."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Any, Callable

from filelock import FileLock

from .canon_correction_schema import canonical_json
from .projection_generation import PinnedGeneration


class OwnedViewError(RuntimeError):
    pass


_CANON_INDEX_TABLES = {"chapters", "scenes", "appearances", "state_changes", "story_events", "entities"}
_OWNER_STATE_ROOTS = {"story_craft", "planning", "promise_ledger", "review_checkpoints",
                      "workflow", "craft", "intent"}
_OWNER_STATE_PATHS = {"progress.volumes_planned", "progress.current_volume",
                      "progress.total_volumes"}
_CANON_STATE_ROOTS = {"entity_state", "protagonist_state", "strand_tracker"}


def _pinned(pinned: PinnedGeneration) -> Path:
    if not isinstance(pinned, PinnedGeneration) or not pinned.generation_root.is_dir():
        raise OwnedViewError("PINNED_GENERATION_REQUIRED")
    return pinned.generation_root


def _chapter_documents(pinned: PinnedGeneration, domain: str) -> list[dict[str, Any]]:
    root = _pinned(pinned) / domain
    documents = []
    if root.is_dir():
        for path in sorted(root.glob("chapter_*.json")):
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise OwnedViewError("INVALID_CANON_SLICE")
            documents.append(value)
    return documents


class OwnedStateStore:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).expanduser().resolve()
        self.overlay_path = self.project_root / ".webnovel/state-overlay.json"
        self.lock_path = self.overlay_path.with_suffix(".lock")

    def _overlay(self) -> dict[str, Any]:
        if not self.overlay_path.exists():
            return {"schema_version": "owner-state-overlay/v1", "revision": 0, "values": {}}
        data = json.loads(self.overlay_path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or data.get("schema_version") != "owner-state-overlay/v1"
                or not isinstance(data.get("values"), dict)):
            raise OwnedViewError("OWNER_STATE_OVERLAY_INVALID")
        return data

    def read_view(self, pinned: PinnedGeneration) -> dict[str, Any]:
        canon: dict[str, Any] = {"entity_state": {}, "progress": {"chapter_status": {}},
                                 "protagonist_state": {}, "strand_tracker": {}}
        for doc in _chapter_documents(pinned, "state"):
            projection = doc.get("projection", {})
            if projection.get("tombstone"):
                canon["progress"]["chapter_status"][str(doc["chapter"])] = "retracted"
                continue
            canon["progress"]["chapter_status"][str(doc["chapter"])] = doc.get("effective_status")
            for delta in projection.get("state_deltas", []):
                entity = str(delta.get("entity_id") or "").strip()
                field = str(delta.get("field") or "").strip()
                if not entity or not field:
                    continue
                target = canon["entity_state"].setdefault(entity, {})
                parts = [part for part in field.split(".") if part]
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                if parts:
                    target[parts[-1]] = delta.get("new")
        overlay = self._overlay()
        values = overlay["values"]
        collision = _CANON_STATE_ROOTS.intersection(values)
        if collision:
            raise OwnedViewError(f"OWNER_CANON_STATE_COLLISION:{sorted(collision)}")
        result = canon
        for key, value in values.items():
            if key in _OWNER_STATE_PATHS:
                parts = key.split(".")
                target = result
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                if parts[-1] in target:
                    raise OwnedViewError(f"OWNER_CANON_STATE_COLLISION:{key}")
                target[parts[-1]] = value
                continue
            if key not in _OWNER_STATE_ROOTS:
                raise OwnedViewError(f"UNOWNED_STATE_OVERLAY_PATH:{key}")
            if key in result:
                raise OwnedViewError(f"OWNER_CANON_STATE_COLLISION:{key}")
            result[key] = value
        result["_view"] = {"generation_id": pinned.generation_id,
                           "semantic_activation_id": pinned.semantic_activation_id,
                           "owner_overlay_revision": overlay.get("revision", 0)}
        return result

    def write_owner_values(self, values: dict[str, Any]) -> int:
        if not isinstance(values, dict) or not values:
            raise OwnedViewError("OWNER_STATE_VALUES_REQUIRED")
        if _CANON_STATE_ROOTS.intersection(values):
            raise OwnedViewError("CANON_STATE_IS_IMMUTABLE")
        unknown = set(values) - _OWNER_STATE_ROOTS - _OWNER_STATE_PATHS
        if unknown:
            raise OwnedViewError(f"UNOWNED_STATE_OVERLAY_PATH:{sorted(unknown)}")
        self.overlay_path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.lock_path)):
            overlay = self._overlay()
            overlay["values"].update(values)
            overlay["revision"] = int(overlay.get("revision", 0)) + 1
            temporary = self.overlay_path.with_name(f".{self.overlay_path.name}.{secrets.token_hex(8)}.tmp")
            data = (canonical_json(overlay) + "\n").encode("utf-8")
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.overlay_path)
            directory_fd = os.open(self.overlay_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return overlay["revision"]


class OwnedIndexView:
    def __init__(self, project_root: str | Path, pinned: PinnedGeneration):
        self.project_root = Path(project_root).expanduser().resolve()
        self.generation_root = _pinned(pinned)
        self.pinned = pinned

    def read_table(self, table: str) -> list[dict[str, Any]]:
        if table not in _CANON_INDEX_TABLES:
            raise OwnedViewError("TABLE_IS_NOT_CANON_OWNED")
        domains = {"chapters": "index", "scenes": "index", "appearances": "index",
                   "state_changes": "index", "entities": "index", "story_events": "events"}
        rows = []
        projection_key = {"chapters": "chapter_meta", "scenes": "scenes",
                          "appearances": "entities_appeared", "state_changes": "state_deltas",
                          "entities": "entity_deltas", "story_events": "accepted_events"}.get(table)
        for doc in _chapter_documents(self.pinned, domains[table]):
            if doc.get("projection", {}).get("tombstone"):
                continue
            payload = doc["projection"].get(projection_key, [])
            if table == "chapters":
                payload = [payload or {}]
            if not isinstance(payload, list):
                payload = [payload]
            rows.extend({"chapter": doc["chapter"],
                         "effective_revision_id": doc["effective_revision_id"],
                         "effective_content_sha256": doc["effective_content_sha256"],
                         "row_kind": table, "payload": row} for row in payload)
        return rows

    def write_owner_sql(self, sql: str, parameters: tuple = ()) -> None:
        match = re.match(r"\s*(INSERT|UPDATE|DELETE)\s+(?:INTO\s+|FROM\s+)?([A-Za-z_][A-Za-z0-9_]*)", sql, re.I)
        if not match:
            raise OwnedViewError("OWNER_SQL_UNSUPPORTED")
        table = match.group(2).lower()
        if table in _CANON_INDEX_TABLES:
            raise OwnedViewError("CANON_INDEX_IS_IMMUTABLE")
        db_path = self.project_root / ".webnovel/index.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute(sql, parameters)
            conn.commit()


class OwnedMemoryView:
    def __init__(self, pinned: PinnedGeneration, owner_rows: list[dict[str, Any]] | None = None):
        self.pinned = pinned
        self.owner_rows = list(owner_rows or [])

    def rows(self) -> list[dict[str, Any]]:
        canon = []
        for doc in _chapter_documents(self.pinned, "memory"):
            if doc.get("projection", {}).get("tombstone"):
                continue
            canon.append({"chapter": doc["chapter"], "payload": doc["projection"],
                          "authority_claim": "CANON_AUTHORITY",
                          "generation_id": self.pinned.generation_id})
        for row in self.owner_rows:
            if row.get("authority_claim") == "CANON_AUTHORITY":
                raise OwnedViewError("OWNER_MEMORY_CANNOT_CLAIM_CANON")
        return canon + [{**row, "authority_claim": row.get("authority_claim", "OWNER_AUTHORITY")}
                        for row in self.owner_rows]


class OwnedRAGView:
    def __init__(self, pinned: PinnedGeneration,
                 owner_search: Callable[[str], list[dict[str, Any]]]):
        self.pinned = pinned
        self.owner_search = owner_search

    def search(self, query: str) -> list[dict[str, Any]]:
        canon = []
        for doc in _chapter_documents(self.pinned, "vector"):
            if doc.get("projection", {}).get("tombstone"):
                continue
            canon.append({"chapter": doc["chapter"], "payload": doc["projection"],
                          "score": 0.0, "authority_claim": "CANON_AUTHORITY",
                          "generation_id": self.pinned.generation_id})
        owner = self.owner_search(query)
        if any(row.get("authority_claim") == "CANON_AUTHORITY" for row in owner):
            raise OwnedViewError("OWNER_RAG_CANNOT_CLAIM_CANON")
        merged = canon + [{**row, "authority_claim": row.get("authority_claim", "OWNER_AUTHORITY")}
                          for row in owner]
        return sorted(merged, key=lambda row: float(row.get("score", 0)), reverse=True)
