import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowUpRight, Download, FileText } from "lucide-react";
import {
  Button,
  Cell,
  CellHeader,
  Chip,
  LedgerRow,
  Stamp,
  Stat,
} from "@/components/ui/primitives";
import { ExtensionDownloadButton } from "@/components/ExtensionDownloadButton";
import { api } from "@/lib/api";
import { clock, until } from "@/lib/format";
import { useMe } from "@/hooks/useMe";
import { useLedger } from "@/hooks/useLedger";

/* ---------------------------------------------------------------------------
   Overview: the bento. Eight cells, each answering a question the user has.
   --------------------------------------------------------------------------- */

export function Overview() {
  const { data: me } = useMe();
  const ledger = useLedger();

  const active = useQuery({
    queryKey: ["activeRun"],
    queryFn: api.activeRun,
    refetchInterval: (query) => (query.state.data?.run?.status === "running" ? 3000 : 15000),
  });

  const safety = useQuery({
    queryKey: ["safety"],
    queryFn: api.safety,
    refetchInterval: 15000,
  });

  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });

  const resume = useQuery({ queryKey: ["resume"], queryFn: api.resumeDraft, retry: false });

  const plan = useQuery({ queryKey: ["plan"], queryFn: api.plan });

  const run = active.data?.run ?? null;
  const usage = safety.data?.usage;
  const firstName = (profile.data?.full_name ?? me?.user.name ?? "").split(" ")[0] || "there";

  return (
    <div className="mx-auto max-w-[1240px]">
      <header className="flex flex-wrap items-end justify-between gap-4 px-1 pb-5 pt-2">
        <div>
          <span className="eyebrow">Overview</span>
          <h1 className="mt-1.5 font-display text-[26px] font-semibold tracking-[-0.02em]">
            Hi {firstName}.
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/app/profile">
            <Stamp>{plan.data?.label ?? "Regular"}</Stamp>
          </Link>
          <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
            {new Date().toLocaleDateString("en-IN", {
              weekday: "long",
              day: "2-digit",
              month: "long",
            })}
          </span>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-12">
        {/* agent */}
        <Cell className="flex flex-col xl:col-span-7">
          <CellHeader label="Agent">
            {run ? (
              <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
                <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-signal" />
                {run.dry_run ? "practice run" : "running"}
              </span>
            ) : null}
          </CellHeader>

          <div className="flex flex-1 flex-col gap-5 px-5 py-5">
            {run ? (
              <>
                <p className="text-[14.5px] leading-relaxed text-ink">
                  Working on <span className="capitalize">{run.platform}</span> ·{" "}
                  {run.applied_count} applied this run.
                </p>
                <div className="flex flex-wrap gap-8">
                  <Stat value={run.applied_count} caption="Applied" tone="moss" />
                  <Stat value={run.skipped_count} caption="Skipped" tone="muted" />
                  <Stat value={run.stuck_count} caption="Needs you" tone="ochre" />
                </div>
              </>
            ) : (
              <>
                <p className="max-w-[46ch] text-[14px] leading-relaxed text-ink-2">
                  Get the Chrome extension, install it, then connect it from Settings to start
                  applying on LinkedIn or Naukri.
                </p>
                <div className="flex flex-wrap items-center gap-3">
                  <ExtensionDownloadButton compact />
                  <Link
                    to="/app/settings"
                    className="text-[12.5px] text-ink-2 underline underline-offset-4 hover:text-ink"
                  >
                    Pair extension
                  </Link>
                </div>
              </>
            )}
          </div>
        </Cell>

        {/* quota */}
        <Cell className="flex flex-col xl:col-span-5">
          <CellHeader label="Quota" />
          <div className="flex flex-1 flex-col justify-between gap-5 px-5 py-5">
            <div className="flex items-end justify-between gap-4">
              <div className="flex items-baseline gap-1">
                <span className="tabular font-display text-[38px] font-semibold leading-none tracking-[-0.03em]">
                  {usage?.applied_today ?? 0}
                </span>
                <span className="tabular font-display text-[18px] font-semibold text-ink-3">
                  /{usage?.effective_daily_cap ?? 10}
                </span>
              </div>
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
                today
              </span>
            </div>

            <QuotaBar used={usage?.applied_today ?? 0} cap={usage?.effective_daily_cap ?? 10} />

            <dl className="flex flex-col gap-2 border-t border-line pt-4">
              <Row term="Resets in" value={until(usage?.quota_resets_at)} />
              <Row term="Reset hour" value={`${usage?.day_reset_hour ?? 10}:00`} />
              <Row
                term="This hour"
                value={`${usage?.applied_last_hour ?? 0}/${usage?.effective_hourly_cap ?? 3}`}
              />
              {usage && usage.warmup_cap < usage.plan_daily_cap ? (
                <Row term="Warm-up" value={`${usage.warmup_cap}/day for now`} tone="ochre" />
              ) : null}
            </dl>
          </div>
        </Cell>

        {/* sent */}
        <BucketCell
          label="Sent"
          to="/app/sent"
          count={ledger.counts.sent}
          tone="applied"
          empty="No applications sent yet. The first one appears the moment the agent submits."
          rows={ledger.sent.slice(0, 4).map((item) => (
            <LedgerRow
              key={item.id}
              time={clock(item.created_at)}
              title={item.job_title ?? "Untitled role"}
              meta={item.company ?? item.platform}
              href={item.job_url ?? undefined}
            />
          ))}
        />

        {/* waiting */}
        <Cell className="flex flex-col xl:col-span-4">
          <CellHeader label="Waiting for confirmations">
            {ledger.counts.waiting ? <Stamp tone="attention">{ledger.counts.waiting}</Stamp> : null}
          </CellHeader>
          <div className="flex flex-1 flex-col px-5 pb-4 pt-3">
            {ledger.waiting.length ? (
              <ul className="flex flex-col">
                {ledger.waiting.slice(0, 3).map((item) => (
                  <li
                    key={item.id}
                    className="border-t border-line py-2.5 first:border-t-0 first:pt-1"
                  >
                    <p className="truncate text-[13px] text-ink">
                      {item.job_title ?? "Untitled role"}
                    </p>
                    <p className="truncate font-mono text-[10px] text-ink-3">
                      {item.reason_label ?? "Needs your answer"}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-5 text-[13px] leading-relaxed text-ink-3">
                Nothing is waiting on you.
              </p>
            )}
            <Link
              to="/app/waiting"
              className="mt-auto pt-3 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3 transition-colors hover:text-ink"
            >
              Open inbox →
            </Link>
          </div>
        </Cell>

        {/* cant send */}
        <BucketCell
          label="Can't send"
          to="/app/failed"
          count={ledger.counts.cantSend}
          tone="skipped"
          hint={
            ledger.counts.preferred
              ? {
                  label: `${ledger.counts.preferred} apply on company sites`,
                  to: "/app/preferred",
                }
              : undefined
          }
          empty="Nothing was blocked. Skips and dead ends show up here."
          rows={ledger.cantSend.slice(0, 4).map((item) => (
            <LedgerRow
              key={item.id}
              time={clock(item.created_at)}
              title={item.job_title ?? "Untitled role"}
              meta={item.reason_label ?? item.platform}
            />
          ))}
        />

        {/* resume */}
        <Cell className="flex flex-col xl:col-span-6">
          <CellHeader label="Your resume">
            <Link
              to="/app/resume"
              className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3 transition-colors hover:text-ink"
            >
              Open
            </Link>
          </CellHeader>
          <div className="flex flex-1 flex-col gap-4 px-5 py-5">
            <div className="flex items-start gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-stamp border border-line bg-surface-2 text-ink-3">
                <FileText size={15} strokeWidth={1.6} />
              </span>
              <div className="min-w-0">
                <p className="truncate text-[13.5px] text-ink">
                  {profile.data?.has_resume ? "Resume on file" : "No resume yet"}
                </p>
                <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
                  {resume.data?.parse_status ?? "none"} ·{" "}
                  {profile.data?.skills.length ?? 0} skills
                </p>
              </div>
            </div>
            <div className="mt-auto flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={!profile.data?.has_resume}
                onClick={() => api.resumeFileUrl().then((r) => window.open(r.url, "_blank"))}
              >
                <Download size={13} strokeWidth={1.8} />
                Download
              </Button>
              <Link to="/app/resume">
                <Button size="sm" variant="secondary">
                  {profile.data?.has_resume ? "Replace" : "Upload"}
                </Button>
              </Link>
            </div>
          </div>
        </Cell>

        {/* profile */}
        <Cell className="flex flex-col xl:col-span-6">
          <CellHeader label="Your profile">
            <Link
              to="/app/profile"
              className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3 transition-colors hover:text-ink"
            >
              Edit
            </Link>
          </CellHeader>
          <div className="flex flex-1 flex-col gap-4 px-5 py-5">
            <div>
              <p className="font-display text-[17px] font-semibold text-ink">
                {profile.data?.full_name || "No name yet"}
              </p>
              <p className="mt-0.5 text-[12.5px] text-ink-2">
                {profile.data?.current_title ?? "—"}
                {profile.data?.current_company ? ` · ${profile.data.current_company}` : ""}
              </p>
              <p className="mt-0.5 font-mono text-[10.5px] text-ink-3">
                {profile.data?.location ?? "Location not set"}
                {profile.data?.years_of_experience
                  ? ` · ${profile.data.years_of_experience} yrs`
                  : ""}
                {profile.data?.expected_ctc_lpa
                  ? ` · expects ${profile.data.expected_ctc_lpa} LPA`
                  : ""}
              </p>
            </div>

            {profile.data?.skills?.length ? (
              <div className="flex flex-wrap gap-1.5">
                {profile.data.skills.slice(0, 6).map((skill) => (
                  <Chip key={skill} className="pointer-events-none">
                    {skill}
                  </Chip>
                ))}
                {profile.data.skills.length > 6 ? (
                  <span className="self-center font-mono text-[10px] text-ink-3">
                    +{profile.data.skills.length - 6}
                  </span>
                ) : null}
              </div>
            ) : null}

            <div className="mt-auto flex items-center justify-between border-t border-line pt-3">
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
                Plan
              </span>
              <span className="flex items-center gap-2 text-[12.5px] text-ink">
                {plan.data?.label ?? "Regular"}
                <span className="font-mono text-[10.5px] text-ink-3">
                  {plan.data?.limits.daily_cap ?? 10}/day
                </span>
                <ArrowUpRight size={11} strokeWidth={2} className="text-ink-3" />
              </span>
            </div>
          </div>
        </Cell>
      </div>
    </div>
  );
}

function BucketCell({
  label,
  to,
  count,
  tone,
  empty,
  rows,
  hint,
}: {
  label: string;
  to: string;
  count: number;
  tone: "applied" | "skipped";
  empty: string;
  rows: React.ReactNode[];
  hint?: { label: string; to: string };
}) {
  return (
    <Cell className="flex flex-col xl:col-span-4">
      <CellHeader label={label}>
        {count ? <Stamp tone={tone}>{count}</Stamp> : null}
      </CellHeader>
      <div className="flex flex-1 flex-col px-5 pb-4 pt-2">
        {rows.length ? (
          <ul className="flex flex-col">{rows}</ul>
        ) : (
          <p className="py-5 text-[13px] leading-relaxed text-ink-3">{empty}</p>
        )}
        <div className="mt-auto flex flex-wrap items-baseline justify-between gap-2 pt-3">
          <Link
            to={to}
            className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3 transition-colors hover:text-ink"
          >
            View all →
          </Link>
          {hint ? (
            <Link
              to={hint.to}
              className="font-mono text-[10px] text-ochre transition-colors hover:text-ink"
            >
              {hint.label} →
            </Link>
          ) : null}
        </div>
      </div>
    </Cell>
  );
}

function QuotaBar({ used, cap }: { used: number; cap: number }) {
  const pct = cap > 0 ? Math.min(100, Math.round((used / cap) * 100)) : 0;
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2"
      role="progressbar"
      aria-valuenow={used}
      aria-valuemin={0}
      aria-valuemax={cap}
      aria-label="Applications used today"
    >
      <div
        className="h-full rounded-full bg-signal transition-[width] duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function Row({
  term,
  value,
  tone = "ink",
}: {
  term: string;
  value: string;
  tone?: "ink" | "ochre";
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">{term}</dt>
      <dd className={tone === "ochre" ? "text-[12px] text-ochre" : "tabular text-[12px] text-ink"}>
        {value}
      </dd>
    </div>
  );
}