"""验证 vendor/uv/ 二进制存在且 SHA256SUMS 一致。"""
import hashlib
from pathlib import Path

import pytest

UV_DIR = Path(__file__).parent.parent.parent / "vendor" / "uv"
EXPECTED = [
    "uv-darwin-arm64",
    "uv-darwin-x86_64",
    "uv-linux-x86_64",
    "uv-windows-x86_64.exe",
]


def _read_sha256sums() -> dict[str, str]:
    sums: dict[str, str] = {}
    for line in (UV_DIR / "SHA256SUMS").read_text().splitlines():
        # Skip comment/provenance lines (e.g. "# uv 0.4.18 (2024-10-01)").
        if line.startswith("#"):
            continue
        sha, name = line.split(maxsplit=1)
        sums[name.strip()] = sha.strip()
    return sums


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("binary", EXPECTED)
def test_uv_binary_exists(binary):
    assert (UV_DIR / binary).exists(), f"missing uv binary: {binary}"


@pytest.mark.parametrize("binary", EXPECTED)
def test_uv_binary_sha256_matches(binary):
    sums = _read_sha256sums()
    assert binary in sums, f"no sha256 entry for {binary}"
    assert _sha256(UV_DIR / binary) == sums[binary]
