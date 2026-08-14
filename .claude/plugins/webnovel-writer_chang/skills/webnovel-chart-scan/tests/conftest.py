import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pytest

@pytest.fixture
def fixtures_dir() -> Path:
    return ROOT / "tests" / "fixtures"
