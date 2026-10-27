# AutoApply Agent — v1 Build Plan (executable)

This file supersedes the *how* in `project-plan (1).md` while keeping its *what*.
Read this file before writing any code. Every slice below is shippable on its own
and ends with a check you can actually run.

Two things are locked by the product owner and are not open for negotiation while
building:

1. **Auth is Google sign-in only.** No passwords, no email verification, no reset flow.
2. **UI/UX is a first-class deliverable,** not a coat of paint. The Logbook design
   system (section 10) is part of the definition of done.

---

## Build status

Last updated: backend complete.

| Slice | Backend | Dashboard | Extension |
|---|---|---|---|
| S0 contract freeze | **done** — `packages/shared/contract.schema.json` + Pydantic mirror + parity test | TS types still to generate | — |
| S1 foundation | **done** — settings, session, 11 tables, Alembic baseline, `/health`, error envelope, structlog | — | — |
| S2 Google auth | **done** — ID-token verify, opaque sessions, CSRF gate, 12 authz tests | sign-in screen pending | — |
| S3 design system | — | not started | — |
| S4 resume + profile + qa | **done** — PDF/DOCX extract, heuristic+LLM parse, confidence, manual fallback, qa CRUD | — | — |
| S5 onboarding | **done** — autosave fields, step rail persistence, completion gate | 6 screens pending | — |
| S6 dashboard core | **done** — Today/Ledger/Needs-you/Answers/Settings backing APIs, polling shape | screens pending | — |
| S7 extension shell | **done** — pairing, tokens, platform status, resume-file | — | WXT shell pending |
| S8 safety | **done** — policy, caps, warm-up, cooldown, heartbeat, sweeper, governor, 100% policy tests | — | local governor pending |
| S9 agent graph | **done** — LangGraph graph, allow-listed tools, all branches tested | — | platform page code pending |
| S10 LinkedIn | **done** — platform-neutral decisions | — | reader/actions + fixtures pending |
| S11 Naukri | **done** — same graph, chat questions answered from profile | — | reader/actions pending |
| S12 answers + HITL | **done** — rules→bank→LLM→human, sensitive routing, injection defence | — | — |
| S13 screenshots | **done** — upload, signed URL, 14-day retention job | — | capture pending |
| S14 deploy + docs | **done** — `backend/README.md`, prod config guards | root README pending | zip packaging pending |

Backend verification: `200 tests passing`, `ruff` clean, `python -m evals.run` 74/74,
full journey exercised over real HTTP (`/health` → sign-in → onboarding → pair →
run → step → ledger → delete).

Verified against the live services on 2026-10-26: Alembic applied to the Neon
project (12 tables), and the full journey ran with `STORAGE_BACKEND=supabase` —
resume uploaded to a private bucket, signed URL fetched over HTTPS with matching
bytes, and account deletion purged the object.

Two backend items cannot be verified without external credentials and stay open:
Google token verification against real Google keys (`GOOGLE_CLIENT_ID`), and live
LLM behaviour (Groq/Nemotron keys). Both have deterministic fallbacks and are
covered by unit tests with the provider stubbed.

---

## 0. Decisions locked for v1

| # | Decision | Why | Cost of changing later |
|---|---|---|---|
| D1 | **Google Sign-In only**, via Google Identity Services with an ID token | One click, no password storage, Google already verified the email | Low — users table keeps `email` |
| D2 | **Opaque DB sessions, not JWT access+refresh** | Instant revoke, no refresh endpoint, no clock skew, ~40 lines of code | Medium — touches every dependency |
| D3 | **Dashboard and API are same-origin** via a `/api` proxy (Vite dev proxy + Vercel rewrite) | Kills CORS and cross-site cookie problems in one move | High — changes cookie policy everywhere |
| D4 | **Extension pairs with an 8-char one-time code**, then uses a long-lived bearer token | Works in dev where the extension ID changes on every reload | Low |
| D5 | **Polling** (3s active / 15s idle), no SSE | Robust behind proxies, looks live to the user | Low |
| D6 | **Backend decides, extension acts.** The LLM never sees selectors or URLs | Prompt-injection boundary | Very high |
| D7 | **Rules → qa_bank → LLM**, in that order, with a hard per-run LLM cap | Near-zero runtime bill | Low |
| D8 | **v1 ships as an unpacked/zip extension**, not a Chrome Web Store listing | Store review is slow and automating LinkedIn/Naukri would likely be rejected | Low |
| D9 | **No dark mode in v1**; tokens are structured so it can be added | Saves a full design pass | Low |
| D10 | **`interrupt()` is not used.** Stuck work returns `status: "hitl"` and a `needs_attention` row | Much simpler than LangGraph interrupts, same product behaviour | Low |

**Deliberate non-goals** (state these in the README, don't hide them): external
company sites, OCR for scanned resumes, per-job cover letters, Firefox/Safari,
mobile app, weekly analytics, team accounts.

---

## 1. What "complete for real users" means

A user with a Google account can, today, on their own machine:

1. Open the dashboard, click **Continue with Google**, and land on onboarding.
2. Upload a text-based PDF/DOCX, see parsed fields, fix what's wrong, never meet a blank form.
3. Finish 6 onboarding steps, read the risk notice, consent, and reach **Ready**.
4. Install the extension from a zip, paste one pairing code, and see their platforms go **Connected**.
5. Open LinkedIn or Naukri, press **Start Magic**, and watch the ledger fill itself.
6. Get every stuck item in **Needs you** with a link that opens the exact job.
7. Change caps/hours/roles, replace the resume, disconnect the extension, delete all data.
8. Hit a designed empty state, loading state, error state and interrupted-run state — not a blank screen.

Anything not on that list is either cut or explicitly labelled as a known limitation.

---

## 2. Stack and exact dependencies

**Monorepo:** pnpm workspaces. `pnpm dev` runs dashboard + backend.

| App | Runtime | Key dependencies |
|---|---|---|
| `backend/` | Python 3.11+ | `fastapi`, `uvicorn[standard]`, `pydantic` v2, `pydantic-settings`, `sqlalchemy[asyncio]` 2.x, `asyncpg`, `alembic`, `google-auth`, `python-multipart`, `pdfplumber`, `python-docx`, `boto3`, `tenacity`, `structlog`, `apscheduler`, `langgraph`, `langgraph-checkpoint-postgres`, `langchain-core`, `langchain-groq`, `langchain-openai` (pointed at NVIDIA NIM), `langsmith` |
| `dashboard/` | Node 20 | `react` 18, `react-dom`, `vite`, `typescript`, `tailwindcss`, `@radix-ui/react-{dialog,dropdown-menu,switch,tabs,tooltip,label}`, `@tanstack/react-query`, `react-router-dom`, `motion` (Framer), `clsx`, `tailwind-merge`, `lucide-react` (stroke 1.5 only), `@sentry/react` (optional) |
| `extension/` | Node 20 | `wxt`, `@wxt-dev/module-react`, `react`, `typescript`, `zustand` |
| `packages/shared/` | — | `contract.schema.json` → generated TS types + Pydantic models, plus a typed API client |

**Not in the stack:** Next.js, GraphQL, Redis, Celery, shadcn/ui (we re-skin Radix
ourselves — the default shadcn look is explicitly banned by the design brief).

---

## 3. Repo layout

```
autoapply/
├── README.md                    # what it is, honest limits, setup, demo script
├── V1-BUILD-PLAN.md             # this file
├── pnpm-workspace.yaml
├── backend/
│   ├── .env.example
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py
│   │   ├── api/            auth.py resume.py profile.py qa.py extension.py runs.py agent.py applications.py safety.py account.py internal.py
│   │   ├── core/           config.py deps.py security.py errors.py logging.py ratelimit.py
│   │   ├── db/             base.py session.py models/ (one file per table) migrations/
│   │   ├── resume/         extract.py parse.py prompts.py
│   │   ├── agents/         graph.py llm.py nodes/ tools.py checkpointer.py
│   │   ├── safety/         policy.py governor.py caps.py sweeper.py
│   │   └── services/       storage.py screenshots.py qa_bank.py
│   ├── evals/              datasets/ evaluators/
│   └── tests/              conftest.py test_auth.py test_authz.py test_safety.py test_agent_step.py fixtures/
├── dashboard/
│   ├── .env.example
│   └── src/  routes/ components/ lib/ styles/ hooks/
├── extension/
│   ├── .env.example
│   └── src/
│       ├── entrypoints/    background.ts content/ popup/
│       ├── platforms/      base.ts linkedin/ naukri/
│       ├── safety/         governor.ts
│       └── lib/            api.ts store.ts
└── packages/shared/
```

---

## 4. Environment variables

Three files, one per app, committed as `.env.example`. Full annotated templates
live at `backend/.env.example`, `dashboard/.env.example`, `extension/.env.example`.

| Variable | App | Required | Notes |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | backend, dashboard | **yes** | Web client ID. Same value in both. No secret needed. |
| `GOOGLE_CLIENT_SECRET` | backend | no | Only for a future authorization-code flow. Leave blank. |
| `AUTH_DEV_BYPASS` | backend | dev only | Fake sign-in for local work. Ignored unless `APP_ENV=development`. |
| `SECRET_KEY` | backend | **yes** | Signs pairing-code hashes and internal tokens. 48+ random chars. |
| `DATABASE_URL` | backend | **yes** | Neon **pooled** string with `postgresql+asyncpg://`. |
| `DATABASE_URL_UNPOOLED` | backend | yes | Alembic only. |
| `GROQ_API_KEY` | backend | no | Without it the app runs rules-only. |
| `NVIDIA_API_KEY` | backend | no | Nemotron, OpenAI-compatible endpoint. |
| `LANGSMITH_API_KEY` | backend | no | Tracing off if empty. |
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_BUCKET` | backend | prod | Supabase Storage REST API. Private bucket, auto-created on first upload. `STORAGE_BACKEND=local` in dev; `S3_*` also supported but needs a separate S3 key pair. |
| `SAFETY_*` | backend | no | Defaults are sane; see section 9. |
| `VITE_API_BASE_URL` | dashboard | no | Leave empty — `/api` is proxied. |
| `VITE_GOOGLE_CLIENT_ID` | dashboard | **yes** | Public client ID. |
| `WXT_API_BASE_URL` | extension | **yes** | `http://localhost:8000/api` in dev. |
| `WXT_DASHBOARD_URL` | extension | **yes** | Where the pairing code is generated. |

**Google Cloud Console setup (once, 5 minutes):**
APIs & Services → OAuth consent screen (External, add yourself as a test user) →
Credentials → Create OAuth client ID → *Web application* → Authorised JavaScript
origins: `http://localhost:5173`, `https://<your-dashboard-domain>`. No redirect
URIs are needed for the ID-token flow.

---

## 5. Data model

Postgres on Neon. `uuid` PKs, `timestamptz` everywhere, every user-owned table has
`user_id` with `ON DELETE CASCADE` so `DELETE /account` is one statement plus a
storage sweep.

```
users(id, google_sub unique not null, email unique not null, email_verified bool,
      name, avatar_url, created_at, last_login_at)

sessions(id, user_id fk cascade, token_hash bytea unique, created_at,
         last_seen_at, expires_at, revoked_at, user_agent, ip_hash)

profiles(user_id pk fk cascade, full_name, phone, location, linkedin_url, naukri_url,
         github_url, portfolio_url, other_links jsonb, summary, skills text[],
         years_of_experience numeric, current_title, current_company, education jsonb,
         notice_period_days int, current_ctc_lpa numeric, expected_ctc_lpa numeric,
         work_authorization, resume_file_key, resume_parsed jsonb,
         parse_status, onboarding_step int default 1, onboarding_done bool default false,
         risk_accepted_at, updated_at)

preferences(user_id pk fk cascade, target_roles text[], domains text[],
            locations text[], work_mode text[], experience_level,
            platforms text[], active_hours jsonb, daily_cap int default 10,
            blacklist_companies text[], blacklist_keywords text[],
            created_at, updated_at)

qa_bank(id, user_id fk cascade, question_pattern, answer, source, approved bool,
        sensitive bool, times_used int default 0, created_at, updated_at,
        UNIQUE (user_id, question_pattern))

platform_connections(user_id fk cascade, platform, signed_in bool,
                     last_seen_at, PRIMARY KEY (user_id, platform))

extension_tokens(id, user_id fk cascade, token_hash bytea unique, scope default 'extension',
                 install_id, label, created_at, last_used_at, revoked_at)

extension_pairing_codes(id, user_id fk cascade, code_hash bytea unique, expires_at,
                        used_at, created_at)

applications(id, user_id fk cascade, platform, job_id, job_title, company, location,
             job_url, status, reason, screenshot_key, answers_used jsonb, run_id,
             trace_id, created_at, updated_at,
             UNIQUE (user_id, platform, job_id))

agent_runs(id, user_id fk cascade, platform, status, dry_run bool, started_at, ended_at,
           last_heartbeat_at, max_applications, window_end, applied_count,
           skipped_count, stuck_count, llm_calls, stop_reason)

CREATE UNIQUE INDEX one_running_run_per_user ON agent_runs (user_id) WHERE status = 'running';

safety_events(id, user_id fk cascade, run_id, type, detail jsonb, created_at, cooldown_until)
```

Enums as `CHECK` constraints (not PG enums) so adding a value is a one-line migration.

Statuses: `applied | dry_run | skipped | needs_attention | resolved | failed`.
Reasons: `external_redirect | already_applied | poor_fit | sensitive_question | low_confidence | captcha | form_error | interrupted | unknown_question`.

Plus LangGraph's checkpoint tables in the same database (separate namespace).

---

## 6. API surface

All routes under `/api`. Dashboard calls use the session cookie. Extension calls
use `Authorization: Bearer <extension token>` and are limited to the extension scope.

| Method | Path | Scope | Purpose |
|---|---|---|---|
| POST | `/auth/google` | none | `{credential}` ID token → set session cookie → user |
| POST | `/auth/dev-login` | none (dev only) | fake sign-in |
| POST | `/auth/logout` | dashboard | revoke session |
| GET | `/auth/me` | dashboard | user + onboarding state + platform chips |
| POST | `/resume` | dashboard | multipart upload → parse → draft |
| GET | `/resume/draft` | dashboard | current parsed draft |
| GET/PUT | `/profile` | dashboard | identity, links, skills, CTC, notice |
| GET/PUT | `/preferences` | dashboard | roles, locations, modes, caps, blacklists |
| POST | `/onboarding/complete` | dashboard | requires `risk_accepted_at` |
| GET/POST/PATCH | `/qa` | dashboard | answers list, create, edit, approve |
| POST | `/extension/pair` | dashboard | mint 8-char one-time code (10 min TTL) |
| POST | `/extension/connect` | none | `{code, install_id}` → extension token (once) |
| GET/DELETE | `/extension/tokens` | dashboard | list / revoke |
| POST | `/platform/status` | extension | signed-in state heartbeat per platform |
| GET | `/extension/resume-file` | extension | short-lived signed URL, active run only |
| POST | `/runs/start` | extension | policy check → run (409 if one is running) |
| POST | `/runs/{id}/heartbeat` | extension | also re-checks policy |
| POST | `/runs/{id}/stop` | extension | user pressed Stop |
| GET | `/runs/active` | dashboard | live run + counters |
| POST | `/agent/step` | extension | observation → actions |
| POST | `/applications/{id}/screenshot` | extension | stuck-step capture upload |
| GET | `/applications` | dashboard | `?since=&status=&platform=&limit=` |
| PATCH | `/applications/{id}` | dashboard | resolve / dismiss |
| GET | `/safety/status` | dashboard | caps, cooldown, active hours |
| DELETE | `/account` | dashboard | delete everything, revoke sessions |
| GET | `/health` | none | liveness + db check |
| POST | `/internal/sweep` | `CRON_SECRET` | heartbeat expiry, screenshot retention |

Every dashboard query is scoped by `user_id` from the session, **never** from the
request body. The extension scope can post observations and read its own run; it
cannot read `/profile`.

---

## 7. Auth design

### Dashboard (Google Identity Services)
1. `index.html` loads `https://accounts.google.com/gsi/client`.
2. The sign-in screen calls `google.accounts.id.initialize({client_id, callback})`
   and `renderButton` into a fixed-size slot (`theme: outline`, `shape: rectangular`,
   `size: large`, `text: continue_with`, `width: 320`). Google's brand guidelines
   require their button, so our design work goes into the screen around it.
3. Callback receives `credential` (a JWT) → `POST /api/auth/google`.
4. Backend verifies it with `google.oidc_id_token.verify_oauth2_token(credential,
   request, GOOGLE_CLIENT_ID)`; checks `email_verified`; upserts `users` on
   `google_sub`; creates a session row; sets cookie
   `aa_session` = `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=30d`.
5. Every request: hash cookie → look up `sessions` (not expired, not revoked) → user.
   Update `last_seen_at` at most once a minute.

Why this is safe: same-origin proxy (D3) means `SameSite=Lax` works and blocks
cross-site POSTs. Non-GET routes additionally require `X-Requested-With: XMLHttpRequest`,
which a cross-site form cannot set. No tokens in `localStorage`, so XSS cannot
exfiltrate a session.

### Extension pairing
1. Settings → **Connect extension** → `POST /api/extension/pair` → `{code, expires_at}`.
   Code is 8 chars from an unambiguous alphabet, stored as SHA-256, single-use, 10 min TTL.
2. Popup shows a "Paste your pairing code" field → `POST /api/extension/connect`
   with `{code, install_id, label}` → returns the bearer token **once**.
3. Extension stores it in `chrome.storage.local`; backend stores only the hash.
4. Settings lists installs with last-used time and a **Disconnect** button.

`install_id` is a random UUID generated on first run, used to label the install and
to avoid stacking duplicate tokens when someone re-pairs.

### Authorization tests (these are release blockers)
- User A's cookie cannot read user B's applications, profile, or run (403/404).
- Extension token on `/profile` or `/preferences` → 403.
- Extension token on another user's run id → 404.
- Revoked session → 401 on the next request.
- Revoked extension token → 401, and the popup shows "Reconnect".

---

## 8. Extension ↔ backend contract

Frozen in `packages/shared/contract.schema.json` before any UI or platform code is
written. TS types and Pydantic models are generated from it.

**Observation (extension → backend)**
```json
{
  "run_id": "uuid",
  "platform": "linkedin",
  "page_type": "apply_form",
  "job": {"id": "4012345", "title": "Backend Engineer", "company": "Acme",
          "location": "Pune, IN", "already_applied": false, "external": false},
  "elements": [
    {"ref": "f12", "kind": "text", "label": "Mobile number", "required": true, "value": ""}
  ],
  "chat": {"question": "What is your notice period?", "input_ref": "c1"},
  "page_text_digest": "optional short excerpt for fit/injection checks",
  "signals": []
}
```

**Action (backend → extension)**
```json
{
  "actions": [
    {"type": "fill_text", "ref": "f12", "value": "+91..."},
    {"type": "click", "ref": "b3"},
    {"type": "wait", "ms": 1200}
  ],
  "status": "continue",
  "reason": null
}
```

Rules, enforced by code on both sides:
- Action types are an allow-list: `fill_text | select_option | check | attach_resume | click | wait | submit | finish`.
- The LLM only ever emits `ref` handles from the current observation.
- The extension drops any action whose `ref` is unknown, and refuses to click anything
  that leaves the platform domain.
- `status: "hitl"` always carries a machine-readable `reason`.
- `page_type: "external"` or `job.external` → skip with `external_redirect`, no apply attempt.

`POST /agent/step` is the only agent endpoint: one observation in, one action batch
out. The graph is checkpointed on `thread_id = run_id`, so a reloaded tab resumes
where it stopped instead of restarting the application.

---

## 9. Agent and safety

### Answer resolution order (deterministic, cheapest first)
1. **Profile rules** — name, email, phone, location, links, notice period, current and
   expected CTC, total experience, current title/company, work authorization, relocation
   (from preferences), skill-specific years. **No LLM call.**
2. **`qa_bank`** — exact-normalised match on the question pattern, approved answers only.
3. **LLM classifier** (Groq) — `standard | sensitive | unknown`.
4. **LLM answer** (Nemotron/Groq) only for `standard` with high confidence, then saved
   to `qa_bank` with `approved=false, source=ai` and reused.
5. **HITL** — `sensitive`, `low_confidence`, `unknown_question`, or the per-run LLM cap is hit.

Sensitive = salary negotiation beyond the stated range, disability/health, gender,
caste, religion, demographics, visa/legal declarations, criminal history, or any
commitment absent from the profile. These always go to **Needs you**, never get guessed.

### Prompt-injection defence
Page and resume text is wrapped in delimited data blocks with a system rule that
nothing inside can change the task. Output is limited to allow-listed refs and
answers, so there is no free-form action surface. If page text contains
instructions aimed at an AI, the job is flagged `suspicious_content` and skipped.

### Loop shape
```
pick_job → already_applied? → skip
        → fit_check (rules, LLM only if unsure) → skip(poor_fit)
        → open_apply → external? → skip(external_redirect)
        → read_form/chat → answer → guardrail → HITL or fill+next → … → submit (skip in dry-run) → log
```
Every error edge routes to HITL with a reason and a job link.

### Safety governor (deterministic code; the LLM cannot override it)
Checked at `/runs/start`, re-checked on every heartbeat, and enforced again locally
in the content script so a compromised backend still can't spam.

| Rule | Default | Ceiling |
|---|---|---|
| Daily quota | `min(preferences.daily_cap, SAFETY_DAILY_CAP)` = 10 | 25 hard |
| Quota reset | 10:00 in the user's timezone (`SAFETY_DAY_RESET_HOUR`) | — |
| Hourly cap | 3 | 6 hard |
| Warm-up | first 14 days start at 5/day, step up weekly | — |
| Rest day | one per week (Sunday) | — |
| Action delay | 400–1800 ms randomised | min 250 ms |
| Pause between applications | 45–180 s | min 30 s |
| Long break | every 8 applications, 4–10 min | — |
| Active hours | user's window, default 09:00–21:00 | never overnight |
| Run window | 120 min, then graceful stop | 240 min |
| Concurrency | one run, one tab, one platform | hard |
| **Hard stop** | CAPTCHA, checkpoint, warning banner, forced logout, rate-limit page, 3 repeated errors, unrecognised page | stop + 24–48 h cooldown |

Hard stops write a `safety_events` row, end the run with `stop_reason`, and surface
in the dashboard as a banner: *"Paused for 24 hours. LinkedIn showed a security
check. Nothing was submitted."*

Heartbeat sweeper (APScheduler, every 60 s) marks runs `interrupted` when
`last_heartbeat_at` is older than `SAFETY_HEARTBEAT_TIMEOUT_SECONDS`. Extension loop
must live in the **content script of the visible tab**; the service worker only does
network calls and keep-awake (`chrome.power`).

---

## 10. Design system — "The Logbook"

Calm, ruled, precise. The identity comes from **layout, hairline rules, huge numerals
and mono timestamps**, not from a font trick. Explicitly banned: purple/blue gradients,
glassmorphism, grids of identical rounded cards, the default shadcn look, Inter,
emoji icons, stock illustrations, blobs, and the cream-plus-trendy-serif cliché.

### Tokens (`styles/tokens.css`, consumed by Tailwind)
| Token | Value | Use |
|---|---|---|
| `--paper` | `#F6F2EA` | app background |
| `--paper-sunk` | `#EFE9DE` | inset areas, table header |
| `--ink` | `#14110D` | primary text, headings |
| `--ink-2` | `#4A4238` | secondary text |
| `--ink-3` | `#6E6459` | meta, mono timestamps (≥4.5:1 on paper) |
| `--rule` | `#D9D1C2` | 1px hairlines |
| `--rule-strong` | `#B9AE9A` | section breaks, focus-adjacent |
| `--signal` | `#D9401B` | vermilion: primary action, live dot, active nav |
| `--signal-ink` | `#A62E10` | vermilion text on paper (AA) |
| `--moss` | `#3F6B46` | applied / success |
| `--ochre` | `#8A5A12` | needs you / caution |
| `--danger` | `#A32218` | destructive confirm |

Scale: 4px base. Radii: **2px** (stamps, inputs) and **4px** (dialogs) — nothing pill-shaped.
Shadows: only the dialog (`0 24px 60px -20px rgb(20 17 13 / .28)`); everything else uses rules.

### Type
One display face + one mono, **chosen in M2 by rendering the Today screen three times**.
Candidates: display — *Satoshi*, *Bricolage Grotesque*, *Cabinet Grotesk*; mono —
*Commit Mono*, *IBM Plex Mono*, *Martian Mono*. Reject any face that cannot show
tabular numerals (`font-variant-numeric: tabular-nums`) or that stops reading at 13px.
Self-host, subset, `font-display: swap`.

Scale: counter 96/88 (clamp to 56 on mobile), h1 40/44, h2 24/30, body 15/24,
meta 13/20, stamp 11/12 uppercase +0.08em, mono always for timestamps and IDs.

### The 8 components (built once in M2, reused everywhere)
1. `Button` — primary (ink fill), signal (vermilion fill), quiet (rule outline), destructive. 40px tall, 2px radius.
2. `Field` — label above, input with 1px rule, 2px signal focus ring, error text in danger, optional uncertain marker.
3. `Stamp` — uppercase status tag, 1px border in the status colour, 2px radius, rotated `-1deg`.
4. `Rule` — hairline divider with optional inline label.
5. `Stat` — huge tabular numeral + caption + optional delta.
6. `LedgerRow` — dense row: mono timestamp, title/company, platform, stamp, hover actions.
7. `Dialog` — Radix, 4px radius, ink/paper only, trap focus, Esc closes.
8. `Toast` — bottom-left, ink background, paper text, 4s, `aria-live="polite"`.

Plus two layout primitives: `AppShell` (232px left rail with hairline, content max 1200px)
and `ProgressRail` (onboarding).

### Motion
120–180 ms, `cubic-bezier(.2,.8,.2,1)`. Ledger rows slide in from `translateY(8px)`
with a 40 ms stagger; counters tick over 400 ms; the live dot pulses once per 2 s.
Everything is wrapped in `prefers-reduced-motion: reduce` (no transforms, no ticks).

### Accessibility (release blockers)
Focus-visible ring `2px var(--signal)` with 2px offset on every interactive element;
AA contrast everywhere; counters in `aria-live="polite"`; skip-to-content link;
full keyboard path through ledger and filters; form errors tied with `aria-describedby`.
Chrome/Edge desktop plus a working 390px layout for onboarding and ledger.

---

## 11. Screen specs

Each screen lists what must exist. **Every screen ships with empty, loading, error
and interrupted states** — that is not optional work at the end.

### Sign-in
Left: wordmark, one line of product truth (*"Applies to the jobs that fit. Tells you
when it can't."*), Google button in a 320px slot. Right: a single hairline-ruled
example ledger row rendered statically, so the product is visible before signup.
No hero image, no gradient.

### Onboarding (6 steps, progress rail, autosave)
| Step | Screen | Must include |
|---|---|---|
| 1 | Upload resume | Drop zone (drag + click, keyboard accessible), parsing state that streams found fields, failure state with the exact fallback copy, manual entry path |
| 2 | Review details | Prefilled fields, uncertain ones marked with a quiet ochre dot + tooltip, inline edit, "nothing is saved until you confirm" |
| 3 | What excites you | Role/domain chips pre-selected from the resume, add-your-own input, experience level segmented control |
| 4 | Where and when | Locations, remote/hybrid/onsite, joining availability (immediate/15/30/60/90), current and expected CTC in LPA, notice period |
| 5 | Usual answers | Common screening questions pre-answered for review; sensitive topics labelled *"I'll always ask you"* |
| 6 | Ready | Safety summary, privacy note, risk consent checkbox (**required**), live platform chips, extension install instructions |

Microcopy rules: second person, specific, no exclamation marks, no emoji.
*"Found 4 roles that fit you. Keep the ones you like."* not *"AI magic!"*.

### Today
Big counters (Applied / Skipped / Needs you) with tabular numerals, one live line
(*"Agent is on Naukri, 3 applied this hour"*) with a pulsing signal dot, quota shown
as a hairline meter with tick marks, platform chips, recent activity as ledger rows
that slide in as polling delivers them. Idle state: *"Nothing running. Open LinkedIn
or Naukri to start."*

### Ledger
Sticky header, hairline rows, filters inline in the header (platform / status / date),
mono timestamps, job title links out, the skip reason shown in ochre under skipped
rows. Empty state explains how the first row gets there. Pagination by
`?since=` cursor, 50 rows.

### Needs you
One column, 720px. Each item: job + company, platform, reason in plain language,
screenshot thumbnail (bordered, expandable), primary **Open on LinkedIn**, secondary
**Mark resolved**, tertiary **Ignore**. Nav badge shows the count. Zero state is a
positive one: *"Nothing needs you. The agent is handling it."*

### Answers
Grouped list (contact, experience, compensation, logistics), mono question text,
answer, source tag (You / Agent), inline edit, approve toggle. Editing is in v1 —
`PATCH /qa` already exists and it is the difference between usable and annoying.

### Settings
Roles, locations, work mode, caps and hours, blacklists, replace resume, extension
installs with **Disconnect**, and a bottom destructive zone (vermilion outline) for
**Delete my data** behind a typed confirmation.

### Extension popup
`Not signed in to app` → `Open LinkedIn / Naukri` → `Sign in to {platform}` →
`Ready: Start Magic` (with a **Practice run** toggle) → `Running` (counters, Pause,
Stop, "keep this tab visible in its own window") → `Paused / Cooldown / Interrupted`
with the reason and the next allowed time.

In-page banner: 320px, bottom-right, ink border on paper, same states, dismissible,
never covers the platform's own apply button.

---

## 12. Build order

Work top to bottom. Do not start a slice before the previous one's check passes.
Each slice is one focused session; feed only the files listed plus this document.

| # | Slice | Days | Done when |
|---|---|---|---|
| S0 | Contract freeze + monorepo skeleton + pnpm workspace + lint/format | 0.5 | `contract.schema.json` generates TS types and Pydantic models; nothing else exists yet |
| S1 | Backend foundation: settings, DB session, Alembic initial migration, `/health`, structlog, error envelope | 0.5 | `alembic upgrade head` on Neon; `/health` returns `{db: "ok"}` |
| S2 | Google auth + sessions + `/auth/me` + dev bypass + authz tests | 1 | Real Google sign-in works locally; session survives reload; 5 authz tests green |
| S3 | Design system: tokens, type test, 8 components, AppShell, motion, a11y pass | 1.5 | A `/styleguide` route renders every component and state; type pair chosen with a written reason |
| S4 | Profile, preferences, qa CRUD, resume upload → extract → LLM parse → draft | 1.5 | PDF and DOCX both parse into a draft; a scanned PDF returns the exact fallback message; rules-only mode still works without an API key |
| S5 | Onboarding UI, 6 steps, autosave, uncertain markers, consent gate | 1.5 | New user reaches Ready in under 4 minutes; refresh mid-step resumes at the same step |
| S6 | Today, Ledger, Needs you, Answers, Settings + polling + all four states | 1.5 | Counters update within 3 s of a new row; every screen has empty/loading/error/offline |
| S7 | Extension shell: WXT, pairing, platform + sign-in detection, popup states, Start Magic gating, dry-run toggle | 1.5 | Pairing works; LinkedIn shows Connected only when actually signed in; Start Magic is disabled until onboarding is done |
| S8 | Safety: `/runs/start` policy, caps, warm-up, cooldown, heartbeat, sweeper, local governor, pytest | 1 | Policy tests 100% green; second run returns 409; a stale heartbeat flips to `interrupted` within 90 s |
| S9 | Agent graph + `/agent/step` + platform base class + LinkedIn reader/actions | 2.5 | Fixture HTML produces correct observations; unknown page type → `hitl` with reason |
| S10 | LinkedIn Easy Apply end to end, dry-run then live on a test account | 1 | 10 dry-runs complete; 10 live applications land on a throwaway account with pacing |
| S11 | Naukri: search, in-site apply, chat questionnaire, external skip | 2 | CTC/notice answered from profile without an LLM call; chat completion logged |
| S12 | Answer engine: classifier, qa_bank reuse, guardrail, injection defence, HITL links | 1.5 | 30-question sensitive set routes correctly; CTC is never blocked; hostile prompt changes nothing |
| S13 | Stuck-step screenshots + 14-day retention job | 0.5 | Needs-you cards show a cropped screenshot; retention job deletes expired objects |
| S14 | Deploy, README, privacy note, demo script, polish pass | 1.5 | Public URL works for a stranger's Google account; delete-my-data verified end to end |

**Total ≈ 19 days solo.** Critical path is S1→S2→S4→S7→S9→S11; S3/S5/S6 can run in
parallel with S4/S7 if two people are working.

### If you have 9 days (hackathon cut)
S0, S1, S2, S3, S4, S5, S6, S7, minimal S8, S9, S10 dry-run + 5 live on a test
account, S14. Ship without Naukri (S11), with a read-only Answers page and one
screenshot state. **Never cut:** auth, authorization, the safety layer, Needs you.

---

## 13. Test plan

| Layer | What | Where |
|---|---|---|
| Unit | Answer resolution order, question normalisation, plan/cap math, token scopes | `backend/tests` |
| Policy | Caps, warm-up, active hours, cooldown, one-run-per-user, heartbeat expiry | `backend/tests/test_safety.py` |
| Authz | Cross-user isolation, extension scope limits, revocation | `backend/tests/test_authz.py` |
| Contract | Observation/action schema validation, unknown refs rejected | `backend/tests/test_agent_step.py` |
| Fixtures | Saved HTML of LinkedIn Easy Apply modal, Naukri apply + chat, external-redirect page, CAPTCHA page | `backend/tests/fixtures/` |
| Evals | 30 sensitive questions, 10 injection snippets, 5 resumes | `backend/evals/` |
| Manual | Dry-run on both platforms, live on a throwaway account, cooldown trigger, delete-my-data | README checklist |

Fixtures come from real pages saved once (DevTools → Save all). They keep selector
work free and stable, and they are the only way to test "unknown page → HITL" safely.

---

## 14. Deployment

| Piece | Where | Notes |
|---|---|---|
| Dashboard | Vercel | Rewrite `/api/:path*` → `https://<backend>/api/:path*` (this is what keeps cookies first-party) |
| Backend | Render (or Railway/Fly) | Single instance, `uvicorn`, APScheduler sweeper in-process; env from section 4 |
| DB | Neon free | Pooled URL for the app, unpooled for migrations |
| Files | Supabase Storage | Private bucket, no public access, signed URLs only. REST API by default (project keys are enough); S3 optional. No credit card needed, unlike R2. |
| Tracing | LangSmith free | `LANGSMITH_TRACING=true` in prod |
| Extension | Zip download from the repo/README | Load unpacked → `chrome://extensions` → Developer mode |

Also needed for "complete": a `README.md` with honest limitations (automation may
violate platform ToS and can get an account restricted — stated plainly, not buried),
and a support contact in Settings.

One-time ops jobs: screenshot retention (daily), heartbeat sweep (every minute),
session cleanup (daily). All three go through `/internal/sweep` behind `CRON_SECRET`.

---

## 15. Definition of done

- [ ] A stranger can sign in with Google in one click and never sees a password field.
- [ ] Onboarding is resume-first, autosaves, resumes mid-flow, and has a working manual fallback.
- [ ] Authorization is tested: cross-user access fails, the extension token cannot read the profile, revoked tokens stop working.
- [ ] The extension pairs with a code, detects both platforms, and only offers Start Magic after onboarding.
- [ ] Dry-run completes full flows on LinkedIn and Naukri without submitting.
- [ ] On a throwaway account the agent submits ≥10 applications per platform with human pacing; real accounts obey warm-up and caps.
- [ ] Naukri CTC/notice questions are answered from the profile; sensitive ones go to HITL.
- [ ] External redirects are skipped and logged with the job link.
- [ ] Ledger and counters update within 3 s without a refresh.
- [ ] Stuck cases appear in Needs you with a working link, a plain-language reason and a screenshot.
- [ ] A CAPTCHA or checkpoint stops the run instantly and starts a cooldown.
- [ ] Only one run per user can be active; an interrupted run is reported with the reason.
- [ ] Delete my data removes profile, resume, screenshots, applications and tokens.
- [ ] Every screen has designed empty, loading, error and interrupted states.
- [ ] The UI follows the Logbook direction and passes the banned-pattern checklist.
- [ ] Keyboard-only path works end to end; reduced-motion is respected; contrast is AA.
- [ ] README states the real limitations, and the demo script runs in under 5 minutes.

---

## 16. Open questions (answer before S0)

1. **Deadline and judging rubric** — decides whether Naukri ships.
2. **Do the $10 credits pay for building only, or runtime too?** If runtime, the LLM cap is the real budget.
3. **Throwaway LinkedIn + Naukri accounts** — needed before S10/S11. Required, not optional.
4. **Production domain** — needed for the Google authorised origin and the Vercel rewrite.