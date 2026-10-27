import { Link } from "react-router-dom";
import { cn } from "@/lib/cn";

export function Logo({ className }: { className?: string }) {
  return (
    <Link
      to="/"
      className={cn("group inline-flex items-center gap-2.5", className)}
      aria-label="AutoApply home"
    >
      <span
        aria-hidden
        className="relative grid h-6 w-6 place-items-center rounded-stamp border border-line-strong"
      >
        <span className="h-2 w-2 rounded-full bg-signal transition-transform duration-300 group-hover:scale-125" />
      </span>
      <span className="font-display text-[15px] font-semibold tracking-[-0.01em] text-ink">
        Auto<span className="text-ink-2">Apply</span>
      </span>
    </Link>
  );
}