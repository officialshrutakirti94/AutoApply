import { useQuery } from "@tanstack/react-query";
import { api, type PlanLimits } from "@/lib/api";
import { Button, Stamp } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { Check } from "lucide-react";

/**
 * The plan card. Read-only unless this is a development build, where the tiers are
 * clickable so the flow can be demonstrated (the API also refuses to switch in
 * production).
 */
export function PlanCard() {
  const plan = useQuery({ queryKey: ["plan"], queryFn: api.plan });
  const isDev = import.meta.env.DEV;

  const switchPlan = async (tier: PlanLimits["tier"]) => {
    await api.switchPlan(tier);
    await plan.refetch();
  };

  const tiers = plan.data?.available ?? [];
  const current = plan.data?.plan;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <p className="font-display text-[22px] font-semibold text-ink">
            {plan.data?.label ?? "Regular"}
          </p>
          <p className="mt-0.5 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
            {plan.data?.limits.daily_cap ?? 10} applications / day ·{" "}
            {plan.data?.limits.hourly_cap ?? 3} / hour
          </p>
        </div>
        <span className="tabular font-mono text-[12px] text-ink-2">
          {plan.data?.limits.price ?? "Free"}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {tiers.map((tier) => {
          const active = tier.tier === current;
          return (
            <div
              key={tier.tier}
              className={cn(
                "flex items-center justify-between gap-3 rounded-stamp border px-3 py-2.5",
                active ? "border-signal/50 bg-signal/5" : "border-line",
              )}
            >
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-[13px] text-ink">
                  {tier.label}
                  {active ? <Stamp tone="signal">Current</Stamp> : null}
                </p>
                <p className="truncate font-mono text-[10.5px] text-ink-3">
                  {tier.daily_cap}/day · {tier.llm_calls_per_day} model answers
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="whitespace-nowrap font-mono text-[11px] text-ink-2">
                  {tier.price}
                </span>
                {isDev && !active ? (
                  <Button size="sm" variant="ghost" onClick={() => switchPlan(tier.tier)}>
                    Switch
                  </Button>
                ) : active ? (
                  <Check size={13} strokeWidth={2.4} className="text-moss" />
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-[11.5px] leading-relaxed text-ink-3">
        The quota resets at 10:00 in your timezone. Every plan uses the same agent — the
        difference is how many applications a day it may spend.
        {isDev ? " Switch buttons are hidden in production." : ""}
      </p>
    </div>
  );
}