# Licensing advice for the four flagship repositories

*Practical guidance, not legal advice. If a repository will be widely distributed or used commercially, a short paid review by a licensing lawyer is cheap insurance.*

## What a licence is

Copyright applies automatically to everything you write. A licence is the written permission you give others to use it. **No licence = "all rights reserved":**
public on GitHub only means people may view and fork it on GitHub (GitHub's terms), not copy, modify or reuse it. "Open source" means you chose a
licence that grants those permissions. Three families:

| Family | Examples | What others may do |
|---|---|---|
| Permissive | MIT, Apache-2.0, BSD | Almost anything, including closed-source commercial use, if they keep your copyright notice (Apache-2.0 adds a patent grant) |
| Copyleft | GPL-3.0, AGPL-3.0 | Use and modify, but anything they distribute that includes your code must be released under the same licence with source. AGPL extends this to software offered over a network |
| Proprietary / source-available | "All rights reserved", PolyForm Noncommercial | Only what you say. Source may be visible but reuse is limited |

## UsageOS (you plan to open-source it)

Facts: the extension is derived from `lugia19/Claude-Usage-Extension`, which is GPL-3.0 (confirmed on its GitHub page 2026-10-24; its LICENSE text
and whether it says "only" or "or later" were not readable, so check the file). The backend and dashboard are your own work.

1. **The extension must stay GPL-3.0.** You cannot relicense someone else's GPL code as MIT. Any copy you distribute must keep its licence text,
   copyright notices and be released with source, and your changes should be marked as changes.
2. **Backend + dashboard are yours to license**, but a repo that mixes an MIT backend with a GPL extension confuses users. Recommended: **GPL-3.0 for the
   whole repository** (one `LICENSE` at the root, same as the extension). If you want the server code to stay open even when someone hosts it as a
   service, use **AGPL-3.0** for `backend/` and `frontend/`, and say so in the README. Choose a permissive licence (MIT/Apache-2.0) for `backend/` and
   `frontend/` only if you want companies to reuse them freely; then add a root note listing which directory has which licence.
3. **Attribution to lugia19** (yes, do it; it is also expected by GPL's notice rules): name and link the upstream project in the README (done in the staged
   README), keep their copyright headers and the Ko-fi/author credits unless you replace the UI text honestly, and add a `NOTICE`/credits line stating
   "derived from lugia19/Claude-Usage-Extension (GPL-3.0)". Contacting them is not legally required but is good practice, and it settles questions the repo
   cannot (their copyright line, whether donation links should stay).
4. **Third-party files inside `extension/lib/`** (a webextension polyfill, a tokenizer data file) carry their own licences; list them in `NOTICE`. I have not checked their licences.
5. **Before publishing to a browser store or telling users to install:** `extension/PRIVACY.md` describes the upstream extension's Firebase sync, not your
   backend. Replace it with an accurate policy. Placeholders in the manifests (`your-name`, `your-server-url.com`, Firefox id) are staying for now by your decision.
6. You are fine to keep a copy-not-fork history, but link the upstream so readers can find it.

**My recommendation:** one root `LICENSE` = GPL-3.0 (or AGPL-3.0 if you want the hosted-service protection), plus `NOTICE` crediting lugia19 and third-party libraries.

## ResearchOS, ClipOS, CompanionOS (public, not open source)

Without a licence they are already "all rights reserved", which is what you want, but it is implicit and the old ResearchOS "MIT" badge said the opposite.
Make it explicit: add a `LICENSE` file such as

```
Copyright (c) 2026 Rishit Babbar. All rights reserved.
This source code is published for viewing only. No permission is granted to copy, modify, distribute or use it, except to view and fork it on GitHub as permitted by GitHub's Terms of Service.
```

(confirm the name and year). If you later want to allow personal or non-commercial use while still not being open source, a ready-made source-available
licence such as PolyForm Noncommercial 1.0.0 is better than writing your own. Do not use MIT/Apache unless you are happy for anyone to reuse the code commercially.
Dependencies (FastAPI, Tauri, ffmpeg, yt-dlp and so on) keep their own licences; this only matters if you distribute binaries or bundles, which these repos don't.
