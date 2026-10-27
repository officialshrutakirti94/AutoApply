import { ApplicationsTable } from "@/components/ApplicationsTable";
import { Stamp } from "@/components/ui/primitives";
import { useLedger } from "@/hooks/useLedger";

export function Sent() {
  const ledger = useLedger();

  return (
    <div className="mx-auto max-w-[1100px]">
      <header className="flex flex-wrap items-end justify-between gap-4 px-1 pb-5 pt-2">
        <div>
          <span className="eyebrow">Applications sent</span>
          <h1 className="mt-1.5 font-display text-[26px] font-semibold tracking-[-0.02em]">
            Everything it has sent
          </h1>
          <p className="mt-1.5 max-w-[58ch] text-[13px] leading-relaxed text-ink-3">
            Submitted, with a timestamp and a link to the job. Practice runs are marked so
            you never mistake one for a real application.
          </p>
        </div>
        <Stamp tone="applied">{ledger.counts.sent}</Stamp>
      </header>

      <ApplicationsTable
        items={ledger.sent}
        empty="No applications sent yet. Connect the extension, start a run, and this list fills itself."
      />
    </div>
  );
}