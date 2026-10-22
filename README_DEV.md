# ProfileOS — developer notes

**Automate facts. Curate identity.** Spec: `PROFILEOS_SPEC.md` · plan/status: `PLAN.md`.

## Verification status (read this first)
- **Live `update-profile` run: succeeded on `main`** (bot commits, real `data/cache/`, 18 generated SVGs). Actions logs are not readable from the build sandbox.
- **Phase 6 CI status: observed live** (`data/cache/ci.json`, written by the bot). **Phase 6 deployment health, event dispatch and release tracker are not live-verified**
  (no project has `health_check` enabled, dispatch is off, no repository has releases yet).
- **Phase 7 is NOT live-verified.** Snapshots, rollups, timeline and the monthly chart are tested with synthetic fixtures in temp directories only. Snapshot
  scheduling has not been validated on GitHub Actions; no real snapshot exists until the first run after Phase 7 is merged.
- First live check after merging Phase 7: run `update-profile` manually, then confirm `snapshots/daily/<year>/<today>.json` exists (a `+1 day` run adds
  exactly one more), `snapshots/timeline.json` exists, a second run the same day makes no commit, and `python -m profileos validate` passes on the result.
- The profile pins are never touched: the client only issues read-only queries (tested).

## Run it
```bash
pip install -r requirements-dev.txt
export PYTHONPATH=src

python -m profileos validate            # schemas + cross-file + marker checks (--strict, --online)
python -m profileos build --fixtures    # offline dry-run on SYNTHETIC data; writes nothing
python -m profileos preview --fixtures --out /tmp/pv   # SVG assets + review page (synthetic data, banner says so)
GITHUB_TOKEN=... python -m profileos build --dry-run   # real data, prints sections only
GITHUB_TOKEN=... python -m profileos build             # real run: updates cache + README markers
python -m pytest -q
```

## Where things live
| You edit (curated) | Machines write (generated) |
|---|---|
| `data/*.yml`, text outside markers in `README.md` | text between `PROFILEOS:START/END` markers, `data/cache/*.json` |

Adding a project = one block in `data/projects.yml`. Flagship taglines/stacks are shown only when `verified: true`
(which requires a tagline and stack). Stack items render only with non-empty `evidence` in `data/stack.yml`.

## Guarantees enforced by tests
- Validation failure ⇒ nothing is written. Broken/missing/duplicate marker ⇒ run fails, README untouched.
- Second run with the same upstream data ⇒ byte-identical outputs, no commit.
- API failure ⇒ last valid cache is used; >24 h old ⇒ labelled "as of <date>"; no cache ⇒ section hidden.
- Private repos are dropped in code even if the API returns them; repo text is sanitised/escaped.

## Phase 6 (status)
Config lives in `data/config.yml` (`ci`, `health`, `event_dispatch`); per-project `deployment` / `ci` fields in `projects.yml`.
Permissions and secrets: `docs/PERMISSIONS.md`. Event dispatch: `docs/EVENT_DISPATCH.md`. New README marker: `RELEASES`
(add `<!-- PROFILEOS:START:RELEASES -->` / `END` once; the shipped README already has it).

## Phase 7 (history)
Config: `snapshots:` in `data/config.yml`; milestones in `data/history.yml`. Formats/rules: `docs/SNAPSHOTS.md`; retention + keep-alive decision:
`docs/RETENTION.md`. New README marker: `TIMELINE` (add `<!-- PROFILEOS:START:TIMELINE -->` / `END` once; the shipped README has it).
Never commit records produced from `--fixtures` (they are never written, and `validate` rejects any marked `synthetic`).

## Install into the profile repo
Copy this folder's contents into `YRB19/YRB19`, commit, then run the `update-profile` workflow once
(Actions → update-profile → Run workflow). The built-in `GITHUB_TOKEN` is enough for public data.
