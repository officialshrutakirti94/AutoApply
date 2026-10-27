import type {
  ChatPrompt,
  ElementKind,
  FormElement,
  JobSummary,
  PageType,
  Signal,
} from "../lib/contract.ts";

/**
 * What a platform adapter produces. The service worker adds `run_id` and
 * `platform` before it posts, so adapters never need to know about a run.
 */
export interface ObservationDraft {
  page_type: PageType;
  job: JobSummary;
  elements: FormElement[];
  chat: ChatPrompt | null;
  page_text_digest: string | null;
  signals: Signal[];
}

export interface PlatformAdapter {
  observe(doc: Document, url: string): ObserveResult;
}

/**
 * Ref handles. The contract allows `^[a-z][0-9]{1,4}$`, so a counter per page is
 * enough: f1.. for form fields, b1.. for buttons/choices, c1 for a chat input.
 */
export class Refs {
  private counters: Record<string, number> = {};

  /** ref -> the live element, so an action can be executed against it later. */
  readonly bound = new Map<string, Element>();

  next(prefix: "f" | "b" | "c" = "f"): string {
    this.counters[prefix] = (this.counters[prefix] ?? 0) + 1;
    return `${prefix}${this.counters[prefix]}`;
  }

  /** Allocate a ref and remember which element it belongs to. */
  assign(prefix: "f" | "b" | "c", element: Element): string {
    const ref = this.next(prefix);
    this.bound.set(ref, element);
    return ref;
  }
}

/** What an adapter hands back: the wire draft plus the element map behind its refs. */
export interface ObserveResult {
  draft: ObservationDraft;
  refs: Map<string, Element>;
}

export function text(element: Element | null | undefined): string {
  return (element?.textContent ?? "").replace(/\s+/g, " ").trim();
}

/** A short excerpt for fit checks and injection detection. Never the whole page. */
export function digest(doc: Document, limit = 600): string | null {
  const body = doc.body;
  if (!body) return null;

  // Linkedin and Naukri embed hydration JSON in hidden <script>/<code> tags.
  // innerText is the real visible text; the clone path is the fixture fallback.
  const rendered = (body as HTMLElement).innerText;
  if (typeof rendered === "string" && rendered.trim()) {
    return rendered.replace(/\s+/g, " ").trim().slice(0, limit);
  }

  const clone = body.cloneNode(true) as Element;
  clone
    .querySelectorAll("script, style, noscript, template, code")
    .forEach((node) => node.remove());

  const value = (clone.textContent ?? "").replace(/\s+/g, " ").trim();
  return value ? value.slice(0, limit) : null;
}

export function element(
  ref: string,
  kind: ElementKind,
  label: string,
  options: { options?: string[]; required?: boolean; value?: string | null } = {},
): FormElement {
  return {
    ref,
    kind,
    label: label.slice(0, 400),
    options: (options.options ?? []).slice(0, 100),
    required: Boolean(options.required),
    value: options.value ?? null,
  };
}

export function jobOf(
  id: string | null | undefined,
  title: string | null,
  company: string | null,
  url: string | null,
  extra: Partial<JobSummary> = {},
): JobSummary {
  return {
    id: (id ?? "").slice(0, 120) || "unknown",
    title: title?.slice(0, 300) ?? null,
    company: company?.slice(0, 200) ?? null,
    job_url: url?.slice(0, 2000) ?? null,
    already_applied: false,
    external: false,
    ...extra,
  };
}

/** Options as the user sees them, minus placeholder rows. */
export function optionLabels(nodes: ArrayLike<Element>): string[] {
  const labels = new Set<string>();
  for (const node of Array.from(nodes)) {
    const label = text(node);
    if (!label) continue;
    if (/^(select an option|--|choose|please select)/i.test(label)) continue;
    labels.add(label.slice(0, 300));
  }
  return [...labels].slice(0, 100);
}