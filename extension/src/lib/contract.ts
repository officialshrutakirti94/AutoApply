/**
 * Mirrors `packages/shared/contract.schema.json` and the backend's Pydantic
 * models. The extension only ever sees `ref` handles, never selectors.
 */

export type Platform = "linkedin" | "naukri";

export type PageType =
  | "search_results"
  | "job_detail"
  | "apply_form"
  | "chat_question"
  | "confirmation"
  | "external"
  | "unknown";

export type ElementKind = "text" | "select" | "radio" | "checkbox" | "file" | "button";

export type Signal =
  | "captcha"
  | "checkpoint"
  | "warning_banner"
  | "forced_logout"
  | "rate_limited"
  | "unknown_page"
  | "suspicious_content";

export type ActionType =
  | "fill_text"
  | "select_option"
  | "check"
  | "attach_resume"
  | "click"
  | "wait"
  | "submit"
  | "finish";

export type StepStatus = "continue" | "done" | "hitl" | "stop";

export interface JobSummary {
  id: string;
  title?: string | null;
  company?: string | null;
  location?: string | null;
  /** Company application URL for external jobs when LinkedIn exposes one. */
  job_url?: string | null;
  already_applied?: boolean;
  external?: boolean;
}

export interface FormElement {
  ref: string;
  kind: ElementKind;
  label?: string;
  options?: string[];
  required?: boolean;
  value?: string | null;
}

export interface ChatPrompt {
  question: string;
  input_ref: string;
}

export interface Observation {
  run_id: string;
  platform: Platform;
  page_type: PageType;
  job: JobSummary;
  elements: FormElement[];
  chat?: ChatPrompt | null;
  page_text_digest?: string | null;
  signals: Signal[];
}

export interface Action {
  type: ActionType;
  ref?: string | null;
  value?: string | null;
  ms?: number | null;
}

export interface Pacing {
  action_delay_ms: number;
  apply_pause_s: number;
  long_break_s: number | null;
}

export interface StepMeta {
  run_id: string;
  run_status: string;
  job_status: string | null;
  applied_count: number;
  skipped_count: number;
  stuck_count: number;
  llm_calls: number;
  llm_calls_left: number;
  trace_id: string | null;
  pacing: Pacing | null;
}

export interface AgentResponse {
  actions: Action[];
  status: StepStatus;
  reason?: string | null;
  meta?: StepMeta | null;
}

export interface RunSummary {
  id: string;
  platform: Platform;
  status: "running" | "done" | "stopped" | "interrupted";
  dry_run: boolean;
  started_at: string;
  ended_at: string | null;
  max_applications: number;
  applied_count: number;
  skipped_count: number;
  stuck_count: number;
  llm_calls: number;
  stop_reason: string | null;
}

export interface SearchPlan {
  roles: string[];
  locations: string[];
  work_mode: string[];
  remote_first: boolean;
}

export interface StartRunOut {
  run: RunSummary;
  pacing: Pacing;
  heartbeat_seconds: number;
  keep_tab_visible: boolean;
  usage: Record<string, unknown> | null;
  search: SearchPlan;
}

export interface HeartbeatOut {
  run: RunSummary;
  allowed: boolean;
  message: string;
  reason?: string | null;
  cooldown_until?: string | null;
}

export interface ConnectOut {
  token: string;
  user_email: string;
  user_name: string | null;
}