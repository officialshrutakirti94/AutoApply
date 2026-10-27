import { api, ApiError } from "@/lib/api";
import { addVisited, clearToken, getState, getToken, hasVisited, patchState, type ActiveRun } from "@/lib/storage";
import { searchUrlFor } from "@/lib/platforms";
import { describeStep } from "@/lib/run-status";
import type { Action, Observation, Platform } from "@/lib/contract";

/**
 * Service worker: the brain of the extension.
 *
 * It owns the run, the pacing, the network and the owned window. The content
 * script is a DOM adapter it calls. Because the loop lives here and not in the
 * tab, a backgrounded platform tab keeps being driven while the user works
 * elsewhere.
 */

const TICK_ALARM = "autoapply.tick";
const MAX_REOPEN = 2;
const MAX_ERRORS = 3;
// Linkedin needs ~1128px before it draws the job pane beside the results list.
const WINDOW = { width: 1280, height: 1000, left: 0, top: 0 } as const;

type Draft = Omit<Observation, "run_id" | "platform">;

type Message =
  | { type: "get-state" }
  | { type: "pair"; code: string }
  | { type: "disconnect" }
  | { type: "platform-status"; platform: Platform; signedIn: boolean }
  | { type: "start-run"; platform: Platform; dryRun: boolean }
  | { type: "stop-run" }
  | { type: "resume-url" }
  | { type: "inspect" }
  | { type: "show-run" };

let loopActive = false;
let consecutiveErrors = 0;
let lastSignature = "";
let sameDecision = 0;

export default defineBackground(() => {
  void getState();

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    void (async () => {
      try {
        sendResponse(await handle(message as Message, sender.tab?.id));
      } catch (error) {
        const text = error instanceof ApiError ? error.message : toText(error);
        await patchState({ lastError: text });
        sendResponse({ ok: false, error: text });
      }
    })();
    return true;
  });

  chrome.alarms.create(TICK_ALARM, { periodInMinutes: 0.5 });
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === TICK_ALARM) void tick();
  });

  chrome.tabs.onRemoved.addListener((tabId) => {
    void onTabGone(tabId);
  });
});

function toText(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}

async function handle(message: Message, _tabId?: number) {
  switch (message.type) {
    case "get-state":
      return stateForPopup();

    case "pair": {
      const state = await getState();
      const result = await api.connect(message.code.trim().toUpperCase(), state.installId);
      await patchState({ token: result.token, lastError: null });
      return { ok: true, email: result.user_email };
    }

    case "disconnect":
      await clearToken();
      return { ok: true };

    case "platform-status": {
      const token = await getToken();
      if (!token) return { ok: false };
      await api.reportPlatform(token, message.platform, message.signedIn).catch(() => undefined);
      return { ok: true };
    }

    case "inspect": {
      // Always the run tab, never whatever tab the user happens to be on.
      const state = await getState();
      if (!state.run) return { ok: false, error: "No active run." };
      const observed = await observe(state.run.tabId);
      let url = "";
      try {
        url = (await chrome.tabs.get(state.run.tabId)).url ?? "";
      } catch {
        url = "(tab closed)";
      }
      return { ...observed, url, runId: state.run.id, log: state.run.log ?? [] };
    }

    case "show-run": {
      const state = await getState();
      if (!state.run) return { ok: false, error: "No active run." };
      try {
        await chrome.windows.update(state.run.windowId, { focused: true });
        return { ok: true };
      } catch {
        await reopen(state.run);
        return { ok: true };
      }
    }

    case "start-run":
      return startRun(message.platform, message.dryRun);

    case "stop-run":
      await stopRun("user_stopped");
      return { ok: true };

    case "resume-url": {
      const token = await getToken();
      if (!token) return { ok: false, error: "Not connected." };
      try {
        const file = await api.resumeFileUrl(token);
        return { ok: true, url: file.url };
      } catch (error) {
        return { ok: false, error: toText(error) };
      }
    }

    default:
      return { ok: false, error: "Unknown message" };
  }
}

// ------------------------------------------------------------------ run control

async function startRun(platform: Platform, dryRun: boolean) {
  const token = await getToken();
  if (!token) return { ok: false, error: "Connect the extension in Settings first." };

  const existing = await getState();
  if (existing.run) return { ok: false, error: "A run is already active." };

  const started = await api.startRun(token, platform, dryRun);

  if (!started.search.roles.length) {
    await api.stopRun(token, started.run.id, "no_target_roles").catch(() => undefined);
    return {
      ok: false,
      error: "Add at least one target role in Settings, then try again.",
    };
  }

  const searchUrl = searchUrlFor(platform, started.search);

  const created = await chrome.windows.create({ url: searchUrl, focused: false, ...WINDOW });
  const tabId = created.tabs?.[0]?.id;
  if (!created.id || !tabId) {
    await api.stopRun(token, started.run.id, "window_failed").catch(() => undefined);
    return { ok: false, error: "Could not open the run window." };
  }

  const active: ActiveRun = {
    id: started.run.id,
    platform,
    tabId,
    windowId: created.id,
    dryRun,
    startedAt: Date.now(),
    visited: [],
    stats: { applied: 0, skipped: 0, stuck: 0, message: "Starting…" },
    reopened: 0,
    resumeAt: null,
    searchUrl,
    log: [`${clock()} opened ${platform} · ${dryRun ? "practice" : "live"}`],
  };

  await patchState({ run: active, lastError: null, lastStop: null });
  void beginRun(active);
  return { ok: true, run: started.run, search: started.search, url: searchUrl };
}

async function stopRun(reason: string): Promise<void> {
  const state = await getState();
  if (state.token && state.run) {
    await api.stopRun(state.token, state.run.id, reason).catch(() => undefined);
  }
  consecutiveErrors = 0;
  lastSignature = "";
  sameDecision = 0;
  await patchState({ run: null, lastStop: { reason, at: Date.now() } });
}

/** The tick alarm: heartbeat, window guard, and restart the loop if it died. */
async function tick(): Promise<void> {
  const state = await getState();
  if (!state.run) return;

  if (state.token) {
    const beat = await api.heartbeat(state.token, state.run.id).catch(() => null);
    if (beat && !beat.allowed) {
      await stopRun(beat.reason ?? "policy_stop");
      return;
    }
  }

  await guardWindow(state.run);
  if (!loopActive) void loop();
}

async function onTabGone(tabId: number): Promise<void> {
  const state = await getState();
  if (state.run?.tabId === tabId) await reopen(state.run);
}

/**
 * Never let the window be minimized: a minimized window is a hidden tab, and a
 * hidden tab is throttled. Restoring it without focusing keeps the user's work
 * undisturbed.
 */
async function guardWindow(run: ActiveRun): Promise<void> {
  try {
    const window = await chrome.windows.get(run.windowId);
    if (window.state === "minimized") {
      await chrome.windows.update(run.windowId, { state: "normal", focused: false });
    }
  } catch {
    await reopen(run);
  }
}

async function reopen(run: ActiveRun): Promise<void> {
  if (run.reopened >= MAX_REOPEN) {
    await stopRun("run_window_closed");
    return;
  }

  const created = await chrome.windows.create({ url: run.searchUrl, focused: false, ...WINDOW });
  const tabId = created.tabs?.[0]?.id;
  if (!created.id || !tabId) {
    await stopRun("run_window_closed");
    return;
  }

  const fresh = await getState();
  if (!fresh.run) return;
  await patchState({
    run: { ...fresh.run, tabId, windowId: created.id, reopened: fresh.run.reopened + 1 },
  });
}

/** Wait for the first load, confirm we really are on a search page, then loop. */
async function beginRun(active: ActiveRun): Promise<void> {
  await waitForLoad(active.tabId);

  const tab = await chrome.tabs.get(active.tabId).catch(() => null);
  if (tab?.url && !landedOnSearch(active.platform, tab.url)) {
    await patchState({
      run: active,
      lastStop: { reason: "search_redirected", at: Date.now() },
    });
    await stopRun("search_redirected");
    return;
  }

  void loop();
}

/** LinkedIn bounces a keyword-less or blocked search to /jobs/; treat that as a failure. */
function landedOnSearch(platform: Platform, url: string): boolean {
  try {
    const parsed = new URL(url);
    if (platform === "linkedin") return parsed.pathname.startsWith("/jobs/search");
    return parsed.hostname.endsWith("naukri.com") && parsed.pathname.includes("-jobs");
  } catch {
    return false;
  }
}

// ----------------------------------------------------------------------- loop

async function loop(): Promise<void> {
  if (loopActive) return;
  loopActive = true;

  try {
    for (;;) {
      const state = await getState();
      const active = state.run;
      const token = state.token;
      if (!active || !token) break;

      // A long break was scheduled; the tick alarm resumes after it.
      if (active.resumeAt && Date.now() < active.resumeAt) break;

      await waitForLoad(active.tabId);
      const observed = await observe(active.tabId, active.visited);
      if (!observed.ok) {
        if (!(await countError(observed.error))) break;
        await sleep(1500);
        continue;
      }

      if (observed.queueExhausted) {
        await stopRun("queue_empty");
        break;
      }

      // The job the platform auto-opened is one this run already handled: move to
      // the next card instead of applying to it twice.
      if (
        observed.draft.page_type === "job_detail" &&
        hasVisited(active, observed.draft.job.id)
      ) {
        const next = (observed as { nextCard?: string | null }).nextCard;
        if (next) {
          await chrome.tabs.update(active.tabId, { url: next }).catch(() => undefined);
          await waitForLoad(active.tabId);
          continue;
        }
        // A job-detail page often has no result cards in its DOM. Return to the
        // search page so the content script can continue from the persisted queue.
        await goToSearch(active);
        await waitForLoad(active.tabId);
        continue;
      }

      // Naukri (and occasionally LinkedIn) serve an error page with a 200 status.
      // Stop and say so rather than spending the run on it.
      const digestText = (observed.draft.page_text_digest ?? "").toLowerCase();
      if (/something went wrong|error loading the page|page not found/.test(digestText)) {
        await stopRun("platform_error_page");
        break;
      }

      const response = await api.step(token, {
        run_id: active.id,
        platform: active.platform,
        ...observed.draft,
      });

      consecutiveErrors = 0;
      const meta = response.meta;
      const entry = `${clock()} ${observed.draft.page_type} → ${response.status}${
        response.reason ? ` (${response.reason.replace(/_/g, " ")})` : ""
      } · ${response.actions.length} action${response.actions.length === 1 ? "" : "s"}`;

      // A page that keeps producing the same decision is stuck, even though every
      // action "succeeds". Eight identical rounds is a loop, not progress.
      const first = response.actions[0];
      const signature = `${observed.draft.page_type}:${first?.type ?? ""}:${first?.ref ?? ""}:${first?.value ?? ""}:${response.status}`;
      sameDecision = signature === lastSignature ? sameDecision + 1 : 0;
      lastSignature = signature;

      await patchState({
        run: {
          ...active,
          resumeAt: null,
          log: [...(active.log ?? []).slice(-24), entry],
          stats: {
            applied: meta?.applied_count ?? active.stats.applied,
            skipped: meta?.skipped_count ?? active.stats.skipped,
            stuck: meta?.stuck_count ?? active.stats.stuck,
            message: describeStep(response.status, response.reason),
          },
        },
      });

      console.log("[autoapply]", entry);

      if (sameDecision >= 8) {
        await stopRun("no_progress");
        break;
      }

      if (response.status === "stop") {
        await stopRun(response.reason ?? "hard_stop");
        break;
      }

      if (response.status === "done" || response.status === "hitl") {
        const jobId = observed.draft.job.id;
        if (jobId && jobId !== "search") {
          await addVisited(jobId);
          await chrome.tabs
            .sendMessage(active.tabId, { type: "mark-visited", jobId })
            .catch(() => undefined);
        }

        const longBreak = meta?.pacing?.long_break_s ?? null;
        const pauseMs = (meta?.pacing?.apply_pause_s ?? 0) * 1000;

        await goToSearch(active);

        if (longBreak && longBreak > 60) {
          const fresh = await getState();
          if (fresh.run) {
            await patchState({
              run: { ...fresh.run, resumeAt: Date.now() + longBreak * 1000 },
            });
          }
          break;
        }

        if (pauseMs) await sleep(pauseMs);
        continue;
      }

      const urlBefore = await tabUrl(active.tabId);
      const outcome = await act(active.tabId, response.actions);
      if (!outcome.ok) {
        if (!(await countError(outcome.error ?? "action failed"))) break;
      }

      // A click that opens a job is an SPA navigation: the URL and the detail
      // pane arrive a moment later. Without this wait the next observation still
      // sees the old list, and it clicks the same card again.
      if (response.actions.some((action) => action.type === "click")) {
        await waitForUrlChange(active.tabId, urlBefore, 6000);
      }

      await sleep(Math.max(meta?.pacing?.action_delay_ms ?? 900, 250));
      if (outcome.submitted) await sleep(2500);
    }
  } catch (error) {
    await patchState({ lastError: toText(error) });
  } finally {
    loopActive = false;
  }
}

async function countError(reason: string): Promise<boolean> {
  consecutiveErrors += 1;
  if (consecutiveErrors >= MAX_ERRORS) {
    await stopRun("repeated_errors");
    return false;
  }
  await patchState({ lastError: reason });
  return true;
}

// ------------------------------------------------------------------ page bridge

type ObserveResponse =
  | { ok: true; draft: Draft; nextCard?: string | null; queueExhausted?: boolean }
  | { ok: false; error: string };

async function observe(
  tabId: number,
  visitedJobIds: string[] = [],
  attempts = 6,
): Promise<ObserveResponse> {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      await chrome.tabs.sendMessage(tabId, { type: "settle" });
      const observed = (await chrome.tabs.sendMessage(tabId, {
        type: "observe",
        visitedJobIds,
      })) as ObserveResponse;
      if (observed?.ok) return observed;
    } catch {
      // The content script is not injected yet, or the tab is navigating.
    }
    await sleep(600);
  }
  return { ok: false, error: "The run tab did not respond." };
}

async function act(
  tabId: number,
  actions: Action[],
): Promise<{ ok: boolean; error?: string; submitted?: boolean }> {
  try {
    return (await chrome.tabs.sendMessage(tabId, { type: "act", actions })) as {
      ok: boolean;
      error?: string;
      submitted?: boolean;
    };
  } catch {
    return { ok: false, error: "The run tab did not respond." };
  }
}

async function tabUrl(tabId: number): Promise<string> {
  try {
    return (await chrome.tabs.get(tabId)).url ?? "";
  } catch {
    return "";
  }
}

/** Resolve once the tab navigates somewhere new, or the timeout passes. */
async function waitForUrlChange(tabId: number, before: string, timeoutMs: number): Promise<void> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    await sleep(250);
    const now = await tabUrl(tabId);
    if (now && now !== before) {
      await waitForLoad(tabId, 8000);
      return;
    }
  }
}

async function waitForLoad(tabId: number, timeoutMs = 25_000): Promise<void> {
  const started = Date.now();
  for (;;) {
    try {
      const tab = await chrome.tabs.get(tabId);
      if (tab.status === "complete") return;
    } catch {
      return;
    }
    if (Date.now() - started > timeoutMs) return;
    await sleep(400);
  }
}

async function goToSearch(run: ActiveRun): Promise<void> {
  try {
    await chrome.tabs.update(run.tabId, { url: run.searchUrl });
  } catch {
    await reopen(run);
  }
}

function clock(): string {
  return new Date().toLocaleTimeString("en-IN", { hour12: false });
}

// ---------------------------------------------------------------------- popup

async function stateForPopup() {
  const state = await getState();
  return {
    connected: Boolean(state.token),
    running: state.run
      ? {
          id: state.run.id,
          platform: state.run.platform,
          dryRun: state.run.dryRun,
          stats: state.run.stats,
          log: (state.run.log ?? []).slice(-4),
        }
      : null,
    lastError: state.lastError,
    lastStop: state.lastStop,
  };
}

export const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));