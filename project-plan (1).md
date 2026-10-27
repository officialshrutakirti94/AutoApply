# AutoApply Agent: Project Plan (v1, budget-aware)

> Upload a resume, confirm what we found, open LinkedIn or Naukri, press **Start Magic**. The agent applies to matching jobs while you do something else. Anything it can't finish lands in a "Needs you" inbox with a direct link.

---

## 0. How to Read This Plan

- **Sections 1-3** say what we build, what we cut, and how we stay inside the $10 credits.
- **Sections 4-9** are the technical design.
- **Sections 10-13** are the safety, security and privacy rules.
- **Sections 14-17** are milestones, risks and the definition of done.

**Assumption to confirm:** the $10 Alan AI credits are spent on *building* the project (AI-assisted code generation). Runtime LLM calls (Groq, Nemotron) run on their own free tiers. If the credits also pay for runtime inference, section 2 still applies, and the "LLM calls per run" cap in section 9 becomes your real spending limit.

---

## 1. What v1 Is (and Isn't)

**The promise:** setup takes minutes, then jobs get applied to automatically on **LinkedIn (Easy Apply)** and **Naukri (apply inside Naukri, including chat questions)**, with every result tracked live on the dashboard.

### In scope
| Area | What we build |
|---|---|
| Dashboard (React) | Auth, resume-first onboarding, Today, Ledger, Needs you, Answers (simple list), Settings |
| Backend (FastAPI) | Auth, authorization, profile and preferences, resume upload and parsing, run control, LangGraph agent |
| Extension (React, MV3) | Platform detection, Start Magic, page reading and acting, safety governor |
| Platforms | LinkedIn Easy Apply and Naukri in-site apply, one shared agent graph |
| HITL | Any interruption becomes a "Needs you" item with a link to the stuck step |
| Safety | Deterministic behaviour rules and a hard stop on any risk signal |
| **Dry-run mode** | Agent fills forms but stops before Submit (for building and demoing safely) |

### Out of scope for v1
- **External sites.** A job that redirects to a company site is **skipped** and logged as `external_redirect`, with the link kept on the dashboard.
- Per-job resumes and cover letters (V2)
- Other platforms, email tracking, OCR for scanned resumes, password reset, dark mode, analytics

---

## 2. Budget Plan ($10 credits)

### The principle
Credits are only wasted on **rework**. So we spend them on small, well-specified slices and never on regenerating things we haven't tested.

### Where costs come from
| Bucket | Plan |
|---|---|
| **Building** (Alan AI credits) | Spend only on work that is hard to do by hand. Write configs, migrations and boilerplate yourself or with free tools. |
| **Runtime LLM** (Groq, Nemotron) | Free tiers (verify current limits). Rules first, LLM last, with caching and a hard per-run call cap. |
| **Infra** | Neon free tier, Vercel/Netlify free tier, a free or hobby backend host, Supabase Storage free tier (S3-compatible), LangSmith free developer tier |

### Rules for spending credits well
1. **Freeze the contract first.** Finish the DB schema, API shapes and the extension-to-backend message format (section 6) *before* generating any UI or extension code. Changing a contract later costs far more than getting it right now.
2. **Vertical slices, one at a time.** One milestone per generation session, tested before the next starts.
3. **Feed this file as context.** Give the builder this plan plus only the files it needs, not the whole repo.
4. **Targeted edits, not regenerate-the-file.** Ask for specific changes and keep a "do not touch" list of finished, working files.
5. **Design once.** Build the design tokens and about 8 components in one pass (M2), then reuse them everywhere. No per-screen redesigns.
6. **Test with fixtures, not credits.** Use saved HTML snapshots of LinkedIn and Naukri pages to test the page-reading code instead of regenerating against live pages.
7. **Keep a reserve.** Hold back about $1.50 for bug-fixing at the end.

### Suggested credit allocation (rough guess, adjust as you go)
| Slice | Share |
|---|---|
| M1 Foundation (schema, auth) | ~$1.00 |
| M2 Design system | ~$1.00 |
| M3-M4 Resume parsing and onboarding | ~$1.75 |
| M5 Dashboard core | ~$1.25 |
| M6-M7 Extension shell and safety | ~$1.50 |
| M8 LinkedIn agent | ~$1.25 |
| M9 Naukri agent | ~$0.75 |
| M10-M11 HITL, evals, polish | ~$0.50 |
| **Reserve for fixes** | **~$1.00** |

These numbers are guesses, so re-check them after M2 and move credits between slices.

### Cut order if credits or time run short
1. Evals beyond a tiny golden set (tracing stays, since it's free)
2. Answers page editing (keep it read-only)
3. **Naukri** (the last must-have, so it's the first real feature to drop)
4. Never cut: auth and authorization, the safety layer, the Needs-you inbox

---

## 3. Time Estimates (solo, AI-assisted)

| # | Milestone | Days |
|---|---|---|
| M1 | Foundation (monorepo, schema, auth) | 1 |
| M2 | Design system | 1 |
| M3 | Resume to prefill | 1 |
| M4 | Onboarding UI | 1.5 |
| M5 | Dashboard core | 1.5 |
| M6 | Extension shell | 1 |
| M7 | Safety layer | 1 |
| M8 | Agent: LinkedIn | 2-3 |
| M9 | Agent: Naukri | 2 |
| M10 | LLM answering and HITL | 1 |
| M11 | Evals and polish | 1 |
| | **Total** | **~14-16 days** |

**If the hackathon is shorter, use the demo cut (~7-8 days):** M1-M6, a minimal M7, and M8 in dry-run plus a few live applications on a test account. Add M9 (Naukri) as time allows. Check the deadline and judging rules and tell me, and I'll tighten this table.

---

## 4. The Complete User Journey

```
PHASE A: SET UP (dashboard, one time, ~5 minutes)
 1. Sign up / log in
 2. Upload resume (text-based PDF or DOCX)
 3. We parse it and PREFILL everything, and the user reviews
    (if parsing fails: friendly message + manual entry)
 4. User picks the roles and domains they're excited about
 5. User sets where (locations, remote/hybrid/onsite) and
    how soon they can join (immediate / 15 / 30 / 60 / 90 days)
 6. User confirms usual answers to common screening questions
 7. "You're ready" screen with the risk notice:
    "Now sign in to LinkedIn and/or Naukri in this browser,
     then install the extension."
    Platform chips: Not connected -> Connected

PHASE B: RUN (browser)
 8. User opens LinkedIn or Naukri (already signed in)
 9. Extension detects the platform and the signed-in state
10. "Start Magic" prompt appears (popup + small in-page banner)
11. User clicks it, and the agent starts
12. User keeps the machine on, and the platform tab VISIBLE
    in its own browser window (see section 7)

PHASE C: TRACK AND RESCUE (dashboard)
13. Dashboard updates every few seconds: Applied / Skipped / Needs you
14. If the agent gets stuck: it logs the reason and a direct link to that
    job/step, then moves to the next job
15. User opens "Needs you", clicks the link, finishes on the platform,
    and marks it resolved
```

**Gate:** Start Magic is disabled until onboarding is complete.

---

## 5. Tech Stack

| Layer | Choice |
|---|---|
| Backend / API | FastAPI (async), Pydantic v2, SQLAlchemy 2 (async), Alembic |
| Agents | LangChain + **LangGraph** (graph, tools, interrupts) |
| Tracing and evals | **LangSmith** (free tier) |
| Database | **NeonDB** (Postgres, pooled connection string) |
| Agent state | `langgraph-checkpoint-postgres` on Neon |
| LLMs | **Groq** (fast, frequent calls) + **NVIDIA Nemotron** (resume parsing, harder answers), through `get_llm(task)` with fallback |
| Resume parsing | `pdfplumber` / `pypdf` and `python-docx` for text, LLM structured output for fields |
| Dashboard | React + Vite + TypeScript, Tailwind (custom tokens), Radix primitives (headless, custom-styled), TanStack Query, React Router, Framer Motion (light) |
| Extension | React + TypeScript on **WXT**, Manifest V3, Zustand |
| Live updates | **Polling** via TanStack Query (every 3-5 s while a run is active). Server-Sent Events can replace it later. |
| Auth | Email and password (argon2), JWT access + refresh |
| Files | Supabase Storage (S3-compatible), private bucket, signed URLs |
| Deploy | Backend on Render/Railway/Fly, dashboard on Vercel/Netlify, extension loaded unpacked |

**Why polling, not SSE:** it is simpler to build, more robust behind proxies, and looks the same to the user (the ledger updates by itself). That saves credits.

### Which LLM does what
| Task | Model |
|---|---|
| Resume parsing into structured profile and suggested roles | Nemotron (once per upload) |
| Classify a screening question (standard / sensitive / unknown) | Groq |
| Job-fit check | Groq (rules first, LLM only if the rules are unsure) |
| Free-text screening answers | Nemotron, or Groq for short ones |
| Fallback | Whichever provider is up |

Model names live in config, not code.

---

## 6. Contract Between Extension and Backend

**Decision (fixes the earlier duplicated-adapter mistake):**
- **The extension owns the page.** It holds the selectors, reads the DOM and performs actions. Code lives in `extension/src/platforms/{linkedin,naukri}`.
- **The backend owns decisions.** The LangGraph agent decides what to do, using a platform-neutral message format. There are no platform adapters on the backend.
- The format is defined once in `packages/shared` (JSON Schema, with TS types and Pydantic models generated from it).

### Observation (extension to backend)
```json
{
  "run_id": "…", "platform": "linkedin|naukri",
  "page_type": "search_results|job_detail|apply_form|chat_question|confirmation|external|unknown",
  "job": { "id": "…", "title": "…", "company": "…", "location": "…", "already_applied": false },
  "elements": [
    { "ref": "f12", "kind": "text|select|radio|checkbox|file|button",
      "label": "…", "options": ["…"], "required": true, "value": "" }
  ],
  "chat": { "question": "…", "input_ref": "c1" },
  "signals": ["captcha", "checkpoint", "warning_banner"]
}
```

### Action (backend to extension)
```json
{ "actions": [
    { "type": "fill_text|select_option|check|attach_resume|click|wait|finish",
      "ref": "f12", "value": "…" } ],
  "status": "continue|done|hitl|stop", "reason": "…" }
```

### Rules
- The LLM **never** sees or sends raw selectors or URLs. It only refers to `ref` handles the extension assigned.
- Actions are an allow-list, validated by code on both sides.
- The extension refuses any action that navigates away from the platform or clicks an external link.

---

## 7. Extension and Agent

### Brain and hands
- **Hands (extension):** runs in the user's real, signed-in Chrome. It reads the page and acts with human-like timing.
- **Brain (FastAPI + LangGraph):** receives an Observation and returns Actions.
- Known fields (name, email, phone, links, notice period, current and expected CTC, experience, location) are filled by **rules from the profile, with no LLM call.**

### Making the run loop reliable (MV3 reality)
- **The loop lives in the content script of the visible tab.** The service worker is only used for network calls, auth and the keep-awake request. It is never the thing that "stays alive".
- The service worker keeps a long-lived port to the content script, and all run state is on the server so any step is **resumable** if either side restarts.
- **The platform tab must stay visible.** Background tabs are throttled by Chrome. The UI therefore tells the user: *"Keep this tab open in its own window. You can keep working in another window."*
- The extension requests **keep-awake** (`chrome.power`, system level) only while a run is active. Closing the laptop lid still sleeps the machine, which we tell the user.
- If the tab closes or the heartbeat stops, the run is marked `interrupted` and the dashboard says so.

### Platform detection
- The content script matches the URL (`linkedin.com/jobs…`, `naukri.com…`) and checks the signed-in state.
- It reports status to the backend, so the dashboard chip flips to **Connected**.
- If the user isn't signed in: "Sign in to LinkedIn first, then I'll be right here."
- When signed in and onboarded, the **Start Magic** prompt appears.

### Platform behaviour
| | LinkedIn | Naukri |
|---|---|---|
| Search | Built from roles, locations, experience, Easy Apply filter, newest first | Built from roles, locations, experience, newest first |
| Apply | **Easy Apply only** (multi-step modal) | Apply **inside Naukri**, including the **chat questionnaire** |
| Resume | Use the account's saved resume by default, upload only if the form requires it | Same |
| Already applied | Skip if the platform shows "Applied" (`already_applied`) | Same |
| External apply | Skip (`external_redirect`) | Skip (`external_redirect`) |

### Resume attachment
When a form requires an upload, the extension asks `GET /extension/resume-file` for a **short-lived signed URL**, fetches the file, and attaches it to the file input. This is the one place the extension token touches the resume, and it only works during an active run.

### Agent graph (shared)
```
pick_job -> already_applied? -(yes)-> skip
   |no
fit_check -(no)-> skip
   |yes
open_apply -> external? -(yes)-> skip(external_redirect)
   |no
read_form/chat <------------------------------+
   |                                          |
answer (profile rules -> qa_bank -> LLM)      |
   |                                          |
guardrail -(sensitive / low confidence)-> HITL (log + link, move on)
   |ok                                        |
fill + next ----------------------------------+
   |
submit (skipped in dry-run) + verify -> log -> governor sets the next pause
```
Checkpoints in Neon, and every error edge routes to HITL (reason, job link, screenshot).

### Dry-run mode
- A toggle on **Start Magic** ("Practice run: fill but don't submit").
- The agent goes through the whole flow, stops at the final review step, and logs the job as `dry_run`.
- This is how you develop and demo without spending real applications or risking an account.

### One active run per user
- A partial unique index allows only one `running` row per user in `agent_runs`.
- The run sends a heartbeat every ~20 s, and a run with no heartbeat for a few minutes is marked `interrupted`, so a new one can start.

---

## 8. Backend: Auth, Authorization and Data

### Authentication
- `POST /auth/register`, `/login`, `/refresh`, `/logout`, `GET /auth/me`
- Passwords hashed with argon2. The **access token is held in memory** by the dashboard, and the **refresh token is an httpOnly, secure, same-site cookie.**
- **No email verification in v1** (no email budget). This is a known gap, mitigated by auth rate limits. Password reset and email verification come in v1.1.

### Authorization
- **Every query is scoped by `user_id` from the token**, never from the request body.
- Two token scopes:
  - `dashboard`: full access to the user's own data
  - `extension`: can post status, request permits, send observations, report applications, and fetch the resume file during an active run, and **cannot read the profile or change anything else**
- Extension tokens are stored **hashed** in `extension_tokens`, so Settings can **revoke** them ("Disconnect extension").
- Rate limits on auth endpoints, and uploads limited by type (PDF/DOCX) and size.

### Resume parsing pipeline
```
Upload -> validate -> store (private) -> extract text -> LLM structured output -> validate -> drafts
```
- **Text-based PDFs and DOCX only.** If no text can be extracted (scanned file), show: *"We couldn't read this file. Upload a text-based PDF or DOCX, or fill your details in manually."* OCR is v1.1.
- Extracted fields each carry a confidence flag so the UI can highlight uncertain ones.
- **Nothing is final until the user confirms in the review step.**
- Manual entry is always available as a fallback.

### Data model
```
users        (id, email, password_hash, created_at)

profiles     (user_id, full_name, phone, email, location,
              linkedin_url, naukri_url, github_url, portfolio_url,
              other_links jsonb, summary, skills[],
              years_of_experience, current_title, current_company,
              education jsonb,
              notice_period_days,            -- 0 = immediate
              current_ctc_lpa, expected_ctc_lpa,
              work_authorization,
              resume_file_key, resume_parsed jsonb,
              onboarding_step, onboarding_done bool,
              risk_accepted_at)

preferences  (user_id, target_roles[], domains[], interests[],
              locations[], work_mode[]  -- remote | hybrid | onsite,
              experience_level  -- entry | mid | experienced,
              platforms[],
              active_hours jsonb, daily_cap,
              blacklist_companies[], blacklist_keywords[])

qa_bank      (id, user_id, question_pattern, answer,
              source  -- user | ai, approved bool, sensitive bool)

platform_connections (user_id, platform, signed_in bool, last_seen_at)

extension_tokens (id, user_id, token_hash, scope, created_at,
                  last_used_at, revoked_at)

applications (id, user_id, platform, job_id, job_title, company,
              location, job_url,
              status  -- applied | dry_run | skipped | needs_attention | resolved | failed,
              reason  -- external_redirect | already_applied | poor_fit | sensitive_question |
                         low_confidence | captcha | form_error | interrupted,
              screenshot_key, answers_used jsonb,
              run_id, trace_id, created_at, updated_at,
              UNIQUE (user_id, platform, job_id))

agent_runs   (id, user_id, platform, status  -- running | done | stopped | interrupted,
              dry_run bool, started_at, ended_at, last_heartbeat_at,
              max_applications, window_end,
              applied_count, skipped_count, stuck_count,
              llm_calls, stop_reason,
              UNIQUE (user_id) WHERE status = 'running')

safety_events (id, user_id, run_id, type, detail, created_at, cooldown_until)
```
Plus LangGraph's checkpoint tables. (The old `run_permits` and `agent_steps` tables are removed: the permit fields live on `agent_runs`, and step detail lives in LangSmith traces linked by `trace_id`.)

### API surface
| Group | Endpoints |
|---|---|
| Auth | register, login, refresh, logout, me |
| Resume | `POST /resume`, `GET /resume/draft` |
| Profile | `GET/PUT /profile`, `GET/PUT /preferences`, `POST /onboarding/complete` |
| Answers | `GET/POST/PATCH /qa` |
| Extension | `POST /extension/connect`, `POST /platform/status`, `GET /extension/resume-file`, `POST /runs/start` (policy check), `POST /runs/{id}/heartbeat`, `POST /runs/{id}/stop` |
| Agent | `POST /agent/step` |
| Applications | `GET /applications?since=…`, `PATCH /applications/{id}` (resolve) |
| Safety | `GET /safety/status` |
| Data | `DELETE /account` (deletes everything, see section 12) |

---

## 9. Controlling LLM Usage

The goal is a near-zero runtime bill and no surprise limits.

1. **Rules before LLM.** Standard fields and known questions never reach the LLM.
2. **Cache answers.** A new question is answered once, saved to `qa_bank`, and reused.
3. **Hard cap per run** (`llm_calls`, for example 30-40). When reached, the agent sends further unknowns to HITL instead of calling the LLM.
4. **Small prompts.** Send only the question, the options and the relevant profile fields, never the whole profile or page.
5. **Small model first.** Groq for classification and short answers, Nemotron only for resume parsing and genuinely hard answers.
6. **Backoff and fallback.** Retry with backoff, then switch provider. If both are rate-limited, **pause the run and tell the user** rather than guessing.

---

## 10. Safety Rules (protect the user's accounts)

> No design can guarantee an account won't be restricted, because automating these platforms goes against their terms of use. The defaults below are **conservative guesses, not tested platform limits**, so tune them with experience. The system keeps risk low by acting slowly and humanly and by stopping at the first sign of friction. The user sees and accepts this during onboarding, and the README says it plainly.

**Rules are deterministic code. The LLM cannot override them.** The backend checks permission at `runs/start` and on heartbeats. The extension's Safety Governor controls every action locally.

| Rule | Default (configurable, with hard ceilings) |
|---|---|
| Warm-up | New accounts start low (around 5/day) and step up over 2-3 weeks |
| Caps | A hard daily ceiling (around 25) and an hourly cap, per platform |
| Rest | One rest day a week |
| Timing | Randomized delays on every action, longer random pauses between applications, occasional longer breaks |
| Active hours | Only inside the user's configured window, never overnight |
| Realism | Natural typing speed, scroll and hover, a short "reading" time before applying |
| Environment | User's own Chrome and session only: no headless or cloud browser, no proxy or VPN, no credentials handled by us |
| Concurrency | One tab, one run, one platform at a time |
| Quality | Skip poor-fit jobs, never submit low-confidence answers, never re-apply |
| **Hard stop** | CAPTCHA, security checkpoint, warning banner, forced logout, rate-limit page, 3 repeated errors, or an unrecognized page: **stop, log, and start a cooldown (24-48h)** |
| Control | Visible "Agent running" indicator, Pause and Stop buttons |

### What counts as sensitive (always HITL, never auto-answered)
Free-text salary negotiation or flexibility beyond the stated range, disability or health, gender, caste, religion or other demographic questions, visa or legal declarations, criminal history, and any commitment not already in the profile.

### What is **not** sensitive (answered from the profile automatically)
**Current CTC, expected CTC, notice period, total and relevant experience, current location, willingness to relocate (if set in preferences), and skill-specific years of experience.** These are the standard Naukri chat questions, and they must not all fall into HITL.

### Demo mode vs real accounts
- **Real accounts** always follow warm-up and caps.
- **Demos and development** use **dry-run** (fills, doesn't submit) and/or a **throwaway test account** with a clearly labelled developer flag that relaxes the caps. The flag is off by default and never offered in the public UI.

---

## 11. Prompt-Injection Defence

Job descriptions, recruiter chat messages and resume text are **untrusted input** that reaches an LLM, and a hostile post could try to steer the agent.

1. **Data, not instructions.** Page text is passed inside clearly delimited blocks, with a system rule that nothing inside them can change the task.
2. **No free-form tools.** The LLM can only produce answers to specific questions and allow-listed actions (section 6), all validated by code.
3. **Handles only.** Actions reference `ref` ids from the current observation. They can't open URLs, run scripts or navigate off-platform.
4. **Answer provenance.** A value typed into a field must come from the profile, the approved `qa_bank`, or a validated LLM answer to *that* field's question.
5. **No secrets in context.** Tokens, passwords and other users' data never enter a prompt.
6. **Suspicion triggers HITL.** If page text contains instructions aimed at an AI ("ignore previous…", "send your resume to…"), the job is flagged and skipped.

---

## 12. Privacy and Data Handling

- **Minimum data:** collect only what the application flow needs.
- **What goes to LLM providers:** the full resume text goes to the parsing model once, and only the question, the options and the relevant profile fields go for screening answers. Names, emails and phone numbers are **not** sent to the classifier. The onboarding screen states this.
- **Storage:** the resume is stored in a **private bucket**, accessed only through short-lived signed URLs.
- **Screenshots:** captured only for stuck steps and cropped to the application dialog where possible. **Auto-deleted after 14 days.**
- **Delete my data:** Settings has a button, backed by `DELETE /account`, that removes the profile, resume, screenshots, applications and tokens.
- **Logs:** traces avoid raw personal fields where possible, and LangSmith project access is limited to the team.
- **Notice:** a short privacy note at signup explains the above in plain language.

---

## 13. Dashboard: Design Direction

**Goal: minimal, memorable, and unmistakably not a template.**

### Avoid
Purple and blue gradients, glassmorphism, grids of identical rounded cards, the default shadcn look, Inter-everywhere, emoji icons, stock illustrations, floating blobs. **Also avoid the newer cliché:** cream background with a trendy serif headline used as the only identity.

### Concept: "The Logbook"
Job hunting as a **logbook the agent keeps for you**: calm, ruled, precise, with one loud accent. The identity comes from **layout and behaviour**, not from a font trick.

| Element | Direction |
|---|---|
| Palette | Warm off-white, near-black ink, **one** signal accent (vermilion), moss for success, ochre for caution |
| Type | One distinctive display face and one mono for timestamps and IDs, **chosen in M2 by testing 2-3 candidates on the Today screen**, not picked up front. Avoid Inter and the most overused display fonts. |
| Structure | Hairline rules instead of boxed cards, generous whitespace, strong left alignment, **very large numerals** |
| Signature move | The **ledger**: dense rows, mono timestamps, stamp-like status tags (APPLIED / SKIPPED / NEEDS YOU) |
| Motion | Rows slide in when the agent logs them, numbers tick up, one pulse on the live indicator, and it respects reduced-motion |
| Components | Radix primitives fully re-skinned with our tokens |
| Icons | One thin-line icon library, used sparingly (no custom icon set in v1) |
| Responsive | Desktop-first. On small screens the ledger collapses into stacked rows, and onboarding works on a phone. |

### UX principles
1. **Resume first.** Upload, review, confirm, with no blank forms.
2. **Review, don't type.** Parsed fields are prefilled, and uncertain ones are marked so users only check what matters.
3. **Autosave everywhere** and resume at the same step.
4. **One decision per screen** in onboarding, with a progress rail.
5. **Always show what's next.** One clear primary action per screen.
6. **Live, not refreshed.** Counters and the ledger update on their own.
7. **Rescue in one click.** "Needs you" opens the exact stuck page.
8. **Plain language** microcopy ("Found 4 roles that fit you. Keep the ones you like.").
9. **Honest states.** Empty, loading, error and "run interrupted" states are designed, not afterthoughts.

---

## 14. Dashboard Screens

### Onboarding (6 steps, progress rail)
| Step | Screen | Notes |
|---|---|---|
| 1 | **Upload resume** | Drop zone, then a calm parsing state that streams what it found. Failure state with a manual fallback. |
| 2 | **Review your details** | Prefilled identity, links, skills, experience. Uncertain fields marked. |
| 3 | **What excites you** | Suggested roles and domains as chips (pre-selected from the resume) plus add-your-own, and an experience level picker |
| 4 | **Where and when** | Locations, remote/hybrid/onsite, joining availability, current and expected CTC |
| 5 | **Your usual answers** | Defaults for common screening questions, with sensitive topics labelled "I'll always ask you" |
| 6 | **You're ready** | Safety summary, privacy note and risk consent. Message: *"Now sign in to LinkedIn and/or Naukri in this browser, then install the extension."* Live platform chips. |

### Main app
| Screen | Contents |
|---|---|
| **Today** | Big counters (Applied / Skipped / Needs you), a live "agent is…" line, quota used, platform chips, recent activity |
| **Ledger** | Table with filters for platform, status and date, a link to each job, and the reason on skipped items |
| **Needs you** | Cards with job, platform, reason, screenshot and a primary **Open on LinkedIn/Naukri** button, then **Mark resolved**. Nav badge shows the count. |
| **Answers** | Read-only list of saved answers in v1 (editing in v1.1) |
| **Settings** | Roles, locations, caps and hours, blacklist, disconnect extension, replace resume, delete my data |

### Extension popup states
`Not signed in to app` -> `Open LinkedIn/Naukri` -> `Sign in to {platform}` -> `Ready: Start Magic (with a "practice run" toggle)` -> `Running (counters, Pause, Stop, keep-this-tab-visible note)` -> `Paused / Cooldown / Interrupted (reason)`.

---

## 15. Evals and Observability (lean)

Tracing is free and always on. Evals stay small.

| Eval | Dataset | Target |
|---|---|---|
| Sensitive-question routing | ~30 labelled questions (sensitive and not) | Sensitive recall at or near 100%, and a **low false-positive rate** so CTC and notice-period questions are not blocked |
| Answer groundedness | The same questions against a sample profile | No invented facts |
| Resume parsing | ~5 resumes (synthetic or your own, LLM-generated to save time) | Tracked per change |
| Injection check | ~10 hostile job/chat snippets | None change the agent's behaviour |
| Policy tests (pytest) | Caps, cooldowns, active hours, single run per user | 100% pass |

Compare Groq and Nemotron on the same sets before fixing the defaults.

---

## 16. Repo Structure

```
autoapply/
├── backend/
│   ├── app/
│   │   ├── api/             # auth, resume, profile, agent, applications
│   │   ├── core/            # config, security, token scopes
│   │   ├── db/              # models, sessions, alembic
│   │   ├── resume/          # extract text + LLM parsing
│   │   ├── agents/
│   │   │   ├── graph.py
│   │   │   ├── nodes/
│   │   │   ├── tools.py     # allow-listed actions only
│   │   │   └── llm.py       # get_llm(task): Groq / Nemotron
│   │   ├── safety/          # policy, cooldowns, run limits
│   │   └── main.py
│   ├── evals/
│   └── tests/
├── dashboard/               # React + Vite
├── extension/               # React + WXT
│   └── src/platforms/       # linkedin/ and naukri/: selectors, page reading, actions
├── packages/shared/         # JSON Schema contract + generated TS types + API client
└── README.md
```

---

## 17. Build Milestones, Risks and Definition of Done

### Milestones
| # | Milestone | Deliverable |
|---|---|---|
| M1 | **Foundation** | Monorepo, FastAPI, Neon + Alembic schema, auth, scoped authorization, **frozen contract (section 6)** |
| M2 | **Design system** | Tokens, type test, re-skinned components, app shell, empty/error states |
| M3 | **Resume to prefill** | Upload, extraction, LLM parsing, draft API, failure fallback |
| M4 | **Onboarding UI** | 6 steps with autosave, highlighted uncertain fields, chips, "You're ready" |
| M5 | **Dashboard core** | Today, Ledger, Needs you, Answers (read-only), Settings, polling updates |
| M6 | **Extension shell** | Popup, extension token, platform and sign-in detection, live chips, Start Magic gating, dry-run toggle |
| M7 | **Safety layer** | Run start policy, caps, warm-up, cooldown, heartbeat, one run per user, Governor (delays, hours, kill switch, keep-awake), tests |
| M8 | **Agent: LinkedIn** | Graph, platform code in the extension, Easy Apply (dry-run first, then live on a test account) |
| M9 | **Agent: Naukri** | Naukri code including chat questions, external skip |
| M10 | **Answering and HITL** | Classifier, `qa_bank`, guardrail, injection defence, Needs-you links to the stuck step |
| M11 | **Evals and polish** | Datasets, evaluators, privacy cleanup job, demo video, README |

### Risks and mitigations
| Risk | Mitigation |
|---|---|
| Account restrictions | Section 10 rules, consent screen, honest README, dry-run for dev |
| Layout changes | Selectors per platform in one folder, fixture-based tests, unknown page means HITL |
| MV3 worker sleeps, tab throttled, laptop sleeps | Loop in the visible tab's content script, resumable server state, heartbeat, keep-awake, clear user guidance |
| Naukri chat blocked by CTC questions | Profile-answered list in section 10 |
| Prompt injection | Section 11 |
| Personal data exposure | Section 12 |
| Wrong or invented answers | Provenance rule, confidence threshold, approved `qa_bank` |
| LLM free-tier limits | Section 9 cap, caching, fallback, pause instead of guess |
| Resume parse failures | Manual entry fallback, confidence flags, user review |
| Credit overrun | Section 2 rules, cut order and reserve |
| Duplicate applications | Unique constraint plus the platform's "Applied" badge check |
| Two simultaneous runs | Partial unique index and heartbeat expiry |
| Neon cold starts | Pooled string, async driver |

### Known limitations in v1 (stated, not hidden)
No email verification or password reset, no OCR for scanned resumes, no external-site applying, no weekly analytics, the platform tab must remain visible, and the safety defaults are untested guesses.

### Before you start (checklist)
- [ ] Confirm what the $10 Alan AI credits pay for (building, runtime, or both)
- [ ] Read the hackathon rules and judging criteria, and confirm the deadline so the time table can be tightened
- [ ] Create a **throwaway LinkedIn and Naukri account** for testing
- [ ] Save HTML snapshots of key pages for fixture tests

### Roadmap after v1
**V1.1:** password reset, email verification, OCR, editable answers, SSE · **V2:** external sites, tailored resumes and cover letters · **V3:** more platforms, response tracking · **V4:** conversion analytics

### Definition of done for v1
- [ ] A new user can sign up, upload a text-based resume, and see details, roles and domains prefilled, with a working manual fallback
- [ ] Onboarding finishes with the "sign in to LinkedIn/Naukri" message and the risk and privacy consent
- [ ] Authorization is tested: users reach only their own data, the extension token can't read the profile, and tokens can be revoked
- [ ] The extension detects LinkedIn and Naukri, shows them as connected, and offers **Start Magic** only after onboarding
- [ ] **Dry-run** completes full flows on both platforms without submitting
- [ ] On a **test account**, the agent submits at least 10 applications per platform with human-like pacing, and **real accounts are limited by warm-up and caps**
- [ ] Naukri chat questions like CTC and notice period are answered from the profile, while sensitive ones go to HITL
- [ ] External redirects are skipped and logged with the job link
- [ ] The ledger and counters update automatically within a few seconds
- [ ] Stuck cases appear in **Needs you** with a working link, reason and screenshot
- [ ] A CAPTCHA or checkpoint stops the run immediately and starts a cooldown
- [ ] Only one run per user can be active, and an interrupted run is reported
- [ ] "Delete my data" removes everything, and screenshots expire after 14 days
- [ ] The small eval suite passes, including sensitive routing and injection checks
- [ ] The UI follows the Logbook direction and avoids generic template styling
