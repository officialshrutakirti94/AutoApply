/**
 * One typed client for the whole app.
 *
 * Everything is same-origin (`/api`), so the session cookie is first-party and
 * carried automatically. Writes also carry `X-Requested-With`, which the backend
 * requires as its CSRF gate — a cross-site form cannot set that header.
 */

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const CSRF_HEADER = { "X-Requested-With": "XMLHttpRequest" };

export class HttpError extends Error {
  status: number;
  code: string;
  details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  /** For multipart uploads: pass the FormData as body and skip the JSON header. */
  form?: FormData;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };

  if (method !== "GET") Object.assign(headers, CSRF_HEADER);

  let body: BodyInit | undefined;
  if (options.form) {
    body = options.form;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body,
    credentials: "include",
    signal: options.signal,
  });

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? safeJson(text) : null;

  if (!response.ok) {
    const error = (payload as { error?: { code?: string; message?: string; details?: unknown } })
      ?.error;
    throw new HttpError(
      response.status,
      error?.code ?? "http_error",
      error?.message ?? `Request failed (${response.status})`,
      error?.details,
    );
  }

  return payload as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------- types

export type Platform = "linkedin" | "naukri";
export type PlanTier = "regular" | "pro" | "pro_plus";
export type ApplicationStatus =
  | "applied"
  | "dry_run"
  | "skipped"
  | "needs_attention"
  | "resolved"
  | "failed";

export type User = {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  plan: PlanTier;
  created_at: string;
};

export type Me = {
  user: User;
  onboarding: {
    step: number;
    done: boolean;
    has_resume: boolean;
    parse_status: "none" | "pending" | "parsed" | "failed" | "manual";
    needs_risk_consent: boolean;
  };
  platforms: { platform: Platform; signed_in: boolean; last_seen_at: string | null }[];
  preferences_ready: boolean;
  llm: { enabled: boolean; max_calls_per_run: number };
};

export type Profile = {
  full_name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  linkedin_url: string | null;
  naukri_url: string | null;
  github_url: string | null;
  portfolio_url: string | null;
  other_links: string[];
  summary: string | null;
  skills: string[];
  years_of_experience: number | null;
  current_title: string | null;
  current_company: string | null;
  education: { degree?: string | null; institution?: string | null; year?: string | null }[];
  notice_period_days: number | null;
  current_ctc_lpa: number | null;
  expected_ctc_lpa: number | null;
  work_authorization: string | null;
  parse_status: string;
  onboarding_step: number;
  onboarding_done: boolean;
  has_resume: boolean;
};

export type Preference = {
  target_roles: string[];
  domains: string[];
  locations: string[];
  work_mode: string[];
  experience_level: string | null;
  platforms: Platform[];
  active_hours: { start: string; end: string; timezone: string };
  daily_cap: number;
  blacklist_companies: string[];
  blacklist_keywords: string[];
};

export type Run = {
  id: string;
  platform: Platform;
  status: "running" | "done" | "stopped" | "interrupted";
  dry_run: boolean;
  started_at: string;
  ended_at: string | null;
  last_heartbeat_at: string;
  window_end: string;
  max_applications: number;
  applied_count: number;
  skipped_count: number;
  stuck_count: number;
  llm_calls: number;
  stop_reason: string | null;
};

export type ActiveRun = {
  run: Run | null;
  today: {
    applied: number;
    dry_run: number;
    skipped: number;
    needs_attention: number;
    resolved: number;
    failed: number;
  };
  unresolved: number;
  heartbeat_seconds: number;
};

export type Application = {
  id: string;
  platform: Platform;
  job_id: string;
  job_title: string | null;
  company: string | null;
  location: string | null;
  job_url: string | null;
  status: ApplicationStatus;
  reason: string | null;
  reason_label: string | null;
  has_screenshot: boolean;
  answers_used: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type SafetyStatus = {
  allowed: boolean;
  message: string;
  reason: string | null;
  cooldown_until: string | null;
  usage: {
    applied_today: number;
    applied_last_hour: number;
    effective_daily_cap: number;
    effective_hourly_cap: number;
    warmup_cap: number;
    account_age_days: number;
    cooldown_until: string | null;
    active_hours: string;
    active_timezone: string;
    day_reset_hour: number;
    quota_resets_at: string | null;
    plan: PlanTier;
    plan_label: string;
    plan_daily_cap: number;
    plan_hourly_cap: number;
    llm_calls_per_day: number;
  };
  daily_ceilings: Record<string, number>;
};

export type PlanLimits = {
  tier: PlanTier;
  label: string;
  daily_cap: number;
  hourly_cap: number;
  llm_calls_per_day: number;
  price: string;
  blurb: string;
};

export type Plan = {
  plan: PlanTier;
  label: string;
  limits: PlanLimits;
  usage: SafetyStatus["usage"];
  available: PlanLimits[];
};

export type ResumeOut = {
  parse_status: string;
  message: string | null;
  draft: Record<string, unknown> | null;
  confidence: Record<string, string>;
  profile: Profile | null;
};

export type QaEntry = {
  id: string;
  question_pattern: string;
  answer: string;
  source: "user" | "ai";
  approved: boolean;
  sensitive: boolean;
  times_used: number;
  created_at: string;
  updated_at: string;
};

// ---------------------------------------------------------------- endpoints

export const api = {
  me: () => request<Me>("/api/auth/me"),

  signOut: () => request<void>("/api/auth/logout", { method: "POST" }),

  signInWithGoogle: (credential: string) =>
    request<Me>("/api/auth/google", { method: "POST", body: { credential } }),

  devSignIn: (email?: string) =>
    request<Me>("/api/auth/dev-login", { method: "POST", body: { email } }),

  profile: () => request<Profile>("/api/profile"),

  updateProfile: (patch: Partial<Profile> & { onboarding_step?: number }) =>
    request<Profile>("/api/profile", { method: "PUT", body: patch }),

  preferences: () => request<Preference>("/api/preferences"),

  updatePreferences: (patch: Partial<Preference>) =>
    request<Preference>("/api/preferences", { method: "PUT", body: patch }),

  completeOnboarding: () =>
    request<Me>("/api/onboarding/complete", {
      method: "POST",
      body: { risk_accepted: true },
    }),

  uploadResume: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ResumeOut>("/api/resume", { method: "POST", form });
  },

  resumeDraft: () => request<ResumeOut>("/api/resume/draft"),

  resumeFileUrl: () => request<{ url: string; expires_in: number }>("/api/resume/file-url"),

  useManualEntry: () => request<ResumeOut>("/api/resume/manual", { method: "POST" }),

  activeRun: () => request<ActiveRun>("/api/runs/active"),

  safety: () => request<SafetyStatus>("/api/safety/status"),

  plan: () => request<Plan>("/api/plan"),

  switchPlan: (plan: PlanTier) =>
    request<Plan>("/api/plan/switch", { method: "POST", body: { plan } }),

  applications: (params: {
    status?: ApplicationStatus;
    platform?: Platform;
    limit?: number;
    offset?: number;
    since?: string;
  } = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        search.set(key, String(value));
      }
    });
    const query = search.toString();
    return request<{ items: Application[]; total_unresolved: number }>(
      `/api/applications${query ? `?${query}` : ""}`,
    );
  },

  resolveApplication: (id: string, status: "resolved" | "skipped" = "resolved") =>
    request<Application>(`/api/applications/${id}`, { method: "PATCH", body: { status } }),

  screenshotUrl: (id: string) =>
    request<{ url: string; expires_in: number }>(`/api/applications/${id}/screenshot-url`),

  listAnswers: () => request<QaEntry[]>("/api/qa"),

  createAnswer: (input: { question: string; answer: string; sensitive?: boolean }) =>
    request<QaEntry>("/api/qa", { method: "POST", body: input }),

  updateAnswer: (id: string, patch: { answer?: string; approved?: boolean; sensitive?: boolean }) =>
    request<QaEntry>(`/api/qa/${id}`, { method: "PATCH", body: patch }),

  deleteAnswer: (id: string) => request<void>(`/api/qa/${id}`, { method: "DELETE" }),

  pairExtension: () =>
    request<{ code: string; expires_at: string; instructions: string }>(
      "/api/extension/pair",
      { method: "POST" },
    ),

  extensionTokens: () =>
    request<
      {
        id: string;
        label: string | null;
        install_id: string | null;
        created_at: string;
        last_used_at: string | null;
        revoked_at: string | null;
        active: boolean;
      }[]
    >("/api/extension/tokens"),

  revokeExtension: (id: string) =>
    request<void>(`/api/extension/tokens/${id}`, { method: "DELETE" }),

  deleteAccount: () => request<void>("/api/account", { method: "DELETE" }),
};