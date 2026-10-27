import { useEffect, useRef, useState } from "react";

const SCRIPT_ID = "google-identity-services";
let initialisedClientId: string | null = null;
const SCRIPT_SRC = "https://accounts.google.com/gsi/client";

type Status = "loading" | "ready" | "unconfigured" | "error";

/**
 * Google's own button. Their brand guidelines require it, so the design work goes
 * into the screen around it — not into re-styling this.
 *
 * The script is loaded once and shared; `renderButton` is idempotent per container.
 */
export function GoogleButton({
  clientId,
  onCredential,
  onError,
  width = 320,
}: {
  clientId: string | undefined;
  onCredential: (credential: string) => void;
  onError?: (message: string) => void;
  width?: number;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<Status>(clientId ? "loading" : "unconfigured");
  const callback = useRef(onCredential);
  callback.current = onCredential;

  useEffect(() => {
    if (!clientId) {
      setStatus("unconfigured");
      return;
    }

    let cancelled = false;

    function render() {
      if (cancelled || !container.current || !window.google?.accounts?.id) return;
      // initialize() throws no error but warns if called twice, and only the last
      // call survives. One initialise per client id, with a stable callback that
      // reads the latest handler from the ref.
      if (initialisedClientId !== clientId) {
        window.google.accounts.id.initialize({
          client_id: clientId!,
          callback: (response) => callback.current(response.credential),
          auto_select: false,
          cancel_on_tap_outside: true,
        });
        initialisedClientId = clientId ?? null;
      }
      window.google.accounts.id.renderButton(container.current, {
        theme: "outline",
        size: "large",
        shape: "rectangular",
        text: "continue_with",
        logo_alignment: "left",
        width,
      });
      setStatus("ready");
    }

    if (window.google?.accounts?.id) {
      render();
      return;
    }

    let script = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    if (!script) {
      script = document.createElement("script");
      script.id = SCRIPT_ID;
      script.src = SCRIPT_SRC;
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }

    const onLoad = () => render();
    const onScriptError = () => {
      setStatus("error");
      onError?.("Could not load Google's sign-in script. Check your connection or an ad blocker.");
    };

    script.addEventListener("load", onLoad);
    script.addEventListener("error", onScriptError);

    // The script may already have loaded between renders.
    const poll = window.setInterval(() => {
      if (window.google?.accounts?.id) {
        window.clearInterval(poll);
        render();
      }
    }, 200);
    const timeout = window.setTimeout(() => window.clearInterval(poll), 8000);

    return () => {
      cancelled = true;
      window.clearInterval(poll);
      window.clearTimeout(timeout);
      script?.removeEventListener("load", onLoad);
      script?.removeEventListener("error", onScriptError);
    };
  }, [clientId, onError, width]);

  if (status === "unconfigured") {
    return (
      <div className="rounded-stamp border border-ochre/40 bg-ochre/5 px-4 py-3 text-[12.5px] leading-relaxed text-ochre">
        <strong className="font-semibold">Google sign-in is not configured.</strong> Set
        <code className="mx-1 rounded bg-surface-2 px-1 py-0.5 font-mono text-[11px]">
          VITE_GOOGLE_CLIENT_ID
        </code>
        in <code className="font-mono text-[11px]">dashboard/.env</code> and restart the dev
        server.
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="rounded-stamp border border-danger/40 bg-danger/5 px-4 py-3 text-[12.5px] text-danger">
        Google&rsquo;s script did not load. Try a different network or disable the ad blocker.
      </div>
    );
  }

  return (
    <div className="flex min-h-[44px] flex-col items-stretch gap-2">
      <div ref={container} />
      {status === "loading" ? (
        <div className="h-10 w-[320px] animate-pulse rounded-stamp border border-line bg-surface" />
      ) : null}
    </div>
  );
}