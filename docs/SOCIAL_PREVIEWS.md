# Repository social previews

Each flagship has a 1280×640 PNG at `assets/social-preview.png` with its SVG source beside it (`flagships/<Repo>/assets/`).
Regenerate all four with `pip install cairosvg && python scripts/build_social_cards.py <out-dir>`; the card text and technologies are defined,
with their evidence files, in `CARDS` in that script.

**Committing the PNG does not set the repository's social preview.** GitHub only uses an image uploaded in the repository settings. For each repo:

1. Open `https://github.com/YRB19/<Repo>/settings`.
2. Under **Social preview**, choose **Edit → Upload an image** and select `assets/social-preview.png`.
3. Check the preview with a link unfurl (paste the repo URL in a chat or the Twitter/LinkedIn card validators).

This has **not** been done for any repository; nothing in ProfileOS claims it is enabled.
GitHub recommends at least 640×320 and under 1 MB; the cards are 1280×640.
