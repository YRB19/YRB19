"""Load the curated YAML layer."""
import json
from pathlib import Path

import yaml

NAMES = ["profile", "projects", "categories", "aliases", "overrides", "links", "history", "stack", "config", "evidence"]
SCHEMA_DIR = Path(__file__).parent / "schemas"


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_all(data_dir: Path) -> dict:
    data_dir = Path(data_dir)
    out = {}
    for n in NAMES:
        p = data_dir / f"{n}.yml"
        out[n] = load_yaml(p) if p.exists() else {}
    return out


def load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
