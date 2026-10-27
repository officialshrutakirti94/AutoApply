import { Link } from "react-router-dom";
import { ArrowRight, Check, ExternalLink } from "lucide-react";
import { SiteHeader } from "@/components/SiteHeader";
import { SiteFooter } from "@/components/SiteFooter";
import {
  Button,
  Cell,
  CellHeader,
  Chip,
  LedgerRow,
  Rule,
  Stamp,
} from "@/components/ui/primitives";
import { PLANS } from "@/lib/plans";
import { useMe } from "@/hooks/useMe";

/* ---------------------------------------------------------------------------
   The landing page. Dark, one accent, no gradients on type, no stock imagery:
   the product's own ledger is the hero graphic.
   --------------------------------------------------------------------------- */

export function Landing() {
  const { data: me } = useMe();

  return (
    <div className="min-h-screen bg-bg">
      <SiteHeader signedIn={Boolean(me)} />
      <main>
        <Hero />
        <PlatformStrip />
        <WhatItDoes />
        <HowItWorks />
        <Safety />
        <Pricing />
        <FinalCta />
      </main>
      <SiteFooter />
    </div>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-line">
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="hero-sun" />
        <div className="hero-floor" />
        <div className="hero-vignette" />
      </div>

      <div className="shell relative z-10 pt-16 pb-24 sm:pt-24 sm:pb-32">
        <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
          <div className="inline-flex items-center gap-2 rounded-stamp border border-line-strong bg-surface/60 px-3 py-1.5">
            <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-signal" />
            <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-2">
              Private beta · LinkedIn &amp; Naukri
            </span>
          </div>

          <h1 className="mt-7 text-balance font-display text-[clamp(2.6rem,7.2vw,5rem)] font-semibold leading-[0.94] tracking-[-0.035em]">
            Stop applying.
            <br />
            <span className="text-ink-2">Start reviewing.</span>
          </h1>

          <p className="mt-6 max-w-[56ch] text-pretty text-[15.5px] leading-relaxed text-ink-2 sm:text-[16.5px]">
            AutoApply fills and submits the jobs that match your profile — in your own
            browser, at a pace a human would keep, and it stops the moment anything looks
            off. Anything it can&rsquo;t finish lands in <em className="not-italic text-ink">Needs you</em>{" "}
            with a link.
          </p>

          <div className="mt-9 flex flex-col items-center gap-3 sm:flex-row">
            <Link to="/signin">
              <Button size="lg" variant="signal" className="w-full sm:w-auto">
                Continue with Google
                <ArrowRight size={16} strokeWidth={1.75} />
              </Button>
            </Link>
            <a href="#how">
              <Button size="lg" variant="secondary" className="w-full sm:w-auto">
                See how it works
              </Button>
            </a>
          </div>

          <p className="mt-5 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-3">
            10 applications a day free · no card · resets 10:00 IST
          </p>
        </div>

        <HeroLedger />
      </div>
    </section>
  );
}

const heroRows = [
  { time: "14:32", title: "Backend Engineer · Acme Systems", meta: "linkedin", tone: "applied" as const, label: "Applied" },
  { time: "14:29", title: "Data Analyst · Finlytics", meta: "naukri", tone: "attention" as const, label: "Needs you" },
  { time: "14:26", title: "Backend Engineer · Northwind", meta: "linkedin", tone: "skipped" as const, label: "Skipped · external" },
  { time: "14:21", title: "SDE II · Blue Orbit", meta: "linkedin", tone: "applied" as const, label: "Applied" },
];

function HeroLedger() {
  return (
    <div className="relative mx-auto mt-16 w-full max-w-2xl">
      <div className="pointer-events-none absolute -inset-x-6 -top-6 bottom-0 rounded-cell bg-gradient-to-b from-transparent to-bg/0" />
      <Cell className="animate-rise-in bg-surface/95 [animation-delay:120ms]">
        <CellHeader label="Agent log">
          <span className="inline-flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-3">
            <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-signal" />
            live
          </span>
        </CellHeader>

        <div className="mt-3 pb-1">
          {heroRows.map((row, index) => (
            <div
              key={row.time}
              className="animate-rise-in"
              style={{ animationDelay: `${180 + index * 70}ms` }}
            >
              <LedgerRow
                time={row.time}
                title={row.title}
                meta={row.meta}
                stamp={<Stamp tone={row.tone}>{row.label}</Stamp>}
              />
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between border-t border-line px-5 py-3">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-3">
            Every action, with a timestamp and a reason
          </span>
          <span className="font-mono text-[10.5px] tabular text-ink-3">10 / 10 today</span>
        </div>
      </Cell>
    </div>
  );
}

function PlatformStrip() {
  const items = [
    "LinkedIn Easy Apply",
    "Naukri in-site apply",
    "Needs-you inbox",
    "10 / day, by plan",
  ];

  return (
    <section className="border-b border-line">
      <div className="shell flex flex-wrap items-center justify-between gap-x-8 gap-y-3 py-5">
        <span className="eyebrow">Built for the two platforms that matter</span>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          {items.map((item) => (
            <span
              key={item}
              className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3"
            >
              <Check size={12} strokeWidth={2} className="text-moss" />
              {item}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

const features = [
  {
    n: "01",
    title: "It reads the form, not a script",
    body:
      "The extension reports each field as a handle. The agent decides what goes in it. It never sees a CSS selector, and it cannot navigate anywhere you aren't.",
  },
  {
    n: "02",
    title: "Answers come from your profile",
    body:
      "Current CTC, expected CTC, notice period, experience, links. Answered instantly with zero model calls. A model is only asked about a genuinely new question — and never about anything sensitive.",
  },
  {
    n: "03",
    title: "It stops before it hurts you",
    body:
      "CAPTCHA, security check, warning banner, three errors in a row. The run ends, a cooldown starts, and nothing is submitted. Your account matters more than the quota.",
  },
];

function WhatItDoes() {
  return (
    <section id="product" className="border-b border-line">
      <div className="shell py-20 sm:py-28">
        <div className="max-w-2xl">
          <span className="eyebrow">What it actually does</span>
          <h2 className="mt-4 text-balance font-display text-[clamp(1.9rem,3.6vw,2.9rem)] font-semibold leading-[1.05] tracking-[-0.02em]">
            Three things, done properly.
          </h2>
          <p className="mt-4 text-[15px] leading-relaxed text-ink-2">
            Most tools promise to apply everywhere. We do the two platforms that Indian
            hiring actually runs on, and we are honest about the edges.
          </p>
        </div>

        <div className="mt-12 grid gap-3 md:grid-cols-3">
          {features.map((feature) => (
            <Cell key={feature.n} className="flex flex-col gap-4 p-6">
              <span className="font-mono text-[11px] tracking-[0.12em] text-signal-ink">
                {feature.n}
              </span>
              <h3 className="font-display text-[17px] font-semibold leading-snug text-ink">
                {feature.title}
              </h3>
              <p className="text-[13.5px] leading-relaxed text-ink-2">{feature.body}</p>
            </Cell>
          ))}
        </div>
      </div>
    </section>
  );
}

const steps = [
  {
    n: "1",
    title: "Upload your resume",
    body:
      "We read it and prefill everything — name, links, skills, experience, CTC. You correct what is wrong. Nothing is final until you confirm it.",
  },
  {
    n: "2",
    title: "Open LinkedIn or Naukri",
    body:
      "Sign in as you normally would. The extension pairs with one eight-character code and the dashboard flips to Connected.",
  },
  {
    n: "3",
    title: "Press Start Magic",
    body:
      "It works inside your own browser, one tab, one job at a time. You watch the log fill up. Anything stuck comes back to you with a link to the exact page.",
  },
];

function HowItWorks() {
  return (
    <section id="how" className="border-b border-line">
      <div className="shell py-20 sm:py-28">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div className="max-w-xl">
            <span className="eyebrow">How it works</span>
            <h2 className="mt-4 text-balance font-display text-[clamp(1.9rem,3.6vw,2.9rem)] font-semibold leading-[1.05] tracking-[-0.02em]">
              Five minutes of setup. Then it runs.
            </h2>
          </div>
          <p className="max-w-sm text-[13.5px] leading-relaxed text-ink-3">
            No password sharing, no headless browser on our servers, no cloud profile. It
            uses the browser you are already signed into.
          </p>
        </div>

        <div className="mt-12 grid gap-px overflow-hidden rounded-cell border border-line bg-line md:grid-cols-3">
          {steps.map((step) => (
            <div key={step.n} className="flex flex-col gap-4 bg-surface p-7">
              <span className="grid h-8 w-8 place-items-center rounded-stamp border border-line-strong font-mono text-[12px] text-ink-2">
                {step.n}
              </span>
              <h3 className="font-display text-[16.5px] font-semibold text-ink">
                {step.title}
              </h3>
              <p className="text-[13.5px] leading-relaxed text-ink-2">{step.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const caps = [
  ["Applications", "10 per day on Regular"],
  ["Hourly", "3 applications"],
  ["Between applications", "45–180 seconds, randomised"],
  ["Quota reset", "10:00, your timezone"],
  ["One run", "one tab, one platform"],
  ["Hard stop", "48-hour cooldown"],
];

const never = [
  "Run headless, or on our servers",
  "Ask for your LinkedIn or Naukri password",
  "Apply to a job that redirects off-platform",
  "Submit an answer it is not sure about",
  "Exceed your daily quota, even if asked to",
];

function Safety() {
  return (
    <section id="safety" className="border-b border-line">
      <div className="shell py-20 sm:py-28">
        <div className="grid gap-12 lg:grid-cols-[1.1fr_1fr] lg:gap-16">
          <div>
            <span className="eyebrow">Safety is the feature</span>
            <h2 className="mt-4 text-balance font-display text-[clamp(1.9rem,3.6vw,2.9rem)] font-semibold leading-[1.05] tracking-[-0.02em]">
              It is designed to stay boring.
            </h2>
            <p className="mt-4 max-w-[52ch] text-[15px] leading-relaxed text-ink-2">
              Automating these platforms breaks their terms. We can&rsquo;t make that risk
              disappear, so we make it small: slow pacing, hard ceilings, and a refusal to
              guess. Every rule below is enforced in code, not by a prompt.
            </p>

            <Rule label="Never" className="mt-10" />
            <ul className="mt-5 flex flex-col gap-3">
              {never.map((item) => (
                <li key={item} className="flex items-start gap-3 text-[13.5px] text-ink-2">
                  <span
                    aria-hidden
                    className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-signal"
                  />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <Cell className="self-start">
            <CellHeader label="Hard limits" />
            <dl className="mt-3">
              {caps.map(([term, value]) => (
                <div
                  key={term}
                  className="flex items-baseline justify-between gap-6 border-t border-line px-5 py-3 first:border-t-0"
                >
                  <dt className="font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3">
                    {term}
                  </dt>
                  <dd className="text-right text-[13px] text-ink">{value}</dd>
                </div>
              ))}
            </dl>
            <div className="border-t border-line px-5 py-3">
              <p className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
                Tuned for account survival, not throughput
              </p>
            </div>
          </Cell>
        </div>
      </div>
    </section>
  );
}

function Pricing() {
  return (
    <section id="pricing" className="border-b border-line">
      <div className="shell py-20 sm:py-28">
        <div className="mx-auto max-w-2xl text-center">
          <span className="eyebrow">Pricing</span>
          <h2 className="mt-4 text-balance font-display text-[clamp(1.9rem,3.6vw,2.9rem)] font-semibold leading-[1.05] tracking-[-0.02em]">
            Pay for more room, never for more risk.
          </h2>
          <p className="mt-4 text-[15px] leading-relaxed text-ink-2">
            Every plan uses the same agent. The difference is how many applications a day
            it is allowed to spend — and the top tier sits exactly on our hard ceiling.
          </p>
        </div>

        <div className="mt-12 grid items-start gap-3 md:grid-cols-3">
          {PLANS.map((plan) => {
            const featured = plan.tier === "pro";
            return (
              <Cell
                key={plan.tier}
                className={
                  featured
                    ? "relative flex flex-col gap-5 border-signal/40 p-6 md:-mt-3 md:pb-8"
                    : "flex flex-col gap-5 p-6"
                }
              >
                {featured ? (
                  <span
                    aria-hidden
                    className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-signal to-transparent"
                  />
                ) : null}

                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-display text-[16px] font-semibold text-ink">
                      {plan.label}
                    </h3>
                    <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3">
                      {plan.daily_cap} / day
                    </p>
                  </div>
                  {featured ? <Stamp tone="signal">Most picked</Stamp> : null}
                </div>

                <div className="flex items-baseline gap-1.5">
                  <span className="tabular font-display text-[30px] font-semibold leading-none tracking-[-0.02em] text-ink">
                    {plan.price.replace(" / month", "")}
                  </span>
                  {plan.price !== "Free" ? (
                    <span className="font-mono text-[11px] text-ink-3">/ month</span>
                  ) : null}
                </div>

                <p className="min-h-[3.5rem] text-[13px] leading-relaxed text-ink-2">
                  {plan.blurb}
                </p>

                <ul className="flex flex-col gap-2 border-t border-line pt-4">
                  {[
                    `${plan.daily_cap} applications a day`,
                    `${plan.hourly_cap} per hour at most`,
                    `${plan.llm_calls_per_day} model answers a day`,
                    "LinkedIn + Naukri",
                    "Needs-you inbox",
                  ].map((line) => (
                    <li
                      key={line}
                      className="flex items-center gap-2 text-[12.5px] text-ink-2"
                    >
                      <Check size={12} strokeWidth={2.2} className="text-moss" />
                      {line}
                    </li>
                  ))}
                </ul>

                <Link to="/signin" className="mt-auto pt-2">
                  <Button
                    variant={featured ? "signal" : "secondary"}
                    className="w-full"
                    size="sm"
                  >
                    {featured ? "Start with Pro" : `Choose ${plan.label}`}
                  </Button>
                </Link>
              </Cell>
            );
          })}
        </div>

        <p className="mt-8 text-center font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3">
          Prices are placeholders while this is a beta · no payment is taken
        </p>
      </div>
    </section>
  );
}

function FinalCta() {
  return (
    <section className="relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute left-1/2 top-[70%] h-[520px] w-[900px] -translate-x-1/2 rounded-[50%] bg-[radial-gradient(circle_at_50%_50%,#e8402a_0%,#8f1d0f_34%,transparent_62%)] opacity-40 blur-[2px]" />
      </div>

      <div className="shell relative z-10 py-20 sm:py-28">
        <Cell className="overflow-hidden bg-surface/80">
          <div className="flex flex-col items-center gap-6 px-6 py-14 text-center sm:py-20">
            <Chip className="pointer-events-none">Private beta</Chip>
            <h2 className="max-w-[22ch] text-balance font-display text-[clamp(2rem,4.4vw,3.2rem)] font-semibold leading-[0.98] tracking-[-0.03em]">
              Ten applications a day, starting tomorrow morning.
            </h2>
            <p className="max-w-[46ch] text-[14.5px] leading-relaxed text-ink-2">
              Sign in with Google, upload one resume, and the log starts filling itself.
              You keep the final say on anything that looks human.
            </p>
            <div className="mt-2 flex flex-col items-center gap-3 sm:flex-row">
              <Link to="/signin">
                <Button size="lg" variant="signal">
                  Continue with Google
                  <ArrowRight size={16} strokeWidth={1.75} />
                </Button>
              </Link>
              <a
                href="https://github.com"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-[13px] text-ink-2 transition-colors hover:text-ink"
              >
                Read the safety rules
                <ExternalLink size={13} strokeWidth={1.75} />
              </a>
            </div>
          </div>
        </Cell>
      </div>
    </section>
  );
}