import { useCallback, useEffect, useState } from "react";
import type { Platform } from "@/lib/contract";
import { detectPlatform, platformLabel, portalHomeUrl } from "@/lib/platforms";
import { shouldShowPairingForm } from "@/lib/connection-state";

type Stats = { applied: number; skipped: number; stuck: number; message: string };

type PopupState = {
  connected: boolean;
  running: { id: string; platform: Platform; dryRun: boolean; stats: Stats; log: string[] } | null;
  lastError: string | null;
  lastStop: { reason: string; at: number } | null;
};

type TabInfo = {
  platform: Platform | null;
  signedIn: boolean | null;
  tabId: number | null;
};

const QUOTE = "The job hunt that runs itself.";

function explainStop(reason: string): string {
  const map: Record<string, string> = {
    no_progress: "it kept seeing the same page, so it stopped instead of looping",
    repeated_errors: "three steps failed in a row",
    run_window_closed: "the run window was closed",
    user_stopped: "you pressed Stop",
    tab_closed: "the run tab was closed",
    window_failed: "the run window could not open",
  };
  if (reason.includes("cooldown")) return "a safety cooldown is active";
  if (reason.includes("captcha")) return "a CAPTCHA stopped it";
  return map[reason] ?? reason.replace(/_/g, " ");
}

export function Popup() {
  const [state, setState] = useState<PopupState | null>(null);
  const [tab, setTab] = useState<TabInfo>({ platform: null, signedIn: null, tabId: null });
  const [code, setCode] = useState("");
  const [reconnectRequested, setReconnectRequested] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [debug, setDebug] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const next = (await chrome.runtime.sendMessage({ type: "get-state" })) as PopupState;
    setState(next);
    if (next.lastError) setError(next.lastError);

    const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
    const platform = active?.url ? detectPlatform(active.url) : null;
    if (!active?.id || !platform) {
      setTab({ platform: null, signedIn: null, tabId: null });
      return;
    }

    const ping = (await chrome.tabs
      .sendMessage(active.id, { type: "ping" })
      .catch(() => null)) as { signedIn: boolean | null } | null;

    setTab({ platform, signedIn: ping?.signedIn ?? null, tabId: active.id });
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  async function pair() {
    setBusy(true);
    setError(null);
    const result = (await chrome.runtime.sendMessage({ type: "pair", code })) as {
      ok: boolean;
      error?: string;
    };
    setBusy(false);
    if (result.ok) {
      setCode("");
      setReconnectRequested(false);
      setError(null);
    } else {
      setError(result.error ?? "Could not connect.");
    }
    await refresh();
    if (!result.ok) setError(result.error ?? "Could not connect.");
  }

  async function startMagic() {
    if (!tab.platform) return;
    setBusy(true);
    setError(null);
    const result = (await chrome.runtime.sendMessage({
      type: "start-run",
      platform: tab.platform,
    })) as { ok: boolean; error?: string };
    setBusy(false);
    if (!result.ok) setError(result.error ?? "Could not start.");
    await refresh();
  }

  async function stop() {
    setBusy(true);
    await chrome.runtime.sendMessage({ type: "stop-run" });
    setBusy(false);
    await refresh();
  }

  async function inspect() {
    // While a run is active this inspects the run tab, not the tab you happen to
    // be looking at (which is usually a different window entirely).
    const observed = state?.running
      ? await chrome.runtime.sendMessage({ type: "inspect" }).catch((cause: Error) => ({
          ok: false,
          error: cause.message,
        }))
      : await (async () => {
          const [active] = await chrome.tabs.query({ active: true, currentWindow: true });
          if (!active?.id) return { ok: false, error: "No active tab." };
          return chrome.tabs.sendMessage(active.id, { type: "observe" });
        })().catch((cause: Error) => ({ ok: false, error: cause.message }));
    setDebug(JSON.stringify(observed, null, 2).slice(0, 4000));
  }

  async function showRunWindow() {
    await chrome.runtime.sendMessage({ type: "show-run" });
    window.close();
  }

  async function openPortal(platform: Platform) {
    await chrome.tabs.create({ url: portalHomeUrl(platform) });
    window.close();
  }

  if (!state) {
    return (
      <main className="pop">
        <p className="hint">Loading…</p>
      </main>
    );
  }

  const running = state.running;
  const showPairingForm = shouldShowPairingForm(state.connected, reconnectRequested);

  return (
    <main className="pop">
      <header className="head">
        <span className="mark" aria-hidden />
        <span className="name">AutoApply</span>
        {running ? (
          <span className="chip live">
            <span className="dot" />
            {platformLabel(running.platform)}
          </span>
        ) : state.connected ? (
          <span className="chip ok">{tab.platform ? platformLabel(tab.platform) : "Connected"}</span>
        ) : (
          <span className="chip">Not connected</span>
        )}
      </header>

      {showPairingForm ? (
        <section className="body">
          <p className="quote">
            {state.connected ? "Reconnect this browser." : "Connect this browser."}
          </p>
          <p className="hint">
            Dashboard → <strong>Settings → Connect extension</strong> → paste the eight-character
            code here.
          </p>
          <input
            className="code"
            value={code}
            onChange={(event) => setCode(event.target.value.toUpperCase())}
            placeholder="ABCD2345"
            maxLength={8}
            spellCheck={false}
            aria-label="Pairing code"
          />
          <button className="primary" onClick={pair} disabled={busy || code.length < 4}>
            {busy ? "Connecting…" : "Connect"}
          </button>
        </section>
      ) : running ? (
        <section className="body">
          <div className="counters">
            <div>
              <span className="n ok">{running.stats.applied}</span>
              <span className="c">applied</span>
            </div>
            <div>
              <span className="n">{running.stats.skipped}</span>
              <span className="c">skipped</span>
            </div>
            <div>
              <span className="n warn">{running.stats.stuck}</span>
              <span className="c">needs you</span>
            </div>
          </div>
          <p className="hint">{running.stats.message}</p>
          {running.log?.length ? (
            <ul className="log" aria-label="Recent steps">
              {running.log.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : null}
          <p className="hint subtle">
            {running.dryRun
              ? "This older run is non-submitting; stop it and start a fresh run to apply."
              : "Live run. Work in other tabs freely; just don't minimize the run window."}
          </p>
          <div className="row">
            <button className="ghost" onClick={showRunWindow}>
              Show run window
            </button>
            <button className="ghost" onClick={stop} disabled={busy}>
              Stop
            </button>
          </div>
        </section>
      ) : !tab.platform ? (
        <section className="body">
          <p className="quote">Open a job portal to begin.</p>
          <div className="row">
            <button className="ghost" onClick={() => openPortal("linkedin")}>
              Open LinkedIn
            </button>
            <button className="ghost" onClick={() => openPortal("naukri")}>
              Open Naukri
            </button>
          </div>
          {state.connected ? (
            <button type="button" className="link" onClick={() => setReconnectRequested(true)}>
              Reconnect with a new pairing code
            </button>
          ) : null}
        </section>
      ) : tab.signedIn === false ? (
        <section className="body">
          <p className="quote">Sign in to {platformLabel(tab.platform)}.</p>
          <p className="hint">Sign in as you normally would, then come back.</p>
          <button className="ghost" onClick={refresh}>
            I'm signed in
          </button>
          {state.connected ? (
            <button type="button" className="link" onClick={() => setReconnectRequested(true)}>
              Reconnect with a new pairing code
            </button>
          ) : null}
        </section>
      ) : (
        <section className="body">
          <p className="quote">“{QUOTE}”</p>
          <p className="hint">
            Ready to apply in <strong>{platformLabel(tab.platform)}</strong>? It searches the last 24
            hours and works through the matches.
          </p>
          <p className="hint subtle">
            Live run: supported Easy Apply forms can be submitted automatically using your profile
            and approved answers. Review those details first.
          </p>
          {state.lastStop ? (
            <p className="hint subtle">
              Last run ended: <strong>{explainStop(state.lastStop.reason)}</strong>
            </p>
          ) : null}
          <button className="primary" onClick={startMagic} disabled={busy}>
            {busy ? "Starting…" : "Start live run"}
          </button>
          {state.connected ? (
            <button
              type="button"
              className="link"
              onClick={() => {
                setError(null);
                setReconnectRequested(true);
              }}
            >
              Reconnect with a new pairing code
            </button>
          ) : null}
        </section>
      )}

      {error ? <p className="error">{error}</p> : null}

      <footer className="foot">
        <span className="mono">v0.1.0</span>
        <button type="button" className="link" onClick={inspect}>
          Inspect page
        </button>
      </footer>

      {debug ? (
        <pre className="debug" onClick={() => setDebug(null)} title="Click to close">
          {debug}
        </pre>
      ) : null}
    </main>
  );
}