"""Cache envelope, change-only writes, canonical hashing."""
import datetime as dt
import hashlib
import json
from pathlib import Path

SCHEMA = 1
ENVELOPE_KEYS = {"schema", "generated_at", "source", "ok", "data"}


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(obj) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


class Cache:
    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, name: str) -> Path:
        return self.root / f"{name}.json"

    def read(self, name: str):
        """Return a valid envelope or None (missing/corrupt files are rejected)."""
        try:
            env = json.loads(self.path(name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(env, dict) or not ENVELOPE_KEYS <= env.keys() or env.get("schema") != SCHEMA:
            return None
        return env

    def write(self, name: str, data, source: str, now: dt.datetime) -> bool:
        """Write only if `data` differs from the cached data. Returns True if written."""
        prev = self.read(name)
        if prev and prev.get("ok") and digest(prev["data"]) == digest(data):
            return False
        env = {"schema": SCHEMA, "generated_at": iso(now), "source": source, "ok": True, "data": data}
        self.root.mkdir(parents=True, exist_ok=True)
        self.path(name).write_text(json.dumps(env, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        return True

    @staticmethod
    def age_hours(env: dict, now: dt.datetime) -> float:
        return (now - parse_iso(env["generated_at"])).total_seconds() / 3600.0


def would_change(cache: "Cache", name: str, data) -> bool:
    prev = cache.read(name)
    return not (prev and prev.get("ok") and digest(prev["data"]) == digest(data))


def _strip(obj, keys):
    if isinstance(obj, dict):
        return {k: _strip(v, keys) for k, v in obj.items() if k not in keys}
    if isinstance(obj, list):
        return [_strip(v, keys) for v in obj]
    return obj


def would_change_status(cache: "Cache", name: str, data, now: dt.datetime, refresh_after_h: float = 24) -> bool:
    """Change-only rule for CI / health datasets, which carry a `checked_at` per record.

    The check time is real information (it is how a later outage decides whether the cache is too old to trust), but a
    commit per run just to move a timestamp is churn. So: ignore `checked_at` when comparing, and refresh the file only
    when a state really changed OR the stored check is older than `refresh_after_h` (at most one timestamp-only commit
    per day, which the daily contribution-calendar update already causes anyway)."""
    prev = cache.read(name)
    if not (prev and prev.get("ok")):
        return True
    if digest(_strip(prev["data"], {"checked_at"})) != digest(_strip(data, {"checked_at"})):
        return True
    return Cache.age_hours(prev, now) >= refresh_after_h
