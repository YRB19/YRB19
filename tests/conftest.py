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
    # The owner decides whether NetOS/FREYA are published (`publish:` in data/projects.yml) and that choice changes over time.
    # The hiding *mechanism* is what these tests pin, so the scratch copy always starts with them unpublished; tests that
    # exercise publishing flip the switch themselves, and tests of the shipped data say nothing about the owner's choice.
    import yaml
    p = tmp_path / "data" / "projects.yml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    for slug in ("NetOS", "FREYA"):
        d[slug]["publish"] = False
    p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True), encoding="utf-8")
    shutil.copy(ROOT / "README.md", tmp_path / "README.md")
    return tmp_path
