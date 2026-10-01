# ProfileOS — Build Plan

Source of truth: `PROFILEOS_SPEC.md` (v1.0). This plan sequences it into shippable phases.
Legend: ✅ built in this drop · 🟡 scaffolded · ⬜ not started

| Phase | Name | Status |
|---|---|---|
| 0 | Prep: legacy archive, data files drafted | ✅ |
| 1 | Static README redesign (marker shell) | ✅ |
| 2 | Data layer, schemas, validation, cache | ✅ |
| 3 | GitHub fetch + analytics | ✅ (fixture-tested; live run needs your repo Actions) |
| 3b | GitHub audit + data reconciliation (`docs/AUDIT.md`, `data/evidence.yml`) | ✅ |
| 4 | README generators + Actions | ✅ |
| 5 | SVG components (light/dark) | ⬜ |
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

## Phase 5 — SVG components
Tokens, light/dark pairs, Pulse, ActivityBar, Heatmap, StackBar, ProjectCard, StatusBadge, EcosystemGraph; SVG safety tests; readable at 360 px.

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

## Open inputs (from spec Appendix A)
Accent colour · verified taglines/stacks (4 flagships) · NetOS/FREYA facts · PersonaOS visibility · stack evidence (C++, Redis, Linux, SQL…) · personal links · Pages hosting option · PAT dispatch yes/no.
