import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { Logo } from "@/components/Logo";
import { GoogleButton } from "@/components/GoogleButton";
import { Button, Rule } from "@/components/ui/primitives";
import { api, HttpError } from "@/lib/api";
import { useMe } from "@/hooks/useMe";

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const DEV_LOGIN = import.meta.env.VITE_ENABLE_DEV_LOGIN === "true";

export function SignIn() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: me, isLoading } = useMe();
  const [error, setError] = useState<string | null>(null);

  const signIn = useMutation({
    mutationFn: (credential: string) => api.signInWithGoogle(credential),
    onSuccess: (session) => {
      queryClient.setQueryData(["me"], session);
      navigate(session.onboarding.done ? "/app" : "/setup", { replace: true });
    },
    onError: (cause) => {
      setError(
        cause instanceof HttpError
          ? cause.message
          : "Could not reach the server. Is the API running?",
      );
    },
  });

  const devSignIn = useMutation({
    mutationFn: () => api.devSignIn(),
    onSuccess: (session) => {
      queryClient.setQueryData(["me"], session);
      navigate(session.onboarding.done ? "/app" : "/setup", { replace: true });
    },
    onError: (cause) => setError(cause instanceof HttpError ? cause.message : "Sign-in failed."),
  });

  // Already signed in: skip this screen entirely.
  if (!isLoading && me) {
    return <Navigate to={me.onboarding.done ? "/app" : "/setup"} replace />;
  }

  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <div className="shell flex h-16 items-center justify-between">
        <Logo />
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-[13px] text-ink-3 transition-colors hover:text-ink"
        >
          <ArrowLeft size={14} strokeWidth={1.75} />
          Back
        </Link>
      </div>

      <main className="flex flex-1 items-center justify-center px-5 pb-16">
        <div className="w-full max-w-[420px]">
          <div className="flex flex-col gap-2">
            <span className="eyebrow">Welcome</span>
            <h1 className="font-display text-[28px] font-semibold leading-tight tracking-[-0.02em]">
              Sign in to AutoApply
            </h1>
            <p className="text-[13.5px] leading-relaxed text-ink-2">
              One Google account. No password to remember, and no password for us to lose.
            </p>
          </div>

          <div className="mt-8 flex flex-col gap-4">
            <GoogleButton
              clientId={CLIENT_ID}
              width={352}
              onCredential={(credential) => {
                setError(null);
                signIn.mutate(credential);
              }}
              onError={setError}
            />

            {signIn.isPending ? (
              <p className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3">
                <Loader2 size={12} className="animate-spin" />
                Verifying with Google
              </p>
            ) : null}

            {error ? (
              <div
                role="alert"
                className="rounded-stamp border border-danger/40 bg-danger/5 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-danger"
              >
                {error}
              </div>
            ) : null}

            {DEV_LOGIN ? (
              <>
                <Rule label="Local only" />
                <Button
                  variant="secondary"
                  className="w-full"
                  onClick={() => devSignIn.mutate()}
                  disabled={devSignIn.isPending}
                >
                  {devSignIn.isPending ? "Signing in…" : "Sign in as a test user"}
                </Button>
                <p className="text-[11.5px] leading-relaxed text-ink-3">
                  Only shown when <code className="font-mono">VITE_ENABLE_DEV_LOGIN=true</code> and
                  the API is running in development.
                </p>
              </>
            ) : null}
          </div>

          <div className="mt-10 border-t border-line pt-5">
            <p className="text-[11.5px] leading-relaxed text-ink-3">
              By continuing you agree that automating LinkedIn and Naukri carries a risk of
              account restriction. We keep the pace slow and stop at the first sign of
              friction, but the risk is yours.{" "}
              <Link to="/#safety" className="link-underline">
                Read the rules
              </Link>
              .
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}