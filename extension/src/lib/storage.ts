import type { Platform } from "./contract";
import { addVisitedJobId } from "./job-queue";

/**
 * What survives a service-worker restart. The authoritative run lives on the
 * server; this is the cache the UI and the loop need to find their way back.
 */
export interface RunStats {
  applied: number;
  skipped: number;
  stuck: number;
  message: string;
}

export interface ActiveRun {
  id: string;
  platform: Platform;
  tabId: number;
  windowId: number;
  dryRun: boolean;
  startedAt: number;
  /** Job ids already opened this run, so the agent never loops on one card. */
  visited: string[];
  /** Counters from the last agent step, for the popup. */
  stats: RunStats;
  /** Times the run tab has been reopened after the user closed it. */
  reopened: number;
  /** Set while a long break is pending; the tick alarm resumes after it. */
  resumeAt: number | null;
  /** The 24h search this run works through, so recovery can return to it. */
  searchUrl: string;
  /** Last few steps, so the popup can show that the loop is alive. */
  log: string[];
}

export interface StoredState {
  token: string | null;
  installId: string;
  run: ActiveRun | null;
  lastError: string | null;
  /** Why the previous run ended, so the popup can explain it. */
  lastStop: { reason: string; at: number } | null;
}

const KEY = "autoapply.v1";

function randomId(): string {
  return crypto.randomUUID().replace(/-/g, "").slice(0, 24);
}

async function read(): Promise<StoredState | null> {
  const stored = await chrome.storage.local.get(KEY);
  return (stored[KEY] as StoredState | undefined) ?? null;
}

export async function getState(): Promise<StoredState> {
  const existing = await read();
  if (existing?.installId) return existing;

  const fresh: StoredState = {
    token: null,
    installId: randomId(),
    run: null,
    lastError: null,
    lastStop: null,
  };
  await chrome.storage.local.set({ [KEY]: fresh });
  return fresh;
}

export async function patchState(patch: Partial<StoredState>): Promise<StoredState> {
  const current = await getState();
  const next = { ...current, ...patch };
  await chrome.storage.local.set({ [KEY]: next });
  return next;
}

export async function clearToken(): Promise<void> {
  await patchState({ token: null, run: null });
}

export async function getToken(): Promise<string | null> {
  return (await getState()).token;
}

export async function addVisited(jobId: string): Promise<void> {
  const state = await getState();
  if (!state.run || state.run.visited.includes(jobId)) return;
  await patchState({
    run: { ...state.run, visited: addVisitedJobId(state.run.visited, jobId) },
  });
}

export function hasVisited(run: ActiveRun | null, jobId: string): boolean {
  return Boolean(run?.visited.includes(jobId));
}

export const STORAGE_KEY = KEY;