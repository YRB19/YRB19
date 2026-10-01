"""Language distribution by bytes across public, non-fork, non-archived, non-excluded repos."""


def distribution(repos, *, exclude_languages=(), exclude_repos=(), min_pct=2.0) -> list:
    excl_r = {x.lower() for x in exclude_repos}
    excl_l = set(exclude_languages)
    totals: dict[str, int] = {}
    for r in repos:
        if r["is_private"] or r["is_fork"] or r["is_archived"] or r["full_name"].lower() in excl_r:
            continue
        for lang, size in r["languages"].items():
            if lang not in excl_l:
                totals[lang] = totals.get(lang, 0) + size
    grand = sum(totals.values())
    if not grand:
        return []
    out, other = [], 0.0
    for lang, size in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0])):
        pct = size * 100.0 / grand
        if pct < min_pct:
            other += pct
        else:
            out.append({"language": lang, "pct": round(pct, 1)})
    if other > 0:
        out.append({"language": "Other", "pct": round(other, 1)})
    return out
