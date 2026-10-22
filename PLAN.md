# ProfileOS — Build Plan

Source of truth: `PROFILEOS_SPEC.md` (v1.0). This plan sequences it into shippable phases.
> **Verification status (updated 2026-10-22):**
> * **Live on `main` (observed in the repository):** the `update-profile` workflow runs on schedule and commits as `profileos[bot]`; generated README
>   blocks, 18 SVG assets and `data/cache/` hold real data. Phase 6 **CI status was fetched live**: `data/cache/ci.json` (committed by the bot,
>   `auth: github-token`) holds real Actions results. The Actions logs and badge are not readable from the build sandbox, so run-level
>   details (duration, exact permissions used) are not independently confirmed here.
> * **Phase 6 deployment health, event dispatch and the release tracker are not live-verified** (no project has `health_check` enabled; dispatch is
>   off; no repository has published releases yet).
> * **Phase 7 is fixture-tested only. Snapshot scheduling has not been validated on GitHub Actions**: no real snapshot exists yet; the first one
>   is created by the first `update-profile` run after Phase 7 is merged.

Legend: ✅ built in this drop · 🟡 scaffolded · ⬜ not started

| Phase | Name | Status |
|---|---|---|
| 0 | Prep: legacy archive, data files drafted | ✅ |
| 1 | Static README redesign (marker shell) | ✅ |
| 2 | Data layer, schemas, validation, cache | ✅ |
| 3 | GitHub fetch + analytics | ✅ (fixture-tested; live run needs your repo Actions) |
| 3b | GitHub audit + data reconciliation (`docs/AUDIT.md`, `data/evidence.yml`) | ✅ |
| 4 | README generators + Actions | ✅ |
| 5 | SVG components (light/dark) | ✅ reviewed; live `update-profile` run generated all 18 assets on `main` |
| 6 | Health, CI, releases, event dispatch | ✅ merged; CI fetch observed live (`ci.json`); health/dispatch/releases not live-verified |
| 7 | Snapshots, rollups, timeline, retention | ✅ built + fixture-tested; **not live-verified**; awaiting your review |
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

## Phase 5 — SVG components ✅
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

**Live result:** the first real `update-profile` runs produced `assets/generated/*.svg` on `main` (bot commits above). Synthetic preview assets were never committed.

### Reconciliation with `main` and production-README fixes (before Phase 6)
Compared the live `main` against the delivered package: code, tests, data files and workflows are identical; only the generated README blocks,
`data/cache/` and `assets/generated/` differ (expected). Two issues in the production README were fixed without touching the visual design:

| Issue | Cause | Fix |
|---|---|---|
| Generic "Recently Shipped" (`[update]`, `[release]` links) | entries rendered only the kind | entries now show what shipped: release tag, merged-PR title or commit headline; generic headlines (`update`, `fix`, `Initial commit`, `Update README.md`...) are dropped, never shown |
| Unclear metric scope | Pulse used GitHub's whole-account totals (including the profile repo and repos not shown) | commits/PRs/repos in Pulse are now counted from **public, non-excluded repos shown on the profile** (private repos never named or counted); every card states its scope in its footnote; heatmap says it is the full GitHub calendar; caches written before this fix make no scope claim |
| Possible self-feeding commits | the profile repo's own bot commits changed its cached activity, which changed the cache, which caused another commit | excluded/internal repos (profile repo, `publish: false`) are scrubbed from `repos`/`activity`/`releases` before caching (one shared rule: `models.excluded_repos`) |

Known, inherent: the contribution calendar changes daily, so there is at most one data commit per day.
NetOS and FREYA are now public and their evidence is recorded (`data/evidence.yml`), but they stay `publish: false` until you flip it.

## Phase 6 — Health, CI, releases, events ✅ (mock-tested; not live-verified; pending your review)
Principle: *automate factual status, preserve uncertainty, never look healthier than the evidence.*

| # | Deliverable | Where |
|---|---|---|
| 1 | CI status: latest run per workflow on the default branch, aggregated worst-first; states `passing/failing/in_progress/queued/cancelled/unknown/not_configured`; stale or ambiguous => `unknown` (not drawn) | `status/ci.py` |
| 2 | Least-privilege auth: optional read-only `PROFILEOS_STATUS_TOKEN` -> `GITHUB_TOKEN` -> public data; broad classic tokens refused; only ever steps down in privilege; GET only | `status/ci.py`, `github/client.py` |
| 3 | Deployment health (opt-in per project, needs flag + URL + `verified` + evidence): states `online/offline/degraded/unknown/not_configured` | `status/health.py` |
| 4 | SSRF guard: URL policy, IPv4/IPv6 + embedded-IPv4 (mapped, NAT64, 6to4, Teredo) rejection, double DNS resolution, pinned-IP connect, peer check, per-hop redirect validation, bounded time/bytes, no credentials sent | `status/netguard.py`, `status/health.py` |
| 5 | Honest health evidence: timeouts/blocks/401-403-429 => `unknown`; `offline` only after refusal/NXDOMAIN in N consecutive runs | `status/health.py` |
| 6 | Release tracker (`RELEASES` marker; heading inside the block so it vanishes when there are no releases): latest published non-draft per project, link, date, pre-release flag; reuses the existing releases dataset (no extra API calls) | `models.release_rows`, `sections.releases` |
| 7 | Cards show CI (glyph + word + run date) and health; new `GREEN`/`AMBER` tokens with computed contrast; red only for failing/offline | `svg/cards.py`, `svg/tokens.py` |
| 8 | Caching: per-record `checked_at`; change-only writes ignore it, with at most one timestamp-only refresh per day; stale cache hidden after `stale_after_h` (72 h) | `storage/cache.py`, `build.py` |
| 9 | Optional event dispatch: `templates/notify-profile.yml` (inert unless variable + secret exist, `permissions: {}`, no fallback credential); config + validation | `templates/`, `docs/EVENT_DISPATCH.md`, `validate.py` |
| 10 | Docs: tokens, scopes, secrets, safety | `docs/PERMISSIONS.md`, `docs/EVENT_DISPATCH.md` |

**Defaults you control (nothing health-related is enabled yet):** no project has `health_check: true`; `event_dispatch.enabled: false`.
To probe RepoHealth: set `deployment: {health_url: "https://repohealth.vercel.app", health_check: true}`, `verified: true`, and add a `health_url`
evidence record (the README "Live demo" link is MEDIUM evidence) — `profileos validate` will tell you what is missing.

**Verification:** fixtures + mocked transports only (see `README_DEV.md`). No live GitHub CI fetch and no live deployment probe was performed.

**Limitations:** unauthenticated CI reads are rate-limited (60/h per IP, shared on hosted runners) and then fall back to cache; the
release query reads the 10 most recently *created* releases per repo (the latest *published* of those is shown); `offline` needs two runs;
the dispatch token needs `Contents: write` on the profile repo (GitHub's minimum for that endpoint); a fine-grained status token's scopes cannot be
inspected by code.

## Phase 7 — Snapshots, rollups, timeline, retention ✅ (fixture-tested; not live-verified; pending your review)
Principle: *preserve history faithfully, define every metric clearly, never manufacture historical facts.* Formats and counting rules:
`docs/SNAPSHOTS.md`; retention, scheduling and the keep-alive decision: `docs/RETENTION.md`.

| # | Deliverable | Where |
|---|---|---|
| 1 | Versioned, schema-validated daily record (`snapshots/daily/<YYYY>/<date>.json`): closed-day commits/PRs/releases, rolling windows, languages, per-project summaries, repo list, scope + counting rules in every record | `history/snapshot.py`, `schemas/snapshot.schema.json` |
| 2 | Explicit timezone policy (`snapshots.timezone`, default UTC); a snapshot dated D describes the closed day D-1 as inclusive UTC instants (DST-correct) | `history/snapshot.py` |
| 3 | Create-only, idempotent daily writes; one per local day; validation first; atomic; past records never regenerated | `history/snapshot.py`, `history/run.py` |
| 4 | Failure policy: stale repo data, API failure, unreadable repo or malformed count => **no snapshot (a gap)**; never zeros; synthetic runs never recorded | `history/run.py`, `github/fetch.fetch_day_commits` |
| 5 | Monthly rollups from stored dailies only: sums of closed days, unique active repos, month-end language reading; coverage + missing days; `lower_bound`/`null` instead of invented precision; older months frozen, drift warned | `history/rollup.py`, `schemas/monthly.schema.json` |
| 6 | Append-only timeline of verified events (repo created, release published, sourced milestone, first observed) with separate date kinds; no inferred dates; shown only for currently published projects | `history/timeline.py`, `schemas/timeline.schema.json`, `data/history.yml` `milestones` |
| 7 | README: `Commits by month` chart (appears once 2 months exist, partial months starred) reusing Phase 5 tokens/safety/themes; concise `TIMELINE` block (new marker) | `generators/models.py`, `svg/bars.py`, `sections.py` |
| 8 | Integrity checks in `profileos validate`: schema, filenames, duplicates, committed synthetic records, credential-looking strings, rollup drift, leftover temp files | `history/run.verify`, `validate.py` |
| 9 | Automation: existing workflow extended (it already commits `snapshots/`); no new scheduler; no keep-alive (documented decision) | `.github/workflows/update-profile.yml`, `docs/RETENTION.md` |

**Rules enforced (and tested):** NetOS/FREYA (and any `publish: false` project, the profile repo, private repos) never appear in snapshots, rollups,
the timeline view or charts; `first_observed` is never used as a creation date; a project published later gets a `first_observed` event dated
that day, never a backdated one; a no-change run writes nothing; a failed render leaves `snapshots/` untouched; every chart states its scope.

**Not drawn on purpose:** language-over-time and per-project trend charts (stored in rollups; no data yet; reserved for the Pages phase).
**Limitations:** history starts at the first real run (no backfill: closed-day counts for past days would have to be re-derived and are not
recorded as history); the PR/release counts need fewer than 10 recent items per repo or they are `null`; "committer date" can differ from push
date; a rewritten (force-pushed) default branch changes what the API reports but never what was already recorded; the daily snapshot is taken by the
first run after local midnight, so its `taken_at` can be up to ~6 h after midnight; GitHub's rule for keeping scheduled workflows alive is not verified.

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
8. Priority-index components that need extra API calls (docs/tests/deploy) still default to neutral 0.5; Phase 6 adds status display, not scoring.
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
