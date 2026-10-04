# Vendored uv Binaries

Bundled `uv` (Python package installer) binaries for offline bootstrap.
Used by `hooks/install_python_deps.py` to create venvs and install Python
dependencies for this plugin's Python-using modules (chart-scan, dashboard, scripts).

## Version

uv **0.4.18** (released 2024-10-01).

Source: <https://github.com/astral-sh/uv/releases/tag/0.4.18>

## Files

| File | Platform |
|---|---|
| `uv-darwin-arm64` | macOS Apple Silicon |
| `uv-darwin-x86_64` | macOS Intel |
| `uv-linux-x86_64` | Linux x86_64 |
| `uv-windows-x86_64.exe` | Windows x86_64 |
| `LICENSE-MIT` | MIT license text (uv is MIT OR Apache-2.0) |
| `LICENSE-APACHE` | Apache-2.0 license text |
| `SHA256SUMS` | Integrity hashes for the 4 binaries |

Note: only `uv` is vendored. `uvx` is intentionally not bundled (small enough
to install via `uv tool install uvx` if needed).

## Verify Integrity

```bash
shasum -a 256 -c SHA256SUMS
```

All 4 lines should report `OK`.

## Updating

To bump uv (e.g., for a CVE fix):

1. Bump `UV_VERSION` in `docs/superpowers/plans/2026-08-15-webnovel-plugin-cross-platform-deps-impl.md` Task 1 Step 2
2. Re-download 4 binaries with the new version URLs
3. Re-fetch LICENSE-MIT and LICENSE-APACHE at the new tag
4. Regenerate SHA256SUMS (preserve the 3 provenance header lines, update version + URL + date)
5. Update this README's version section
6. Commit as `feat(install): bump uv to ${NEW_VERSION}`

## License

uv is dual-licensed MIT OR Apache-2.0. Redistributed copies must include the
LICENSE text — see LICENSE-MIT and LICENSE-APACHE in this directory.
