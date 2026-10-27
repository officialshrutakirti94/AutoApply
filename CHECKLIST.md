# Frontend Checklist — dashboard v2

Live status for `DASHBOARD-PLAN.md`. Verified by `dashboard/scripts/e2e.mjs` in a real
browser against the live backend: **30/30 checks passed**.

Legend: `[x]` verified · `[~]` built and API-verified, UI path not clicked in the test
· `[ ]` not done

---

## F0 — foundation

- [x] Landing page (hero, features, how it works, safety, pricing, footer)
- [x] Dark tokens: one vermilion accent, hairlines, 4px radius
- [x] Type: Bricolage Grotesque + IBM Plex Mono
- [x] Primitives: Button, Stamp, Chip, Rule, Cell, CellHeader, Stat, Field, Input, LedgerRow
- [x] `/signin` with Google Identity Services + dev sign-in
- [x] Typed API client, CSRF header on every write
- [x] `npm run build` green

---

## F1 — remove and re-route

- [x] `/styleguide` and the palette page deleted (no route, no link, absent from the bundle)
- [x] `/setup` added; sign-in lands there while `onboarding.done = false`
- [x] Signed-in user hitting `/setup` is redirected to `/app`
- [x] Unfinished user hitting `/app` is redirected to `/setup`
- [x] Sidebar shows exactly the five sections

---

## F2 — setup

- [x] Screen 1 greets by first name ("Hi Dev." / "Hi Shrutakirti.")
- [x] Screen 1 accepts PDF/DOCX (drag-drop + file picker wired)
- [~] Parse success prefills screen 2 — the endpoint is verified, the upload click is not in the browser test
- [~] Unreadable file shows the fallback copy — built, not exercised by the test
- [x] Screen 2 asks for GitHub, current CTC, experience, career field, roles, level
- [x] Screen 2 writes to `PUT /api/profile` and `PUT /api/preferences`
- [x] Screen 3 has locations, work mode, active hours, platforms, consent
- [x] Finish calls `POST /api/onboarding/complete` and lands on `/app`
- [x] Finish shows a staged loader ("Profile ? Preferences ? Dashboard") and blocks double submits
- [x] Continue advances instantly (never blocked by a save) — this was a bug, fixed
- [x] Refresh mid-setup returns to setup

---

## F3 — shell + overview

- [x] Sidebar: Overview, Applications sent, Waiting for confirmations, Can't send, Your resume, Your profile
- [x] Greeting cell: "Hi Shrutakirti." + plan stamp + date
- [x] Agent cell with live-run state and disabled Start ("extension coming soon")
- [x] Quota cell: used/cap, reset countdown, reset hour, hourly
- [x] Sent / Waiting / Can't send cells from one bucketed query
- [x] Resume cell with parse status and Download
- [x] Profile cell with name, title, skills, plan
- [x] Designed empty states in every cell
- [ ] Counters moving within 3 s of a live run — blocked until the extension exists

---

## F4 — the three application pages

- [x] Sent renders with time, role, company, platform, link
- [x] Waiting renders only question-blocked items, with the cause explained
- [x] Waiting offers Open on LinkedIn/Naukri + Mark resolved
- [x] Can't send renders structural skips with reason labels + Dismiss
- [~] Resolve / Dismiss round-trip — wired to `PATCH /api/applications/{id}`, not clicked in the test

---

## F5 — resume + profile

- [x] Resume page: parse status, confidence table, extracted content
- [x] Resume Download wired to the signed URL
- [~] Resume Replace upload — built, not clicked in the test
- [x] Profile page edits every field and saves
- [x] Plan card: tier, daily cap, price, reset hour, all three tiers, current marked
- [x] Plan switch visible in dev only
- [x] Delete my data behind a typed confirmation
- [~] Delete actually completes — wired, not clicked in the test

---

## Verification

- [x] `npm run build` — zero TypeScript errors
- [x] Real browser, live API: landing → sign-in → setup → dashboard → all five sections
- [x] 41/41 e2e checks (real DOCX upload, prefill, disabled-Finish, and the finishing loader)
- [x] No horizontal overflow at 390 px; layout verified at 1440 px
- [ ] 768 px breakpoint pass
- [ ] Keyboard-only end-to-end pass
- [ ] AA contrast audit on stamps and meta text
- [x] `prefers-reduced-motion` honoured globally
- [x] Screenshots captured in `%TEMP%\opencode\shots`

### Bugs found by this verification (all fixed)

1. **`VITE_API_BASE_URL` was absolute** — every request became cross-site, so the
   `SameSite=Lax` session cookie was never sent. Now empty, same-origin via the proxy.
2. **Vite bound IPv6-only** — `127.0.0.1:5173` refused connections. Now `host: true`.
3. **Sign-in still redirected to the deleted `/onboarding` route.** Now `/setup`.
4. **Continue blocked on the network** — a slow save left the button looking dead.
   Navigation is now immediate; only Finish awaits.

### One thing you must do

Google sign-in is rejected with *"The given origin is not allowed for the given client
ID"*: add `http://localhost:5173` (and the production origin) under **Authorised
JavaScript origins** for that OAuth client. Dev sign-in works in the meantime.
---

# Extension Checklist — "Apply Magic"

`npm test` → 14 passing · `tsc --noEmit` clean · `wxt build` green · loaded in Chrome.

## Done and verified
- [x] E0 — WXT + React + TS, MV3 manifest (storage, power, alarms, tabs; LinkedIn/Naukri/Supabase hosts)
- [x] E0 — popup with all states, token storage, typed API client, message bus
- [x] E1 — LinkedIn extractor: search cards, job detail, Easy Apply form (selects, radios, upload)
- [x] E1 — Naukri extractor: listing cards, chat choice question, chat free-text question
- [x] E1 — 24h search URLs for both platforms (9 tests)
- [x] E1 — 5 fixture tests against the real captured pages
- [x] E1 — live check: content script produced `search_results` with 6 cards from the fixture served at a linkedin.com URL, zero false signals
- [x] E2 — pairing, platform detection, in-page banner, Apply Magic → `runs/start`
- [x] E3 — owned run window (`focused:false`), 30 s tick alarm, restore-on-minimize, reopen-after-close (max 2), keep-awake
- [x] E4 — action executor (all 8 types), SW-driven loop, pacing, long-break via alarm, 3-error stop
- [x] E5 — `attach_resume` via signed URL → DataTransfer
- [x] E6 — Naukri chat answered through the same select path (no backend change)
- [x] E7 — stuck jobs: reason + link only, no screenshots
- [x] E8 — hard-stop signals (visible-widget detection), off-domain click refusal, heartbeat stop

## Needs a live signed-in session to prove
- [ ] 10 dry-run applications on LinkedIn, paced, no repeats
- [ ] The run window keeps working while another window has focus
- [ ] Tab closed → reopened and resumed; minimized → restored
- [ ] Live application on a throwaway account
- [ ] Naukri chat answered end to end (CTC / notice from profile)
- [ ] A sensitive question lands in Waiting for confirmations with a working link
- [x] D2 — Settings page: pairing code (10 min, single use), install steps, connected browsers + disconnect, automation limits
- [x] D2 — extension zip built and served at `/autoapply-extension.zip` from the dashboard
- [x] D2 — verified in a browser: code generated, extension paired via the API, install listed, code replay rejected (401)
