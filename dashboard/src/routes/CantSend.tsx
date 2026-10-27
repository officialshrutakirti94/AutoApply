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

  return (
    <div className="mx-auto max-w-[1100px]">
      <header className="flex flex-wrap items-end justify-between gap-4 px-1 pb-5 pt-2">
        <div>
          <span className="eyebrow">Can&rsquo;t send</span>
          <h1 className="mt-1.5 font-display text-[26px] font-semibold tracking-[-0.02em]">
            Jobs it walked away from
          </h1>
          <p className="mt-1.5 max-w-[62ch] text-[13px] leading-relaxed text-ink-3">
            Structural dead ends: the application lives on the company&rsquo;s own site, you
            already applied, the role did not fit, or the platform showed a security check.
            Nothing here needs you — it is a record, not a task.
          </p>
        </div>
        <Stamp tone="skipped">{ledger.counts.cantSend}</Stamp>
      </header>

      <ApplicationsTable
        items={ledger.cantSend}
        empty="Nothing was blocked. External redirects, already-applied jobs and CAPTCHA stops appear here."
        onResolve={(id) => dismiss.mutate(id)}
        resolving={dismiss.isPending}
      />
    </div>
  );
}