import argparse
import os
import sys
from pathlib import Path


def _root(a):
    return Path(a.root).resolve()


def cmd_validate(a) -> int:
    from .validate import check_repos_online, validate

    rep = validate(_root(a), strict=a.strict)
    if a.online:
        online = check_repos_online(_root(a))
        rep.warnings += online.warnings
    for w in rep.warnings:
        print(f"warning: {w}")
    for e in rep.errors:
        print(f"error: {e}")
    print("validate:", "OK" if rep.ok else f"FAILED ({len(rep.errors)} error(s))", f"· {len(rep.warnings)} warning(s)")
    return 0 if rep.ok else 1


def cmd_build(a) -> int:
    from .build import BuildError, build

    try:
        res = build(_root(a), fixtures=a.fixtures, dry_run=a.dry_run or a.fixtures)
    except BuildError as e:
        print(f"build failed: {e}", file=sys.stderr)
        return 1
    for w in res.warnings:
        print(f"warning: {w}", file=sys.stderr)
    if res.dry_run:
        if a.fixtures:
            print("=== FIXTURE DATA (synthetic, illustrative only — nothing written) ===\n")
        for sid, body in res.blocks.items():
            print(f"--- {sid} ---\n{body}\n")
    print("build:", "changed" if res.changed else "no material change")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="profileos")
    p.add_argument("--root", default=os.environ.get("PROFILEOS_ROOT", "."))
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--strict", action="store_true")
    v.add_argument("--online", action="store_true")
    v.set_defaults(fn=cmd_validate)
    b = sub.add_parser("build")
    b.add_argument("--dry-run", action="store_true")
    b.add_argument("--fixtures", action="store_true", help="use synthetic API data (implies --dry-run)")
    b.set_defaults(fn=cmd_build)
    a = p.parse_args(argv)
    return a.fn(a)
