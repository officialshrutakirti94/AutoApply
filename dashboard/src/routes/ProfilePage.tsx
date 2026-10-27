import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Check, Loader2 } from "lucide-react";
import { PlanCard } from "@/components/PlanCard";
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
import { api, HttpError, type Profile } from "@/lib/api";
import { useMe } from "@/hooks/useMe";

const CAREER_FIELDS = [
  "Software",
  "Data & AI",
  "Design",
  "Product",
  "Marketing & Growth",
  "Operations",
];

export function ProfilePage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const me = useMe();
  const profileQuery = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const preferencesQuery = useQuery({ queryKey: ["preferences"], queryFn: api.preferences });
  const safety = useQuery({ queryKey: ["safety"], queryFn: api.safety });

  const [draft, setDraft] = useState<Partial<Profile>>({});
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState("");

  useEffect(() => {
    if (profileQuery.data) setDraft(profileQuery.data);
  }, [profileQuery.data]);

  const save = useMutation({
    mutationFn: (patch: Partial<Profile>) => api.updateProfile(patch),
    onMutate: () => {
      setSaved(false);
      setError(null);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["profile"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    },
    onError: (cause) =>
      setError(cause instanceof HttpError ? cause.message : "Could not save."),
  });

  const deleteAccount = useMutation({
    mutationFn: api.deleteAccount,
    onSuccess: () => {
      queryClient.clear();
      navigate("/", { replace: true });
    },
    onError: (cause) =>
      setError(cause instanceof HttpError ? cause.message : "Could not delete the account."),
  });

  if (profileQuery.isLoading) {
    return (
      <div className="flex items-center gap-2 px-1 py-8 font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3">
        <Loader2 size={12} className="animate-spin" />
        Loading profile
      </div>
    );
  }

  const values = draft;
  const usage = safety.data?.usage;

  const set = <K extends keyof Profile>(key: K, value: Profile[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));

  return (
    <div className="mx-auto max-w-[1100px]">
      <header className="flex flex-wrap items-end justify-between gap-4 px-1 pb-5 pt-2">
        <div>
          <span className="eyebrow">Your profile</span>
          <h1 className="mt-1.5 font-display text-[26px] font-semibold tracking-[-0.02em]">
            {values.full_name || me.data?.user.name || "Your profile"}
          </h1>
          <p className="mt-1.5 max-w-[58ch] text-[13px] leading-relaxed text-ink-3">
            These are the answers the agent gives on your behalf. Keep them accurate —
            anything it cannot ground here goes back to you instead of being invented.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {saved ? (
            <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-moss">
              <Check size={11} strokeWidth={2.4} /> Saved
            </span>
          ) : null}
          <Button size="sm" onClick={() => save.mutate(values)} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </header>

      {error ? (
        <p className="mb-3 rounded-stamp border border-danger/40 bg-danger/5 px-3.5 py-2.5 text-[12.5px] text-danger">
          {error}
        </p>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-[1.4fr_1fr]">
        <div className="flex flex-col gap-3">
          <Cell>
            <CellHeader label="Identity" />
            <div className="grid gap-4 px-5 py-5 sm:grid-cols-2">
              <Field label="Full name" htmlFor="p_name">
                <Input
                  id="p_name"
                  value={values.full_name ?? ""}
                  onChange={(e) => set("full_name", e.target.value)}
                />
              </Field>
              <Field label="Phone" htmlFor="p_phone">
                <Input
                  id="p_phone"
                  value={values.phone ?? ""}
                  onChange={(e) => set("phone", e.target.value)}
                />
              </Field>
              <Field label="Current city" htmlFor="p_city">
                <Input
                  id="p_city"
                  value={values.location ?? ""}
                  onChange={(e) => set("location", e.target.value)}
                />
              </Field>
              <Field label="Email" hint="From Google." htmlFor="p_email">
                <Input id="p_email" value={values.email ?? ""} readOnly className="opacity-60" />
              </Field>
            </div>
          </Cell>

          <Cell>
            <CellHeader label="Links" />
            <div className="grid gap-4 px-5 py-5 sm:grid-cols-2">
              <Field label="GitHub" htmlFor="p_github">
                <Input
                  id="p_github"
                  value={values.github_url ?? ""}
                  onChange={(e) => set("github_url", e.target.value)}
                />
              </Field>
              <Field label="LinkedIn" htmlFor="p_linkedin">
                <Input
                  id="p_linkedin"
                  value={values.linkedin_url ?? ""}
                  onChange={(e) => set("linkedin_url", e.target.value)}
                />
              </Field>
              <Field label="Portfolio" htmlFor="p_portfolio">
                <Input
                  id="p_portfolio"
                  value={values.portfolio_url ?? ""}
                  onChange={(e) => set("portfolio_url", e.target.value)}
                />
              </Field>
            </div>
          </Cell>

          <Cell>
            <CellHeader label="Experience and pay" />
            <div className="grid gap-4 px-5 py-5 sm:grid-cols-2">
              <Field label="Current title" htmlFor="p_title">
                <Input
                  id="p_title"
                  value={values.current_title ?? ""}
                  onChange={(e) => set("current_title", e.target.value)}
                />
              </Field>
              <Field label="Current company" htmlFor="p_company">
                <Input
                  id="p_company"
                  value={values.current_company ?? ""}
                  onChange={(e) => set("current_company", e.target.value)}
                />
              </Field>
              <Field label="Total experience (years)" htmlFor="p_years">
                <Input
                  id="p_years"
                  inputMode="decimal"
                  value={values.years_of_experience ?? ""}
                  onChange={(e) =>
                    set(
                      "years_of_experience",
                      e.target.value === "" ? null : Number(e.target.value),
                    )
                  }
                />
              </Field>
              <Field label="Notice period (days)" htmlFor="p_notice">
                <Input
                  id="p_notice"
                  inputMode="numeric"
                  value={values.notice_period_days ?? ""}
                  onChange={(e) =>
                    set(
                      "notice_period_days",
                      e.target.value === "" ? null : Number(e.target.value),
                    )
                  }
                />
              </Field>
              <Field label="Current CTC (LPA)" htmlFor="p_cur">
                <Input
                  id="p_cur"
                  inputMode="decimal"
                  value={values.current_ctc_lpa ?? ""}
                  onChange={(e) =>
                    set("current_ctc_lpa", e.target.value === "" ? null : Number(e.target.value))
                  }
                />
              </Field>
              <Field label="Expected CTC (LPA)" htmlFor="p_exp">
                <Input
                  id="p_exp"
                  inputMode="decimal"
                  value={values.expected_ctc_lpa ?? ""}
                  onChange={(e) =>
                    set("expected_ctc_lpa", e.target.value === "" ? null : Number(e.target.value))
                  }
                />
              </Field>
            </div>
          </Cell>

          <Cell>
            <CellHeader label="Career field and skills" />
            <div className="flex flex-col gap-4 px-5 py-5">
              <div>
                <p className="mb-2 text-[13px] font-medium text-ink-2">Field</p>
                <div className="flex flex-wrap gap-1.5">
                  {CAREER_FIELDS.map((field) => (
                    <Chip
                      key={field}
                      active={preferencesQuery.data?.domains?.[0] === field}
                      onClick={() =>
                        api
                          .updatePreferences({ domains: [field] })
                          .then(() =>
                            queryClient.invalidateQueries({ queryKey: ["preferences"] }),
                          )
                      }
                    >
                      {field}
                    </Chip>
                  ))}
                </div>
              </div>

              <Rule label="Target roles" />
              <div className="flex flex-wrap gap-1.5">
                {(preferencesQuery.data?.target_roles ?? []).map((role) => (
                  <Chip key={role} className="pointer-events-none">
                    {role}
                  </Chip>
                ))}
                {(preferencesQuery.data?.target_roles ?? []).length === 0 ? (
                  <p className="text-[12.5px] text-ink-3">No roles selected.</p>
                ) : null}
              </div>

              <Rule label="Skills" />
              <div className="flex flex-wrap gap-1.5">
                {(values.skills ?? []).map((skill) => (
                  <Chip key={skill} className="pointer-events-none">
                    {skill}
                  </Chip>
                ))}
                {(values.skills ?? []).length === 0 ? (
                  <p className="text-[12.5px] text-ink-3">Extracted from your resume.</p>
                ) : null}
              </div>
            </div>
          </Cell>
        </div>

        <div className="flex flex-col gap-3">
          <Cell>
            <CellHeader label="Plan">
              {usage ? <Stamp>{usage.plan_label}</Stamp> : null}
            </CellHeader>
            <div className="px-5 py-5">
              <PlanCard />
            </div>
          </Cell>

          <Cell>
            <CellHeader label="Usage today" />
            <div className="flex flex-col gap-2 px-5 py-5">
              <Row
                term="Applications"
                value={`${usage?.applied_today ?? 0} / ${usage?.effective_daily_cap ?? 10}`}
              />
              <Row term="This hour" value={`${usage?.applied_last_hour ?? 0} / ${usage?.effective_hourly_cap ?? 3}`} />
              <Row term="Reset hour" value={`${usage?.day_reset_hour ?? 10}:00`} />
              <Row term="Timezone" value={usage?.active_timezone ?? "Asia/Kolkata"} />
            </div>
          </Cell>

          <Cell className="border-danger/30">
            <CellHeader label="Danger zone" />
            <div className="flex flex-col gap-3 px-5 py-5">
              <p className="flex items-start gap-2 text-[12.5px] leading-relaxed text-ink-2">
                <AlertTriangle size={14} strokeWidth={1.8} className="mt-0.5 shrink-0 text-danger" />
                Deletes your profile, resume, applications and extension tokens. There is no
                undo.
              </p>
              <Input
                value={confirmDelete}
                onChange={(event) => setConfirmDelete(event.target.value)}
                placeholder='Type "delete" to confirm'
                aria-label="Type delete to confirm"
              />
              <Button
                variant="secondary"
                className="border-danger/40 text-danger hover:border-danger hover:bg-danger/5"
                disabled={confirmDelete.trim().toLowerCase() !== "delete" || deleteAccount.isPending}
                onClick={() => deleteAccount.mutate()}
              >
                {deleteAccount.isPending ? "Deleting…" : "Delete my data"}
              </Button>
            </div>
          </Cell>
        </div>
      </div>
    </div>
  );
}

function Row({ term, value }: { term: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">{term}</span>
      <span className="tabular text-[12px] text-ink">{value}</span>
    </div>
  );
}