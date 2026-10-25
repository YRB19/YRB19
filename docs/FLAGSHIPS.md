# Phase 8 — flagship repositories: change summary and open questions

Audit date 2026-10-23, from full clones of `main` of each repository. Staged files are in `flagships/<Repo>/`; copy them into the repo root
(the zip delivered with this phase is laid out that way: `unzip -o` from the repo root). Nothing has been merged or changed on GitHub.

## What changed per repository

| Repo | README changes (all claims checked against code/manifests) |
|---|---|
| **UsageOS** | Real clone URL (`YRB19/UsageOS`). Notification scheduler is in the **backend** (two asyncio loops), not the extension. Removed unbuilt/unsupported claims: extension `npm install && npm run build` (no `package.json`), `npm test`/`pytest`/`ruff` (no tests), Caddy in compose (absent), `CORS_ORIGINS`/`.env.example` values that did not match. Added the external `atlas-network` step, the real endpoint/auth table, security limitations, and an honest licensing/attribution section. |
| **ResearchOS** | Removed Telegram-first wording (no Telegram client in `app/`; `app/telegram.py` listed in the old README does not exist) and the MIT badge/"MIT" section (no LICENSE). Replaced the `.env` configuration table: the code reads only `DB_PATH`; keys/models/loop settings come in each `POST /jobs` `config`; default `max_iterations` is 5 (old README said 3). Loop diagram, evidence handling, agents, API, tests. |
| **ClipOS** | Pipeline diagram with caption burn-in marked manual; real models (`z-ai/glm-5.2` + OpenRouter fallback), Haar-cascade reframing limits, hard-coded Homebrew ffmpeg path noted; removed "Opus Clip clone" framing; stated that no screenshots/output exist. |
| **CompanionOS** | Features restricted to the routes/native commands in code; WidgetKit extension flagged as manual Xcode setup; workflow table; `e2e.yml` `continue-on-error` disclosed; CI shown as **failing as of 2026-10-21** with logs unavailable, no passing badge; licence placeholder replaced by an explicit "no licence file". |

Each repo also gets `assets/social-preview.svg` and `.png` (see `SOCIAL_PREVIEWS.md`).

## Decisions received 2026-10-24 and what is still open

- Extension is derived from `lugia19/Claude-Usage-Extension` (confirmed by owner) → README attribution updated; see `LICENSING.md` for licence advice.
- UsageOS will be open-sourced; ResearchOS, ClipOS, CompanionOS stay public but not open source.
- Extension placeholders stay as they are for now; UsageOS backend authentication is planned (not part of this phase).
- CompanionOS CI investigation deferred (low priority).
- **Still open:** which licence for UsageOS (recommended GPL-3.0, or AGPL-3.0) and the copyright holder name/year for the "all rights reserved" files.

## Original questions (items 1, 4, 5, 8 now answered or deferred as above)

### UsageOS provenance and licensing
1. **Origin of `extension/`.** The initial commit (`05acfd2`, 2026-07-08, author YRB19) already contains the whole extension, a GPL-3.0 `LICENSE` with no
   project-specific copyright line, and files referring to `lugia19` (Ko-fi links in `popup.js`, `background.js`, `notification_card.js`,
   `shared/localization.js`; links to `lugia19/Claude-Usage-Extension` and `lugia19/claude-webext-patcher`; an `extension/README.md` written for that project).
   Is the extension a fork of, or derived from, `lugia19/Claude-Usage-Extension`? If so GPL-3.0 obligations (attribution, source availability, licence
   of the combined work) apply and need your decision. This audit cannot determine it from the repository alone, and the git history does not show an upstream.
2. **Root licence.** The old README said "MIT — see LICENSE" but no root `LICENSE` exists, and MIT for the whole repo conflicts with a GPL-3.0 component
   unless that component is separate. Which licence do you want for `backend/` and `frontend/`? (No licence was added or changed.)
3. **Donation links.** The extension still sends users to another maintainer's Ko-fi. Keep, remove or replace is your call.
4. **Placeholders left untouched** because they sit in upstream-derived files and no replacement is established: `extension/manifest*.json`
   (`"author": "your-name"`, Firefox id `claude_usage_tracker@your-domain.com`, host permission `https://your-server-url.com/*`), `options.html`
   placeholder, `backend/pyproject.toml` authors (`Your Name <your-email@example.com>`), `extension/README.md` links to `your-username/*`,
   `extension/PRIVACY.md` (`your-email@example.com`). `PRIVACY.md` describes the upstream extension's Firebase sync, not the UsageOS backend. Provide the real values
   or tell me to leave them.
5. **Backend authentication.** Account/note/avatar/webhook endpoints are unauthenticated (see README). Out of scope for a documentation phase; flagged.

### Other repositories
6. **ResearchOS** has no LICENSE (the badge was removed, not replaced). Choose a licence or confirm none.
7. **ClipOS, CompanionOS, ResearchOS** have no LICENSE; CompanionOS's README said "Add license information here".
8. **CompanionOS CI is failing** (last recorded run 2026-07-29, ~3 months old). Do you want it investigated (needs Actions access to that repo)?
9. **Screenshots / demo output**: none of the four repos has any. Real screenshots from you (or a recorded run) would let the READMEs show the product.
10. **`flagships/*/.upstream-files`** exist only for the link check; delete them if you don't want them in the repo (they are not shipped to the flagship repos).

## Metadata (not changed; verify before editing)

Repository description, topics, homepage and social preview were **not** touched. Suggested, from verified content only:
UsageOS "Self-hosted tracker for Claude.ai usage limits across multiple accounts"; ResearchOS "Research-job API with parallel specialist agents and an evidence loop";
ClipOS "Turns long videos into short vertical clips with captions"; CompanionOS "Desktop Formula 1 timing and session tracker (Tauri, React)".
Topics inferred from the stacks: `fastapi`, `postgresql`, `react`, `browser-extension` / `fastapi`, `sqlite`, `llm` / `fastapi`, `faster-whisper`, `opencv` / `tauri`, `react`, `typescript`, `formula-1`.
No demo links exist. Pins, visibility and branch protection are unchanged.
