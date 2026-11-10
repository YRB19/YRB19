"""Assemble SVG assets from the shared view-models and build the README <picture> markup."""
import html
import re
from dataclasses import dataclass

from . import features, models
from .svg import bars, bubbles, cards, city, cta, pet, projectmap, rhythm, safety, signal
from .svg.base import W, esc, num
from .svg.tokens import DEFAULT_ACCENT, MODES, Theme

ASSET_DIR = "assets/generated"


class AssetError(Exception):
    pass


@dataclass(frozen=True)
class Asset:
    name: str
    title: str
    alt: str
    svg: dict  # mode -> SVG text
    emit: bool = True      # False: a building block of a composite, kept in memory only (never written)
    width: int = W
    narrow: str = ""      # name of the stacked variant served to phones (composites only)


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "x"


def card_name(slug: str) -> str:
    return f"card-{slugify(slug)}"


def asset_path(name: str, mode: str) -> str:
    return f"{ASSET_DIR}/{name}.{mode}.svg"


def _make(name, mod, model, themes, min_height=0, emit=True) -> Asset:
    title = mod.title(model) if hasattr(mod, "title") else mod.TITLE
    alt = mod.alt(model)
    meta = {"name": name, "title": title, "alt": alt, "min_height": min_height}
    svg = {mode: mod.render(model, themes[mode], meta) for mode in MODES}
    for mode, text in svg.items():
        problems = safety.validate(text, safety.LIMITS.get(name, safety.MAX_BYTES))
        if problems:
            raise AssetError(f"{name}.{mode}.svg failed safety checks: {'; '.join(problems)}")
    return Asset(name, title, alt, svg, emit=emit)


GAP = 16
WIDE_AT = 700   # px of viewport: at or above this the two-column composite is served, below it the stacked one

# composite name -> (title, rows). A row is a list of columns, a column a list of member cards stacked top to bottom.
# A composite exists only when at least two members have data; columns that end up shorter than their neighbour have their
# last card stretched so every row ends on one line (no ragged edges).
GROUPS = {
    "overview": ("Profile overview", [[["profile-signal", "activity"], ["code-pet", "activity-rhythm"]]]),
    "systems": ("Project map, contribution city and languages", [[["project-map"], ["contribution-city", "language-bubbles"]]]),
}


def _height(svg: str) -> float:
    return float(re.search(r'<svg[^>]* height="([\d.]+)"', svg).group(1))


def _nest(svg: str, x: float, y: float) -> str:
    """Embed a finished card as a nested <svg>. Its own labels are dropped: the composite carries one title + desc."""
    svg = svg.strip()
    svg = svg.replace('<svg xmlns="http://www.w3.org/2000/svg" ', f'<svg x="{num(x)}" y="{num(y)}" ', 1)
    svg = re.sub(r' role="img" aria-labelledby="[^"]*"', "", svg, count=1)
    return re.sub(r"<title[^>]*>.*?</title><desc[^>]*>.*?</desc>", "", svg, count=1, flags=re.S)


def _compose(name, title, rows, specs, themes, cols) -> Asset:
    """rows: [[column, ...], ...] with column = [member, ...]. cols=1 stacks every member in order (the phone version)."""
    members = [n for row in rows for col in row for n in col]
    if cols == 1:
        rows = [[[n]] for n in members]
    width = cols * W + (cols - 1) * GAP
    alt = " ".join(specs[n][3] for n in members)
    svg = {}
    for mode in MODES:
        y, body = 0.0, []
        for row in rows:
            heights = [[_height(specs[n][4].svg[mode]) for n in col] for col in row]
            rh = max(sum(h) + GAP * (len(h) - 1) for h in heights)
            for c, col in enumerate(row):
                cy = y
                for i, n in enumerate(col):
                    nat = heights[c][i]
                    last = i == len(col) - 1
                    h = nat + (rh - (sum(heights[c]) + GAP * (len(col) - 1))) if last else nat
                    one = specs[n][4].svg[mode] if h <= nat else _make(n, specs[n][0], specs[n][1], themes, min_height=h).svg[mode]
                    body.append(_nest(one, c * (W + GAP), cy))
                    cy += h + GAP
            y += rh + GAP
        h = y - GAP
        svg[mode] = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{num(h)}" viewBox="0 0 {width} {num(h)}" '
                     f'role="img" aria-labelledby="po-{name}-t po-{name}-d"><title id="po-{name}-t">{esc(title, 120)}</title>'
                     f'<desc id="po-{name}-d">{esc(alt, 1500)}</desc>{"".join(body)}</svg>\n')
        problems = safety.validate(svg[mode], safety.LIMITS["wide"])
        if problems:
            raise AssetError(f"{name}.{mode}.svg failed safety checks: {'; '.join(problems)}")
    return Asset(name, title, alt, svg, width=width)


def build_assets(ctx) -> dict:
    """name -> Asset for every visual the current data can honestly support. Missing data => no asset."""
    accent = (ctx.prof.get("theme") or {}).get("accent", DEFAULT_ACCENT)
    themes = {mode: Theme(mode, accent) for mode in MODES}
    out: dict[str, Asset] = {}
    spec = [
        ("profile-signal", signal, features.signal_model(ctx)),
        ("project-map", projectmap, features.project_map_model(ctx)),
        ("language-bubbles", bubbles, features.bubbles_model(ctx)),
        ("contribution-city", city, features.city_model(ctx)),
        ("activity-rhythm", rhythm, features.rhythm_model(ctx)),
        ("code-pet", pet, features.pet_model(ctx)),
        ("activity", bars, models.activity_model(ctx)),
        ("monthly", bars, models.monthly_model(ctx)),
        ("collaboration", cta, features.collaboration_model(ctx)),
    ]
    cards_ = models.card_models(ctx)
    for card in cards_:
        spec.append((card_name(card["slug"]), cards, card))
    groups = dict(GROUPS)
    card_names = [card_name(c["slug"]) for c in cards_]
    if card_names:
        groups["featured"] = ("Featured systems", [[[n] for n in card_names[i:i + 2]] for i in range(0, len(card_names), 2)])
    grouped = {n for _, rows in groups.values() for row in rows for col in row for n in col}
    built: dict[str, tuple] = {}
    for name, mod, model in spec:
        if not model:
            continue
        if name in out:
            raise AssetError(f"duplicate asset name {name!r}")
        a = _make(name, mod, model, themes, emit=name not in grouped)
        out[name] = a
        built[name] = (mod, model, None, a.alt, a)
    for gname, (gtitle, rows) in groups.items():
        rows = [[[n for n in col if n in built] for col in row] for row in rows]
        rows = [[col for col in row if col] for row in rows]
        rows = [row for row in rows if row]
        present = [n for row in rows for col in row for n in col]
        if len(present) < 2:
            for n in present:                      # a lone member is published on its own
                out[n] = Asset(**{**out[n].__dict__, "emit": True})
            continue
        out[gname] = _compose(gname, gtitle, rows, built, themes, 2)
        out[f"{gname}-narrow"] = _compose(f"{gname}-narrow", gtitle, rows, built, themes, 1)
        out[gname] = Asset(**{**out[gname].__dict__, "narrow": f"{gname}-narrow"})
    return out


def files(assets: dict) -> dict:
    """relative path -> SVG text, for every published asset in both modes."""
    return {asset_path(a.name, mode): svg for a in assets.values() if a.emit for mode, svg in a.svg.items()}


def picture(asset: Asset, width: int | None = None, assets: dict | None = None) -> str:
    """Light/dark <picture>. Alt text carries the key data (accessibility + fallback when images do not load).
    A composite adds viewport-width sources: the two-column version on desktop, the stacked version on a phone."""
    alt = html.escape(asset.alt, quote=True)
    if asset.narrow:
        n = asset.narrow
        return (
            "<picture>\n"
            f'  <source media="(prefers-color-scheme: dark) and (min-width: {WIDE_AT}px)" srcset="{asset_path(asset.name, "dark")}">\n'
            f'  <source media="(prefers-color-scheme: light) and (min-width: {WIDE_AT}px)" srcset="{asset_path(asset.name, "light")}">\n'
            f'  <source media="(prefers-color-scheme: dark)" srcset="{asset_path(n, "dark")}">\n'
            f'  <source media="(prefers-color-scheme: light)" srcset="{asset_path(n, "light")}">\n'
            f'  <img alt="{alt}" src="{asset_path(n, "light")}" width="{asset.width}">\n'
            "</picture>"
        )
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="{asset_path(asset.name, "dark")}">\n'
        f'  <source media="(prefers-color-scheme: light)" srcset="{asset_path(asset.name, "light")}">\n'
        f'  <img alt="{alt}" src="{asset_path(asset.name, "light")}" width="{width or asset.width}">\n'
        "</picture>"
    )
