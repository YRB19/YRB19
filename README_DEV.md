# ProfileOS — developer notes

**Automate facts. Curate identity.** Spec: `PROFILEOS_SPEC.md` · plan/status: `PLAN.md`.

## Verification status (read this first)
- **Live GitHub workflow: not production-verified.** The fetch/analyse/generate pipeline has not been run against a live authenticated
  GitHub request. It is covered by fixture-based tests, a mocked HTTP client and the 2026-10-01 public-web audit (`docs/AUDIT.md`),
  but the real GraphQL query shape and the Actions run are unproven until the first `update-profile` run succeeds in `YRB19/YRB19`.
- Generated SVGs are covered by tests (safety, light/dark, missing data, alt text, 360px font floor) and were reviewed visually,
  but only on **synthetic fixture data**. Nothing in `assets/generated/` is committed until a real run produces it.
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

## Install into the profile repo
Copy this folder's contents into `YRB19/YRB19`, commit, then run the `update-profile` workflow once
(Actions → update-profile → Run workflow). The built-in `GITHUB_TOKEN` is enough for public data.
