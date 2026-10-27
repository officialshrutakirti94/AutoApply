# Dashboard Plan v2 — setup, then a working bento dashboard

**Landing page: final. Nothing in it changes.**
Everything after sign-in is built to this plan. Live status: `CHECKLIST.md`.

---

## 1. Routes

| Route | Screen |
|---|---|
| `/` | Landing (untouched) |
| `/signin` | Google sign-in + dev sign-in |
| `/setup` | "Hi {name}" → resume → details → where & when → consent |
| `/app` | Overview bento |
| `/app/sent` | Applications sent |
| `/app/waiting` | Waiting for confirmations |
| `/app/failed` | Can't send |
| `/app/resume` | Your resume |
| `/app/profile` | Your profile + plan + danger zone |

Guard: `GET /api/auth/me` → `onboarding.done === false` → `/setup`; true → `/app`.

---

## 2. Setup (resume first)

**Screen 1 — "Hi {name}."** Resume drop zone (`POST /api/resume`, PDF/DOCX ≤ 5 MB).
Parse success prefills screen 2. Unreadable file → fallback copy + manual path
(`POST /api/resume/manual`). Skippable.

**Screen 2 — details.** `PUT /api/profile` and `PUT /api/preferences`, 600 ms debounce.

| Field | Backend |
|---|---|
| Full name, phone, city, email (read-only) | `profile` |
| GitHub, LinkedIn, portfolio | `profile` links |
| Current title, company, total experience | `profile` |
| Current CTC, expected CTC | `profile` |
| Notice period (0/15/30/60/90 chips) | `profile.notice_period_days` |
| Career field | `preferences.domains[0]` |
| Target roles (seeded by field) | `preferences.target_roles` |
| Experience level (entry/mid/experienced) | `preferences.experience_level` |

**Screen 3 — where and when.** Locations, work mode, active hours, platforms, risk
notice → `POST /api/onboarding/complete` → `/app`.

Navigation never waits on a save: Continue advances immediately, writes settle in the
background. Only Finish awaits, because onboarding needs the preferences stored.

---

## 3. Dashboard

Left rail: Overview · Applications sent · Waiting for confirmations · Can't send ·
Your resume · Your profile. Plan chip + user + sign-out at the bottom.

### Overview bento (12-col)

| Cell | Span | Data |
|---|---|---|
| Agent | 7 | `GET /api/runs/active` — live line, counters, Start/Stop (disabled, "extension coming soon") |
| Quota | 5 | `GET /api/safety/status` — used/cap, reset countdown, hourly, warm-up note |
| Sent | 4 | first rows of the sent bucket |
| Waiting | 4 | question-blocked items + "Open inbox" |
| Can't send | 4 | structural skips |
| Your resume | 6 | `GET /api/resume/draft` + signed download |
| Your profile | 6 | `GET /api/profile` + `GET /api/plan` |

Polling: 3 s while a run is active, 15 s otherwise.

### The three buckets

One `GET /api/applications?limit=200` is bucketed client-side, so counts and lists can
never disagree:

```
applied | dry_run                                  -> Sent
needs_attention + sensitive/unknown/low_confidence -> Waiting (you must confirm)
everything else                                    -> Can't send
```

**Waiting** explains the specific cause and offers Open + Mark resolved.
**Can't send** is a record, not a task: cause label, link, Dismiss.

### Resume / Profile
Resume: parse status, per-field confidence, summary, skills, Download (signed URL),
Replace. Profile: every field editable, plan card (three tiers, current marked, switch
in dev only), usage, and Delete my data behind a typed confirmation.

---

## 4. No backend changes needed

Both buckets come from data the API already returns. Everything on this plan uses
endpoints that exist and are covered by the backend test suite.