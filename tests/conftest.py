import datetime as dt
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOW = dt.datetime(2026, 9, 30, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def repo_copy(tmp_path):
    """A scratch copy of the real data + README so builds can write safely."""
    shutil.copytree(ROOT / "data", tmp_path / "data", ignore=shutil.ignore_patterns("cache"))
    (tmp_path / "data" / "cache").mkdir()
    shutil.copy(ROOT / "README.md", tmp_path / "README.md")
    return tmp_path
