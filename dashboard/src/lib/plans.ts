import type { PlanLimits } from "@/lib/api";

/**
 * Landing-page pricing copy.
 *
 * The prices and caps mirror `backend/app/safety/plans.py`. The backend owns the
 * entitlement; this file only renders it, and `GET /api/plan` returns the same
 * numbers for the in-app plan card. Keep the two in step.
 */
export const PLANS: PlanLimits[] = [
  {
    tier: "regular",
    label: "Regular",
    daily_cap: 10,
    hourly_cap: 3,
    llm_calls_per_day: 60,
    price: "Free",
    blurb: "10 applications a day, both platforms, everything the agent can do.",
  },
  {
    tier: "pro",
    label: "Pro",
    daily_cap: 18,
    hourly_cap: 4,
    llm_calls_per_day: 120,
    price: "₹499 / month",
    blurb: "18 applications a day and more room for free-text screening answers.",
  },
  {
    tier: "pro_plus",
    label: "Pro Plus",
    daily_cap: 25,
    hourly_cap: 6,
    llm_calls_per_day: 200,
    price: "₹999 / month",
    blurb: "The maximum we allow. 25 applications a day, the hard safety ceiling.",
  },
];