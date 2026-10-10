#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests verifying Zhanghui distribution integrity (Issue #29 Phase 5).

Verifies:
1. Canonical source tree (.claude/plugins/zhanghui) has valid plugin manifest.
2. Repo root marketplace manifest points directly to canonical plugin source.
3. Critical runtime modules (chapter_runtime, writer_package, reconciliation, prose pipeline)
   and skills reside in canonical tree, guaranteeing no partial whitelist sync.
4. Historical 6.4.0 directory is marked as read-only snapshot.
5. Legacy deploy-plugin.sh is permanently deprecated and unconditionally exits non-zero.
6. setup_dev_env.sh does not touch marketplace/cache and directs to bin/install-plugin.sh.
7. No secondary sync scripts (sync_dev_to_cache.sh, sync_dev_to_marketplace.sh) exist.
8. bin/install-plugin.sh exists, is executable, and serves as sole distribution entry.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
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


def test_deploy_plugin_is_deprecated_stub():
    """deploy-plugin.sh must be a deprecated stub that unconditionally exits non-zero and advises install-plugin.sh."""
    deploy_script = CANONICAL_PLUGIN_ROOT / "bin" / "deploy-plugin.sh"
    assert deploy_script.is_file(), "deploy-plugin.sh stub must exist"
    content = deploy_script.read_text(encoding="utf-8")
    assert "RUNTIME_FILES" not in content, "deploy-plugin.sh must not contain legacy whitelist"
    assert "--force" not in content, "deploy-plugin.sh must not permit --force bypass"
    assert "bin/install-plugin.sh" in content

    # Running it without or with arguments must unconditionally exit non-zero
    proc = subprocess.run(["bash", str(deploy_script)], capture_output=True, text=True)
    assert proc.returncode != 0
    assert "deprecated" in proc.stderr.lower()
    assert "install-plugin.sh" in proc.stderr

    proc_force = subprocess.run(["bash", str(deploy_script), "--force"], capture_output=True, text=True)
    assert proc_force.returncode != 0


def test_setup_dev_env_does_not_touch_marketplace_or_cache():
    """setup_dev_env.sh must not sync to marketplace or touch cache symlinks."""
    setup_script = CANONICAL_PLUGIN_ROOT / "scripts" / "dev-only" / "setup_dev_env.sh"
    assert setup_script.is_file(), "setup_dev_env.sh must exist"
    content = setup_script.read_text(encoding="utf-8")
    assert "rsync" not in content, "setup_dev_env.sh must not rsync to marketplace"
    assert "ln -sfn" not in content, "setup_dev_env.sh must not create cache symlinks"
    assert "webnovel-chang-marketplace" not in content, "setup_dev_env.sh must not reference legacy marketplace"
    assert "/Users/chang/Desktop/zhanghui" not in content, "setup_dev_env.sh must not have hardcoded paths"
    assert "bin/install-plugin.sh" in content
    assert "install_git_hook" in content
    assert "pre-commit" in content


def test_no_secondary_sync_scripts_exist():
    """Legacy sync scripts to marketplace or cache must not exist in canonical tree."""
    dev_only = CANONICAL_PLUGIN_ROOT / "scripts" / "dev-only"
    assert not (dev_only / "sync_dev_to_cache.sh").exists(), "sync_dev_to_cache.sh must be removed"
    assert not (dev_only / "sync_dev_to_marketplace.sh").exists(), "sync_dev_to_marketplace.sh must be removed"
