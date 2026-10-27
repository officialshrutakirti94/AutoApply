import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileText,
  Loader2,
  Plus,
  Upload,
  X,
} from "lucide-react";
import { Logo } from "@/components/Logo";
import { Button, Chip, Field, Input, Rule, Stamp } from "@/components/ui/primitives";
import { api, HttpError, type Platform, type Preference, type Profile } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useSetupState, useAutosave } from "@/hooks/useSetup";

/* ---------------------------------------------------------------------------
   Setup: Hi {name} -> resume -> details -> where & when -> consent.
   Resume comes first on purpose: it prefills everything after it.
   --------------------------------------------------------------------------- */

const CAREER_FIELDS = [
  "Software",
  "Data & AI",
  "Design",
  "Product",
  "Marketing & Growth",
  "Operations",
];

const ROLE_SEEDS: Record<string, string[]> = {
  Software: ["Backend Engineer", "Frontend Engineer", "Full Stack Engineer", "DevOps Engineer", "QA Engineer"],
  "Data & AI": ["AI Engineer", "ML Engineer", "Data Scientist", "Data Engineer", "Data Analyst"],
  Design: ["Product Designer", "UI Designer", "UX Researcher"],
  Product: ["Product Manager", "Associate Product Manager"],
  "Marketing & Growth": ["Marketing Specialist", "Content Writer", "SEO Specialist", "Growth Manager"],
  Operations: ["Operations Executive", "Business Analyst", "Customer Success"],
};

const NOTICE_OPTIONS = [0, 15, 30, 60, 90];

export function Setup() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const state = useSetupState();
  const autosave = useAutosave();
  const [screen, setScreen] = useState(0);
  const [error, setError] = useState<string | null>(null);
  // 0 = idle, 1 saving profile, 2 saving preferences, 3 opening the dashboard.
  const [finishStage, setFinishStage] = useState<0 | 1 | 2 | 3>(0);
  const finishing = finishStage > 0;

  const { profile, preferences, patchProfile, patchPreference, clearDirty, saveProfile, savePreferences, resume } = state;

  // Always read the newest values when finishing: an awaited save must not use a
  // closure captured before the last chip click was committed.
  const latest = useRef({ profile, preferences });
  latest.current = { profile, preferences };

  const setFieldValue = <K extends keyof Profile,>(key: K, value: Profile[K]) => {
    const patch = { [key]: value } as Partial<Profile>;
    patchProfile(patch);
    autosave.queue("profile", () => saveProfile.mutateAsync(patch));
  };

  const setPreferenceValue = <K extends keyof Preference,>(key: K, value: Preference[K]) => {
    const patch = { [key]: value } as Partial<Preference>;
    patchPreference(patch);
    autosave.queue("prefs", () => savePreferences.mutateAsync(patch));
  };

  // Seed the role chips from the parsed resume, once, and only while the user has
  // not chosen anything themselves.
  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current) return;
    const suggested = (resume?.draft as { suggested_roles?: string[] } | null)?.suggested_roles;
    const suggestedDomains = (resume?.draft as { suggested_domains?: string[] } | null)
      ?.suggested_domains;
    // The person's own job title is the best role suggestion there is; a resume
    // that lists "AI Engineer" should not be turned into "Infra & DevOps".
    const fromTitle = profile.current_title ? [profile.current_title] : [];
    const candidates = [...new Set([...fromTitle, ...(suggested ?? [])])];
    if (!candidates.length || (preferences.target_roles?.length ?? 0) > 0) return;
    seeded.current = true;
    const patch: Partial<Preference> = { target_roles: candidates.slice(0, 5) };
    if (suggestedDomains?.length) patch.domains = [suggestedDomains[0]];
    patchPreference(patch);
    void savePreferences.mutateAsync(patch).catch(() => {});
  }, [resume, profile.current_title, preferences.target_roles, patchPreference, savePreferences]);

  // Already finished: never show setup again.
  useEffect(() => {
    if (state.me?.onboarding.done) navigate("/app", { replace: true });
  }, [state.me?.onboarding.done, navigate]);

  if (state.isLoading) {
    return (
      <Shell>
        <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3">
          <Loader2 size={12} className="animate-spin" />
          Loading your profile
        </div>
      </Shell>
    );
  }

  const firstName = (profile.full_name ?? state.me?.user.name ?? "").split(" ")[0] || "there";

  const canContinue = [
    true, // screen 0: resume is optional (manual entry is always allowed)
    Boolean(profile.full_name?.trim()) &&
      Boolean(preferences.target_roles?.length) &&
      Boolean(preferences.experience_level),
    Boolean(preferences.platforms?.length) &&
      Boolean(preferences.locations?.length) &&
      Boolean(preferences.target_roles?.length),
  ][screen];

  // A disabled button with no explanation is a dead end. Say exactly what is
  // missing, on the screen where the user is stuck.
  const missing: string[] = [];
  if (screen === 1) {
    if (!profile.full_name?.trim()) missing.push("your full name");
    if (!preferences.target_roles?.length) missing.push("at least one target role");
    if (!preferences.experience_level) missing.push("your experience level");
  }
  if (screen === 2) {
    if (!preferences.locations?.length) missing.push("a location");
    if (!preferences.platforms?.length) missing.push("at least one platform");
    if (!preferences.target_roles?.length) missing.push("at least one target role");
  }

  async function next() {
    setError(null);

    // Screen 1 (details): advancing must never wait on the network. The debounced
    // saves are already in flight, so advance immediately and let them settle.
    if (screen === 1) {
      void saveProfile.mutateAsync(profile).catch(() => {});
      void savePreferences.mutateAsync(preferences).catch(() => {});
      void saveProfile.mutateAsync({ onboarding_step: 3 }).catch(() => {});
      setScreen(2);
      return;
    }

    if (screen !== 2) {
      setScreen(screen + 1);
      return;
    }

    if (finishing) return;

    // Screen 2 (where and when): this one does have to wait. Onboarding cannot
    // complete until the preferences and roles are actually stored, or the backend
    // rejects it with a 422 telling us exactly which field is missing.
    try {
      autosave.cancel();
      setFinishStage(1);
      await saveProfile.mutateAsync(latest.current.profile);
      setFinishStage(2);
      await savePreferences.mutateAsync(latest.current.preferences);
      setFinishStage(3);
      await api.completeOnboarding();
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      navigate("/app", { replace: true });
    } catch (cause) {
      console.error("setup finish failed:", cause);
      setFinishStage(0);
      setError(
        cause instanceof HttpError
          ? cause.message
          : "Could not finish setup. Check the fields above and try again.",
      );
    }
  }

  return (
    <Shell step={screen}>
      {screen === 0 ? (
        <Greeting
          name={firstName}
          onParsed={clearDirty}
          onNext={() => setScreen(1)}
          onManual={async () => {
            await api.useManualEntry().catch(() => {});
            setScreen(1);
          }}
          profileName={profile.full_name ?? null}
          hasResume={Boolean(profile.has_resume)}
        />
      ) : null}

      {screen === 1 ? (
        <Details
          profile={profile}
          preferences={preferences}
          saveState={autosave.state}
          onChange={setFieldValue}
          onPreference={setPreferenceValue}
        />
      ) : null}

      {screen === 2 ? (
        <WhereAndWhen preferences={preferences} onPreference={setPreferenceValue} />
      ) : null}

      {error ? (
        <p
          role="alert"
          className="mt-6 rounded-stamp border border-danger/40 bg-danger/5 px-3.5 py-2.5 text-[12.5px] text-danger"
        >
          {error}
        </p>
      ) : null}

      {missing.length ? (
        <p className="mt-8 flex flex-wrap items-baseline gap-x-3 gap-y-1 border-l-2 border-ochre/60 pl-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-ochre">
            Still needed
          </span>
          <span className="text-[12.5px] text-ink-2">{missing.join(" · ")}</span>
        </p>
      ) : null}

      <div className="mt-6 flex items-center justify-between border-t border-line pt-5">
        <Button
          variant="ghost"
          onClick={() => setScreen((current) => Math.max(0, current - 1))}
          disabled={screen === 0 || finishing}
        >
          <ArrowLeft size={14} strokeWidth={1.8} />
          Back
        </Button>

        <div className="flex items-center gap-3">
          {finishing ? null : autosave.state === "saved" ? (
            <span className="flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.1em] text-moss">
              <Check size={11} strokeWidth={2.4} />
              Saved
            </span>
          ) : autosave.state === "saving" ? (
            <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
              Saving…
            </span>
          ) : autosave.state === "error" ? (
            <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-danger">
              Not saved
            </span>
          ) : null}

          <Button
            variant="signal"
            onClick={next}
            disabled={!canContinue || finishing}
            title={missing.length ? `Still needed: ${missing.join(", ")}` : undefined}
          >
            {finishing ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Finishing…
              </>
            ) : (
              <>
                {screen === 2 ? "Finish setup" : "Continue"}
                <ArrowRight size={14} strokeWidth={1.8} />
              </>
            )}
          </Button>
        </div>
      </div>

      {/* While the writes land and the session refreshes, say what is happening
          instead of leaving the button spinning with no context. */}
      {finishing ? <FinishOverlay stage={finishStage} /> : null}
    </Shell>
  );
}

const FINISH_STAGES = [
  "",
  "Saving your profile",
  "Saving your preferences",
  "Opening your dashboard",
];

function FinishOverlay({ stage }: { stage: 0 | 1 | 2 | 3 }) {
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-bg/95 px-6"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="flex w-full max-w-[340px] flex-col items-center gap-5 rounded-cell border border-line bg-surface px-6 py-7 text-center">
        <span className="grid h-11 w-11 place-items-center rounded-stamp border border-line-strong">
          <span className="h-2 w-2 animate-pulse-dot rounded-full bg-signal" />
        </span>

        <div>
          <p className="font-display text-[17px] font-semibold tracking-[-0.01em] text-ink">
            Setting up your agent
          </p>
          <p className="mt-1.5 font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-3">
            {FINISH_STAGES[stage] ?? ""}
          </p>
        </div>

        <ol className="flex w-full flex-col gap-2 border-t border-line pt-4 text-left">
          {["Profile", "Preferences", "Dashboard"].map((label, index) => {
            const done = stage > index + 1;
            const active = stage === index + 1;
            return (
              <li
                key={label}
                className={
                  done
                    ? "flex items-center gap-2.5 text-[12px] text-ink-2"
                    : active
                      ? "flex items-center gap-2.5 text-[12px] text-ink"
                      : "flex items-center gap-2.5 text-[12px] text-ink-3"
                }
              >
                <span
                  className={
                    done
                      ? "grid h-4 w-4 place-items-center rounded-full border border-moss/60 text-moss"
                      : active
                        ? "grid h-4 w-4 place-items-center rounded-full border border-signal/70"
                        : "grid h-4 w-4 place-items-center rounded-full border border-line-strong"
                  }
                >
                  {done ? <Check size={9} strokeWidth={3} /> : null}
                  {active ? (
                    <span className="h-1 w-1 animate-pulse-dot rounded-full bg-signal" />
                  ) : null}
                </span>
                {label}
                {done ? <span className="ml-auto font-mono text-[9.5px] uppercase tracking-[0.1em] text-moss">done</span> : null}
              </li>
            );
          })}
        </ol>

        <p className="text-[11.5px] leading-relaxed text-ink-3">
          This takes a moment. Keep this tab open.
        </p>
      </div>
    </div>
  );
}

function Shell({ children, step }: { children: React.ReactNode; step?: number }) {
  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <header className="border-b border-line">
        <div className="shell flex h-16 items-center justify-between">
          <div className="flex items-center gap-3">
            <Logo />
            <Stamp tone="signal">Setup</Stamp>
          </div>
          {step !== undefined ? (
            <div className="flex items-center gap-2" aria-label={`Step ${step + 1} of 3`}>
              {[0, 1, 2].map((index) => (
                <span
                  key={index}
                  className={cn(
                    "h-1.5 rounded-full transition-all",
                    index === step ? "w-6 bg-signal" : index < step ? "w-1.5 bg-ink-3" : "w-1.5 bg-line-strong",
                  )}
                />
              ))}
            </div>
          ) : null}
        </div>
      </header>
      <main className="flex flex-1 items-start justify-center px-5 py-10 sm:py-14">
        <div className="w-full max-w-[620px]">{children}</div>
      </main>
    </div>
  );
}

/* ------------------------------------------------------------------ screen 1 */

function Greeting({
  name,
  profileName,
  hasResume,
  onNext,
  onManual,
  onParsed,
}: {
  name: string;
  profileName: string | null;
  hasResume: boolean;
  onNext: () => void;
  onManual: () => void;
  onParsed: () => void;
}) {
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState<"idle" | "parsing" | "parsed" | "failed">("idle");
  const [message, setMessage] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadResume(file),
    onMutate: () => {
      setStatus("parsing");
      setMessage(null);
    },
    onSuccess: async (result) => {
      // Let the freshly parsed profile take over the form, then refetch it.
      onParsed();
      await queryClient.invalidateQueries({ queryKey: ["profile"] });
      await queryClient.invalidateQueries({ queryKey: ["resume"] });
      if (result.parse_status === "failed") {
        setStatus("failed");
        setMessage(result.message ?? "We couldn't read this file.");
        return;
      }
      setStatus("parsed");
      setMessage(null);
    },
    onError: (cause) => {
      setStatus("failed");
      setMessage(cause instanceof HttpError ? cause.message : "Upload failed.");
    },
  });

  function accept(files: FileList | null) {
    const file = files?.[0];
    if (file) upload.mutate(file);
  }

  return (
    <div>
      <h1 className="font-display text-[clamp(1.8rem,4vw,2.4rem)] font-semibold leading-[1.08] tracking-[-0.025em]">
        Hi {name}.
      </h1>
      <p className="mt-3 max-w-[52ch] text-[14.5px] leading-relaxed text-ink-2">
        Let&rsquo;s build your profile. Three screens, everything autosaved — start with your
        resume and we&rsquo;ll fill in most of it for you.
      </p>

      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          accept(event.dataTransfer.files);
        }}
        className={cn(
          "mt-8 rounded-cell border border-dashed p-8 text-center transition-colors",
          dragging ? "border-signal bg-signal/5" : "border-line-strong bg-surface",
        )}
      >
        {status === "parsing" ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 size={20} className="animate-spin text-ink-3" />
            <p className="text-[13.5px] text-ink-2">Reading your resume…</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <span className="grid h-11 w-11 place-items-center rounded-stamp border border-line bg-surface-2 text-ink-3">
              {status === "parsed" ? (
                <Check size={18} strokeWidth={2} className="text-moss" />
              ) : (
                <Upload size={18} strokeWidth={1.7} />
              )}
            </span>
            <div>
              <p className="text-[14px] text-ink">
                {status === "parsed"
                  ? `Resume parsed${profileName ? ` — found ${profileName}` : ""}`
                  : "Drop your resume here"}
              </p>
              <p className="mt-1 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
                PDF or DOCX · up to 5 MB
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-2">
              <Button variant="secondary" size="sm" onClick={() => input.current?.click()}>
                <FileText size={13} strokeWidth={1.8} />
                {hasResume ? "Replace file" : "Choose file"}
              </Button>
              <input
                ref={input}
                type="file"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                className="sr-only"
                onChange={(event) => accept(event.target.files)}
              />
            </div>
          </div>
        )}
      </div>

      {status === "failed" ? (
        <div className="mt-4 rounded-stamp border border-ochre/40 bg-ochre/5 px-4 py-3">
          <p className="text-[12.5px] leading-relaxed text-ochre">{message}</p>
          <Button variant="ghost" size="sm" className="mt-2 px-0" onClick={onManual}>
            Fill my details in manually
            <ArrowRight size={13} strokeWidth={1.8} />
          </Button>
        </div>
      ) : null}

      <div className="mt-8 flex flex-wrap items-center gap-3">
        <Button variant="signal" onClick={onNext}>
          {status === "parsed" ? "Review what we found" : "Skip for now"}
          <ArrowRight size={14} strokeWidth={1.8} />
        </Button>
        <button
          type="button"
          onClick={onManual}
          className="text-[12.5px] text-ink-3 transition-colors hover:text-ink"
        >
          I&rsquo;ll type it myself
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ screen 2 */

function Details({
  profile,
  preferences,
  saveState,
  onChange,
  onPreference,
}: {
  profile: ReturnType<typeof useSetupState>["profile"];
  preferences: ReturnType<typeof useSetupState>["preferences"];
  saveState: string;
  onChange: <K extends keyof Profile>(key: K, value: Profile[K]) => void;
  onPreference: <K extends keyof Preference>(key: K, value: Preference[K]) => void;
}) {
  const fields = CAREER_FIELDS;
  const activeField = preferences.domains?.[0] ?? "Software";
  const roleSeeds = ROLE_SEEDS[activeField] ?? [];
  const selectedRoles = preferences.target_roles ?? [];

  return (
    <div>
      <h1 className="font-display text-[clamp(1.6rem,3.4vw,2rem)] font-semibold leading-tight tracking-[-0.02em]">
        Your details
      </h1>
      <p className="mt-2 text-[13.5px] leading-relaxed text-ink-2">
        Prefilled from your resume. Fix anything that looks wrong — the agent answers forms
        from these values.
      </p>

      <Rule label="About you" className="mt-8" />
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Field label="Full name" htmlFor="full_name">
          <Input
            id="full_name"
            value={profile.full_name ?? ""}
            onChange={(event) => onChange("full_name", event.target.value)}
            placeholder="Priya Sharma"
          />
        </Field>
        <Field label="Phone" htmlFor="phone">
          <Input
            id="phone"
            value={profile.phone ?? ""}
            onChange={(event) => onChange("phone", event.target.value)}
            placeholder="+91 98765 43210"
          />
        </Field>
        <Field label="Current city" htmlFor="location">
          <Input
            id="location"
            value={profile.location ?? ""}
            onChange={(event) => onChange("location", event.target.value)}
            placeholder="Pune, India"
          />
        </Field>
        <Field label="Email" hint="From your Google account." htmlFor="email">
          <Input id="email" value={profile.email ?? ""} readOnly className="opacity-60" />
        </Field>
      </div>

      <Rule label="Links" className="mt-8" />
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Field label="GitHub" htmlFor="github_url">
          <Input
            id="github_url"
            value={profile.github_url ?? ""}
            onChange={(event) => onChange("github_url", event.target.value)}
            placeholder="github.com/username"
          />
        </Field>
        <Field label="LinkedIn" htmlFor="linkedin_url">
          <Input
            id="linkedin_url"
            value={profile.linkedin_url ?? ""}
            onChange={(event) => onChange("linkedin_url", event.target.value)}
            placeholder="linkedin.com/in/username"
          />
        </Field>
        <Field label="Portfolio" htmlFor="portfolio_url">
          <Input
            id="portfolio_url"
            value={profile.portfolio_url ?? ""}
            onChange={(event) => onChange("portfolio_url", event.target.value)}
            placeholder="yoursite.com"
          />
        </Field>
      </div>

      <Rule label="Experience" className="mt-8" />
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Field label="Current title" htmlFor="current_title">
          <Input
            id="current_title"
            value={profile.current_title ?? ""}
            onChange={(event) => onChange("current_title", event.target.value)}
            placeholder="Backend Engineer"
          />
        </Field>
        <Field label="Current company" htmlFor="current_company">
          <Input
            id="current_company"
            value={profile.current_company ?? ""}
            onChange={(event) => onChange("current_company", event.target.value)}
            placeholder="Acme Systems"
          />
        </Field>
        <Field label="Total experience (years)" htmlFor="years">
          <Input
            id="years"
            inputMode="decimal"
            value={profile.years_of_experience ?? ""}
            onChange={(event) =>
              onChange(
                "years_of_experience",
                event.target.value === "" ? null : Number(event.target.value),
              )
            }
            placeholder="5"
          />
        </Field>
        <Field label="Notice period" htmlFor="notice">
          <div className="flex flex-wrap gap-1.5 pt-1.5" id="notice">
            {NOTICE_OPTIONS.map((days) => (
              <Chip
                key={days}
                active={profile.notice_period_days === days}
                onClick={() => onChange("notice_period_days", days)}
              >
                {days === 0 ? "Immediate" : `${days} days`}
              </Chip>
            ))}
          </div>
        </Field>
      </div>

      <Rule label="Compensation" className="mt-8" />
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Field label="Current CTC (LPA)" htmlFor="current_ctc">
          <Input
            id="current_ctc"
            inputMode="decimal"
            value={profile.current_ctc_lpa ?? ""}
            onChange={(event) =>
              onChange(
                "current_ctc_lpa",
                event.target.value === "" ? null : Number(event.target.value),
              )
            }
            placeholder="18"
          />
        </Field>
        <Field label="Expected CTC (LPA)" htmlFor="expected_ctc">
          <Input
            id="expected_ctc"
            inputMode="decimal"
            value={profile.expected_ctc_lpa ?? ""}
            onChange={(event) =>
              onChange(
                "expected_ctc_lpa",
                event.target.value === "" ? null : Number(event.target.value),
              )
            }
            placeholder="24"
          />
        </Field>
      </div>

      <Rule label="Career field" className="mt-8" />
      <p className="mt-3 text-[12.5px] leading-relaxed text-ink-3">
        Pick the field you want to work in. It decides the roles we suggest.
      </p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {fields.map((field) => (
          <Chip
            key={field}
            active={preferences.domains?.[0] === field}
            onClick={() => {
              onPreference("domains", [field]);
              onPreference("target_roles", []);
            }}
          >
            {field}
          </Chip>
        ))}
      </div>

      <div className="mt-5 flex flex-wrap gap-1.5">
        {roleSeeds.map((role) => (
          <Chip
            key={role}
            active={selectedRoles.includes(role)}
            onClick={() =>
              onPreference(
                "target_roles",
                selectedRoles.includes(role)
                  ? selectedRoles.filter((item) => item !== role)
                  : [...selectedRoles, role],
              )
            }
          >
            {role}
          </Chip>
        ))}
      </div>
      <p className="mt-2 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
        {selectedRoles.length} selected · at least one required
      </p>

      <Rule label="Experience level" className="mt-8" />
      <div className="mt-3 flex flex-wrap gap-1.5">
        {(["entry", "mid", "experienced"] as const).map((level) => (
          <Chip
            key={level}
            active={preferences.experience_level === level}
            onClick={() => onPreference("experience_level", level)}
          >
            {level === "entry" ? "Entry" : level === "mid" ? "Mid" : "Experienced"}
          </Chip>
        ))}
      </div>

      {saveState === "saving" ? (
        <p className="mt-4 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
          Saving…
        </p>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ screen 3 */

function WhereAndWhen({
  preferences,
  onPreference,
}: {
  preferences: ReturnType<typeof useSetupState>["preferences"];
  onPreference: <K extends keyof Preference>(key: K, value: Preference[K]) => void;
}) {
  const [locationDraft, setLocationDraft] = useState("");
  const locations = preferences.locations ?? [];
  const modes = preferences.work_mode ?? [];
  const platforms = preferences.platforms ?? [];
  const hours = preferences.active_hours ?? { start: "09:00", end: "21:00", timezone: "Asia/Kolkata" };

  // Commit on blur as well as Enter: a location the user typed but never "added"
  // used to disappear, leaving Finish silently disabled.
  const commitLocation = () => {
    const value = locationDraft.trim();
    if (value && !locations.includes(value)) {
      onPreference("locations", [...locations, value]);
    }
    setLocationDraft("");
  };

  return (
    <div>
      <h1 className="font-display text-[clamp(1.6rem,3.4vw,2rem)] font-semibold leading-tight tracking-[-0.02em]">
        Where and when
      </h1>
      <p className="mt-2 text-[13.5px] leading-relaxed text-ink-2">
        The agent only works inside these limits. You can change them any time.
      </p>

      <Rule label="Locations" className="mt-8" />
      <div className="mt-4 flex gap-2">
        <Input
          value={locationDraft}
          onChange={(event) => setLocationDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commitLocation();
            }
          }}
          onBlur={commitLocation}
          placeholder="Pune, Remote, Bengaluru…"
        />
        <Button variant="secondary" onClick={commitLocation} aria-label="Add location">
          <Plus size={14} strokeWidth={1.8} />
        </Button>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {locations.map((location) => (
          <span
            key={location}
            className="inline-flex h-7 items-center gap-1.5 rounded-stamp border border-line px-2.5 text-[12.5px] text-ink-2"
          >
            {location}
            <button
              type="button"
              aria-label={`Remove ${location}`}
              onClick={() =>
                onPreference(
                  "locations",
                  locations.filter((item) => item !== location),
                )
              }
              className="text-ink-3 transition-colors hover:text-danger"
            >
              <X size={11} strokeWidth={2} />
            </button>
          </span>
        ))}
        {locations.length === 0 ? (
          <p className="text-[12.5px] text-ink-3">Add at least one location.</p>
        ) : null}
      </div>

      <Rule label="Work mode" className="mt-8" />
      <div className="mt-3 flex flex-wrap gap-1.5">
        {(["remote", "hybrid", "onsite"] as const).map((mode) => (
          <Chip
            key={mode}
            active={modes.includes(mode)}
            onClick={() =>
              onPreference(
                "work_mode",
                modes.includes(mode) ? modes.filter((item) => item !== mode) : [...modes, mode],
              )
            }
          >
            {mode === "onsite" ? "On-site" : mode.charAt(0).toUpperCase() + mode.slice(1)}
          </Chip>
        ))}
      </div>

      <Rule label="Active hours" className="mt-8" />
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Start" htmlFor="hours_start">
          <Input
            id="hours_start"
            type="time"
            value={hours.start}
            onChange={(event) =>
              onPreference("active_hours", { ...hours, start: event.target.value })
            }
          />
        </Field>
        <Field label="End" htmlFor="hours_end">
          <Input
            id="hours_end"
            type="time"
            value={hours.end}
            onChange={(event) =>
              onPreference("active_hours", { ...hours, end: event.target.value })
            }
          />
        </Field>
      </div>
      <p className="mt-2 text-[12px] leading-relaxed text-ink-3">
        The daily quota resets at 10:00 {hours.timezone.split("/").pop()?.replace("_", " ")}.
        Applications made outside these hours wait.
      </p>

      <Rule label="Platforms" className="mt-8" />
      <div className="mt-3 flex flex-wrap gap-1.5">
        {(["linkedin", "naukri"] as const).map((platform) => (
          <Chip
            key={platform}
            active={platforms.includes(platform)}
            onClick={() =>
              onPreference(
                "platforms",
                platforms.includes(platform)
                  ? platforms.filter((item) => item !== platform)
                  : ([...platforms, platform] as Platform[]),
              )
            }
          >
            {platform === "linkedin" ? "LinkedIn" : "Naukri"}
          </Chip>
        ))}
      </div>

      <div className="mt-8 rounded-cell border border-line bg-surface p-4">
        <p className="text-[12.5px] leading-relaxed text-ink-2">
          <span className="text-ink">Before you finish:</span> automating LinkedIn and Naukri
          breaks their terms of use. We keep the pace slow and stop at the first sign of
          friction, but the risk of a restricted account is yours. By pressing Finish you
          accept that.
        </p>
      </div>
    </div>
  );
}
