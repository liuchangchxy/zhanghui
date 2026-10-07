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
from .projection_generation import PinnedGeneration, ProjectionGeneration


class OwnedViewError(RuntimeError):
    pass


_CANON_INDEX_TABLES = {"chapters", "scenes", "appearances", "state_changes", "story_events", "entities", "relationships"}
_OWNER_STATE_ROOTS = {"story_craft", "planning", "promise_ledger", "review_checkpoints",
                      "workflow", "craft", "intent", "disambiguation_warnings",
                      "disambiguation_pending"}
_OWNER_STATE_PATHS = {"progress.volumes_planned", "progress.current_volume",
                      "progress.total_volumes", "progress.chapter_status"}
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
        from .state_projection_writer import StateProjectionWriter

        canon: dict[str, Any] = {"entity_state": {}, "progress": {"chapter_status": {}},
                                 "protagonist_state": {}, "strand_tracker": {}}
        reducer = StateProjectionWriter(self.project_root)
        for doc in _chapter_documents(pinned, "state"):
            projection = doc.get("projection", {})
            if projection.get("tombstone"):
                canon["progress"]["chapter_status"][str(doc["chapter"])] = "retracted"
                continue
            payload = projection.get("commit_payload")
            if not isinstance(payload, dict):
                raise OwnedViewError("CANON_STATE_SLICE_INCOMPLETE")
            reducer.reduce_state(canon, payload)
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
                if key == "progress.chapter_status" and isinstance(value, dict):
                    conflicts = set(target.get(parts[-1], {})).intersection(value)
                    if conflicts:
                        raise OwnedViewError(f"OWNER_CANON_STATE_COLLISION:{sorted(conflicts)}")
                    target.setdefault(parts[-1], {}).update(value)
                    continue
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
        statuses = values.get("progress.chapter_status")
        if statuses is not None and (not isinstance(statuses, dict) or any(
                value not in {"chapter_drafted", "chapter_reviewed", "chapter_rejected"}
                for value in statuses.values())):
            raise OwnedViewError("CANON_CHAPTER_STATUS_IS_IMMUTABLE")
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
                   "state_changes": "index", "entities": "index", "story_events": "events",
                   "relationships": "events"}
        rows = []
        projection_key = {"chapters": "chapter_meta", "scenes": "scenes",
                          "appearances": "entities_appeared", "state_changes": "state_deltas",
                          "entities": "entity_deltas", "story_events": "accepted_events",
                          "relationships": "accepted_events"}.get(table)
        for doc in _chapter_documents(self.pinned, domains[table]):
            if doc.get("projection", {}).get("tombstone"):
                continue
            payload = doc["projection"].get(projection_key, [])
            if table == "chapters":
                payload = [payload or {}]
            if table == "relationships":
                normalized = []
                for event in (payload or []):
                    if not isinstance(event, dict) or event.get("event_type") != "relationship_changed":
                        continue
                    body = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                    normalized.append({"from_entity": body.get("from_entity") or event.get("subject"),
                                       "to_entity": body.get("to_entity") or body.get("to"),
                                       "type": body.get("relationship_type") or body.get("relation_type") or body.get("type"),
                                       "description": body.get("description"), "chapter": doc["chapter"]})
                payload = normalized
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
        from .memory.schema import COMMIT_PROJECTION_EVIDENCE_PREFIXES

        canon = []
        for doc in _chapter_documents(self.pinned, "memory"):
            if doc.get("projection", {}).get("tombstone"):
                continue
            canon.append({"chapter": doc["chapter"], "payload": doc["projection"],
                          "authority_claim": "CANON_AUTHORITY",
                          "generation_id": self.pinned.generation_id})
        mutable_rows = []
        for row in self.owner_rows:
            evidence = row.get("evidence", [])
            if any(str(marker).startswith(COMMIT_PROJECTION_EVIDENCE_PREFIXES)
                   for marker in (evidence if isinstance(evidence, list) else [evidence])):
                continue
            if row.get("authority_claim") == "CANON_AUTHORITY":
                raise OwnedViewError("OWNER_MEMORY_CANNOT_CLAIM_CANON")
            mutable_rows.append(row)
        return canon + [{**row, "authority_claim": row.get("authority_claim", "OWNER_AUTHORITY")}
                        for row in mutable_rows]


class OwnedRAGView:
    def __init__(self, pinned: PinnedGeneration,
                 owner_search: Callable[[str], list[dict[str, Any]]]):
        self.pinned = pinned
        self.owner_search = owner_search

    def search(self, query: str, *, strategy: str = "hybrid",
               query_embedding: list[float] | None = None,
               chunk_type: str | None = None, chapter: int | None = None,
               center_entities: list[str] | None = None) -> list[dict[str, Any]]:
        canon_docs = []
        for doc in _chapter_documents(self.pinned, "vector"):
            if doc.get("projection", {}).get("tombstone"):
                continue
            for chunk in doc.get("projection", {}).get("chunks", []):
                if chapter is not None and int(doc["chapter"]) > int(chapter):
                    continue
                if chunk_type and chunk.get("chunk_type") != chunk_type:
                    continue
                canon_docs.append({**chunk, "chapter": int(doc["chapter"]),
                                   "generation_id": self.pinned.generation_id,
                                   "authority_claim": "CANON_AUTHORITY"})
        query_terms = [token.lower() for token in re.findall(r"[\w\u3400-\u9fff]+", query) if token]
        query_counts = {term: query_terms.count(term) for term in set(query_terms)}
        lengths = [int(item.get("doc_length") or 0) for item in canon_docs]
        average_length = sum(lengths) / len(lengths) if lengths else 1.0
        document_frequency = {term: sum(term in set(item.get("terms", [])) for item in canon_docs)
                              for term in query_counts}
        bm25_scores = {}
        for item in canon_docs:
            terms = item.get("terms", [])
            counts = {term: terms.count(term) for term in query_counts}
            length = max(1, int(item.get("doc_length") or 0))
            score = 0.0
            for term in query_counts:
                tf = counts.get(term, 0)
                df = document_frequency.get(term, 0)
                if tf and df:
                    idf = __import__("math").log((len(canon_docs) - df + 0.5) / (df + 0.5) + 1)
                    normalized_tf = tf / length
                    score += idf * (normalized_tf * 2.5) / (
                        normalized_tf + 1.5 * (1 - 0.75 + 0.75 * length / average_length))
            bm25_scores[item["chunk_id"]] = score
        vector_scores = {}
        if query_embedding:
            for item in canon_docs:
                vector = item.get("embedding")
                if not vector:
                    continue
                dot = sum(float(a) * float(b) for a, b in zip(query_embedding, vector))
                norm_a = sum(float(a) ** 2 for a in query_embedding) ** 0.5
                norm_b = sum(float(b) ** 2 for b in vector) ** 0.5
                vector_scores[item["chunk_id"]] = dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
        def rank(scores):
            return {key: rank for rank, (key, _score) in enumerate(
                sorted(scores.items(), key=lambda pair: pair[1], reverse=True), start=1)}
        bm25_rank, vector_rank = rank(bm25_scores), rank(vector_scores)
        related_entities: set[str] = set()
        entity_terms: dict[str, set[str]] = {}
        for entity_doc in _chapter_documents(self.pinned, "index"):
            if entity_doc.get("projection", {}).get("tombstone"):
                continue
            for entity in entity_doc.get("projection", {}).get("entity_deltas", []):
                if not isinstance(entity, dict):
                    continue
                entity_id = str(entity.get("entity_id") or entity.get("id") or "").strip()
                if not entity_id:
                    continue
                terms = {entity_id}
                canonical_name = str(entity.get("canonical_name") or "").strip()
                if canonical_name:
                    terms.add(canonical_name)
                aliases = entity.get("aliases", [])
                if isinstance(aliases, list):
                    terms.update(str(alias).strip() for alias in aliases if str(alias).strip())
                entity_terms.setdefault(entity_id, set()).update(terms)
        seed_terms: set[str] = set()
        max_chapter = max((int(doc["chapter"]) for doc in _chapter_documents(self.pinned, "vector")),
                          default=0)
        if strategy == "graph_hybrid" and center_entities:
            seeds = {str(item).strip() for item in center_entities if str(item).strip()}
            for seed in seeds:
                seed_terms.update(entity_terms.get(seed, {seed}))
            for event_doc in _chapter_documents(self.pinned, "events"):
                if event_doc.get("projection", {}).get("tombstone"):
                    continue
                for event in event_doc.get("projection", {}).get("accepted_events", []):
                    if not isinstance(event, dict) or event.get("event_type") != "relationship_changed":
                        continue
                    body = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                    left = str(event.get("subject") or body.get("from_entity") or "").strip()
                    right = str(body.get("to_entity") or body.get("to") or "").strip()
                    if left in seeds and right:
                        related_entities.add(right)
                    if right in seeds and left:
                        related_entities.add(left)
            related_terms = set().union(*(entity_terms.get(item, {item}) for item in related_entities)) if related_entities else set()
        else:
            related_terms = set()
        rows = []
        for item in canon_docs:
            cid = item["chunk_id"]
            if strategy == "bm25":
                score, source = bm25_scores.get(cid, 0.0), "bm25"
            elif strategy == "vector":
                score, source = vector_scores.get(cid, 0.0), "vector"
            else:
                score = (1 / (60 + bm25_rank[cid]) if cid in bm25_rank else 0.0)
                score += (1 / (60 + vector_rank[cid]) if cid in vector_rank else 0.0)
                source = "graph_hybrid" if strategy == "graph_hybrid" else "hybrid"
                if strategy == "graph_hybrid" and center_entities:
                    text = str(item.get("content") or "")
                    if any(entity in text for entity in seed_terms):
                        score += 0.1
                    elif any(entity in text for entity in related_terms):
                        score += 0.05
                    gap = max(0, max_chapter - int(item.get("chapter") or 0))
                    score += max(0.0, 1.0 - min(gap, 100) / 100.0) * 0.02
            if score > 0:
                rows.append({**item, "score": score, "source": source})
        owner = self.owner_search(query)
        if any(row.get("authority_claim") == "CANON_AUTHORITY" for row in owner):
            raise OwnedViewError("OWNER_RAG_CANNOT_CLAIM_CANON")
        merged = rows + [{**row, "authority_claim": row.get("authority_claim", "OWNER_AUTHORITY")}
                         for row in owner]
        return sorted(merged, key=lambda row: float(row.get("score", 0)), reverse=True)


class OwnedProjectView:
    """One operation-scoped pin; runtime callers never resolve candidates."""

    def __init__(self, project_root: str | Path, pinned: PinnedGeneration):
        self.project_root = Path(project_root).expanduser().resolve()
        _pinned(pinned)
        self.pinned = pinned
        self.state = OwnedStateStore(self.project_root)
        self.index = OwnedIndexView(self.project_root, pinned)
        self.memory = OwnedMemoryView(pinned)

    @classmethod
    def pin_active(cls, project_root: str | Path) -> "OwnedProjectView | None":
        protocol = ProjectionGeneration(project_root)
        enrolled = protocol.enrollment_path.exists()
        pinned = protocol.pin_active_generation()
        if pinned is None:
            if enrolled:
                raise OwnedViewError("ENROLLED_PUBLICATION_MISSING")
            return None
        return cls(project_root, pinned)

    def assert_still_active(self) -> None:
        current = ProjectionGeneration(self.project_root).pin_active_generation()
        if (current is None or current.publication_record_sha256 != self.pinned.publication_record_sha256
                or current.generation_id != self.pinned.generation_id):
            raise OwnedViewError("ACTIVE_PUBLICATION_CHANGED_DURING_OPERATION")

    def state_view(self) -> dict[str, Any]:
        return self.state.read_view(self.pinned)

    def canon_chapter(self, chapter: int) -> dict[str, Any]:
        matches = []
        for domain in ("events", "state", "index", "summary", "memory", "vector", "intent_diagnostics"):
            path = self.pinned.generation_root / domain / f"chapter_{chapter:03d}.json"
            if path.is_file():
                matches.append(json.loads(path.read_text(encoding="utf-8")))
        if not matches:
            raise OwnedViewError("CHAPTER_NOT_IN_PINNED_GENERATION")
        if any(row.get("effective_revision_id") != matches[0].get("effective_revision_id")
               or row.get("effective_content_sha256") != matches[0].get("effective_content_sha256")
               for row in matches):
            raise OwnedViewError("GENERATION_CHAPTER_SLICE_MISMATCH")
        return {"generation_id": self.pinned.generation_id,
                "publication_record_id": self.pinned.publication_record_id,
                "semantic_activation_id": self.pinned.semantic_activation_id,
                "effective_revision_id": matches[0]["effective_revision_id"],
                "effective_content_sha256": matches[0]["effective_content_sha256"],
                "effective_status": matches[0]["effective_status"],
                "domains": {row["writer"]: row["projection"] for row in matches}}

    def effective_commits_before(self, chapter: int) -> list[dict[str, Any]]:
        rows = []
        for path in sorted((self.pinned.generation_root / "index").glob("chapter_*.json")):
            number = int(path.stem.removeprefix("chapter_"))
            if number >= chapter:
                continue
            view = self.canon_chapter(number)
            index = view["domains"].get("index", {})
            events = view["domains"].get("events", {}).get("accepted_events", [])
            state = view["domains"].get("state", {})
            extraction = {
                "chapter_meta": index.get("chapter_meta", {}),
                "summary_text": view["domains"].get("summary", {}).get("summary_text", ""),
                "accepted_events": events if isinstance(events, list) else [],
                "state_deltas": state.get("state_deltas", []),
                "entity_deltas": index.get("entity_deltas", []),
            }
            rows.append({"chapter": number,
                         "payload": {"meta": {"chapter": number, "status": view["effective_status"]},
                                     "extraction_result": extraction,
                                     "effective_revision_id": view["effective_revision_id"],
                                     "effective_content_sha256": view["effective_content_sha256"]}})
        return rows


def activation_health_report(project_root: str | Path) -> dict[str, Any]:
    """Operator report separates the pinned active record from staged candidates."""
    root = Path(project_root).expanduser().resolve()
    protocol = ProjectionGeneration(root)
    if not protocol.enrollment_path.exists():
        return {"mode": "base_only", "active_status": "not_enrolled",
                "candidate_status": "not_scanned"}
    try:
        from .effective_history import EffectiveHistoryStore

        pinned = protocol.pin_active_generation()
        if pinned is None:
            raise OwnedViewError("ENROLLED_PUBLICATION_MISSING")
        store = EffectiveHistoryStore()
        history = store.read_active_snapshot(root)
        if not history.ok:
            raise OwnedViewError(";".join(history.diagnostics))
        overlay = OwnedStateStore(root)._overlay()
        candidates = []
        for path in sorted((root / ".story-system/corrections").glob("chapter_*/*/corrections/*.correction.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                candidate = store.resolve_candidate(root, str(value.get("correction_id") or ""))
                candidates.append({"correction_id": value.get("correction_id"),
                                  "status": "ready" if candidate.ok else "blocked",
                                  "diagnostics": list(candidate.diagnostics)})
            except Exception as exc:
                candidates.append({"path": path.relative_to(root).as_posix(),
                                  "status": "blocked", "diagnostics": [str(exc)]})
        return {
            "mode": "activation_managed", "active_status": "valid",
            "semantic_activation_id": pinned.semantic_activation_id,
            "effective_history_digest": history.effective_history_digest,
            "effective_tip": max(history.chapters, default=None),
            "generation_id": pinned.generation_id,
            "publication_record_id": pinned.publication_record_id,
            "owner_overlay_revision": overlay.get("revision", 0),
            "candidate_status": "ready" if any(row["status"] == "ready" for row in candidates)
            else "pending_or_blocked", "candidates": candidates,
        }
    except Exception as exc:
        return {"mode": "activation_managed", "active_status": "blocked",
                "candidate_status": "not_scanned", "error": str(exc)}
