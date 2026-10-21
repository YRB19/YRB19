# Permissions, tokens and secrets

ProfileOS is read-only against GitHub and against deployments. The only thing it writes is generated files in the profile
repository itself (`README.md`, `assets/generated/`, `data/cache/`). Nothing below is required for the profile to build:
every credential is optional and every feature degrades to "show nothing", never to "show green".

## What each workflow can do

| Workflow | Trigger | `permissions:` | Secrets it can read |
| --- | --- | --- | --- |
| `update-profile` (profile repo) | schedule, manual, `repository_dispatch`, push to `data/src/templates` | `contents: write` (commit generated files) | `GITHUB_TOKEN` (automatic), `PROFILEOS_STATUS_TOKEN` (optional) |
| `validate` (profile repo) | pull requests, pushes | `contents: read` | none (safe for fork PRs) |
| `notify-profile` (OPTIONAL, in other repos, from `templates/notify-profile.yml`) | release published | `{}` (none) | `PROFILEOS_DISPATCH_TOKEN` (optional) |

## Credentials, in the order ProfileOS prefers them

### 1. CI status (GitHub Actions runs)

CI status is read from `GET /repos/{owner}/{repo}/actions/runs`, public repositories only, flagship projects only.

| Credential | Needed? | What to create | Used for |
| --- | --- | --- | --- |
| `PROFILEOS_STATUS_TOKEN` | optional | A **fine-grained** personal access token, resource owner = you, *Only select repositories* = the flagship repos, repository permissions **Actions: Read-only** and **Metadata: Read-only**, and nothing else. Set a short expiry. Store it as an Actions secret on the profile repo. | Reading workflow runs with a higher rate limit |
| `GITHUB_TOKEN` | automatic | Nothing to create. | Tried second. It is scoped to the profile repo, so it is **not assumed** to be able to read other repositories' runs. |
| no token | fallback | Nothing. | Public repositories expose their Actions runs without authentication, at the lower unauthenticated rate limit. |

Rules the code enforces (`src/profileos/status/ci.py`, covered by `tests/test_ci.py`):

* Credentials are tried from most to least specific. A `401/403/404` with a credential is retried **without** it; the code
  never steps up in privilege.
* Every request is a `GET`. There is no write path in the status code.
* A *classic* token whose `x-oauth-scopes` header shows `repo`, `public_repo`, `workflow`, `admin:*`, `write:*`,
  `delete_repo` and similar is **refused**: it is contacted once to learn its scopes, a warning is logged, and the run
  continues with less privileged access. Fine-grained tokens and `GITHUB_TOKEN` send no scopes header, so this check
  cannot vouch for them. Create the token exactly as described above.
* Do not use a full-access PAT. Nothing here needs one.
* Tokens are never written to the cache, the README, SVGs, warnings or logs.

Caveat: the unauthenticated limit is 60 requests/hour per IP and GitHub-hosted runners share IPs. If the public fallback is
rate limited, CI chips simply keep their last cached value (up to `ci.stale_after_h`, default 72 h) and then disappear.

### 2. Deployment health

Probes run **only** for a project that has `deployment.health_check: true` and a `deployment.health_url`. No credential of
any kind is sent to a deployment: the request is built from a fixed header set (`Host`, `User-Agent`, `Accept`,
`Accept-Encoding`, `Connection`) and the health module has no access to the environment. See "Health-check safety" below.

### 3. Event-driven refresh

See `docs/EVENT_DISPATCH.md`. `PROFILEOS_DISPATCH_TOKEN` lives on the *sending* repositories only, never on the profile repo.

## Health-check safety

* Opt-in per project: `deployment.health_check: true`, a `health_url`, `verified: true`, and an evidence record
  (`evidence.yml → projects → <slug> → health_url`, HIGH/MEDIUM/STATED, same value). `profileos validate` enforces all four.
  URLs are never taken from README text automatically.
* URL policy: `https` (plain `http` only if `health.allow_http: true`), host names only (no IP literals, no `0x7f.1`-style
  spellings, no `localhost`/`.local`/`.internal`), ports from `health.allowed_ports` (default 80/443), no credentials, query
  or fragment.
* Address policy, IPv4 and IPv6: every address a name resolves to must be globally routable. Loopback, private, link-local,
  CGNAT, documentation, benchmarking, multicast, reserved and unspecified ranges are rejected, as are IPv6 forms that embed an
  IPv4 address (`::ffff:a.b.c.d`, NAT64 `64:ff9b::/96`, 6to4 `2002::/16`, Teredo). One private answer rejects the whole name.
* DNS rebinding: the name is resolved twice, both answers must be public and overlap, and the connection goes to the
  **pinned IP** (never re-resolved); TLS verifies the certificate against the real host name and the connected peer must equal
  the pinned IP.
* Redirects: followed manually, at most `health.max_redirects` (default 3), every hop re-validated (URL, DNS, ports), only to
  the original host or hosts listed in `deployment.redirect_hosts`, never https → http.
* Bounds: `health.timeout_s` per socket operation (default 5 s), a total time budget, `health.max_bytes` read (default 64 KiB),
  `health.max_checks` probes per run.
* Honest states: a timeout, resolver hiccup, blocked redirect or a 401/403/429 is `unknown`, never `offline`. `offline` needs a
  connection refusal or NXDOMAIN in `health.offline_after` consecutive runs (default 2). 5xx and other 4xx are `degraded`.

## Optional secrets, summarised

| Secret / variable | Where | Default | Effect if missing |
| --- | --- | --- | --- |
| `PROFILEOS_STATUS_TOKEN` | profile repo, secret | unset | CI is read with `GITHUB_TOKEN`, then public data |
| `PROFILEOS_DISPATCH_TOKEN` | each sending repo, secret | unset | the notify job exits quietly; scheduled/manual refresh unaffected |
| `PROFILEOS_DISPATCH_ENABLED` | each sending repo, variable | unset | the notify job does not run |
| `PROFILEOS_TARGET_REPO` | each sending repo, variable | `YRB19/YRB19` | dispatches go to the default profile repo |

## What is *not* verified

All of the above is covered by deterministic tests using mocked transports and fixtures. It has **not** been exercised
against live GitHub or a live deployment from this environment (outbound access here is allow-listed). The first scheduled
run after merge is the live test; expected outcomes and a checklist are in `README_DEV.md`.
