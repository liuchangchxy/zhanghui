"""集成测试：跑 install_python_deps.py 在干净 ubuntu:latest Docker 容器里。

默认 skip（CI 慢 + 需 docker）。本地跑：
    DOCKER_INSTALL_TEST=1 python3 -m pytest tests/test_install_docker.py -v -s
"""
import os
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent.parent


@pytest.mark.skipif(
    os.environ.get("DOCKER_INSTALL_TEST") != "1",
    reason="set DOCKER_INSTALL_TEST=1 to run (slow, needs docker)",
)
def test_install_in_clean_ubuntu_container(tmp_path):
    dockerfile_src = PLUGIN_ROOT / "scripts" / "tests" / "Dockerfile.install-test"
    build_ctx = tmp_path
    (build_ctx / "Dockerfile").write_text(dockerfile_src.read_text())
    # Copy plugin into build context
    subprocess.run(
        ["cp", "-R", str(PLUGIN_ROOT) + "/.", str(build_ctx) + "/"],
        check=True,
    )
    result = subprocess.run(
        ["docker", "build", "-t", "wn-install-test", str(build_ctx)],
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, f"docker build failed:\n{result.stderr}"