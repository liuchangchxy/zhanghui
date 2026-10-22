#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One character must resolve to one entity id.

《海港旧信》 chapter 2 carried both `xu_zhiyuan` and `许知远` as protagonist entities. The
index projection created the second row from `protagonist_state.name` even though
`protagonist_state.entity_id` already declared `xu_zhiyuan`. Both rows were returned by
`index get-core-entities`, so the data agent emitted disambiguation pending on every chapter
and precommit was blocked until a human chose one.

The fix keys the protagonist entity by its declared canonical id. Legacy name-keyed rows are
retired only when the row itself declares that same canonical id; name similarity alone is
never treated as identity, so two different characters are never merged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_modules.config import DataModulesConfig
from data_modules.index_manager import EntityMeta, IndexManager
from data_modules.index_projection_writer import IndexProjectionWriter


def _manager(tmp_path: Path, state: dict) -> IndexManager:
    state_dir = tmp_path / ".webnovel"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    return IndexManager(config)


def _entity(manager: IndexManager, entity_id: str, *, name: str, protagonist: bool, current: dict | None = None) -> None:
    manager.upsert_entity(
        EntityMeta(
            id=entity_id,
            type="角色",
            canonical_name=name,
            tier="主角" if protagonist else "装饰",
            desc="",
            current=current or {},
            first_appearance=0,
            last_appearance=0,
            is_protagonist=protagonist,
        )
    )


def _sync(tmp_path: Path, manager: IndexManager) -> dict:
    _synced, report = IndexProjectionWriter(tmp_path)._sync_canonical_state_entities(manager)
    return report


def test_fresh_project_creates_only_the_declared_canonical_protagonist(tmp_path: Path) -> None:
    state = {
        "protagonist_state": {"name": "许知远", "entity_id": "xu_zhiyuan"},
        "entity_state": {"xu_zhiyuan": {"location": {"current": "旧潮位站"}}},
    }
    manager = _manager(tmp_path, state)

    report = _sync(tmp_path, manager)

    roles = manager.get_entities_by_type("角色")
    assert [row["id"] for row in roles] == ["xu_zhiyuan"]
    assert manager.get_protagonist()["id"] == "xu_zhiyuan"
    # The display name is an alias, not a second entity.
    assert manager.get_entity("许知远")["id"] == "xu_zhiyuan"
    assert report.get("retired_duplicates") is None


def test_legacy_name_keyed_protagonist_is_retired_without_losing_aliases(tmp_path: Path) -> None:
    state = {"protagonist_state": {"name": "许知远", "entity_id": "xu_zhiyuan"}}
    manager = _manager(tmp_path, state)
    # Exactly the chapter-2 shape: the old sync created a row keyed by the display name.
    _entity(manager, "许知远", name="许知远", protagonist=True, current={"entity_id": "xu_zhiyuan"})
    _entity(manager, "xu_zhiyuan", name="许知远", protagonist=True)
    for alias in ("许知远", "protagonist", "主角"):
        manager.register_alias(alias, "许知远", "角色")
        manager.register_alias(alias, "xu_zhiyuan", "角色")

    report = _sync(tmp_path, manager)

    assert [row["id"] for row in manager.get_core_entities()] == ["xu_zhiyuan"]
    assert manager.get_protagonist()["id"] == "xu_zhiyuan"
    assert [row["id"] for row in manager.get_entities_by_alias("许知远")] == ["xu_zhiyuan"]
    assert [row["id"] for row in manager.get_entities_by_alias("主角")] == ["xu_zhiyuan"]

    rows = {row["id"]: row for row in manager.get_entities_by_type("角色", include_archived=True)}
    assert rows["许知远"]["is_archived"] == 1
    assert rows["许知远"]["is_protagonist"] == 0
    assert rows["xu_zhiyuan"]["is_archived"] == 0
    assert report["retired_duplicates"] == [{"id": "许知远", "merged_into": "xu_zhiyuan"}]

    # Idempotent: the retired row is not retired again.
    report_again = _sync(tmp_path, manager)
    assert report_again.get("retired_duplicates") is None


@pytest.mark.parametrize(
    "legacy_current",
    [
        {"entity_id": "someone_else"},  # the row declares a different identity
        {},  # no identity declaration: a shared name is not proof
    ],
)
def test_different_characters_sharing_a_name_are_not_merged(
    tmp_path: Path, legacy_current: dict
) -> None:
    state = {"protagonist_state": {"name": "许知远", "entity_id": "xu_zhiyuan"}}
    manager = _manager(tmp_path, state)
    _entity(manager, "xu_zhiyuan", name="许知远", protagonist=True)
    _entity(manager, "许知远", name="许知远", protagonist=False, current=legacy_current)
    manager.register_alias("许知远", "许知远", "角色")

    report = _sync(tmp_path, manager)

    rows = {row["id"]: row for row in manager.get_entities_by_type("角色", include_archived=True)}
    assert rows["许知远"]["is_archived"] == 0, "只有同名不构成同一角色的证据"
    assert rows["许知远"]["is_protagonist"] == 0
    assert "许知远" in {row["id"] for row in manager.get_entities_by_alias("许知远")}
    assert report.get("retired_duplicates") is None
