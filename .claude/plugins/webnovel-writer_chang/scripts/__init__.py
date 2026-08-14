"""
webnovel-writer scripts package

This package contains all Python scripts for the webnovel-writer plugin.
"""

__version__ = "6.3.0"
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
