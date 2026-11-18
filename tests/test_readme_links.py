"""Link rows must survive GitHub's Markdown: Markdown on the same line as an HTML tag is not parsed (it shows as raw text)."""
import datetime as dt
import re

from profileos.build import build
from profileos.github.fixtures import FixtureClient
from profileos.sanitize import link

NOW = dt.datetime(2026, 11, 14, 12, tzinfo=dt.timezone.utc)


def test_no_markdown_shares_a_line_with_an_html_block_tag(repo_copy):
    res = build(repo_copy, client=FixtureClient(NOW), now=NOW, dry_run=True)
    for sid, block in res.blocks.items():
        for line in block.splitlines():
            if re.match(r"\s*</?(div|table|tr|td)\b", line):
                assert not re.search(r"\[[^\]]+\]\([^)]+\)|\*\*", line), (sid, line)


def test_link_rows_are_markdown_inside_the_centered_div(repo_copy):
    res = build(repo_copy, client=FixtureClient(NOW), now=NOW, dry_run=True)
    for sid in ("SELECTED_SYSTEMS", "PROJECT_MAP", "CTA"):
        block = res.blocks[sid]
        assert re.search(r"</picture>\n\n\*\*\[[^\n]+\n\n</div>", block), sid
    assert "**[Email](mailto:" in res.blocks["CTA"]


def test_mailto_links_are_plain_addresses_only():
    assert link("mailto:a.b+c@example.com") == "mailto:a.b+c@example.com"
    for bad in ("mailto:a@b.co?subject=x", "mailto:a@b", "mailto:a b@x.com", "javascript:alert(1)", "mailto:<x>@y.com"):
        assert link(bad) is None, bad
