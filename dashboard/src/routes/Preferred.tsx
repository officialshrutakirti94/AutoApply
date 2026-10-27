import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Check } from "lucide-react";
import { Stamp } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useLedger } from "@/hooks/useLedger";
import { clock } from "@/lib/format";

function isCompanySiteLink(url: string | null): boolean {
  if (!url) return false;
  try {
    const hostname = new URL(url).hostname;
    return hostname !== "linkedin.com" && !hostname.endsWith(".linkedin.com");
  } catch {
    return false;
  }
}

/**
 * Preferred jobs: the agent found them, decided the application happens on the
 * company's own site, and stepped back. These are the ones worth your time.
 */
export function Preferred() {
  const ledger = useLedger();
  const queryClient = useQueryClient();

  const done = useMutation({
    mutationFn: (id: string) => api.resolveApplication(id, "resolved"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["applications"] }),
  });

  return (
    <div className="mx-auto max-w-[1100px]">
      <header className="flex flex-wrap items-end justify-between gap-4 px-1 pb-5 pt-2">
        <div>
          <span className="eyebrow">Preferred jobs</span>
          <h1 className="mt-1.5 font-display text-[26px] font-semibold tracking-[-0.02em]">
            Apply on the company site
          </h1>
          <p className="mt-1.5 max-w-[62ch] text-[13px] leading-relaxed text-ink-3">
            These matched your profile but are not Easy Apply. The agent never follows a link
            off the platform. If LinkedIn exposes the company application link, open it here;
            otherwise open the LinkedIn job and continue manually.
          </p>
        </div>
        <Stamp tone="attention">{ledger.counts.preferred}</Stamp>
      </header>

      {ledger.preferred.length ? (
        <div className="flex flex-col gap-3">
          {ledger.preferred.map((item) => {
            const companySiteLink = isCompanySiteLink(item.job_url);
            return (
              <div key={item.id} className="rounded-cell border border-line bg-surface p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[14.5px] text-ink">{item.job_title ?? "Untitled role"}</p>
                    <p className="mt-0.5 font-mono text-[10.5px] text-ink-3">
                      {item.company ?? "—"} · {item.platform} · {clock(item.created_at)}
                    </p>
                  </div>
                  <Stamp tone="skipped">Company site</Stamp>
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-3">
                  {item.job_url ? (
                    <a href={item.job_url} target="_blank" rel="noreferrer">
                      <span className="inline-flex h-9 items-center gap-1.5 rounded-stamp bg-ink px-3.5 text-[12.5px] font-semibold text-bg">
                        {companySiteLink ? "Open company site" : "Open LinkedIn job"}
                        <ArrowUpRight size={13} strokeWidth={2} />
                      </span>
                    </a>
                  ) : (
                    <span className="text-[12.5px] text-ink-3">No link captured</span>
                  )}
                  <button
                    type="button"
                    onClick={() => done.mutate(item.id)}
                    disabled={done.isPending}
                    className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-3 transition-colors hover:text-moss disabled:opacity-50"
                  >
                    <Check size={13} strokeWidth={2} />
                    I applied
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-cell border border-dashed border-line-strong px-6 py-12 text-center">
          <p className="mx-auto max-w-[46ch] text-[13.5px] leading-relaxed text-ink-3">
            Nothing here yet. When a matching job applies on the company&rsquo;s own site, it lands
            in this list instead of being skipped silently.
          </p>
        </div>
      )}
    </div>
  );
}