import { useEffect } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  Inbox,
  Star,
  LogOut,
  Send,
  Settings,
  UserRound,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Logo } from "@/components/Logo";
import { Stamp } from "@/components/ui/primitives";
import { api, HttpError, type Me } from "@/lib/api";
import { cn } from "@/lib/cn";
import { initials } from "@/lib/format";
import { useMe } from "@/hooks/useMe";
import { useLedger } from "@/hooks/useLedger";

type SidebarCounts = {
  sent: number;
  waiting: number;
  preferred: number;
  cantSend: number;
};

type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  count?: keyof SidebarCounts;
};

const nav: NavItem[] = [
  { to: "/app/sent", label: "Applications sent", icon: Send, count: "sent" },
  { to: "/app/waiting", label: "Waiting for confirmations", icon: Inbox, count: "waiting" },
  { to: "/app/preferred", label: "Preferred jobs", icon: Star, count: "preferred" },
  { to: "/app/failed", label: "Can't send", icon: XCircle, count: "cantSend" },
  { to: "/app/resume", label: "Your resume", icon: FileText },
  { to: "/app/profile", label: "Your profile", icon: UserRound },
  { to: "/app/settings", label: "Settings", icon: Settings },
];

export function AppLayout() {
  const location = useLocation();
  const { data: me, isLoading, error } = useMe();
  const { counts } = useLedger();
  const queryClient = useQueryClient();

  const signOut = useMutation({
    mutationFn: api.signOut,
    onSuccess: () => {
      queryClient.clear();
      window.location.assign("/");
    },
  });

  useEffect(() => {
    if (error instanceof HttpError && error.status === 401) {
      queryClient.removeQueries({ queryKey: ["me"] });
    }
  }, [error, queryClient]);

  if (isLoading) return <ShellSkeleton />;

  if (!me) {
    if (error instanceof HttpError && error.status === 401) {
      return <Navigate to="/signin" replace state={{ from: location.pathname }} />;
    }
    return (
      <div className="grid min-h-screen place-items-center px-6 text-center">
        <div className="max-w-sm">
          <p className="text-[15px] text-ink">Cannot reach the API.</p>
          <p className="mt-2 text-[13px] leading-relaxed text-ink-2">
            Is the backend running on <code className="font-mono">127.0.0.1:8000</code>?
          </p>
        </div>
      </div>
    );
  }

  if (!me.onboarding.done) return <Navigate to="/setup" replace />;

  return (
    <div className="min-h-screen bg-bg">
      <div className="mx-auto flex w-full max-w-[1440px]">
      <Sidebar user={me} counts={counts} onSignOut={() => signOut.mutate()} />

        <div className="min-w-0 flex-1">
        <MobileBar user={me} counts={counts} />
          <main className="px-4 pb-16 pt-4 sm:px-6 lg:px-8">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}

function Sidebar({
  user,
  counts,
  onSignOut,
}: {
  user: Me;
  counts: SidebarCounts;
  onSignOut: () => void;
}) {
  return (
    <aside className="sticky top-0 hidden h-screen w-[252px] shrink-0 flex-col justify-between border-r border-line px-4 py-5 lg:flex">
      <div className="flex flex-col gap-8">
        <div className="px-2">
          <Logo />
        </div>

        <nav aria-label="Dashboard" className="flex flex-col gap-0.5">
          <NavLink
            to="/app"
            end
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2.5 rounded-stamp px-2.5 py-2 text-[13.5px] transition-colors",
                isActive ? "bg-surface text-ink" : "text-ink-2 hover:bg-surface hover:text-ink",
              )
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    isActive ? "bg-signal" : "bg-line-strong",
                  )}
                />
                Overview
              </>
            )}
          </NavLink>

          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-stamp px-2.5 py-2 text-[13px] transition-colors",
                  isActive ? "bg-surface text-ink" : "text-ink-2 hover:bg-surface hover:text-ink",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon
                    size={14}
                    strokeWidth={1.6}
                    className={isActive ? "text-signal" : "text-ink-3"}
                  />
                  <span className="min-w-0 flex-1">{item.label}</span>
                  {item.count && counts[item.count] > 0 ? (
                    <CountBadge count={counts[item.count]} label={item.label} />
                  ) : null}
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="flex flex-col gap-3">
        <Link
          to="/app/profile"
          className="flex items-center justify-between rounded-stamp border border-line px-2.5 py-2 transition-colors hover:border-line-strong"
        >
          <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
            Plan
          </span>
          <Stamp>{user.user.plan.replace("_", " ")}</Stamp>
        </Link>

        <div className="flex items-center gap-2.5 px-1">
          <Avatar name={user.user.name} email={user.user.email} url={user.user.avatar_url} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[12.5px] text-ink">{user.user.name ?? "You"}</p>
            <p className="truncate font-mono text-[10px] text-ink-3">{user.user.email}</p>
          </div>
          <button
            type="button"
            onClick={onSignOut}
            aria-label="Sign out"
            className="rounded-stamp p-1.5 text-ink-3 transition-colors hover:bg-surface hover:text-ink"
          >
            <LogOut size={14} strokeWidth={1.7} />
          </button>
        </div>
      </div>
    </aside>
  );
}

function MobileBar({ user, counts }: { user: Me; counts: SidebarCounts }) {
  return (
    <div className="sticky top-0 z-30 border-b border-line bg-bg/95 lg:hidden">
      <div className="flex items-center justify-between px-4 py-3">
        <Logo />
        <Stamp>{user.user.plan.replace("_", " ")}</Stamp>
      </div>
      <nav aria-label="Dashboard" className="flex gap-1 overflow-x-auto px-3 pb-2">
        <NavLink
          to="/app"
          end
          className={({ isActive }) =>
            cn(
              "whitespace-nowrap rounded-stamp px-2.5 py-1.5 text-[12px]",
              isActive ? "bg-surface text-ink" : "text-ink-2",
            )
          }
        >
          Overview
        </NavLink>
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                "whitespace-nowrap rounded-stamp px-2.5 py-1.5 text-[12px]",
                isActive ? "bg-surface text-ink" : "text-ink-2",
              )
            }
          >
            <span>{item.label}</span>
            {item.count && counts[item.count] > 0 ? (
              <CountBadge count={counts[item.count]} label={item.label} compact />
            ) : null}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

function CountBadge({
  count,
  label,
  compact = false,
}: {
  count: number;
  label: string;
  compact?: boolean;
}) {
  return (
    <span
      aria-label={`${count} ${label}`}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-orange-100 font-mono font-semibold text-orange-800 ring-1 ring-inset ring-orange-200",
        compact ? "min-w-[18px] px-1 text-[9px] leading-[18px]" : "min-w-[20px] px-1.5 text-[10px] leading-5",
      )}
    >
      {count}
    </span>
  );
}

function Avatar({
  name,
  email,
  url,
}: {
  name: string | null;
  email: string;
  url: string | null;
}) {
  if (url) {
    return (
      <img
        src={url}
        alt=""
        referrerPolicy="no-referrer"
        className="h-7 w-7 shrink-0 rounded-full border border-line object-cover"
      />
    );
  }
  return (
    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-line bg-surface-2 font-mono text-[10px] text-ink-2">
      {initials(name, email)}
    </span>
  );
}

function ShellSkeleton() {
  return (
    <div className="flex min-h-screen">
      <div className="hidden w-[252px] border-r border-line lg:block" />
      <div className="flex-1 p-6">
        <div className="grid gap-3 xl:grid-cols-12">
          {[8, 4, 4, 4, 4, 6, 6].map((span, index) => (
            <div
              key={index}
              className="h-32 animate-pulse rounded-cell border border-line bg-surface/60"
              style={{ gridColumn: `span ${span} / span ${span}` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
