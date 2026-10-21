# Event-driven refresh (optional, disabled by default)

The profile already refreshes every 6 hours, on demand (`workflow_dispatch`) and on `repository_dispatch` events of type
`profileos-refresh`. This feature lets another repository send that event when it publishes a release, so the profile
updates in minutes instead of hours. It is **disabled by default**: the template lives in `templates/`, not in
`.github/workflows/`, and does nothing even when copied until a variable *and* a secret exist.

Scheduled and manual refreshes keep working whether or not this is configured.

## Enable it for one repository

1. Create a **fine-grained personal access token**: resource owner = you, *Only select repositories* = the **profile
   repository only**, repository permission **Contents: Read and write** (GitHub requires this permission for the
   "create a repository dispatch event" endpoint; there is no narrower one), nothing else, expiry 90 days or less.
   Check GitHub's current documentation for that endpoint when you create it.
2. In the repository that publishes releases (for example `UsageOS`):
   * add the token as an Actions **secret** named `PROFILEOS_DISPATCH_TOKEN`;
   * add an Actions **variable** `PROFILEOS_DISPATCH_ENABLED` = `true`;
   * optionally add `PROFILEOS_TARGET_REPO` (default `YRB19/YRB19`);
   * copy `templates/notify-profile.yml` to `.github/workflows/notify-profile.yml`.
3. In `data/config.yml`, record the intent so `profileos validate` can check it:

   ```yaml
   event_dispatch:
     enabled: true
     target_repo: YRB19/YRB19
     event_type: profileos-refresh
     sources: [YRB19/UsageOS]
     events: [release]
   ```

   Validation fails if `enabled` is true with no sources/events, if the target is not yours, or if the event type is not a
   `repository_dispatch` type of `update-profile.yml`.

## Behaviour and guarantees

* The job runs with `permissions: {}`. It uses **only** `PROFILEOS_DISPATCH_TOKEN`; there is no fallback to `GITHUB_TOKEN`
  or any other credential. Missing secret → notice and clean exit.
* Only `release: published` triggers it (drafts never fire that event). The payload is `{event_type, client_payload:
  {source, event}}`: no secrets, no repo content.
* A failed dispatch (401/403/404/422/network) is a warning, never a failed release.
* Bursts: the profile workflow serialises runs with its `concurrency` group, and an unchanged result produces no commit.
* The token can write contents of the profile repository, so scope it to that one repo, keep the expiry short, and keep it
  only on the sending repositories. The profile's own bot commits do not trigger another run (actor guard).

## Not yet verified live

The template's shell logic is tested with a stubbed `curl` (no token → nothing sent; token → one scoped POST; malformed
target → nothing sent; HTTP errors → warning only). It has not been run on GitHub Actions or sent a real dispatch.
