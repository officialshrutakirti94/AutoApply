import { Link } from "react-router-dom";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/primitives";

const links = [
  { href: "/#product", label: "Product" },
  { href: "/#how", label: "How it works" },
  { href: "/#safety", label: "Safety" },
  { href: "/#pricing", label: "Pricing" },
];

export function SiteHeader({ signedIn = false }: { signedIn?: boolean }) {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg/95">
      <div className="shell flex h-16 items-center justify-between gap-6">
        <div className="flex items-center gap-8">
          <Logo />
          <nav aria-label="Main" className="hidden items-center gap-6 md:flex">
            {links.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="text-[13.5px] text-ink-2 transition-colors hover:text-ink"
              >
                {link.label}
              </a>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-2">
          {signedIn ? (
            <Link to="/app">
              <Button size="sm">Open dashboard</Button>
            </Link>
          ) : (
            <>
              <Link
                to="/signin"
                className="hidden px-2 text-[13.5px] text-ink-2 transition-colors hover:text-ink sm:block"
              >
                Sign in
              </Link>
              <Link to="/signin">
                <Button size="sm" variant="signal">
                  Get started
                </Button>
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}