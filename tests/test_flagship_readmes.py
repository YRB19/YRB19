from pathlib import Path

from profileos.readme_check import check_all, check_repo

ROOT = Path(__file__).resolve().parents[1] / "flagships"
REPOS = ("UsageOS", "ResearchOS", "ClipOS", "CompanionOS")


def test_all_four_flagships_are_staged():
    assert sorted(p.name for p in ROOT.iterdir() if p.is_dir()) == sorted(REPOS)


def test_staged_readmes_pass_conventions():
    assert check_all(ROOT) == []


def test_checker_catches_each_failure_class(tmp_path):
    d = tmp_path / "ResearchOS"
    (d / "assets").mkdir(parents=True)
    (d / "README.md").write_text(
        "![](x.png)\n[a](missing.md)\nclone your-username/x\n/home/bob/x nvapi-ABCDEFGHIJKL\n"
        "![b](https://img.shields.io/badge/build-passing-green)\n![l](https://img.shields.io/badge/license-MIT-blue)\n"
        "Telegram-first.\n```mermaid\npie\n```\n", encoding="utf-8")
    msgs = " | ".join(check_repo(d))
    for needle in ("alt text", "broken local", "placeholder", "local machine", "secret", "static CI",
                   "MIT claim", "Mermaid", "social preview", "Telegram"):
        assert needle in msgs, needle


def test_placeholders_inside_code_fences_are_allowed(tmp_path):
    d = tmp_path / "X"
    (d / "assets").mkdir(parents=True)
    (d / "README.md").write_text("```bash\ngit clone your-username\n```\n", encoding="utf-8")
    assert not any("placeholder" in m for m in check_repo(d))


def test_card_generator_is_deterministic_and_verified(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("cards", Path(__file__).resolve().parents[1] / "scripts" / "build_social_cards.py")
    mod = importlib.util.module_from_spec(spec); import sys; sys.modules["cards"] = mod; spec.loader.exec_module(mod)
    for c in mod.CARDS:
        assert 2 <= len(c.tech) <= 4 and c.evidence
        svg = mod.render_svg(c)
        assert "#3B82F6" in svg and c.repo in svg
        assert (ROOT / c.repo / "assets" / "social-preview.svg").read_text(encoding="utf-8") == svg
