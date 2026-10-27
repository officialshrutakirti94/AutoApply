import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/cn";

/* ---------------------------------------------------------------------------
   The design system, in one file for now. Every component is flat: hairlines,
   4px radius, no shadows. The accent is used only for the primary action, the
   live dot and status.
   --------------------------------------------------------------------------- */

type ButtonVariant = "primary" | "secondary" | "ghost" | "signal";
type ButtonSize = "sm" | "md" | "lg";

const buttonBase =
  "inline-flex items-center justify-center gap-2 rounded-stamp font-display font-semibold " +
  "transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-45 " +
  "whitespace-nowrap select-none";

const buttonVariants: Record<ButtonVariant, string> = {
  primary: "bg-ink text-bg hover:bg-white",
  signal: "bg-signal text-white hover:bg-[#ff4b32]",
  secondary: "border border-line-strong text-ink hover:border-ink-3 hover:bg-surface-2",
  ghost: "text-ink-2 hover:text-ink hover:bg-surface-2",
};

const buttonSizes: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-10 px-4 text-[14px]",
  lg: "h-12 px-6 text-[15px]",
};

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", size = "md", type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(buttonBase, buttonVariants[variant], buttonSizes[size], className)}
      {...props}
    />
  );
});

/** A block-level status tag. Uppercase, mono, 1px border, slightly tilted. */
export function Stamp({
  tone = "neutral",
  children,
  className,
}: {
  tone?: "neutral" | "applied" | "attention" | "skipped" | "signal";
  children: ReactNode;
  className?: string;
}) {
  const tones: Record<string, string> = {
    neutral: "border-line-strong text-ink-2",
    applied: "border-moss/50 text-moss",
    attention: "border-ochre/50 text-ochre",
    skipped: "border-line-strong text-ink-3",
    signal: "border-signal/60 text-signal-ink",
  };

  return (
    <span
      className={cn(
        "inline-flex rotate-[-1deg] items-center rounded-stamp border px-1.5 py-0.5",
        "font-mono text-[10px] uppercase leading-none tracking-[0.1em]",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** A quiet pill for filters and roles. Rectangular, not a bubble. */
export function Chip({
  children,
  active = false,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex h-7 items-center rounded-stamp border px-2.5 text-[12.5px] transition-colors",
        active
          ? "border-ink bg-ink text-bg"
          : "border-line text-ink-2 hover:border-line-strong hover:text-ink",
        className,
      )}
      aria-pressed={active}
      {...props}
    >
      {children}
    </button>
  );
}

/** A 1px rule with an optional inline label, instead of a card boundary. */
export function Rule({ label, className }: { label?: string; className?: string }) {
  if (!label) return <hr className={cn("border-0 border-t border-line", className)} />;
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <span className="eyebrow whitespace-nowrap">{label}</span>
      <span className="h-px flex-1 bg-line" />
    </div>
  );
}

/** The bento cell. A border, a radius, nothing else. */
export function Cell({
  as: Tag = "div",
  className,
  children,
  ...props
}: {
  as?: "div" | "section" | "article" | "li";
  className?: string;
  children: ReactNode;
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <Tag className={cn("cell relative overflow-hidden", className)} {...props}>
      {children}
    </Tag>
  );
}

/** Cell header: mono label on the left, an action on the right. */
export function CellHeader({
  label,
  children,
  className,
}: {
  label: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center justify-between gap-3 px-5 pt-4", className)}>
      <span className="eyebrow">{label}</span>
      {children}
    </div>
  );
}

/** A huge tabular numeral with a caption under it. */
export function Stat({
  value,
  caption,
  tone = "ink",
  className,
}: {
  value: ReactNode;
  caption: string;
  tone?: "ink" | "moss" | "ochre" | "signal" | "muted";
  className?: string;
}) {
  const tones: Record<string, string> = {
    ink: "text-ink",
    moss: "text-moss",
    ochre: "text-ochre",
    signal: "text-signal-ink",
    muted: "text-ink-3",
  };
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <span
        className={cn(
          "tabular font-display text-[40px] font-semibold leading-none tracking-[-0.03em]",
          tones[tone],
        )}
      >
        {value}
      </span>
      <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-ink-3">
        {caption}
      </span>
    </div>
  );
}

export function Field({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-[13px] font-medium text-ink-2">
        {label}
      </label>
      {children}
      {hint ? <p className="text-[12.5px] text-ink-3">{hint}</p> : null}
    </div>
  );
}

export const inputClass =
  "h-10 w-full rounded-stamp border border-line bg-surface px-3 text-[14px] text-ink " +
  "placeholder:text-ink-3 hover:border-line-strong focus:border-line-strong";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(inputClass, props.className)} />;
}

/** A single ledger row: mono time, title, right-hand stamp. */
export function LedgerRow({
  time,
  title,
  meta,
  stamp,
  href,
  className,
}: {
  time: string;
  title: string;
  meta?: string;
  stamp?: ReactNode;
  href?: string;
  className?: string;
}) {
  const content = (
    <>
      <span className="w-12 shrink-0 font-mono text-[11px] tabular text-ink-3">{time}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13.5px] text-ink">{title}</span>
        {meta ? (
          <span className="block truncate font-mono text-[11px] text-ink-3">{meta}</span>
        ) : null}
      </span>
      {stamp}
    </>
  );

  const classes = cn(
    "flex items-center gap-3 border-t border-line px-5 py-2.5 first:border-t-0",
    href && "transition-colors hover:bg-surface-2",
    className,
  );

  return href ? (
    <a href={href} target="_blank" rel="noreferrer" className={classes}>
      {content}
    </a>
  ) : (
    <div className={classes}>{content}</div>
  );
}