"""Profile-experience enhancement: the eight features (docs/FEATURES.md).

All fixtures here are SYNTHETIC (clearly labelled by the SYN_ prefix / FixtureClient) and are never written to the repo's
real cache or history.
"""
import datetime as dt
import re
from types import SimpleNamespace as NS

import pytest
import yaml

from conftest import NOW, ROOT
from profileos.build import build
from profileos.generators import features, models, visuals
from profileos.generators.markers import REGISTERED, check_markers, migrate_legacy, replace_blocks
from profileos.generators.svg import bubbles, city, pet, projectmap, rhythm, safety, signal
from profileos.generators.svg.tokens import MODES, Theme
from profileos.github.fixtures import FixtureClient
from test_build import _ctx

D0 = dt.date(2026, 9, 30)


def SYN_ctx(counts, now=NOW, peak=0):
    """SYNTHETIC calendar: `counts` is oldest->newest, the last entry is the fetch day."""
    days = [{"date": (D0 - dt.timedelta(days=len(counts) - 1 - i)).isoformat(), "count": c} for i, c in enumerate(counts)]
    return NS(ds={"contributions": {"calendar": {"total": sum(counts), "days": days}}}, now=now, snapshot_date="2026-09-30", pet_peak=peak)


def meta(name, alt="alt"):
    return {"name": name, "title": "t", "alt": alt}


# ---- Project Map ------------------------------------------------------------------------------------------------
def N(slug, langs=(), topics=(), stars=0, **kw):
    return {"slug": slug, "name": slug, "url": f"https://github.com/YRB19/{slug}", "category": kw.get("category", "ai"), "category_label": "AI",
            "language": langs[0] if langs else None, "languages": list(langs), "topics": list(topics), "stars": stars,
            "radius": features.star_radius(stars), "os_series": kw.get("os", False)}


def test_star_radius_is_bounded_monotonic_and_never_zero():
    r = [features.star_radius(s) for s in (0, 1, 2, 10, 50, 5000)]
    assert r[0] == features.R_MIN > 0 and r == sorted(r) and r[-1] == r[-2] == features.R_MAX
    assert features.star_radius(1) - features.star_radius(0) < 2.5       # one star does not balloon a node


def test_edges_only_from_shared_language_or_topic_never_from_names():
    nodes = [N("AlphaOS", ["Python"]), N("AlphaTool", ["Rust"]), N("C", ["Python"], ["cli"]), N("D", ["Go"], ["cli"]), N("Lonely")]
    edges = {(e["source"], e["target"]): e for e in features.map_edges(nodes)}
    assert set(edges) == {("AlphaOS", "C"), ("C", "D")}                     # similar names alone connect nothing
    assert edges[("AlphaOS", "C")]["shared_languages"] == ["Python"] and edges[("C", "D")]["shared_topics"] == ["cli"]
    assert edges[("AlphaOS", "C")]["strength"] == 1


def test_edge_strength_counts_shared_attributes_and_cap_keeps_strongest():
    hub = N("hub", ["Python", "TypeScript"], ["a", "b"])
    others = [N(f"n{i}", ["Python", "TypeScript"] if i == 0 else ["Python"], ["a"] if i < 2 else []) for i in range(6)]
    edges = features.map_edges([hub] + others)
    assert max(e["strength"] for e in edges) == 3
    capped = features.cap_edges(edges, per_node=2)
    assert len(capped) <= len(edges) and {e["target"] for e in capped if e["source"] == "hub"} >= {"n0", "n1"}   # strongest survive


def test_significant_language_threshold_ignores_trace_languages():
    assert features.significant_languages({"Python": 900, "CSS": 20}, "Python") == {"Python"}
    assert features.significant_languages({"Python": 500, "CSS": 400}) == {"Python", "CSS"}


def test_layout_is_deterministic_and_collision_free():
    nodes = [N(f"Project{i}", ["Python" if i % 2 else "Rust"], stars=i % 3, os=i < 4) for i in range(12)]
    edges = features.cap_edges(features.map_edges(nodes))
    a = projectmap.solve(nodes, edges)
    b = projectmap.solve(nodes, edges)
    assert a[0] == b[0] and a[2] == b[2]
    pos, info, _ = a
    assert projectmap.overlaps(pos, info) == []
    assert all(20 <= x <= 412 for x, _ in pos)                              # inside the canvas


def test_layout_handles_projects_with_no_relationships():
    nodes = [N(f"Solo{i}") for i in range(6)]
    pos, info, _ = projectmap.solve(nodes, [])
    assert len(pos) == 6 and projectmap.overlaps(pos, info) == []


def test_map_uses_only_published_resolved_projects(repo_copy):
    ctx = _ctx(repo_copy)
    m = features.project_map_model(ctx)
    names = {n["name"] for n in m["nodes"]}
    assert {"UsageOS", "ResearchOS"} <= names and not names & {"NetOS", "FREYA", "YRB19"}     # publish:false and the profile repo stay out
    assert all(not n["url"].endswith("/YRB19") for n in m["nodes"])


def test_map_follows_publish_switch_not_hardcoded_names(repo_copy):
    p = repo_copy / "data" / "projects.yml"
    d = yaml.safe_load(p.read_text())
    d["NetOS"]["publish"] = True
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    assert "NetOS" in {n["name"] for n in features.project_map_model(_ctx(repo_copy))["nodes"]}


def test_map_svg_is_understandable_without_colour_and_marks_relationship_types():
    nodes = [N("A", ["Python"], ["x"], category="ai", os=True), N("B", ["Python"], ["x"], category="systems"), N("C", ["Go"], category="ai")]
    m = {"nodes": nodes, "edges": features.map_edges(nodes), "static_edges": features.map_edges(nodes), "show_stars": False}
    svg = projectmap.render(m, Theme("light"), meta("project-map", projectmap.alt(m)))
    assert safety.validate(svg) == []
    assert ">A<" in svg and ">S<" in svg                                       # category code printed inside nodes
    assert "shared topic" in svg and "OS series" in svg
    assert "stroke-dasharray" not in svg.split("<line")[1].split("/>")[0]      # topic (strong) edge is solid


# ---- Profile Signal -------------------------------------------------------------------------------------------------
def test_signal_metric_scopes_and_values(repo_copy):
    ctx = _ctx(repo_copy)
    ctx.ds["profile"] = {"followers": 12, "public_repos": 24}
    m = features.signal_model(ctx)
    t = {x["key"]: x["value"] for x in m["tiles"]}
    assert [x["key"] for x in m["tiles"]] == ["stars", "contributions", "repositories", "followers"]
    assert t["followers"] == 12 and t["repositories"] == 24                        # account totals, not the featured-project count
    assert t["stars"] == sum(r["stars"] for r in ctx.resolved.values())
    assert t["contributions"] == ctx.ds["contributions"]["calendar"]["total"]       # same calendar as the city
    assert all(k in m["metric_scopes"] for k in t)


def test_signal_omits_unavailable_tiles_instead_of_inventing_zero(repo_copy):
    ctx = _ctx(repo_copy)
    ctx.ds.pop("profile", None)
    keys = [t["key"] for t in features.signal_model(ctx)["tiles"]]
    assert "followers" not in keys and "repositories" not in keys and "stars" in keys
    ctx.ds.pop("contributions"), ctx.ds.pop("repos")
    ctx.resolved = {}
    assert features.signal_model(ctx) is None


def test_signal_excludes_forks_and_hidden_repos_from_stars(repo_copy):
    ctx = _ctx(repo_copy)
    for r in ctx.resolved.values():
        r["stars"] = 5
    ctx.resolved["UsageOS"] = dict(ctx.resolved["UsageOS"], is_fork=True)
    assert features.signal_model(ctx)["tiles"][0]["value"] == 5 * (len(ctx.resolved) - 1)


def test_signal_svg_renders_in_both_modes_with_definitions_in_alt():
    m = {"tiles": [{"key": "stars", "label": "Stars", "scope": "published projects", "value": 3},
                   {"key": "followers", "label": "Followers", "scope": "on GitHub", "value": 1234567}],
         "generated_at": "2026-09-30", "metric_scopes": {"stars": "S scope.", "followers": "F scope."}, "note": "n."}
    for mode in MODES:
        svg = signal.render(m, Theme(mode), meta("profile-signal", signal.alt(m)))
        assert safety.validate(svg) == [] and "1,234,567" in svg
    assert "S scope." in signal.alt(m) and "F scope." in signal.alt(m)


# ---- Code Pet -----------------------------------------------------------------------------------------------------------
def test_pet_level_boundaries_are_exact_and_documented():
    assert [features.mood_index(n) for n in (0, 1, 2, 3, 4, 5, 7)] == [0, 1, 1, 2, 2, 3, 3]
    assert [features.food_index(n) for n in (0, 1, 9, 10, 24, 25)] == [0, 1, 1, 2, 2, 3]
    at = features.GROWTH_AT
    assert [features._index(v, at) for v in (0, 99, 100, 399, 400, 799, 800, 1499, 1500)] == [0, 0, 1, 1, 2, 2, 3, 3, 4]
    assert features.MOODS[0] == "Resting" and features.GROWTH[-1] == "Veteran"


def test_streaks_week_and_latest_day_from_real_calendar():
    counts = [0] * 20 + [2, 0, 1, 3, 4, 0, 5]                # newest last; last day (fetch day) = 5
    m = features.pet_model(SYN_ctx(counts))
    assert m["current_streak"] == 1 and m["longest_streak"] == 3
    assert m["weekly_contributions"] == 2 + 0 + 1 + 3 + 4 + 0 + 5 - 2 + 2 or m["weekly_contributions"] == sum(counts[-7:])
    assert m["latest_completed_day_count"] == 0 and m["latest_completed_day"] == "2026-09-29"


def test_open_fetch_day_never_breaks_a_streak():
    m = features.pet_model(SYN_ctx([0] * 10 + [1, 1, 1, 0]))          # today empty so far: the streak carries from yesterday
    assert m["current_streak"] == 3


def test_missing_a_day_is_never_punitive():
    busy = [3] * 60
    a = features.pet_model(SYN_ctx(busy))
    b = features.pet_model(SYN_ctx(busy + [0]))                       # one rest day
    assert b["growth_index"] >= a["growth_index"] - 0 and b["growth_level"] == a["growth_level"] or b["growth_index"] >= a["growth_index"]
    quiet = features.pet_model(SYN_ctx([0] * 60))
    assert quiet["mood"] == "Resting" and quiet["growth_level"] == "Newborn"       # resting, not dead or sick
    text = " ".join(str(v) for v in quiet.values()).lower()
    for bad in ("dead", "die", "sick", "hungry", "starv", "sad", "guilt", "neglect", "missed"):
        assert bad not in text


def test_growth_never_decreases_high_water_mark():
    quiet = [0] * 100
    assert features.pet_model(SYN_ctx(quiet))["growth_level"] == "Newborn"
    m = features.pet_model(SYN_ctx(quiet, peak=3))
    assert m["growth_level"] == "Adult" and m["growth_computed_index"] == 0


def test_pet_hidden_without_calendar():
    assert features.pet_model(NS(ds={}, now=NOW, snapshot_date="x", pet_peak=0)) is None


def test_pet_svg_all_stages_and_moods_render_safely_in_both_modes():
    ink_sizes = set()
    for stage in range(5):
        for mood in range(4):
            px = pet.sprite(stage, mood)
            assert px and all(0 <= x < pet.GW and 0 <= y < pet.GH for x, y in px)
            ink_sizes.add(len(px))
    assert len(ink_sizes) > 8                                         # stages/moods really look different
    m = features.pet_model(SYN_ctx([1, 0, 2, 0, 0, 3, 1, 1] * 10))
    for mode in MODES:
        svg = pet.render(m, Theme(mode), meta("code-pet", pet.alt(m)))
        assert safety.validate(svg) == [] and "YRB19" in svg
        assert all(len(l) < 75 for l in re.findall(r">([^<]+)</text>", svg))     # no sprawling text


# ---- Contribution City ----------------------------------------------------------------------------------------------
def test_city_height_mapping_is_bounded_and_matches_levels():
    ctx = SYN_ctx([0, 1, 5, 10, 20, 40] * 20)
    ctx.ds["contributions"]["calendar"]["total"] = sum([0, 1, 5, 10, 20, 40] * 20)
    m = features.city_model(ctx)
    assert m["heights"] == list(features.LEVEL_HEIGHTS) and max(m["heights"]) <= 24 and m["heights"][0] == 0
    by_count = {}
    for c in m["cells"]:
        by_count.setdefault(c["count"], set()).add(c["level"])
    assert by_count[0] == {0} and all(len(v) == 1 for v in by_count.values())
    assert by_count[1] == {1} and by_count[40] == {4}
    assert m["date_range"] == [m["cells"][0]["date"], m["cells"][-1]["date"]]       # no extrapolated dates


def test_city_uses_every_real_day_and_adds_none():
    counts = [0, 2, 0, 0, 7] * 30
    m = features.city_model(SYN_ctx(counts))
    assert len(m["cells"]) == len(counts) and sum(c["count"] for c in m["cells"]) == sum(counts)


def test_city_svg_stays_bounded_even_for_a_fully_dense_year():
    counts = [1 + (i * 37) % 50 for i in range(365)]
    ctx = SYN_ctx(counts)
    m = features.city_model(ctx)
    for mode in MODES:
        svg = city.render(m, Theme(mode), meta("contribution-city", city.alt(m)))
        assert safety.validate(svg, safety.LIMITS["contribution-city"]) == [] and len(svg.encode()) < safety.LIMITS["contribution-city"]
    empty = features.city_model(SYN_ctx([0] * 100))
    assert safety.validate(city.render(empty, Theme("dark"), meta("contribution-city", "a")), safety.LIMITS["contribution-city"]) == []


def test_city_is_not_colour_only():
    svg = city.render(features.city_model(SYN_ctx([0, 30] * 40)), Theme("light"), meta("contribution-city", "a"))
    assert "Less" in svg and "More" in svg and "contributions" in svg


# ---- Activity Rhythm -------------------------------------------------------------------------------------------------------
def test_rhythm_aggregates_by_weekday_over_real_days():
    # 2026-09-30 is a Wednesday; give Mondays 3, everything else 0, over 70 days
    counts = [0] * 70
    for i in range(70):
        if (D0 - dt.timedelta(days=69 - i)).weekday() == 0:
            counts[i] = 3
    m = features.rhythm_model(SYN_ctx(counts))
    rows = {r["weekday"]: r for r in m["rows"]}
    assert rows["Mon"]["count"] == 30 and sum(r["count"] for r in m["rows"]) == m["total"] == 30
    assert rows["Mon"]["percentage"] == 100.0 and rows["Tue"]["count"] == 0
    assert [r["weekday"] for r in m["rows"]] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def test_rhythm_hidden_without_enough_history():
    assert features.rhythm_model(SYN_ctx([1] * (features.MIN_RHYTHM_DAYS - 1))) is None
    assert features.rhythm_model(SYN_ctx([0] * 200)) is None
    assert features.rhythm_model(NS(ds={}, now=NOW)) is None


def test_rhythm_svg_labels_and_scope():
    m = features.rhythm_model(SYN_ctx([1, 2, 0, 4, 1, 0, 3] * 12))
    for mode in MODES:
        svg = rhythm.render(m, Theme(mode), meta("activity-rhythm", rhythm.alt(m)))
        assert safety.validate(svg) == [] and all(d in svg for d in ("Mon", "Sun"))
    assert "calendar weekday" in m["note"] and "last 12 months" in m["note"]      # scope stated; the "not productivity" disclaimer was trimmed on purpose


# ---- Language bubbles -----------------------------------------------------------------------------------------------------
def test_bubble_percentages_come_from_bytes_and_other_aggregates(repo_copy):
    ctx = _ctx(repo_copy)
    ctx.repos = [{"name": f"r{i}", "full_name": f"YRB19/r{i}", "is_private": False, "is_fork": False, "is_archived": False,
                  "languages": {f"L{i}": 1000 - i * 100, "Big": 5000}} for i in range(10)]
    m = features.bubbles_model(ctx)
    assert sum(i["bytes"] for i in m["items"]) == m["total_bytes"] == sum(sum(r["languages"].values()) for r in ctx.repos)
    assert m["items"][0]["language"] == "Big" and m["items"][-1]["language"] == "Other"
    assert abs(sum(i["percentage"] for i in m["items"]) - 100) < 0.3
    assert len(m["items"]) <= features.MAX_BUBBLES + 1
    assert m["items"][0]["repositories"] == sorted((r["name"] for r in ctx.repos), key=str.lower)


def test_bubble_packing_is_proportional_deterministic_and_non_overlapping():
    shares = [48.4, 28.8, 13.8, 5.7, 2.0, 1.3]
    a, size = bubbles.pack(shares)
    assert a == bubbles.pack(shares)[0]
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            assert ((a[i][0] - a[j][0]) ** 2 + (a[i][1] - a[j][1]) ** 2) ** 0.5 >= a[i][2] + a[j][2] - 1e-6
    ratio = (a[0][2] / a[1][2]) ** 2
    assert abs(ratio - shares[0] / shares[1]) < 0.01                      # area, not radius, tracks share


def test_bubbles_svg_lists_every_language_as_text():
    m = {"items": [{"language": "Python", "bytes": 90, "percentage": 90.0, "repositories": []},
                   {"language": "Other", "bytes": 10, "percentage": 10.0, "repositories": []}], "total_bytes": 100, "note": "n."}
    for mode in MODES:
        svg = bubbles.render(m, Theme(mode), meta("language-bubbles", bubbles.alt(m)))
        assert safety.validate(svg) == [] and "90.0%" in svg and "10.0%" in svg
    assert "Skill" not in svg and "proficien" not in svg.lower()


# ---- Collaboration CTA ----------------------------------------------------------------------------------------------------
def test_cta_uses_only_approved_links_and_makes_no_availability_promise(repo_copy):
    ctx = _ctx(repo_copy)
    m = features.collaboration_model(ctx)
    assert [l["url"] for l in m["approved_links"]] == [l["url"] for l in ctx.d["links"]["links"]]
    low = (m["headline"] + (m["description"] or "")).lower()
    for promise in ("available for", "open to work", "hire me", "hiring", "freelance"):
        assert promise not in low


def test_cta_drops_unsafe_links(repo_copy):
    ctx = _ctx(repo_copy)
    ctx.d["links"]["links"].append({"label": "Bad", "url": "javascript:alert(1)"})
    assert all(l["label"] != "Bad" for l in features.collaboration_model(ctx)["approved_links"])


def test_cta_links_are_validated_by_schema(repo_copy):
    from profileos.validate import validate
    p = repo_copy / "data" / "links.yml"
    p.write_text(yaml.safe_dump({"links": [{"label": "Mail", "url": "not a url"}]}))
    assert not validate(repo_copy).ok


def test_building_metadata_must_reference_published_projects(repo_copy):
    from profileos.validate import validate
    p = repo_copy / "data" / "profile.yml"
    d = yaml.safe_load(p.read_text())
    d["now"]["building"] = ["NetOS"]                                        # publish: false in the scratch copy
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    assert any("not published" in e for e in validate(repo_copy).errors)
    d["now"]["building"] = ["Nope"]
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    assert any("unknown project" in e for e in validate(repo_copy).errors)


# ---- marker migration --------------------------------------------------------------------------------------------------------
LEGACY = """# T
## Currently Building
<!-- PROFILEOS:START:CURRENTLY_BUILDING -->
old
<!-- PROFILEOS:END:CURRENTLY_BUILDING -->

<!-- PROFILEOS:START:NOW -->
old
<!-- PROFILEOS:END:NOW -->

<!-- PROFILEOS:START:PULSE -->
old
<!-- PROFILEOS:END:PULSE -->

<!-- PROFILEOS:START:RECENTLY_SHIPPED -->
old
<!-- PROFILEOS:END:RECENTLY_SHIPPED -->

<!-- PROFILEOS:START:OS_SERIES -->
old
<!-- PROFILEOS:END:OS_SERIES -->

<!-- PROFILEOS:START:STACK -->
x
<!-- PROFILEOS:END:STACK -->

<!-- PROFILEOS:START:ACTIVITY -->
old
<!-- PROFILEOS:END:ACTIVITY -->

<!-- PROFILEOS:START:LINKS -->
old
<!-- PROFILEOS:END:LINKS -->
"""


def test_legacy_markers_migrate_safely_and_idempotently():
    new, notes = migrate_legacy(LEGACY)
    assert notes
    for gone in ("CURRENTLY_BUILDING", "NOW", "PULSE", "RECENTLY_SHIPPED", "OS_SERIES", "LINKS"):
        assert f"PROFILEOS:START:{gone} " not in new
    for sid in ("SIGNAL", "BUILDING", "PROJECT_MAP", "CTA", "CITY"):
        assert new.count(f"<!-- PROFILEOS:START:{sid} -->") == 1 and new.count(f"<!-- PROFILEOS:END:{sid} -->") == 1, sid
    assert "# T" in new and "x\n<!-- PROFILEOS:END:STACK -->" in new            # text outside generated blocks is untouched
    for absorbed in ("LANGUAGE_BUBBLES", "RHYTHM", "PET", "ACTIVITY"):
        assert f"PROFILEOS:START:{absorbed} " not in new
    again, notes2 = migrate_legacy(new)
    assert again == new and notes2 == []
    errors, _ = check_markers(new, required=[s for s in REGISTERED if s not in ("RELEASES", "SELECTED_SYSTEMS", "EARLIER_BUILDS", "TIMELINE", "FOOTER")])
    assert errors == []


def test_migration_leaves_malformed_legacy_markers_for_the_checker():
    broken = "<!-- PROFILEOS:START:NOW -->\n<!-- PROFILEOS:START:NOW -->\n<!-- PROFILEOS:END:NOW -->\n"
    new, _ = migrate_legacy(broken)
    assert new.count("PROFILEOS:START:NOW") == 2


def test_build_migrates_an_old_readme_in_one_run(repo_copy):
    old_style = (repo_copy / "README.md").read_text()
    for new_id, legacy in (("SIGNAL", "PULSE"), ("PROJECT_MAP", "OS_SERIES"), ("CTA", "LINKS"), ("BUILDING", "NOW")):
        old_style = old_style.replace(f"START:{new_id} ", f"START:{legacy} ").replace(f"END:{new_id} ", f"END:{legacy} ")
    (repo_copy / "README.md").write_text(old_style)
    res = build(repo_copy, fixtures=True, now=NOW)
    text = (repo_copy / "README.md").read_text()
    assert any("migrated marker" in w for w in res.warnings)
    assert "START:PULSE" not in text and text.count("START:SIGNAL") == 1 and "overview.light.svg" in text


# ---- no duplicate visuals; README shape; mobile ----------------------------------------------------------------------------------
def test_readme_shows_each_distribution_once_and_old_widgets_are_gone(repo_copy):
    res = build(repo_copy, fixtures=True, now=NOW)
    text = (repo_copy / "README.md").read_text()
    srcs = re.findall(r'srcset="assets/generated/([a-z0-9-]+)\.dark\.svg"', text)
    assert len(srcs) == len(set(srcs))
    for retired in ("pulse", "heatmap", "languages", "os-series"):
        assert retired not in srcs
    # every feature is published inside a composite: signal + pet, map + languages, city + rhythm (+ the cards), and the banner
    assert {"overview", "overview-narrow", "systems", "systems-narrow", "featured", "collaboration"} <= set(srcs)
    assert not {"profile-signal", "code-pet", "project-map", "language-bubbles", "contribution-city", "activity-rhythm"} & set(srcs)  # never twice
    for old in ("Currently Building", "Development Pulse", "The OS Series"):
        assert old not in text


def test_every_new_image_has_alt_light_dark_and_fits_a_360px_screen(repo_copy):
    res = build(repo_copy, fixtures=True, dry_run=True, now=NOW)
    for name in ("profile-signal", "project-map", "language-bubbles", "contribution-city", "activity-rhythm", "code-pet", "collaboration"):
        a = res.asset_objects[name]
        assert a.alt.strip() and set(a.svg) == {"light", "dark"}
        for svg in a.svg.values():
            w = int(re.search(r'width="(\d+)"', svg).group(1))
            assert w <= 432                                                   # building blocks are phone-width; composites are checked below
            assert not re.search(r"https?://(?!www\.w3\.org)", svg)           # no external references
            sizes = [float(x) for x in re.findall(r'font-size="([\d.]+)"', svg)]
            assert min(sizes) >= 16                                           # the project's legibility floor
    pic = visuals.picture(res.asset_objects["project-map"])
    assert 'width="432"' in pic and "prefers-color-scheme: dark" in pic


def test_missing_history_does_not_break_or_fake_the_monthly_chart(repo_copy):
    res = build(repo_copy, fixtures=True, dry_run=True, now=NOW)
    assert "monthly" not in res.asset_objects and "contribution-city" in res.asset_objects


def test_synthetic_runs_never_write_the_pet_high_water_mark(repo_copy):
    build(repo_copy, fixtures=True, now=NOW)
    assert not (repo_copy / "data" / "cache" / "pet.json").exists()
    build(repo_copy, client=FixtureClient(NOW), now=NOW)
    assert not (repo_copy / "data" / "cache" / "pet.json").exists()


def test_profile_counts_fetch_rejects_malformed_numbers():
    from profileos.github.client import GitHubError
    from profileos.github.fetch import fetch_profile
    assert fetch_profile(FixtureClient(NOW), "YRB19") == {"followers": 12, "public_repos": 24}
    class Bad:
        def graphql(self, q, v):
            return {"user": {"followers": {"totalCount": None}, "repositories": {"totalCount": 3}}}
    with pytest.raises(GitHubError):
        fetch_profile(Bad(), "YRB19")


def test_composites_are_two_column_on_desktop_and_phone_width_when_stacked(repo_copy):
    res = build(repo_copy, fixtures=True, dry_run=True, now=NOW)
    for name in ("overview", "systems", "featured"):
        wide, narrow = res.asset_objects[name], res.asset_objects[f"{name}-narrow"]
        assert wide.narrow == f"{name}-narrow" and wide.alt == narrow.alt
        for mode in ("light", "dark"):
            ww = int(re.search(r'<svg[^>]* width="(\d+)"', wide.svg[mode]).group(1))
            nw = int(re.search(r'<svg[^>]* width="(\d+)"', narrow.svg[mode]).group(1))
            assert ww == 2 * 432 + visuals.GAP and nw == 432
            assert safety.validate(wide.svg[mode], safety.LIMITS["wide"]) == []
            assert wide.svg[mode].count("<svg") > 2                                # nested cards
    # the two columns of a row end on the same line: no ragged edge
    svg = res.asset_objects["overview"].svg["light"]
    cards = re.findall(r'<svg x="([\d.]+)" y="([\d.]+)" width="432" height="([\d.]+)"', svg)
    bottoms = {}
    for x, y, h in cards:
        bottoms[x] = max(bottoms.get(x, 0), float(y) + float(h))
    assert len(bottoms) == 2 and len(set(round(v, 1) for v in bottoms.values())) == 1
