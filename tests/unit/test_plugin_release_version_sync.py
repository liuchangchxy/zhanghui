#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Release-metadata contract for the plugin marketplace update path.

Regression guard for the acceptance defect where PR #46/#47 merged without a version
change: `claude plugin update zhanghui@zhanghui` answered "already at the latest version
(6.4.0)" and never copied the fixed code, so existing users could not receive the fixes.

The real fix has two halves, both checked here:
* the release helper resolves the *current* tree layout
  (`<repo>/.claude/plugins/zhanghui` + `<repo>/.claude-plugin/marketplace.json`);
* plugin manifest, marketplace catalog and README badge/release row agree.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / ".claude" / "plugins" / "zhanghui" / "scripts" / "sync_plugin_version.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(HELPER), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_release_metadata_is_in_sync_for_the_real_repository_layout():
    result = _run("--check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "in sync" in result.stdout.lower()


def test_release_helper_reads_the_plugin_and_marketplace_from_different_roots():
    """The helper must not assume the plugin tree is the repository root."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("sync_plugin_version_under_test", HELPER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.PLUGIN_JSON_PATH.is_file(), module.PLUGIN_JSON_PATH
    assert module.PLUGIN_JSON_PATH.parent.parent == REPO_ROOT / ".claude" / "plugins" / "zhanghui"
    assert module.MARKETPLACE_JSON_PATH == REPO_ROOT / ".claude-plugin" / "marketplace.json"
    assert module.MARKETPLACE_JSON_PATH.is_file()
    assert module.README_PATH == REPO_ROOT / "README.md"
    assert module.README_PATH.is_file()
