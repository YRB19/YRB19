# GitHub audit — 2026-10-01

**Scope and limits.** No API token was available, so this is an *unauthenticated* audit: github.com pages, full git history
(clones), repository archives, and a read of README / manifests / lockfiles / Dockerfiles / workflows / source.
Private repositories and private activity are invisible; CI run logs and live URLs could not be read. Every published value is
recorded in `data/evidence.yml` with its confidence (HIGH = code/config · MEDIUM = README/docs · STATED = your project brief ·
LOW = inference, never published). Activity numbers are *activity signals only* (default-branch commits as of 2026-10-01).

## 1. Account inventory
22 public repositories: 16 non-fork, 6 forks (Foodelns, Wan2.2, newtondarkmode, git-revision20, TrackWeight, multipleWindow3dScene — excluded from everything).
Profile pins (5): UsageOS, ClipOS, repohealth, CompanionOS, ResearchOS. Followers: 2. No topics, no GitHub descriptions (except N8N-YT, Cosmic-Explorer, Capstone-GOW), no licences, no releases/tags anywhere.

| Repo | Created | Last commit | Commits | 7d / 30d / 90d | ★ | ⑂ | Open issues / PRs | Releases | Language (GitHub) |
|---|---|---|---|---|---|---|---|---|---|
| UsageOS | 2026-07-08 | 2026-09-30 | 58 | 6 / 6 / 58 | 1 | 0 | 0 / 0 | 0 | JavaScript |
| ResearchOS | 2026-06-26 | 2026-08-02 | 11 | 0 / 0 / 8 | 1 | 0 | 1 / 0 | 0 | Python |
| ClipOS | 2026-07-11 | 2026-08-01 | 21 | 0 / 0 / 21 | 1 | 0 | 0 / 0 | 0 | Python |
| CompanionOS | 2026-07-18 | 2026-07-29 | 66 | 0 / 0 / 66 | 0 | 0 | 0 / 0 | 0 | TypeScript |
| repohealth | 2025-10-04 | 2026-05-16 | 23 | 0 / 0 / 0 | 1 | 1 | 0 / 1 | 0 | TypeScript |
| Finwise | 2026-03-24 | 2026-04-13 | 14 | 0 / 0 / 0 | 0 | 0 | 0 / 0 | 0 | JavaScript |
| Cosmic-Explorer | 2026-04-27 | 2026-05-09 | 56 | 0 / 0 / 0 | 0 | 0 | 0 / 0 | 0 | JavaScript |
| N8N-YT | 2026-05-13 | 2026-05-13 | 2 | 0 / 0 / 0 | 1 | 0 | 0 / 0 | 0 | — |
| Capstone-GOW | 2025-10-23 | 2025-12-09 | 70 | 0 / 0 / 0 | 0 | 0 | 0 / 0 | 0 | CSS |
| IPL_auction | 2025-11-26 | 2025-11-27 | 4 | 0 / 0 / 0 | 0 | 0 | 0 / 0 | 0 | JavaScript |
| Pokmon-card-trading-exchange | 2025-11-22 | 2025-11-23 | 5 | 0 / 0 / 0 | 0 | 0 | 0 / 0 | 0 | TypeScript |
| Hackathon-16-hrs | 2025-10-04 | 2025-10-05 | 15 | 0 / 0 / 0 | 0 | 3 | 0 / 0 | 0 | TypeScript |
| Hackathon-16hrs | 2025-10-04 | 2025-10-04 | 14 | 0 / 0 / 0 | 0 | 0 | 0 / 0 | 0 | TypeScript |
| YRB19 | 2026-05-13 | 2026-10-01 | 8 | 8 / 8 / 8 | 0 | 0 | 0 / 0 | 0 | Python |

`pokemon-web` and `d` are empty repositories (no archive). Commit windows use `committerDate`-independent author dates; the profile repo itself is excluded from generated activity (`config.exclude_repos`).

## 2. Inconsistencies: data files / spec vs GitHub
| # | Previous assumption | What GitHub shows | Resolution |
|---|---|---|---|
| 1 | NetOS and FREYA are public flagship repos | Both return **404** unauthenticated and are not in the public list | Kept in `projects.yml` unpublished; omitted from generated sections until a public repo resolves |
| 2 | Pins = six flagships | 5 pins, and one is `repohealth`; NetOS/FREYA not pinned | Informational; pins stay manual |
| 3 | Stack: C++ and Linux and RAG | No C++ file, no RAG/vector code, no Linux-specific evidence in any public repo | Left hidden (no evidence) |
| 4 | Stack: Redis, Whisper, ffmpeg, OpenCV, Rust, Tauri, Vercel | All supported (ClipOS, CompanionOS, repohealth) | Evidence recorded |
| 5 | ResearchOS "Telegram-first" (README) | `app/` has no Telegram client code | Telegram not published for ResearchOS |
| 6 | RepoHealth is Next.js 15 (README) | `package.json` pins Next 16.2.6; `name` is `my-v0-project`; 15/23 commits by the v0 bot | Code wins; noted |
| 7 | Cosmic Explorer is React + TypeScript | JavaScript/JSX app (one `.ts` file); README is aspirational; 3 contributors (you: 27/56 commits) | TypeScript not published |
| 8 | CompanionOS CI exists | 4 workflows exist; **all four latest runs show "failing"** | Recorded; cause needs authenticated logs |
| 9 | CompanionOS stack lists `widgets-native` | Not in `package.json` or `Cargo.toml` | Not published |
| 10 | UsageOS README clone URL | Still `your-username/UsageOS.git`; manifest author `your-name`, host `your-server-url.com`; README mentions Caddy but no Caddy config exists; `DEPLOY.md` uses "ATLAS Claude" names | Flagged for the repo-README phase |
| 11 | ResearchOS README shows an MIT badge | No LICENSE file in any repository | Flagged |
| 12 | Legacy README: "17 repos" | 22 public (16 non-fork) | Hard-coded count already removed |
| 13 | `earlier_before: 2025-01-01` | Earliest non-fork repo was created 2025-10-04, so nothing is "earlier" by date | Curated `group: earlier` is used instead |
| 14 | Profile repo as deployed | `.DS_Store` files committed; `update-profile` has never run ("no status"); `validate` passes; generated blocks still empty | `.DS_Store` added to `.gitignore`; run the workflow once |
| 15 | Two commit identities | CompanionOS/ClipOS commits appear as both `YRB19` and `Rishit Babbar` | Pulse uses GitHub's contribution calendar; unlinked emails would under-count |

## 3. Provenance flag (UsageOS extension)
`extension/` carries a GPL-3.0 `LICENSE`, a Chrome Web Store/AMO badge for a *different* listing, and source links to another maintainer's Ko-fi page
(`extension/background.js`, `popup.js`); the repo root has no licence and the README gives no attribution. Facts only — see the decision list.

## 4. Other public repositories (not published; classification only)
- **Capstone-GOW** — static HTML/CSS/JS fan site (≈90 MB of media), 70 commits, 2025-10 to 2025-12. Description: "Capstone project for SNW".
- **Pokmon-card-trading-exchange** — Figma Make export (React/Vite/Radix), 3 of 5 commits by `figma[bot]`.
- **Hackathon-16-hrs / Hackathon-16hrs** — two near-duplicate "GitHub Repository Health Platform" exports (Bolt/Figma); `-16-hrs` has 3 forks.
- **IPL_auction** — 2 files (README + `Layout.js`); commit history includes a deleted `IPL-Auction.zip`.
- **YRB19** — this profile repo (excluded). **pokemon-web**, **d** — empty.
