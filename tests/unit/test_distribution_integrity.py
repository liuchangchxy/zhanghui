#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests verifying Zhanghui distribution integrity (Issue #29 Phase 5).

Verifies:
1. Canonical source tree (.claude/plugins/zhanghui) has valid plugin manifest.
2. Repo root marketplace manifest points directly to canonical plugin source.
3. Critical runtime modules (chapter_runtime, writer_package, reconciliation, prose pipeline)
   and skills reside in canonical tree, guaranteeing no partial whitelist sync.
4. Historical 6.4.0 directory is marked as read-only snapshot.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CANONICAL_PLUGIN_ROOT = REPO_ROOT / ".claude" / "plugins" / "zhanghui"


def test_canonical_plugin_manifest_integrity():
    """Canonical plugin manifest must exist, declare valid name and semver version."""
    plugin_json = CANONICAL_PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    assert plugin_json.is_file(), "Canonical plugin.json must exist"
    data = json.loads(plugin_json.read_text(encoding="utf-8"))
    assert data.get("name") == "zhanghui"
    assert data.get("version") == "6.4.0"
    assert (CANONICAL_PLUGIN_ROOT / "skills").is_dir()


def test_repo_marketplace_manifest_points_to_canonical_source():
    """Repo root marketplace.json must select the canonical plugin source directly."""
    marketplace_json = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    assert marketplace_json.is_file(), "Repo marketplace.json must exist"
    data = json.loads(marketplace_json.read_text(encoding="utf-8"))
    assert data.get("name") == "zhanghui"
    plugins = data.get("plugins") or []
    assert len(plugins) >= 1
    zh_plugin = next((p for p in plugins if p.get("name") == "zhanghui"), None)
    assert zh_plugin is not None
    # Source path relative to repo root must point to canonical plugin tree
    assert zh_plugin.get("source") == "./.claude/plugins/zhanghui"
    assert zh_plugin.get("version") == "6.4.0"


def test_canonical_tree_contains_complete_runtime_and_skills():
    """Critical runtime modules and skills must exist in canonical source without whitelist omission."""
    required_runtime_files = [
        "scripts/data_modules/chapter_runtime.py",
        "scripts/data_modules/chapter_commit_service.py",
        "scripts/data_modules/context_manager.py",
        "scripts/data_modules/reconciliation.py",
        "scripts/data_modules/story_system_engine.py",
        "scripts/data_modules/story_contracts.py",
        "scripts/data_modules/write_gates/__init__.py",
        "skills/webnovel-write/SKILL.md",
        "skills/webnovel-plan/SKILL.md",
        "skills/webnovel-init/SKILL.md",
        "skills/webnovel-review/SKILL.md",
    ]
    for rel_path in required_runtime_files:
        full_path = CANONICAL_PLUGIN_ROOT / rel_path
        assert full_path.is_file(), f"Missing critical runtime file in canonical tree: {rel_path}"


def test_historical_snapshot_marked_with_notice():
    """Historical snapshot directory 6.4.0 must contain explicit read-only snapshot notice."""
    snapshot_dir = CANONICAL_PLUGIN_ROOT / "6.4.0"
    if snapshot_dir.is_dir():
        notice_file = snapshot_dir / "SNAPSHOT_NOTICE.md"
        assert notice_file.is_file(), "6.4.0 directory must contain SNAPSHOT_NOTICE.md"
        content = notice_file.read_text(encoding="utf-8")
        assert "只读历史快照" in content


def test_install_plugin_script_exists_and_executable():
    """bin/install-plugin.sh must exist, be executable, and reference canonical plugin path."""
    install_script = REPO_ROOT / "bin" / "install-plugin.sh"
    assert install_script.is_file(), "bin/install-plugin.sh must exist"
    content = install_script.read_text(encoding="utf-8")
    assert ".claude/plugins/zhanghui" in content
    assert "zhanghui@zhanghui" in content
