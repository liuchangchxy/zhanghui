#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .commit_artifacts import extraction_dict, extraction_list, extraction_text
from .config import DataModulesConfig
from .durable_projection import require_durable_commit_match
from .index_manager import ChapterMeta, IndexManager, SceneMeta, StateChangeMeta
from .story_system_mode import canonical_projection_write_scope

try:
    from chapter_paths import find_chapter_file
except ImportError:  # pragma: no cover
    from scripts.chapter_paths import find_chapter_file


class IndexProjectionWriter:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def apply(self, commit_payload: dict) -> dict:
        require_durable_commit_match(self.project_root, commit_payload)
        if commit_payload["meta"]["status"] != "accepted":
            return {"applied": False, "writer": "index", "reason": "commit_rejected"}

        with canonical_projection_write_scope(self.project_root):
            return self._apply_accepted_commit(commit_payload)

    @staticmethod
    def _retire_legacy_protagonist_row(manager: IndexManager, name: str, canonical_id: str) -> bool:
        """Retire the display-name-keyed protagonist row left by the old sync.

        The old projection created that row from `protagonist_state.name` even when
        `entity_id` was present, so older projects can carry two protagonist rows. The
        duplicate is repaired only when it *declares the same canonical id* in its own
        `current_json` — name similarity alone is never treated as identity, so a different
        character that happens to share a name is left alone.
        """
        if not name or not canonical_id or name == canonical_id:
            return False
        canonical = manager.get_entity(canonical_id)
        legacy = manager.get_entity(name)
        if not canonical or not legacy or str(legacy.get("id")) != name:
            return False
        if legacy.get("is_archived") or not canonical.get("is_protagonist"):
            return False
        body = legacy.get("current_json")
        if not isinstance(body, dict):
            return False
        if str(body.get("entity_id") or "").strip() != canonical_id:
            return False
        return manager.retire_entity_identity(name, canonical_id)

    def _sync_canonical_state_entities(self, manager: IndexManager) -> tuple[int, dict]:
        """Backfill entities from the mutable project files, reporting what was consumed.

        `state.json` and `MASTER_SETTING.json` are *external, mutable* inputs: rebuilding the
        same durable commit's projection reads whatever they contain at rebuild time. That
        dependency is real and pre-existing; what was wrong is that it was invisible — a
        parse failure returned 0 and the projection reported success either way.

        So this records the exact bytes consumed (`inputs[].sha256`) and any failure
        (`errors[]`) alongside the count, and the projection result carries it. The
        dependency is now auditable instead of hidden, without changing which files are
        authoritative.
        """
        report: dict[str, Any] = {"inputs": [], "errors": [], "synced": 0}
        state_path = self.project_root / ".webnovel" / "state.json"
        if not state_path.is_file():
            report["state_json"] = "absent"
            return 0, report
        try:
            raw_state = state_path.read_text(encoding="utf-8")
        except OSError as exc:
            report["errors"].append({"path": str(state_path), "error": f"unreadable: {exc}"})
            return 0, report
        try:
            state_data = json.loads(raw_state)
        except json.JSONDecodeError as exc:
            report["errors"].append({"path": str(state_path), "error": f"invalid_json: {exc}"})
            return 0, report
        report["inputs"].append(
            {"path": str(state_path), "sha256": hashlib.sha256(raw_state.encode("utf-8")).hexdigest()}
        )
        if not isinstance(state_data, dict):
            report["errors"].append({"path": str(state_path), "error": "not_a_json_object"})
            return 0, report
        synced = 0

        # Synchronize protagonist from protagonist_state if present.
        #
        # The entity identity is `protagonist_state.entity_id`, not the display name. Using
        # the name meant a project whose canonical id was `xu_zhiyuan` also got a second
        # entity literally keyed `许知远`, both marked protagonist. The data agent then saw
        # two core entities for one character and emitted disambiguation pending on every
        # chapter, which blocked precommit until a human picked a side.
        protagonist_state = state_data.get("protagonist_state") or {}
        if isinstance(protagonist_state, dict):
            p_name = str(protagonist_state.get("name") or "").strip()
            p_id = str(protagonist_state.get("entity_id") or "").strip()
            canonical_id = p_id or p_name
            if canonical_id:
                if not manager.get_entity(canonical_id):
                    from .index_manager import EntityMeta
                    manager.upsert_entity(
                        EntityMeta(
                            id=canonical_id,
                            type="角色",
                            canonical_name=p_name or canonical_id,
                            tier="主角",
                            desc=str(protagonist_state.get("current_realm") or "").strip(),
                            current=protagonist_state,
                            first_appearance=0,
                            last_appearance=0,
                            is_protagonist=True,
                        )
                    )
                    synced += 1
                if p_id and p_name and p_id != p_name:
                    if self._retire_legacy_protagonist_row(manager, p_name, p_id):
                        report["retired_duplicates"] = [
                            *(report.get("retired_duplicates") or []),
                            {"id": p_name, "merged_into": p_id},
                        ]

        entity_state = state_data.get("entity_state") or {}
        if isinstance(entity_state, dict):
            for name, info in entity_state.items():
                if not isinstance(name, str) or not name.strip():
                    continue
                name = name.strip()
                existing = manager.get_entity(name)
                if not existing:
                    desc = ""
                    tier = "装饰"
                    is_protagonist = False
                    current = {}
                    if isinstance(info, dict):
                        desc = str(info.get("身份") or info.get("description") or info.get("desc") or "").strip()
                        if info.get("身份") == "主角" or info.get("is_protagonist"):
                            is_protagonist = True
                            tier = "主角"
                        current = {k: v for k, v in info.items() if k not in ("身份", "description", "desc")}
                    from .index_manager import EntityMeta
                    manager.upsert_entity(
                        EntityMeta(
                            id=name,
                            type="角色",
                            canonical_name=name,
                            tier=tier,
                            desc=desc,
                            current=current,
                            first_appearance=0,
                            last_appearance=0,
                            is_protagonist=is_protagonist,
                        )
                    )
                    synced += 1

        # Synchronize locations and items from world_settings
        world_settings = state_data.get("world_settings") or {}
        if isinstance(world_settings, dict):
            for loc in world_settings.get("locations") or []:
                loc_name = loc if isinstance(loc, str) else (loc.get("name") if isinstance(loc, dict) else "")
                if loc_name and isinstance(loc_name, str) and not manager.get_entity(loc_name.strip()):
                    from .index_manager import EntityMeta
                    manager.upsert_entity(EntityMeta(
                        id=loc_name.strip(), type="地点", canonical_name=loc_name.strip(),
                        tier="装饰", desc="", current={}, first_appearance=0, last_appearance=0, is_protagonist=False
                    ))
                    synced += 1
            for item in (world_settings.get("items") or []) + (world_settings.get("objects") or []):
                item_name = item if isinstance(item, str) else (item.get("name") if isinstance(item, dict) else "")
                if item_name and isinstance(item_name, str) and not manager.get_entity(item_name.strip()):
                    from .index_manager import EntityMeta
                    manager.upsert_entity(EntityMeta(
                        id=item_name.strip(), type="物品", canonical_name=item_name.strip(),
                        tier="装饰", desc="", current={}, first_appearance=0, last_appearance=0, is_protagonist=False
                    ))
                    synced += 1

        # Synchronize static entities from structured MASTER_SETTING.json if available
        master_path = self.project_root / ".story-system" / "MASTER_SETTING.json"
        if master_path.is_file():
            try:
                raw_master = master_path.read_text(encoding="utf-8")
                m_data = json.loads(raw_master)
                report["inputs"].append(
                    {
                        "path": str(master_path),
                        "sha256": hashlib.sha256(raw_master.encode("utf-8")).hexdigest(),
                    }
                )
                for ent in m_data.get("entities", []) or []:
                    if isinstance(ent, dict):
                        n = str(ent.get("name") or ent.get("id") or ent.get("canonical_name") or "").strip()
                        etype = str(ent.get("type") or "角色").strip() or "角色"
                        if n and not manager.get_entity(n):
                            from .index_manager import EntityMeta
                            manager.upsert_entity(EntityMeta(
                                id=n, type=etype, canonical_name=n,
                                tier="装饰", desc="", current={}, first_appearance=0, last_appearance=0, is_protagonist=False
                            ))
                            synced += 1
                for loc in m_data.get("locations", []) or []:
                    loc_name = loc if isinstance(loc, str) else (loc.get("name") if isinstance(loc, dict) else "")
                    if loc_name and isinstance(loc_name, str) and not manager.get_entity(loc_name.strip()):
                        from .index_manager import EntityMeta
                        manager.upsert_entity(EntityMeta(
                            id=loc_name.strip(), type="地点", canonical_name=loc_name.strip(),
                            tier="装饰", desc="", current={}, first_appearance=0, last_appearance=0, is_protagonist=False
                        ))
                        synced += 1
                for item in (m_data.get("items", []) or []) + (m_data.get("objects", []) or []):
                    item_name = item if isinstance(item, str) else (item.get("name") if isinstance(item, dict) else "")
                    if item_name and isinstance(item_name, str) and not manager.get_entity(item_name.strip()):
                        from .index_manager import EntityMeta
                        manager.upsert_entity(EntityMeta(
                            id=item_name.strip(), type="物品", canonical_name=item_name.strip(),
                            tier="装饰", desc="", current={}, first_appearance=0, last_appearance=0, is_protagonist=False
                        ))
                        synced += 1
            except (OSError, json.JSONDecodeError, AttributeError, TypeError) as exc:
                # Recorded rather than swallowed: a master-setting parse failure means the
                # projection silently synced fewer entities than the file implies.
                report["errors"].append(
                    {"path": str(master_path), "error": f"{type(exc).__name__}: {exc}"}
                )

        report["synced"] = synced
        return synced, report

    def _apply_accepted_commit(self, commit_payload: dict) -> dict:
        manager = IndexManager(DataModulesConfig.from_project_root(self.project_root))
        applied_count = 0

        # Synchronize canonical state entities from state.json (Canonical authority > derived projection)
        synced_canon, canon_report = self._sync_canonical_state_entities(manager)
        applied_count += synced_canon

        chapter_applied = self._upsert_chapter(manager, commit_payload)
        if chapter_applied:
            applied_count += 1

        scenes_count = self._apply_scenes(manager, commit_payload)
        applied_count += scenes_count

        appearances_count = self._apply_appearances(manager, commit_payload)
        applied_count += appearances_count

        state_changes_count = self._apply_state_changes(manager, commit_payload)
        applied_count += state_changes_count

        entity_delta_count = 0
        for delta in self._collect_entity_deltas(commit_payload):
            result = manager.apply_entity_delta(delta)
            if result:
                entity_delta_count += 1
                applied_count += 1
        return {
            "applied": applied_count > 0,
            "writer": "index",
            "applied_count": applied_count,
            "chapters": 1 if chapter_applied else 0,
            "scenes": scenes_count,
            "appearances": appearances_count,
            "state_changes": state_changes_count,
            "entity_deltas": entity_delta_count,
            # Which mutable external files this projection read, and whether reading them
            # worked. Rebuilding the same commit under different state.json content can
            # produce a different index — this is the record that makes that traceable.
            "canonical_sync": canon_report,
        }

    def _upsert_chapter(self, manager: IndexManager, commit_payload: dict) -> bool:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        if chapter <= 0:
            return False

        meta = extraction_dict(commit_payload, "chapter_meta")

        title = str(
            meta.get("title")
            or commit_payload.get("chapter_title")
            or self._title_from_chapter_file(chapter)
            or ""
        ).strip()
        location = str(meta.get("location") or commit_payload.get("location") or "").strip()
        summary = str(extraction_text(commit_payload, "summary_text") or meta.get("summary") or "").strip()
        word_count = self._safe_int(meta.get("word_count") or commit_payload.get("word_count"))
        if word_count <= 0:
            word_count = self._chapter_word_count(chapter)

        characters = meta.get("characters") or self._collect_character_ids(commit_payload)
        if not isinstance(characters, list):
            characters = []

        manager.add_chapter(
            ChapterMeta(
                chapter=chapter,
                title=title,
                location=location,
                word_count=word_count,
                characters=[str(c) for c in characters if str(c).strip()],
                summary=summary,
            )
        )
        return True

    def _apply_scenes(self, manager: IndexManager, commit_payload: dict) -> int:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        scenes = extraction_list(commit_payload, "scenes")
        if chapter <= 0 or not isinstance(scenes, list) or not scenes:
            return 0

        scene_metas: list[SceneMeta] = []
        for idx, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                continue
            scene_index = self._safe_int(scene.get("scene_index") or scene.get("index") or idx)
            characters = scene.get("characters") or scene.get("character_ids") or []
            if not isinstance(characters, list):
                characters = []
            scene_metas.append(
                SceneMeta(
                    chapter=chapter,
                    scene_index=scene_index,
                    start_line=self._safe_int(scene.get("start_line")),
                    end_line=self._safe_int(scene.get("end_line")),
                    location=str(scene.get("location") or "").strip(),
                    summary=str(scene.get("summary") or scene.get("content") or "").strip(),
                    characters=[str(c) for c in characters if str(c).strip()],
                )
            )
        if not scene_metas:
            return 0
        manager.add_scenes(chapter, scene_metas)
        return len(scene_metas)

    def _apply_appearances(self, manager: IndexManager, commit_payload: dict) -> int:
        chapter = int(commit_payload.get("meta", {}).get("chapter") or 0)
        entities = extraction_list(commit_payload, "entities_appeared")
        if chapter <= 0 or not isinstance(entities, list):
            return 0

        applied = 0
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            entity_id = str(entity.get("id") or entity.get("entity_id") or "").strip()
            if not entity_id or entity_id == "NEW":
                continue
            mentions = entity.get("mentions") or []
            if isinstance(mentions, str):
                mentions = [mentions]
            if not isinstance(mentions, list):
                mentions = []
            manager.record_appearance(
                entity_id=entity_id,
                chapter=chapter,
                mentions=[str(m) for m in mentions if str(m).strip()],
                confidence=self._safe_float(entity.get("confidence"), 1.0),
            )
            applied += 1
        return applied

    def _apply_state_changes(self, manager: IndexManager, commit_payload: dict) -> int:
        applied = 0
        for change in self._collect_state_changes(commit_payload):
            entity_id = str(change.get("entity_id") or "").strip()
            field = str(change.get("field") or "").strip()
            chapter = self._safe_int(change.get("chapter") or commit_payload.get("meta", {}).get("chapter"))
            if not entity_id or not field or chapter <= 0:
                continue
            old_value = self._stringify(change.get("old"))
            new_value = self._stringify(change.get("new"))
            reason = str(change.get("reason") or "").strip()
            if self._state_change_exists(manager, entity_id, field, old_value, new_value, reason, chapter):
                continue
            manager.record_state_change(
                StateChangeMeta(
                    entity_id=entity_id,
                    field=field,
                    old_value=old_value,
                    new_value=new_value,
                    reason=reason,
                    chapter=chapter,
                )
            )
            applied += 1
        return applied

    def _collect_state_changes(self, commit_payload: dict) -> list[dict]:
        deltas = [
            self._normalize_state_delta(delta)
            for delta in extraction_list(commit_payload, "state_deltas")
            if isinstance(delta, dict)
        ]
        seen = {
            (
                str(delta.get("entity_id") or "").strip(),
                str(delta.get("field") or "").strip(),
                self._safe_int(delta.get("chapter") or commit_payload.get("meta", {}).get("chapter")),
            )
            for delta in deltas
        }

        for event in extraction_list(commit_payload, "accepted_events"):
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("event_type") or "").strip()
            payload = dict(event.get("payload") or {})
            if event_type == "power_breakthrough":
                field = str(payload.get("field") or payload.get("field_path") or "realm").strip()
            elif event_type == "character_state_changed":
                field = str(payload.get("field") or payload.get("field_path") or "").strip()
            else:
                continue
            entity_id = str(payload.get("entity_id") or event.get("subject") or "").strip()
            chapter = self._safe_int(event.get("chapter") or commit_payload.get("meta", {}).get("chapter"))
            key = (entity_id, field, chapter)
            if not entity_id or not field or key in seen:
                continue
            seen.add(key)
            deltas.append(
                {
                    "entity_id": entity_id,
                    "field": field,
                    "old": (
                        payload.get("old")
                        if "old" in payload
                        else payload.get("from")
                        if "from" in payload
                        else payload.get("old_value")
                        if "old_value" in payload
                        else payload.get("previous_state")
                    ),
                    "new": (
                        payload.get("new")
                        if "new" in payload
                        else payload.get("to")
                        if "to" in payload
                        else payload.get("new_value")
                        if "new_value" in payload
                        else payload.get("new_state")
                    ),
                    "reason": event_type,
                    "chapter": chapter,
                }
            )
        return deltas

    def _normalize_state_delta(self, delta: dict) -> dict:
        result = dict(delta)
        if "field" not in result and "field_path" in result:
            result["field"] = result["field_path"]
        if "new" not in result and "new_value" in result:
            result["new"] = result["new_value"]
        if "old" not in result and "old_value" in result:
            result["old"] = result["old_value"]
        return result

    def _state_change_exists(
        self,
        manager: IndexManager,
        entity_id: str,
        field: str,
        old_value: str,
        new_value: str,
        reason: str,
        chapter: int,
    ) -> bool:
        with manager._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1 FROM state_changes
                WHERE entity_id = ?
                  AND field = ?
                  AND chapter = ?
                  AND COALESCE(old_value, '') = ?
                  AND COALESCE(new_value, '') = ?
                  AND COALESCE(reason, '') = ?
                LIMIT 1
                """,
                (entity_id, field, chapter, old_value, new_value, reason),
            )
            return cursor.fetchone() is not None

    def _collect_character_ids(self, commit_payload: dict) -> list[str]:
        ids: list[str] = []
        for entity in extraction_list(commit_payload, "entities_appeared"):
            if not isinstance(entity, dict):
                continue
            entity_id = str(entity.get("id") or entity.get("entity_id") or "").strip()
            if entity_id and entity_id != "NEW":
                ids.append(entity_id)
        for delta in extraction_list(commit_payload, "entity_deltas"):
            if not isinstance(delta, dict):
                continue
            entity_id = str(delta.get("entity_id") or delta.get("id") or "").strip()
            entity_type = str(delta.get("type") or delta.get("entity_type") or "").strip()
            if entity_id and (not entity_type or entity_type == "角色"):
                ids.append(entity_id)
        return list(dict.fromkeys(ids))

    def _title_from_chapter_file(self, chapter: int) -> str:
        path = find_chapter_file(self.project_root, chapter)
        if path is None:
            return ""
        stem = path.stem
        match = re.match(r"第0*\d+章[-_ ]+(.+)$", stem)
        return match.group(1).strip() if match else ""

    def _chapter_word_count(self, chapter: int) -> int:
        path = find_chapter_file(self.project_root, chapter)
        if path is None:
            return 0
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return 0
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"^#+ .*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"---", "", text)
        return len(text.strip())

    def _stringify(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)

    def _safe_int(self, value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _safe_float(self, value: object, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _collect_entity_deltas(self, commit_payload: dict) -> list[dict]:
        deltas = [dict(delta) for delta in extraction_list(commit_payload, "entity_deltas") if isinstance(delta, dict)]
        for event in extraction_list(commit_payload, "accepted_events"):
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("event_type") or "").strip()
            payload = dict(event.get("payload") or {})
            chapter = int(event.get("chapter") or commit_payload.get("meta", {}).get("chapter") or 0)
            if event_type == "relationship_changed":
                from_entity = str(payload.get("from_entity") or event.get("subject") or "").strip()
                to_entity = str(payload.get("to_entity") or payload.get("to") or "").strip()
                rel_type = str(
                    payload.get("relationship_type")
                    or payload.get("relation_type")
                    or payload.get("type")
                    or ""
                ).strip()
                if from_entity and to_entity and rel_type:
                    deltas.append(
                        {
                            "from_entity": from_entity,
                            "to_entity": to_entity,
                            "relationship_type": rel_type,
                            "description": str(payload.get("description") or "").strip(),
                            "chapter": chapter,
                        }
                    )
            elif event_type == "artifact_obtained":
                entity_id = str(
                    payload.get("artifact_id")
                    or payload.get("entity_id")
                    or payload.get("id")
                    or payload.get("artifact_name")
                    or payload.get("item")
                    or payload.get("name")
                    or ""
                ).strip()
                if not entity_id:
                    continue
                current = {}
                owner = str(
                    payload.get("owner")
                    or payload.get("holder")
                    or payload.get("to")
                    or event.get("subject")
                    or ""
                ).strip()
                location = str(payload.get("location") or payload.get("source") or "").strip()
                if owner:
                    current["holder"] = owner
                if location:
                    current["location"] = location
                deltas.append(
                    {
                        "entity_id": entity_id,
                        "canonical_name": str(
                            payload.get("canonical_name")
                            or payload.get("artifact_name")
                            or payload.get("item")
                            or payload.get("name")
                            or entity_id
                        ).strip(),
                        "type": str(payload.get("type") or "物品").strip() or "物品",
                        "current": current,
                        "desc": str(payload.get("description") or "").strip(),
                        "chapter": chapter,
                    }
                )
        return deltas

    def apply_effective(self, effective_input, build_handle) -> dict:
        from .effective_history import EffectiveProjectionInput, write_effective_projection
        if not isinstance(effective_input, EffectiveProjectionInput):
            raise TypeError("apply_effective requires EffectiveProjectionInput")
        entry = effective_input.effective_entry
        extraction = entry.extraction_result or {}
        return write_effective_projection(
            self.project_root, effective_input, build_handle, "index", "index",
            {"tombstone": entry.status != "accepted",
             "chapter_meta": extraction.get("chapter_meta", {}),
             "accepted_events": extraction.get("accepted_events", []),
             "state_deltas": extraction.get("state_deltas", []),
             "entity_deltas": extraction.get("entity_deltas", [])},
        )
