"""
webnovel-writer scripts package

This package contains all Python scripts for the webnovel-writer plugin.
"""

def _plugin_version() -> str:
    """Read the version from the one place that is authoritative for it.

    This used to be a hand-maintained `"6.4.0"` literal that nothing consumed, so it simply
    drifted: the package claimed 6.4.0 while `plugin.json` said 6.5.0. A second copy of a
    version string is a second thing to forget, and a version string that lies is worse than
    no version string — the audit found the installed host loading a stale tree that reported
    the same version as the canonical one. Derive it, never restate it.
    """
    import json
    from pathlib import Path

    manifest = Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json"
    try:
        return str(json.loads(manifest.read_text(encoding="utf-8"))["version"])
    except (OSError, ValueError, KeyError):
        return "unknown"


__version__ = _plugin_version()
__author__ = "chang"

__all__ = [
    "security_utils",
    "project_locator",
    "chapter_paths",
]


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    import importlib

    module = importlib.import_module(f"{__name__}.{name}")
    globals()[name] = module
    return module
