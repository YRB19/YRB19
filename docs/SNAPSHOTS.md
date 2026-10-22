# Historical snapshots, rollups and timeline (Phase 7)

Principle: **preserve history faithfully, define every metric clearly, never manufacture historical facts.**

Everything lives under `snapshots/` and is written by the existing `update-profile` workflow. Nothing here is a quality
measure: counts are activity signals.

```
snapshots/
  daily/<YYYY>/<YYYY-MM-DD>.json   one record per local day, create-only
  monthly/<YYYY-MM>.json           derived from the daily records only
  timeline.json                    append-only list of verified events
```

All three are versioned (`"schema": 1`) and validated against `src/profileos/schemas/{snapshot,monthly,timeline}.schema.json`
before they are written and again by `python -m profileos validate`.

## Time policy

* `snapshots.timezone` (default `UTC`, in `data/config.yml`) defines the day. It is an IANA name; an unknown name is an error,
  never a silent fallback.
* A snapshot **dated D** is the first successful run on local day D. It describes the **closed day D-1** (the complete previous
  local day), expressed as inclusive UTC instants `[start, end]`. DST days have their real length (23/25 h).
* Closed days never overlap, so they can be summed. Rolling windows overlap and can not.

## Daily record

| Field | Meaning |
| --- | --- |
| `date`, `timezone`, `taken_at` | local snapshot date, its timezone, and the UTC instant it was taken |
| `closed_day` | `{date, start, end}` the window every `closed_day` count refers to |
| `source`, `scope` | where the data came from and `scope.rules`: the counting rule for every metric (stored in every record) |
| `repos` | `included` (count), `names`, `active_on_closed_day` (>= 1 commit that day) |
| `totals.closed_day` | `commits`, `merged_prs`, `releases` for the closed day |
| `totals.rolling` | `d7`, `d30`, `d90` default-branch commits ending at `taken_at` (point-in-time readings) |
| `languages` | share of code bytes as drawn on the profile (point-in-time) |
| `projects.<slug>` | per published project: closed-day counts, rolling counts, repo creation date, last push date |

**Counting rules.** Default-branch commits by committer date, any author. `merged_prs` / `releases` are `null` when the API
returned a full page of recent items (10), meaning a complete count cannot be established; `null` is never turned into `0`.
Covered repositories: public, non-fork repositories excluding the profile repository and any project with `publish: false`.
Private repositories are never read into a snapshot, so private names and activity cannot appear. No tokens or API payloads
are stored; the record is a small normalised summary.

**Write rules.** Written only when (a) none exists for today, (b) the repository list was freshly fetched in this run, (c) every
closed-day count could be read, and (d) the record validates. Otherwise **no snapshot is written** (a gap). Past snapshots are
never regenerated or modified. Fixture/synthetic runs are never recorded, and `validate` fails if a record marked `synthetic`
is found.

## Monthly rollup

Derived **only** from stored daily records; a closed day belongs to the month it falls in.

| Metric | Statistic |
| --- | --- |
| `commits`, `merged_prs`, `releases` | **sum** of closed-day counts over the covered days (no double counting) |
| `active_repos` | **unique** repositories with >= 1 commit on a covered day (a union, not a sum) |
| `languages` | **month-end reading**: the last daily snapshot whose closed day is in the month, with its date |
| rolling d7/d30/d90 | never aggregated |

`coverage` lists the covered and missing days and `complete`. Gaps are reported, never filled or extrapolated.
`lower_bound: true` marks a sum that omits days whose PR/release count was unknown; if nothing was known the value is `null`.
The two most recent months are refreshed (change-only); older months are frozen. `validate` warns if a stored rollup no longer
matches a recomputation (for example after a late gap-fill).

## Timeline

Each event keeps its own source and date, and four dates are never substituted for one another:

| Type | Date comes from | `date_kind` |
| --- | --- | --- |
| `repository_created` | GitHub `createdAt` (not a launch date) | `repository_created_at` |
| `release_published` | GitHub `publishedAt` of a non-draft release | `release_published_at` |
| `milestone` | an explicit entry in `data/history.yml` (`project`, `date`, `title`, `source`, optional `url`) | `milestone_date` |
| `first_observed` | the day ProfileOS first listed a project, **only** for projects that appeared after the timeline was seeded | `first_observed_by_profileos` |

Nothing is inferred from commits. "Significant merged pull request" is deliberately not an event type: significance can not be
established from API data without ranking work. Events are append-only (the API's release window rolls forward; the timeline must
not). The README shows the newest `snapshots.timeline_max_items` events for **currently published** projects only; the stored
file is a faithful record, and publishing a project later adds it with a `first_observed` date, never a backdated one.

Milestone example (`data/history.yml`):

```yaml
milestones:
  - { project: UsageOS, date: 2026-06-01, title: "Public beta", source: "docs/CHANGELOG.md", url: "https://github.com/YRB19/UsageOS/blob/main/docs/CHANGELOG.md" }
```

## Public README and charts

The README gets one compact chart ("Commits by month", only once two months have data; partial months are starred) and a short
timeline block. Language-over-time and per-project trends are stored in the rollups but **not drawn**: they need months of data
and are reserved for the later Pages phase.

## Corrections and migrations

Records are never edited by the code. A correction is a deliberate, reviewed commit that edits or deletes the file by hand and
says why in the commit message. A schema change adds `schema: 2` with a migration note here; version 1 files stay valid.
Unpublishing a project does not rewrite snapshots (they record what was published at the time); the README view hides it.
