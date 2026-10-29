import { useMutation, useQueryClient } from "@tanstack/react-query";
import { WaitingTable } from "@/components/ApplicationsTable";
import { Stamp } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useLedger } from "@/hooks/useLedger";

export function Waiting() {
  const ledger = useLedger();
  const queryClient = useQueryClient();

  const resolve = useMutation({
    mutationFn: (id: string) => api.resolveApplication(id, "resolved"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["applications"] }),
  });

  return (
    <div className="mx-auto max-w-[1100px]">
      <header className="flex flex-wrap items-end justify-between gap-4 px-1 pb-5 pt-2">
        <div>
          <span className="eyebrow">Waiting for confirmations</span>
          <h1 className="mt-1.5 font-display text-[26px] font-semibold tracking-[-0.02em]">
            It needs your answer
          </h1>
          <p className="mt-1.5 max-w-[62ch] text-[13px] leading-relaxed text-ink-3">
            Required questions that need your input now appear in Can&rsquo;t send with an option
            to save your answer for future applications.
          </p>
        </div>
        <Stamp tone="attention">{ledger.counts.waiting}</Stamp>
      </header>

      <WaitingTable
        items={ledger.waiting}
        onResolve={(id) => resolve.mutate(id)}
        resolving={resolve.isPending}
      />
    </div>
  );
}