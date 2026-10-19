# ProfileOS — Build Plan

Source of truth: `PROFILEOS_SPEC.md` (v1.0). This plan sequences it into shippable phases.
> **Verification status:** the fetch → analyse → generate workflow has **not been run against a live authenticated GitHub request**
> and is not production-verified. It is covered by fixture-based tests, a mocked HTTP client, and the public-web audit of 2026-10-01.
> The first successful `update-profile` run in `YRB19/YRB19` is the real test.

Legend: ✅ built in this drop · 🟡 scaffolded · ⬜ not started

| Phase | Name | Status |
|---|---|---|
| 0 | Prep: legacy archive, data files drafted | ✅ |
| 1 | Static README redesign (marker shell) | ✅ |
| 2 | Data layer, schemas, validation, cache | ✅ |
| 3 | GitHub fetch + analytics | ✅ (fixture-tested; live run needs your repo Actions) |
| 3b | GitHub audit + data reconciliation (`docs/AUDIT.md`, `data/evidence.yml`) | ✅ |
| 4 | README generators + Actions | ✅ |
| 5 | SVG components (light/dark) | ✅ built, tested, visually reviewed on synthetic data — awaiting your review |
| 6 | Health, CI, releases, event dispatch | ⬜ |
| 7 | Snapshots, timeline, keep-alive | ⬜ |
| 8 | Flagship repo READMEs + social cards | ⬜ |
| 9 | GitHub Pages app | ⬜ |
| 10 | Hardening + docs | ⬜ |

Order of value: 1 → 2 → 3 → 4 → 5 (profile already strong), then 6–10.

---

## Phase 0 — Prep
- Archive current README → `docs/legacy-README.md`.
- Draft `profile.yml`, `projects.yml`, `links.yml`, `stack.yml`, `config.yml`, `categories.yml`, `overrides.yml`, `aliases.yml`, `history.yml`.
- **You:** confirm flagship repos are public, fill verified taglines/stacks, pick accent, confirm stack evidence.
- **Exit:** all YAML passes `validate`.

## Phase 1 — Static redesign
- Hand-written hero, What I Build, Engineering Approach (exact spec text), empty marker blocks, Links.
- Removed: AI-tool table, hard-coded repo count, ASCII header, third-party stat images, quote, badge wall.
- **Exit:** mobile-readable README, zero dynamic content required.

## Phase 2 — Data layer + validation
- JSON Schemas for every YAML file; loader; cross-file checks (aliases, relations, overrides, repo slugs, secrets-in-YAML, public-only URLs, verified⇒tagline+stack, stack evidence, marker integrity).
- Cache envelope, change-only writes, canonical hashing.
- `validate.yml` workflow.
- **Exit:** bad metadata fails with a clear message before anything is written.

## Phase 3 — GitHub fetch + analytics
- GraphQL client (retry/backoff, `retry-after`, rate-limit guard, cursor pagination, public-only re-check), REST w/ ETag.
- Datasets: repos, activity, releases, contributions.
- Analytics: activity score + state mapping, priority index, Recently Shipped, language distribution, categorisation, new-repo discovery, most-active / newest-build.
- Fallback to last valid cache; hide sections with no data.
- **Exit:** `python -m profileos build --dry-run --fixtures` prints every section.

## Phase 4 — README generators + Actions
- Strict marker replacement (fail on missing/duplicate), sanitised Markdown renderers, date-granularity footer.
- `update-profile.yml` (6 h cron + dispatch + path-filtered push), commit only on material change.
- **Exit:** scheduled run updates only marker content; a no-change run makes no commit.

## Phase 5 — SVG components ✅ (pending your review)
Built on the existing validated data model; the README Markdown and every SVG read from one set of view-models
(`generators/models.py`), so they cannot disagree.

| # | Deliverable | Where |
|---|---|---|
| 1 | Light/dark tokens (GitHub-style surfaces, one accent `#3B82F6`); accent auto-nudged to meet 3:1 (graphics) / 4.5:1 (small text) | `generators/svg/tokens.py` |
| 2 | Development Pulse card (2x2 numbers; Releases tile only when release data exists) | `svg/pulse.py` |
| 3 | Activity bars (commits per project, curated order — not ranked by commits) | `svg/bars.py` |
| 4 | Contribution heatmap (one cell per day, 5 steps, legend) | `svg/heatmap.py` |
| 5 | Language distribution bar (labels + percentages, never colour alone) | `svg/langbar.py` |
| 6 | Project cards (every line optional; card collapses, no empty labels) | `svg/cards.py` |
| 7 | Status badges (drawn glyph + label; shown only for evidence-backed statuses) | `svg/badges.py` |
| 8 | OS-series ecosystem graph (uniform nodes; edges only where `relations` are declared) | `svg/ecosystem.py` |
| – | Safety/accessibility gate (no script/external refs/animation; role, title, desc required; 50 KB cap) | `svg/safety.py` |
| – | Asset assembly, `<picture>` light/dark markup, change-only writes, stale-asset cleanup | `generators/visuals.py`, `build.py` |
| – | Visual review page (`profileos preview --fixtures --out DIR`), banner marks synthetic data | `preview.py` |

**Rules enforced (and tested)**
- NetOS and FREYA stay in `projects.yml` with `publish: false`; absent from every public section, card, graph, language total and alt text.
- Status is displayed only when an evidence record (HIGH/MEDIUM/STATED) backs it (today: CompanionOS only). Draft statuses stay internal.
- Stack/tagline/description come only from evidence-backed values; C++, RAG and Linux stay hidden.
- Missing data omits the asset or the line: outage + no cache → only the curated OS-series graph is drawn; no zeros, no placeholders.
- Order of cards and bars is curated priority, never commit counts; no scores, grades or rankings anywhere.
- Mobile: all SVGs share a 432-unit canvas; GitHub scales that to ~328px on a phone, so the minimum font is 16 units (≈12px).
- Profile text (headline, bio, What I Build, Engineering Approach, Exploring/Learning, links) is unchanged; Planning Next is empty; GitHub is the only link.
- The client is read-only (tested): no mutations, so the profile pins are never modified.

**Review evidence**
- Rendered all 9 assets (pulse, activity, heatmap, languages, os-series, 4 cards) in Chromium at a 360px viewport, light and dark, at the
  328px content width GitHub uses on phones: no clipping, no horizontal scroll. This used **synthetic fixture data** — real numbers appear only after a live run.
- Known trade-off: at the 16-unit font floor the heatmap skips some month labels where they would collide.

**Not done on purpose:** Phase 6, the Pages app, and any change to GitHub pins. `assets/generated/` is empty until a real run produces assets
(synthetic assets are never committed to the profile).

## Phase 6 — Health, CI, releases, events
Deployment + CI fetchers, DNS-level SSRF guard, release tracker, optional `notify-profile.yml`.

## Phase 7 — Snapshots & timeline
Daily/monthly rollups, timeline (no invented dates), keep-alive.

## Phase 8 — Flagship READMEs & social cards
§13 templates per repo; PNG cards via resvg/cairosvg; NetOS/FREYA only from verified info.

## Phase 9 — Pages app
Vite + React + TS + Tailwind; dashboard, explorer, detail, activity, ecosystem, timeline, compare; `pages.yml`.

## Phase 10 — Hardening
Failure-injection tests, `README_DEV.md`, Dependabot, SHA-pinned actions.

---

## Deliberate additions / interpretations of the spec
1. `LINKS` marker added (spec says links are "rendered once at build").
2. `shipped_window_days` (default 60) added so stale releases don't show as "recent".
3. `show_zero_stars` display flag added (Appendix A #10).
4. Language hints in `categories.yml → language_map` (Rust/C++ → systems) for rule 5.
5. README-keyword categorisation (rule 4) deferred: needs an extra API call per repo.
6. Footer date = date the *data last changed* (not run date) so stamp-only commits never happen.
7. Discovery state in `data/cache/discovery.json` (first-seen dates) to implement the repo-list diff.
8. Priority-index components that need extra API calls (docs/tests/deploy) default to neutral 0.5 until Phase 6.
9. "Meaningful commit" uses `changedFilesIfAvailable` > 0 plus message/bot/merge rules; doc-only detection deferred.
10. Per-dataset TTL skipping (§15.2) is not implemented yet: every run fetches (<25 calls). Revisit in Phase 10.
11. Actions are referenced by version tag; SHA-pinning is a Phase 10 task.

12. `data/evidence.yml` added: every published tagline/description/demo/docs/stack value needs a HIGH/MEDIUM/STATED record; LOW is recorded, never published (enforced by `validate`).
13. Manual `status` is displayed only when evidence backs it (CompanionOS: README says active development); other statuses stay internal.
14. `YRB19/YRB19` added to `config.exclude_repos` so the profile repo's own commits never read as "building".
15. `publish: false` (projects.yml, schema + validator aware) keeps a project in internal metadata only; one switch controls every public output.
16. Heatmap labels, card meta lines and the ecosystem legend degrade by dropping items (never by shrinking text below 16 units).

## Open inputs (from spec Appendix A)
Accent colour · verified taglines/stacks (4 flagships) · NetOS/FREYA facts · PersonaOS visibility · stack evidence (C++, Redis, Linux, SQL…) · personal links · Pages hosting option · PAT dispatch yes/no.
