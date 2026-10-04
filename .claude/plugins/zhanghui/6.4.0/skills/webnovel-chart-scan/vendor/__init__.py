"""Vendored upstream packages.

Each subdirectory is an unmodified (or near-unmodified) subset of an
upstream repository, kept locally so we don't depend on PyPI/GitHub at
runtime. Subpackages have their own ``__init__.py`` so they remain
importable via ``vendor.<name>.<module>``.
"""