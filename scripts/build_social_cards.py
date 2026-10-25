#!/usr/bin/env python3
"""Render the four flagship repository social-preview cards (1280x640).

Writes ``<out>/<Repo>/assets/social-preview.svg`` and ``.png`` for each repo.
Everything printed on a card comes from CARDS below; each technology is tied to
the manifest/code that proves it so the card cannot claim more than the repo.

Usage:  python scripts/build_social_cards.py OUT_DIR

Rendering uses CairoSVG (pip install cairosvg). The foundation is monochrome;
the single accent is #3B82F6. Committing the PNG does NOT set the GitHub social
preview - that is a manual step, see docs/SOCIAL_PREVIEWS.md.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from html import escape
from pathlib import Path

W, H = 1280, 640
ACCENT = "#3B82F6"
BG = "#0A0A0A"
FG = "#FAFAFA"
MUTED = "#A3A3A3"
LINE = "#2A2A2A"
FONT = "Inter, 'Helvetica Neue', Arial, sans-serif"
MONO = "'DejaVu Sans Mono', monospace"


@dataclass(frozen=True)
class Card:
    repo: str
    description: str          # one verified sentence
    tech: tuple[str, ...]     # 2-4 verified technologies
    evidence: tuple[str, ...]  # where each claim is verifiable (not rendered)
    motif: str


CARDS: tuple[Card, ...] = (
    Card(
        "UsageOS",
        "Self-hosted tracker for Claude.ai usage limits across multiple accounts.",
        ("FastAPI", "PostgreSQL", "React", "Browser extension"),
        ("backend/requirements.txt", "docker-compose.yml postgres:16-alpine",
         "frontend/package.json", "extension/manifest.json manifest_version 3"),
        "bars",
    ),
    Card(
        "ResearchOS",
        "Research-job API: parallel specialist agents, an evidence loop, PDF reports.",
        ("Python", "FastAPI", "SQLite", "NVIDIA NIM"),
        ("requirements.txt", "app/db.py", "app/llm.py", "app/agents.py", "app/export.py"),
        "loop",
    ),
    Card(
        "ClipOS",
        "Turns long videos into short vertical clips with generated captions.",
        ("FastAPI", "faster-whisper", "OpenCV", "Redis RQ"),
        ("clipos-backend/requirements.txt", "app/core/pipeline.py", "app/core/reframe.py"),
        "crop",
    ),
    Card(
        "CompanionOS",
        "Desktop Formula 1 timing and session tracker.",
        ("Tauri", "React", "TypeScript", "Rust"),
        ("package.json", "src-tauri/Cargo.toml", "src/router.tsx"),
        "track",
    ),
)


def _motif(kind: str) -> str:
    """Abstract, project-specific shapes in the right-hand area (x 760-1220)."""
    a = ACCENT
    if kind == "bars":  # three usage bars with a reset tick
        rows = [(190, 0.72), (250, 0.38), (310, 0.9)]
        out = []
        for y, f in rows:
            out.append(f'<rect x="780" y="{y}" width="400" height="14" rx="7" fill="{LINE}"/>')
            out.append(f'<rect x="780" y="{y}" width="{int(400 * f)}" height="14" rx="7" fill="{a}"/>')
            out.append(f'<rect x="1180" y="{y - 8}" width="2" height="30" fill="{MUTED}"/>')
        return "".join(out)
    if kind == "loop":  # evidence nodes converging on a ring with a feedback arc
        nodes = [(800, 190), (800, 270), (800, 350), (800, 430)]
        out = [f'<circle cx="1050" cy="310" r="78" fill="none" stroke="{a}" stroke-width="6"/>',
               f'<path d="M1128 310 a78 78 0 0 1 -30 62" fill="none" stroke="{FG}" stroke-width="6"/>']
        for x, y in nodes:
            out.append(f'<circle cx="{x}" cy="{y}" r="10" fill="{MUTED}"/>')
            out.append(f'<line x1="{x + 10}" y1="{y}" x2="972" y2="310" stroke="{LINE}" stroke-width="3"/>')
        out.append(f'<circle cx="1050" cy="310" r="16" fill="{a}"/>')
        return "".join(out)
    if kind == "crop":  # landscape strip with a highlighted 9:16 window
        return (f'<rect x="770" y="230" width="420" height="236" rx="8" fill="none" stroke="{MUTED}" stroke-width="3"/>'
                f'<rect x="920" y="196" width="133" height="304" rx="8" fill="none" stroke="{a}" stroke-width="6"/>'
                f'<line x1="770" y1="348" x2="920" y2="348" stroke="{LINE}" stroke-width="3" stroke-dasharray="8 8"/>'
                f'<line x1="1053" y1="348" x2="1190" y2="348" stroke="{LINE}" stroke-width="3" stroke-dasharray="8 8"/>')
    if kind == "track":  # abstract closed circuit with three sector marks and a position dot
        d = "M820 360 C780 260 860 190 960 200 C1060 210 1100 150 1160 220 C1220 290 1150 400 1050 410 C960 418 900 470 840 430 C815 412 825 380 820 360 Z"
        return (f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="22" stroke-linejoin="round"/>'
                f'<path d="{d}" fill="none" stroke="{MUTED}" stroke-width="3" stroke-linejoin="round"/>'
                f'<circle cx="960" cy="200" r="11" fill="{a}"/>'
                f'<rect x="1156" y="204" width="3" height="34" fill="{FG}" transform="rotate(30 1158 220)"/>')
    raise ValueError(kind)


def _wrap(text: str, limit: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > limit:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


def render_svg(card: Card) -> str:
    title_size = 92
    desc_lines = _wrap(card.description, 34)
    desc = "".join(
        f'<tspan x="80" dy="{0 if i == 0 else 44}">{escape(line)}</tspan>'
        for i, line in enumerate(desc_lines)
    )
    chips, x = [], 80
    for t in card.tech:
        w = 24 + int(len(t) * 14.5)
        chips.append(
            f'<rect x="{x}" y="520" width="{w}" height="44" rx="22" fill="none" stroke="{MUTED}" stroke-width="2"/>'
            f'<text x="{x + w / 2}" y="549" text-anchor="middle" font-family="{FONT}" font-size="22" fill="{FG}">{escape(t)}</text>'
        )
        x += w + 14
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
        f'aria-labelledby="t d"><title id="t">{escape(card.repo)}</title>'
        f'<desc id="d">{escape(card.description)} Built with {escape(", ".join(card.tech))}.</desc>'
        f'<rect width="{W}" height="{H}" fill="{BG}"/>'
        f'<rect x="0" y="0" width="12" height="{H}" fill="{ACCENT}"/>'
        f'<text x="80" y="150" font-family="{FONT}" font-size="{title_size}" font-weight="700" fill="{FG}">{escape(card.repo)}</text>'
        f'<rect x="80" y="178" width="96" height="6" fill="{ACCENT}"/>'
        f'<text x="80" y="250" font-family="{FONT}" font-size="34" fill="{MUTED}">{desc}</text>'
        f'{_motif(card.motif)}'
        f'{"".join(chips)}'
        f'<text x="{W - 80}" y="{H - 28}" text-anchor="end" font-family="{MONO}" font-size="20" fill="{MUTED}">github.com/YRB19/{escape(card.repo)}</text>'
        f'</svg>\n'
    )


def build(out: Path) -> list[Path]:
    import cairosvg  # imported lazily so the module is importable without it

    written: list[Path] = []
    for card in CARDS:
        folder = out / card.repo / "assets"
        folder.mkdir(parents=True, exist_ok=True)
        svg = render_svg(card)
        svg_path, png_path = folder / "social-preview.svg", folder / "social-preview.png"
        svg_path.write_text(svg, encoding="utf-8")
        cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png_path), output_width=W, output_height=H)
        written += [svg_path, png_path]
    return written


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    for p in build(Path(sys.argv[1])):
        print(p)
