import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import type { Application } from "@/lib/api";
import { Stamp } from "@/components/ui/primitives";
import { clock } from "@/lib/format";

/** The ledger table, shared by Sent / Waiting / Can't send. */
export function ApplicationsTable({
  items,
  empty,
  onResolve,
  resolving,
  showCause = true,
  onSaveAnswer,
}: {
  items: Application[];
  empty: string;
  onResolve?: (id: string) => void;
  resolving?: boolean;
  showCause?: boolean;
  onSaveAnswer?: (question: string, answer: string, sensitive: boolean) => Promise<void>;
}) {
  if (!items.length) {
    return (
      <div className="rounded-cell border border-dashed border-line-strong px-6 py-12 text-center">
        <p className="mx-auto max-w-[44ch] text-[13.5px] leading-relaxed text-ink-3">{empty}</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-cell border border-line bg-surface">
      <div className="hidden items-center gap-4 border-b border-line px-5 py-2.5 sm:flex">
        <span className="w-12 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
          time
        </span>
        <span className="flex-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
          role
        </span>
        <span className="w-24 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
          platform
        </span>
        <span className="w-32 text-right font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
          status
        </span>
      </div>

      {items.map((item) => (
        <div
          key={item.id}
          className="flex flex-col gap-2 border-t border-line px-5 py-3 first:border-t-0 sm:flex-row sm:flex-wrap sm:items-center sm:gap-4"
        >
          <span className="w-12 shrink-0 font-mono text-[11px] tabular text-ink-3">
            {clock(item.created_at)}
          </span>

          <div className="min-w-0 flex-1">
            <p className="truncate text-[13.5px] text-ink">{item.job_title ?? "Untitled role"}</p>
            <p className="truncate font-mono text-[10.5px] text-ink-3">
              {item.company ?? "—"}
              {showCause && item.reason_label ? ` · ${item.reason_label}` : ""}
            </p>
          </div>

          <span className="w-24 shrink-0 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-3">
            {item.platform}
          </span>

          <div className="flex w-full shrink-0 items-center justify-between gap-3 sm:w-32 sm:justify-end">
            <Stamp tone={stampTone(item)}>{stampLabel(item)}</Stamp>
            <div className="flex items-center gap-2">
              {item.job_url ? (
                <a
                  href={item.job_url}
                  target="_blank"
                  rel="noreferrer"
                  aria-label="Open the job"
                  className="text-ink-3 transition-colors hover:text-ink"
                >
                  <ArrowUpRight size={13} strokeWidth={1.8} />
                </a>
              ) : null}
              {onResolve ? (
                <button
                  type="button"
                  onClick={() => onResolve(item.id)}
                  disabled={resolving}
                  className="text-[11.5px] text-ink-3 transition-colors hover:text-ink disabled:opacity-50"
                >
                  Dismiss
                </button>
              ) : null}
            </div>
          </div>
          {onSaveAnswer ? (
            <BlockedQuestionAnswers item={item} onSaveAnswer={onSaveAnswer} />
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function WaitingTable({
  items,
  onResolve,
  resolving,
}: {
  items: Application[];
  onResolve: (id: string) => void;
  resolving: boolean;
}) {
  if (!items.length) {
    return (
      <div className="rounded-cell border border-dashed border-line-strong px-6 py-12 text-center">
        <p className="mx-auto max-w-[46ch] text-[13.5px] leading-relaxed text-ink-3">
          Nothing is waiting on you. When the agent hits a question it will not answer on
          its own, the job appears here with the exact question.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {items.map((item) => (
        <div key={item.id} className="rounded-cell border border-line bg-surface p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[14.5px] text-ink">{item.job_title ?? "Untitled role"}</p>
              <p className="mt-0.5 font-mono text-[10.5px] text-ink-3">
                {item.company ?? "—"} · {item.platform} · {clock(item.created_at)}
              </p>
            </div>
            <Stamp tone="attention">Needs you</Stamp>
          </div>

          <p className="mt-3 border-t border-line pt-3 text-[13px] leading-relaxed text-ink-2">
            {explain(item.reason)}
          </p>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            {item.job_url ? (
              <a href={item.job_url} target="_blank" rel="noreferrer">
                <span className="inline-flex h-8 items-center gap-1.5 rounded-stamp bg-ink px-3 text-[12.5px] font-semibold text-bg">
                  Open on {item.platform === "linkedin" ? "LinkedIn" : "Naukri"}
                  <ArrowUpRight size={12} strokeWidth={2} />
                </span>
              </a>
            ) : null}
            <button
              type="button"
              onClick={() => onResolve(item.id)}
              disabled={resolving}
              className="text-[12.5px] text-ink-3 transition-colors hover:text-ink disabled:opacity-50"
            >
              Mark resolved
            </button>
            <Link
              to="/app/profile"
              className="text-[12.5px] text-ink-3 transition-colors hover:text-ink"
            >
              Update my profile
            </Link>
          </div>
        </div>
      ))}
    </div>
  );
}

function BlockedQuestionAnswers({
  item,
  onSaveAnswer,
}: {
  item: Application;
  onSaveAnswer: (question: string, answer: string, sensitive: boolean) => Promise<void>;
}) {
  const raw = item.answers_used.__needs_user_input__;
  if (!Array.isArray(raw)) return null;

  const questions = raw.filter(
    (entry): entry is { question: string; reason?: string; sensitive?: boolean } =>
      typeof entry === "object" &&
      entry !== null &&
      typeof (entry as Record<string, unknown>).question === "string",
  );
  if (!questions.length) return null;

  return (
    <div className="w-full border-t border-line pt-3">
      <p className="text-[12px] font-medium text-ink-2">What stopped this application</p>
      <div className="mt-2 flex flex-col gap-3">
        {questions.map((entry, index) => (
          <BlockedQuestion
            key={`${item.id}-${index}`}
            question={entry.question}
            sensitive={entry.sensitive === true || entry.reason === "sensitive_question"}
            onSaveAnswer={onSaveAnswer}
          />
        ))}
      </div>
      <p className="mt-2 text-[11px] text-ink-3">
        Saved answers are available for future applications. This blocked job will not be retried
        automatically.
      </p>
    </div>
  );
}

function BlockedQuestion({
  question,
  sensitive,
  onSaveAnswer,
}: {
  question: string;
  sensitive: boolean;
  onSaveAnswer: (question: string, answer: string, sensitive: boolean) => Promise<void>;
}) {
  const [answer, setAnswer] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSaveAnswer(question, answer.trim(), sensitive);
      setSaved(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save this answer.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-stamp bg-bg px-3 py-3">
      <p className="text-[12px] text-ink">{question}</p>
      {saved ? (
        <p className="mt-2 text-[11.5px] text-ink-3">Saved for future applications.</p>
      ) : (
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <textarea
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            rows={2}
            maxLength={2000}
            aria-label={`Your answer to ${question}`}
            className="min-w-0 flex-1 resize-y rounded-stamp border border-line bg-surface px-2.5 py-2 text-[12px] text-ink outline-none focus:border-ink-3"
            placeholder="Write the answer you want reused"
          />
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving || !answer.trim()}
            className="self-end rounded-stamp bg-ink px-3 py-2 text-[11.5px] font-medium text-bg disabled:opacity-50 sm:self-start"
          >
            {saving ? "Saving…" : "Save for future"}
          </button>
        </div>
      )}
      {error ? <p className="mt-2 text-[11.5px] text-danger">{error}</p> : null}
    </div>
  );
}

function stampTone(item: Application): "applied" | "attention" | "skipped" | "neutral" {
  if (item.status === "applied") return "applied";
  if (item.status === "dry_run") return "neutral";
  if (item.status === "needs_attention") return "attention";
  return "skipped";
}

function stampLabel(item: Application): string {
  if (item.status === "applied") return "Sent";
  if (item.status === "dry_run") return "Practice";
  if (item.status === "needs_attention") return "Needs you";
  return "Skipped";
}

function explain(reason: string | null): string {
  switch (reason) {
    case "sensitive_question":
      return "The agent stopped at a question it will never answer for you — something sensitive, like a legal declaration, a demographic detail or salary negotiation.";
    case "unknown_question":
      return "The agent did not know the answer to a screening question and would not guess. Answer it once and it is reused from then on.";
    case "low_confidence":
      return "The proposed answer was not grounded in your profile, so it was held back rather than invented.";
    default:
      return "This application needs your confirmation before it can be sent.";
  }
}