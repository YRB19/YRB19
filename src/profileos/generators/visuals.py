"""Assemble SVG assets from the shared view-models and build the README <picture> markup."""
import html
import re
from dataclasses import dataclass

from . import models
from .svg import bars, cards, ecosystem, heatmap, langbar, pulse, safety
from .svg.base import W
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


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "x"


def card_name(slug: str) -> str:
    return f"card-{slugify(slug)}"


def asset_path(name: str, mode: str) -> str:
    return f"{ASSET_DIR}/{name}.{mode}.svg"


def _make(name, mod, model, themes) -> Asset:
    title = mod.title(model) if hasattr(mod, "title") else mod.TITLE
    alt = mod.alt(model)
    meta = {"name": name, "title": title, "alt": alt}
    svg = {mode: mod.render(model, themes[mode], meta) for mode in MODES}
    for mode, text in svg.items():
        problems = safety.validate(text)
        if problems:
            raise AssetError(f"{name}.{mode}.svg failed safety checks: {'; '.join(problems)}")
    return Asset(name, title, alt, svg)


def build_assets(ctx) -> dict:
    """name -> Asset for every visual the current data can honestly support. Missing data => no asset."""
    accent = (ctx.prof.get("theme") or {}).get("accent", DEFAULT_ACCENT)
    themes = {mode: Theme(mode, accent) for mode in MODES}
    out: dict[str, Asset] = {}
    spec = [
        ("pulse", pulse, models.pulse_model(ctx)),
        ("activity", bars, models.activity_model(ctx)),
        ("heatmap", heatmap, models.heatmap_model(ctx)),
        ("languages", langbar, models.language_model(ctx)),
        ("os-series", ecosystem, models.ecosystem_model(ctx)),
    ]
    for card in models.card_models(ctx):
        spec.append((card_name(card["slug"]), cards, card))
    for name, mod, model in spec:
        if not model:
            continue
        if name in out:
            raise AssetError(f"duplicate asset name {name!r}")
        out[name] = _make(name, mod, model, themes)
    return out


def files(assets: dict) -> dict:
    """relative path -> SVG text, for every asset in both modes."""
    return {asset_path(a.name, mode): svg for a in assets.values() for mode, svg in a.svg.items()}


def picture(asset: Asset, width: int = W) -> str:
    """Light/dark <picture>. Alt text carries the key data (accessibility + fallback when images do not load)."""
    alt = html.escape(asset.alt, quote=True)
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="{asset_path(asset.name, "dark")}">\n'
        f'  <source media="(prefers-color-scheme: light)" srcset="{asset_path(asset.name, "light")}">\n'
        f'  <img alt="{alt}" src="{asset_path(asset.name, "light")}" width="{width}">\n'
        "</picture>"
    )
