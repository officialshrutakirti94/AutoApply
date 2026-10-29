import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApplicationsTable } from "@/components/ApplicationsTable";
import { Stamp } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useLedger } from "@/hooks/useLedger";

export function CantSend() {
  const ledger = useLedger();
  const queryClient = useQueryClient();

  const dismiss = useMutation({
    mutationFn: (id: string) => api.resolveApplication(id, "resolved"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["applications"] }),
  });

  const saveAnswer = async (
    question: string,
    answer: string,
    sensitive: boolean,
  ): Promise<void> => {
    const normalize = (value: string) => {
      let normalized = value
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, " ")
        .replace(/\s+/g, " ")
        .trim();
      for (const prefix of [
        "what is your ",
        "what are your ",
        "whats your ",
        "what s your ",
        "please enter your ",
        "please provide your ",
        "enter your ",
        "do you have a ",
        "do you have an ",
      ]) {
        if (normalized.startsWith(prefix)) {
          normalized = normalized.slice(prefix.length);
          break;
        }
      }
      return normalized.slice(0, 500);
    };
    const pattern = normalize(question);
    const existing = (await api.listAnswers()).find(
      (entry) => entry.question_pattern === pattern,
    );
    if (existing) {
      await api.updateAnswer(existing.id, { answer, approved: true, sensitive });
    } else {
      await api.createAnswer({ question, answer, sensitive });
    }
  };

  return (
    <div className="mx-auto max-w-[1100px]">
      <header className="flex flex-wrap items-end justify-between gap-4 px-1 pb-5 pt-2">
        <div>
          <span className="eyebrow">Can&rsquo;t send</span>
          <h1 className="mt-1.5 font-display text-[26px] font-semibold tracking-[-0.02em]">
            Jobs it walked away from
          </h1>
          <p className="mt-1.5 max-w-[62ch] text-[13px] leading-relaxed text-ink-3">
            Review why an application stopped. For unanswered required questions, add your own
            response here to reuse on future jobs; this job will not be retried automatically.
          </p>
        </div>
        <Stamp tone="skipped">{ledger.counts.cantSend}</Stamp>
      </header>

      <ApplicationsTable
        items={ledger.cantSend}
        empty="Nothing was blocked. External redirects, already-applied jobs and CAPTCHA stops appear here."
        onResolve={(id) => dismiss.mutate(id)}
        resolving={dismiss.isPending}
        onSaveAnswer={saveAnswer}
      />
    </div>
  );
}