# Retention, scheduling and keep-alive

## Retention policy

* **Daily snapshots are kept forever.** A record is ~3-6 KB (dozens of repositories at most), so ~1-2 MB per year. There is no
  pruning and none is planned. Nothing is deleted to reduce file counts.
* **Monthly rollups** are small and kept forever; they are derived and can be rebuilt from the dailies.
* If size ever matters, the documented option is to *archive* a whole past year (move `daily/<YYYY>/` into a single
  `snapshots/archive/<YYYY>.json.gz` with a note and a commit message explaining it), never to drop days. Not implemented, not needed.
* `data/cache/` is a working cache (latest values only) and is not history.

## Scheduling and automation

No new scheduler. The existing `update-profile` workflow (every 6 hours, on demand, on `repository_dispatch`) takes the day's
snapshot on its first successful run of each local day; later runs find it and do nothing.

* **Idempotent:** one create-only file per day; repeat runs change nothing.
* **No overlap:** the workflow's `concurrency` group (`profileos`, no cancel) serialises runs.
* **Atomic and ordered:** all outputs are rendered first; then files are written via temp-file + rename. A failed run leaves
  `snapshots/` and `data/cache/` untouched (tested).
* **Meaningful commits only:** a day with a new snapshot is a legitimate change (new history). A run with nothing new makes no commit.
* Monthly rollups are rewritten only when content changes (the two latest months).

## Is a keep-alive needed?

GitHub disables scheduled workflows in a **public** repository after 60 days without repository activity.

What the repository does today (read from `main`): the workflow commits whenever generated data changes. Before Phase 7 that was
driven by the daily contribution calendar and project activity, but a quiet period (no pushes anywhere for 60 days) could make
runs produce no commit. With Phase 7, **every local day with a successful run adds a daily snapshot commit**, even when commit
counts are zero (a recorded zero is a true fact, not a fabrication). That is a useful, non-artificial commit every day, which
should keep the schedule alive as a side effect.

**Decision: no keep-alive mechanism is implemented or enabled.** Reasons: it would add empty/meaningless commits, the daily
snapshot already provides activity, and the exact GitHub rule for what counts as "activity" (in particular whether commits pushed
with `GITHUB_TOKEN` by a bot count) is **not verified here**. If, after Phase 7 is running, GitHub ever shows the "scheduled
workflow disabled" notice, the trade-offs of the smallest remedy are: (a) re-enable by hand (free, manual); (b) a monthly
`workflow_dispatch`-only reminder issue (no commits, needs a token with `issues: write`); (c) an API call that re-enables the
workflow (needs `actions: write`, broader than today's `contents: write`). Prefer (a) or (b); do not add empty commits.

## What is verified

Implemented and fixture-tested: everything above except GitHub's disabling rule. **Not live-verified:** no snapshot has been taken
by a real `update-profile` run yet; the first real daily snapshot will be created by the first run after Phase 7 is merged.
