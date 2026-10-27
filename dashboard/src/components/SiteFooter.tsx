import { Logo } from "@/components/Logo";

const columns = [
  {
    title: "Product",
    links: [
      { label: "How it works", href: "/#how" },
      { label: "Safety rules", href: "/#safety" },
      { label: "Pricing", href: "/#pricing" },
      { label: "Dashboard", href: "/signin" },
    ],
  },
  {
    title: "Platforms",
    links: [
      { label: "LinkedIn Easy Apply", href: "/#product" },
      { label: "Naukri in-site apply", href: "/#product" },
      { label: "Needs-you inbox", href: "/#product" },
    ],
  },
  {
    title: "Trust",
    links: [
      { label: "What it never does", href: "/#safety" },
      { label: "Your data", href: "/#safety" },
      { label: "Delete everything", href: "/#safety" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-line">
      <div className="shell py-14">
        <div className="grid gap-10 md:grid-cols-[1.4fr_repeat(3,1fr)]">
          <div className="flex flex-col gap-4">
            <Logo />
            <p className="max-w-[34ch] text-[13px] leading-relaxed text-ink-3">
              An agent that fills and submits job applications in your own browser, at
              a pace that keeps your account alive.
            </p>
            <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-3">
              <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-signal" />
              Private beta
            </div>
          </div>

          {columns.map((column) => (
            <div key={column.title} className="flex flex-col gap-3">
              <span className="eyebrow">{column.title}</span>
              <ul className="flex flex-col gap-2">
                {column.links.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      className="text-[13px] text-ink-2 transition-colors hover:text-ink"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-2 border-t border-line pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3">
            © {new Date().getFullYear()} AutoApply · Built for India&rsquo;s job market
          </p>
          <p className="max-w-[52ch] text-[11.5px] leading-relaxed text-ink-3">
            Automating LinkedIn and Naukri goes against their terms of use. We keep the
            pace slow and stop at the first sign of friction, but the risk is yours.
          </p>
        </div>
      </div>
    </footer>
  );
}