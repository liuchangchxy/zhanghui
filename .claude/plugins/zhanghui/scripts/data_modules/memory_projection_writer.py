#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from .config import DataModulesConfig
from .durable_projection import require_durable_commit_match
from .memory.writer import MemoryWriter


class MemoryProjectionWriter:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def apply(self, commit_payload: dict) -> dict:
        require_durable_commit_match(self.project_root, commit_payload)
        if commit_payload["meta"]["status"] != "accepted":
            return {"applied": False, "writer": "memory", "reason": "commit_rejected"}
        result = MemoryWriter(DataModulesConfig.from_project_root(self.project_root)).apply_commit_projection(
            commit_payload
        )
        return {
            "applied": bool((result or {}).get("items_added") or (result or {}).get("items_updated")),
            "writer": "memory",
            **(result or {}),
        }

    def apply_effective(self, effective_input, build_handle) -> dict:
        from .effective_history import EffectiveProjectionInput, write_effective_projection
        from .intent_reconciliation import reconcile_effective_history
        if not isinstance(effective_input, EffectiveProjectionInput):
            raise TypeError("apply_effective requires EffectiveProjectionInput")
        entry = effective_input.effective_entry
        extraction = entry.extraction_result or {}
        global_obligations = reconcile_effective_history(build_handle.snapshot)
        # Lifecycle is reconciled against the complete accepted history so a
        # later close/payoff is visible, then each obligation is stored only
        # in its creation chapter's memory slice.
        obligations = {}
        for name in ("open_loops", "reader_promises"):
            obligations[name] = [row for row in global_obligations.get(name, [])
                                 if row.get("source_chapter") == entry.chapter]
        return write_effective_projection(
            self.project_root, effective_input, build_handle, "memory", "memory",
            {"tombstone": entry.status != "accepted",
             "accepted_events": extraction.get("accepted_events", []),
             "state_deltas": extraction.get("state_deltas", []),
             "derived_obligations": obligations,
             "semantic_class": "CANON_DERIVED_OBLIGATION"},
        )
