"""Static visual review page for the generated SVG assets (not part of the profile; for human review only)."""
import html
from pathlib import Path

from .generators import visuals

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ProfileOS visual review</title>
<style>
:root{{color-scheme:light dark}}
body{{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;background:#f6f8fa;color:#1f2328}}
@media(prefers-color-scheme:dark){{body{{background:#010409;color:#e6edf3}}}}
main{{max-width:1040px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-size:22px;margin:0 0 8px}} h2{{font-size:17px;margin:40px 0 4px}} p{{margin:6px 0}}
.note{{border:1px solid #d29922;background:rgba(210,153,34,.12);padding:10px 14px;border-radius:8px}}
.meta{{font-size:13px;opacity:.75}}
.row{{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px}}
.frame{{padding:0;border-radius:10px;box-sizing:border-box;max-width:100%;overflow:hidden}}
.frame.light{{background:#fff}} .frame.dark{{background:#0d1117}}
.phone{{width:328px;max-width:100%}} .desk{{width:432px;max-width:100%}}
img{{display:block;max-width:100%;height:auto}}
code{{font-size:12px}}
</style></head><body><main>
<h1>ProfileOS — Phase 5 visual review</h1>
<p class="note"><strong>{banner}</strong></p>
<p class="meta">Each asset is shown at a 360px phone viewport (328px content width, GitHub's mobile README width) and at its natural 432px width, on GitHub's light and dark page backgrounds.</p>
{sections}
</main></body></html>
"""


def write_preview(assets: dict, out_dir: Path, banner: str) -> Path:
    """assets: name -> Asset (from visuals.build_assets). Returns the path of index.html."""
    out_dir = Path(out_dir)
    svg_dir = out_dir / "assets"
    svg_dir.mkdir(parents=True, exist_ok=True)
    for a in assets.values():
        for mode, svg in a.svg.items():
            (svg_dir / f"{a.name}.{mode}.svg").write_text(svg, encoding="utf-8", newline="\n")

    def frames(a, cls, width_cls):
        return "".join(
            f'<div class="frame {mode}"><div class="{width_cls}"><img src="assets/{a.name}.{mode}.svg" alt="{html.escape(a.alt, quote=True)}"></div></div>'
            for mode in ("light", "dark")
        )

    parts = []
    for a in assets.values():
        parts.append(
            f"<h2>{html.escape(a.title)}</h2><p class='meta'><code>{visuals.asset_path(a.name, 'light')}</code> · "
            f"alt: {html.escape(a.alt)}</p>"
            f'<div class="row">{frames(a, "phone", "phone")}</div>'
            f'<div class="row">{frames(a, "desk", "desk")}</div>'
        )
    page = PAGE.format(banner=html.escape(banner), sections="\n".join(parts))
    index = out_dir / "index.html"
    index.write_text(page, encoding="utf-8")
    return index
