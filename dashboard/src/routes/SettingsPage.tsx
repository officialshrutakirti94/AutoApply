import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Download, Loader2, Plus, Unplug, X } from "lucide-react";
import {
  Button,
  Cell,
  CellHeader,
  Chip,
  Field,
  Input,
  Rule,
  Stamp,
} from "@/components/ui/primitives";
import { api, HttpError } from "@/lib/api";
import { shortDate, until } from "@/lib/format";

/**
 * Settings. The extension cannot sign in to Google, so it pairs with a code the
 * dashboard mints here: one code, one use, ten minutes.
 */

const ZIP_URL = import.meta.env.VITE_EXTENSION_DOWNLOAD_URL;

export function SettingsPage() {
  const queryClient = useQueryClient();
  const tokens = useQuery({ queryKey: ["extensionTokens"], queryFn: api.extensionTokens });
  const safety = useQuery({ queryKey: ["safety"], queryFn: api.safety });
  const preferences = useQuery({ queryKey: ["preferences"], queryFn: api.preferences });
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });

  const [pairing, setPairing] = useState<{ code: string; expiresAt: number } | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cap, setCap] = useState<number>(10);
  const [hours, setHours] = useState<{ start: string; end: string }>({ start: "09:00", end: "21:00" });
  const [saved, setSaved] = useState(false);
  const [roles, setRoles] = useState<string[]>([]);
  const [locations, setLocations] = useState<string[]>([]);
  const [roleDraft, setRoleDraft] = useState("");
  const [locationDraft, setLocationDraft] = useState("");

  useEffect(() => {
    if (!preferences.data) return;
    setCap(preferences.data.daily_cap);
    setHours({
      start: preferences.data.active_hours.start,
      end: preferences.data.active_hours.end,
    });
    setRoles(preferences.data.target_roles);
    setLocations(preferences.data.locations);
  }, [preferences.data]);

  // One-second tick only while a code is on screen.
  const [, setNow] = useState(Date.now());
  useEffect(() => {
    if (!pairing) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [pairing]);

  const remaining = pairing ? Math.max(0, pairing.expiresAt - Date.now()) : 0;
  const expired = Boolean(pairing) && remaining <= 0;

  const activeInstalls = useMemo(
    () => (tokens.data ?? []).filter((token) => token.active),
    [tokens.data],
  );

  const createCode = useMutation({
    mutationFn: api.pairExtension,
    onMutate: () => setError(null),
    onSuccess: (result) => {
      setPairing({ code: result.code, expiresAt: new Date(result.expires_at).getTime() });
      setCopied(false);
    },
    onError: (cause) =>
      setError(cause instanceof HttpError ? cause.message : "Could not create a code."),
  });

  const disconnect = useMutation({
    mutationFn: api.revokeExtension,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["extensionTokens"] }),
  });

  const saveLimits = useMutation({
    mutationFn: () =>
      api.updatePreferences({
        daily_cap: cap,
        active_hours: {
          start: hours.start,
          end: hours.end,
          timezone: preferences.data?.active_hours.timezone ?? "Asia/Kolkata",
        },
      }),
    onMutate: () => setError(null),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["preferences"] }),
        queryClient.invalidateQueries({ queryKey: ["safety"] }),
      ]);
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    },
    onError: (cause) =>
      setError(cause instanceof HttpError ? cause.message : "Could not save the limits."),
  });

  // Roles and locations drive what the extension searches for. Until now they
  // could only be set during onboarding, which left people stuck with whatever
  // the resume parse suggested.
  const savePrefs = useMutation({
    mutationFn: (patch: { target_roles?: string[]; locations?: string[] }) =>
      api.updatePreferences(patch),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["preferences"] }),
        queryClient.invalidateQueries({ queryKey: ["safety"] }),
      ]);
      setSaved(true);
      setTimeout(() => setSaved(false), 1600);
    },
    onError: (cause) =>
      setError(cause instanceof HttpError ? cause.message : "Could not save."),
  });

  function addRole(value: string) {
    const role = value.trim();
    setRoleDraft("");
    if (!role || roles.includes(role)) return;
    const next = [...roles, role];
    setRoles(next);
    savePrefs.mutate({ target_roles: next });
  }

  function removeRole(role: string) {
    const next = roles.filter((item) => item !== role);
    setRoles(next);
    savePrefs.mutate({ target_roles: next });
  }

  function addLocation(value: string) {
    const location = value.trim();
    setLocationDraft("");
    if (!location || locations.includes(location)) return;
    const next = [...locations, location];
    setLocations(next);
    savePrefs.mutate({ locations: next });
  }

  function removeLocation(location: string) {
    const next = locations.filter((item) => item !== location);
    setLocations(next);
    savePrefs.mutate({ locations: next });
  }

  const roleSuggestions = [
    ...new Set([
      profile.data?.current_title ?? "",
      "AI Engineer",
      "Backend Engineer",
      "Data Analyst",
    ]),
  ].filter((role) => role && !roles.includes(role));

  const usage = safety.data?.usage;

  return (
    <div className="mx-auto max-w-[980px]">
      <header className="flex flex-wrap items-end justify-between gap-4 px-1 pb-5 pt-2">
        <div>
          <span className="eyebrow">Settings</span>
          <h1 className="mt-1.5 font-display text-[26px] font-semibold tracking-[-0.02em]">
            Connect your browser
          </h1>
          <p className="mt-1.5 max-w-[62ch] text-[13px] leading-relaxed text-ink-3">
            The extension runs inside your own Chrome, so it needs one code from here. After that it
            stays connected until you disconnect it.
          </p>
        </div>
        <Stamp tone={activeInstalls.length ? "applied" : "skipped"}>
          {activeInstalls.length ? `${activeInstalls.length} connected` : "Not connected"}
        </Stamp>
      </header>

      {error ? (
        <p className="mb-3 rounded-stamp border border-danger/40 bg-danger/5 px-3.5 py-2.5 text-[12.5px] text-danger">
          {error}
        </p>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-[1.25fr_1fr]">
        <div className="flex flex-col gap-3">
        <Cell>
          <CellHeader label="What it applies to" />
          <div className="flex flex-col gap-5 px-5 py-5">
            <div>
              <p className="mb-2 text-[13px] font-medium text-ink-2">Target roles</p>
              <div className="flex flex-wrap gap-1.5">
                {roles.map((role) => (
                  <span
                    key={role}
                    className="inline-flex h-7 items-center gap-1.5 rounded-stamp border border-line-strong px-2.5 text-[12.5px] text-ink"
                  >
                    {role}
                    <button
                      type="button"
                      aria-label={`Remove ${role}`}
                      onClick={() => removeRole(role)}
                      className="text-ink-3 transition-colors hover:text-danger"
                    >
                      <X size={11} strokeWidth={2} />
                    </button>
                  </span>
                ))}
                {roles.length === 0 ? (
                  <p className="text-[12.5px] text-ochre">Add at least one role, or a run cannot start.</p>
                ) : null}
              </div>

              <div className="mt-3 flex gap-2">
                <Input
                  value={roleDraft}
                  onChange={(event) => setRoleDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      addRole(roleDraft);
                    }
                  }}
                  onBlur={() => addRole(roleDraft)}
                  placeholder={profile.data?.current_title ?? "AI Engineer"}
                />
                <Button variant="secondary" onClick={() => addRole(roleDraft)} aria-label="Add role">
                  <Plus size={14} strokeWidth={1.8} />
                </Button>
              </div>

              {roleSuggestions.length ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {roleSuggestions.map((role) => (
                    <button
                      key={role}
                      type="button"
                      onClick={() => addRole(role)}
                      className="rounded-stamp border border-line px-2 py-0.5 text-[11.5px] text-ink-3 transition-colors hover:border-line-strong hover:text-ink"
                    >
                      + {role}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            <Rule label="Locations" />
            <div className="flex flex-wrap gap-1.5">
              {locations.map((location) => (
                <span
                  key={location}
                  className="inline-flex h-7 items-center gap-1.5 rounded-stamp border border-line-strong px-2.5 text-[12.5px] text-ink"
                >
                  {location}
                  <button
                    type="button"
                    aria-label={`Remove ${location}`}
                    onClick={() => removeLocation(location)}
                    className="text-ink-3 transition-colors hover:text-danger"
                  >
                    <X size={11} strokeWidth={2} />
                  </button>
                </span>
              ))}
              <span className="inline-flex h-7 items-center rounded-stamp border border-dashed border-line-strong px-2.5 text-[12px] text-ink-3">
                India by default
              </span>
            </div>
            <div className="flex gap-2">
              <Input
                value={locationDraft}
                onChange={(event) => setLocationDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    addLocation(locationDraft);
                  }
                }}
                onBlur={() => addLocation(locationDraft)}
                placeholder="Bengaluru"
              />
              <Button variant="secondary" onClick={() => addLocation(locationDraft)} aria-label="Add location">
                <Plus size={14} strokeWidth={1.8} />
              </Button>
            </div>

            <p className="text-[11.5px] leading-relaxed text-ink-3">
              The extension searches the first role here, in the first location (or India if none).
              Change these and the next run searches something else.
            </p>
          </div>
        </Cell>

        <Cell>
          <CellHeader label="Pairing code" />
          <div className="flex flex-col gap-5 px-5 py-5">
            {pairing ? (
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center gap-4">
                  <span className="tabular select-all font-mono text-[30px] tracking-[0.28em] text-ink">
                    {pairing.code}
                  </span>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={async () => {
                      await navigator.clipboard.writeText(pairing.code);
                      setCopied(true);
                      setTimeout(() => setCopied(false), 1600);
                    }}
                  >
                    {copied ? <Check size={13} strokeWidth={2.2} /> : <Copy size={13} strokeWidth={1.8} />}
                    {copied ? "Copied" : "Copy"}
                  </Button>
                </div>

                <p
                  className={
                    expired
                      ? "text-[12.5px] text-danger"
                      : "font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3"
                  }
                >
                  {expired
                    ? "That code expired. Generate a new one."
                    : `Expires in ${until(new Date(pairing.expiresAt).toISOString())} · single use`}
                </p>
              </div>
            ) : (
              <p className="max-w-[52ch] text-[13px] leading-relaxed text-ink-2">
                Generate a code, open the extension popup, and paste it there. It works once and
                expires in ten minutes.
              </p>
            )}

            <Rule label="Install the extension" />

            <ol className="flex flex-col gap-3">
              {[
                "Open chrome://extensions and turn on Developer mode.",
                "Choose “Load unpacked” and pick the extension folder, or drop in the zip.",
                "Open LinkedIn or Naukri, click the AutoApply icon, and paste the code.",
              ].map((step, index) => (
                <li key={step} className="flex items-start gap-3 text-[13px] text-ink-2">
                  <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border border-line-strong font-mono text-[10px] text-ink-3">
                    {index + 1}
                  </span>
                  {step}
                </li>
              ))}
            </ol>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="signal"
                onClick={() => createCode.mutate()}
                disabled={createCode.isPending}
              >
                {createCode.isPending ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : null}
                {pairing ? "New code" : "Generate pairing code"}
              </Button>
              {ZIP_URL ? (
                <a href={ZIP_URL} target="_blank" rel="noreferrer">
                  <Button variant="secondary">
                    <Download size={14} strokeWidth={1.8} />
                    Download extension
                  </Button>
                </a>
              ) : (
                <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
                  Extension build coming soon
                </span>
              )}
            </div>
          </div>
        </Cell>

        <div className="flex flex-col gap-3">
          <Cell>
            <CellHeader label="Connected browsers" />
            <div className="flex flex-col px-5 pb-4 pt-2">
              {tokens.isLoading ? (
                <p className="py-4 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
                  Loading…
                </p>
              ) : activeInstalls.length ? (
                activeInstalls.map((token) => (
                  <div
                    key={token.id}
                    className="flex items-center justify-between gap-3 border-t border-line py-3 first:border-t-0 first:pt-1"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[13px] text-ink">
                        {token.label ?? "Chrome extension"}
                      </p>
                      <p className="font-mono text-[10px] text-ink-3">
                        paired {shortDate(token.created_at)}
                        {token.last_used_at ? ` · used ${shortDate(token.last_used_at)}` : ""}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => disconnect.mutate(token.id)}
                      disabled={disconnect.isPending}
                    >
                      <Unplug size={13} strokeWidth={1.8} />
                      Disconnect
                    </Button>
                  </div>
                ))
              ) : (
                <p className="py-4 text-[13px] leading-relaxed text-ink-3">
                  No browser connected yet. Generate a code and paste it into the extension.
                </p>
              )}
            </div>
          </Cell>

          <Cell>
            <CellHeader label="Automation limits">
              {saved ? (
                <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-moss">
                  Saved
                </span>
              ) : null}
            </CellHeader>
            <div className="flex flex-col gap-4 px-5 py-5">
              <Field
                label="Applications per day"
                hint={`Your plan allows up to ${usage?.plan_daily_cap ?? 10}. This can only lower it.`}
                htmlFor="daily_cap"
              >
                <Input
                  id="daily_cap"
                  inputMode="numeric"
                  value={cap}
                  onChange={(event) => setCap(Number(event.target.value) || 1)}
                />
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Active from" htmlFor="hours_start">
                  <Input
                    id="hours_start"
                    type="time"
                    value={hours.start}
                    onChange={(event) => setHours((current) => ({ ...current, start: event.target.value }))}
                  />
                </Field>
                <Field label="Until" htmlFor="hours_end">
                  <Input
                    id="hours_end"
                    type="time"
                    value={hours.end}
                    onChange={(event) => setHours((current) => ({ ...current, end: event.target.value }))}
                  />
                </Field>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {(preferences.data?.platforms ?? []).map((platform) => (
                  <Chip key={platform} className="pointer-events-none">
                    {platform}
                  </Chip>
                ))}
              </div>

              <p className="border-t border-line pt-3 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
                Resets {usage?.day_reset_hour ?? 10}:00 · {usage?.active_timezone ?? "Asia/Kolkata"}
              </p>

              <Button onClick={() => saveLimits.mutate()} disabled={saveLimits.isPending}>
                {saveLimits.isPending ? "Saving…" : "Save limits"}
              </Button>
            </div>
          </Cell>
        </div>
        </div>
      </div>
    </div>
  );
}