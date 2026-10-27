import type {
  AgentResponse,
  ConnectOut,
  HeartbeatOut,
  Observation,
  StartRunOut,
} from "./contract";

/**
 * Backend client. The base URL is compiled in, because a service worker has no
 * proxy to lean on: the extension talks to the API directly with a bearer token.
 */
export const API_BASE = (import.meta.env.WXT_API_BASE_URL ?? "http://127.0.0.1:8000/api").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const error = (payload as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "http_error",
      error?.message ?? `Request failed (${response.status})`,
    );
  }

  return payload as T;
}

function auth(token: string, body?: unknown): RequestInit {
  return {
    method: body === undefined ? "GET" : "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

export const api = {
  /** Public: the pairing code is the credential. */
  connect(code: string, installId: string): Promise<ConnectOut> {
    return request<ConnectOut>("/extension/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ code, install_id: installId, label: "Chrome extension" }),
    });
  },

  reportPlatform(token: string, platform: string, signedIn: boolean): Promise<void> {
    return request<void>("/platform/status", auth(token, { platform, signed_in: signedIn }));
  },

  startRun(token: string, platform: string, dryRun: boolean): Promise<StartRunOut> {
    return request<StartRunOut>("/runs/start", auth(token, { platform, dry_run: dryRun }));
  },

  heartbeat(token: string, runId: string): Promise<HeartbeatOut> {
    return request<HeartbeatOut>(`/runs/${runId}/heartbeat`, auth(token, {}));
  },

  stopRun(token: string, runId: string, reason: string): Promise<unknown> {
    return request(`/runs/${runId}/stop`, auth(token, { reason }));
  },

  step(token: string, observation: Observation): Promise<AgentResponse> {
    return request<AgentResponse>("/agent/step", auth(token, observation));
  },

  resumeFileUrl(token: string): Promise<{ url: string; expires_in: number }> {
    return request<{ url: string; expires_in: number }>("/extension/resume-file", auth(token));
  },
};