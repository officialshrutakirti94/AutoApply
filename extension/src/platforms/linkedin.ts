import type { FormElement, JobSummary, Signal } from "@/lib/contract";
import {
  Refs,
  digest,
  element,
  jobOf,
  optionLabels,
  text,
  type ObserveResult,
  type PlatformAdapter,
} from "./types.ts";
import { detectSignals } from "./detect.ts";

/**
 * LinkedIn.
 *
 * Class names are stable; `emberNNN` ids are not, so nothing here uses them.
 * Every element is bound to the node behind its ref, so the executor acts on
 * exactly what was described.
 */

const MODAL = ".jobs-easy-apply-modal, [data-test-modal-id='easy-apply-modal']";
const FIELD = ".fb-dash-form-element";
const CARD = "div.job-card-container[data-job-id], li[data-occludable-job-id]";
const JOB_DETAILS =
  ".jobs-details__main-content, .jobs-search__job-details--container";

const KEEP_BUTTON = /\b(next|continue|review|submit|save)\b/i;
const DROP_BUTTON = /\b(back|dismiss|cancel|close|discard)\b/i;
const EXTERNAL_APPLICATION_NOTICE =
  /\bresponses managed off linkedin\b|\bapply on (?:the )?company(?:'s)? (?:website|site)\b|\bapply on external\b/i;
const APPLICATION_LINK_LABEL = /\b(apply|application|company website|external)\b/i;

function isVisible(node: Element): boolean {
  const element = node as HTMLElement;
  if (typeof element.getClientRects !== "function") return true; // fixtures have no layout
  return element.getClientRects().length > 0;
}

function accessibleLabel(node: Element): string {
  return `${text(node)} ${node.getAttribute("aria-label") ?? ""}`.trim();
}

function findEasyApplyControl(scope: Element): Element | null {
  // The generic `.jobs-apply-button` class is used for both Easy Apply and
  // company-site applications. The visible/accessibility label distinguishes them.
  return (
    Array.from(scope.querySelectorAll("button, a[role='button'], a")).find(
      (node) => isVisible(node) && /\beasy\s*apply\b/i.test(accessibleLabel(node)),
    ) ?? null
  );
}

function findOtherApplyControl(scope: Element): Element | null {
  return (
    Array.from(scope.querySelectorAll("button, a[role='button'], a")).find((node) => {
      if (!isVisible(node)) return false;
      const label = accessibleLabel(node);
      return /\bapply\b/i.test(label) && !/\beasy\s*apply\b/i.test(label);
    }) ?? null
  );
}

function externalHttpUrl(href: string, baseUrl: string): string | null {
  try {
    const url = new URL(href, baseUrl);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;

    if (!isLinkedInHost(url.hostname)) return url.toString();

    for (const [key, value] of url.searchParams) {
      if (!/^(url|redirect|redirecturl|target|destination)$/i.test(key)) continue;
      const destination = new URL(value, baseUrl);
      if (
        (destination.protocol === "http:" || destination.protocol === "https:") &&
        !isLinkedInHost(destination.hostname)
      ) {
        return destination.toString();
      }
    }
  } catch {
    return null;
  }
  return null;
}

function isLinkedInHost(hostname: string): boolean {
  return hostname === "linkedin.com" || hostname.endsWith(".linkedin.com");
}

function externalApplicationUrl(
  scope: Element,
  applyControl: Element | null,
  baseUrl: string,
): string | null {
  const candidates: Element[] = [];
  if (applyControl) {
    candidates.push(applyControl);
    const group = applyControl.closest(".jobs-s-apply, .jobs-apply-button--top-card");
    if (group) candidates.push(...Array.from(group.querySelectorAll("a[href]")));
  }
  candidates.push(
    ...Array.from(scope.querySelectorAll("a[href]")).filter((anchor) =>
      APPLICATION_LINK_LABEL.test(accessibleLabel(anchor)),
    ),
  );

  for (const candidate of candidates) {
    const href =
      candidate.getAttribute("href") ??
      candidate.getAttribute("data-href") ??
      candidate.getAttribute("data-url");
    if (!href) continue;
    const destination = externalHttpUrl(href, baseUrl);
    if (destination) return destination;
  }
  return null;
}

function jobTitle(doc: Document): string {
  return (
    text(doc.querySelector(".job-details-jobs-unified-top-card__job-title")) ||
    text(doc.querySelector(".jobs-search__job-details--container h1")) ||
    text(doc.querySelector("h1.t-24")) ||
    text(doc.querySelector("h1")) ||
    doc.title.replace(/\s*\|\s*LinkedIn\s*$/i, "")
  ).slice(0, 120);
}

function jobIdFromUrl(url: string): string | null {
  const match = /[?&]currentJobId=(\d+)/.exec(url) ?? /\/jobs\/view\/(\d+)/.exec(url);
  return match?.[1] ?? null;
}

function appliedBadge(scope: Element): boolean {
  const markers = scope.querySelectorAll(
    ".job-card-container__footer-item, .job-card-list__footer-wrapper, .artdeco-entity-lockup__caption",
  );
  return Array.from(markers).some((node) => /\bapplied\b/i.test(text(node)));
}

function signalsOf(doc: Document): Signal[] {
  const found = detectSignals(doc);
  const signals: Signal[] = [];
  if (found.captcha) signals.push("captcha");
  if (found.checkpoint) signals.push("checkpoint");
  if (found.warningBanner) signals.push("warning_banner");
  if (found.forcedLogout) signals.push("forced_logout");
  if (found.rateLimited) signals.push("rate_limited");
  return signals;
}

function unknownPage(doc: Document, url: string, signals: Signal[]): ObserveResult {
  return {
    draft: {
      page_type: "unknown",
      job: jobOf(null, null, null, url),
      elements: [],
      chat: null,
      page_text_digest: digest(doc),
      signals: [...signals, "unknown_page"],
    },
    refs: new Map(),
  };
}

function observe(doc: Document, url: string): ObserveResult {
  const signals = signalsOf(doc);

  const modal = doc.querySelector(MODAL);
  if (modal) return applyForm(doc, url, modal, signals);

  // Linkedin also puts `?currentJobId=` on the results page, because it opens the
  // first job by itself. The list is what is usable there, so report the cards and
  // let the run open a real job page instead of an empty pane.
  const jobId = jobIdFromUrl(url);
  const onResultsList = /\/jobs\/(search|collections)(\/|$)/.test(new URL(url).pathname);
  if (jobId && !onResultsList) {
    // A pane that has not drawn yet must not be reported as "external" — that
    // silently skips a job we could have applied to. It becomes a HITL instead.
    return jobDetail(doc, url, jobId, signals) ?? unknownPage(doc, url, signals);
  }

  return searchResults(doc, url, signals) ?? unknownPage(doc, url, signals);
}

function searchResults(doc: Document, url: string, signals: Signal[]): ObserveResult | null {
  const cards = Array.from(doc.querySelectorAll(CARD));
  if (!cards.length) return null;

  const refs = new Refs();
  const elements: FormElement[] = [];
  const seen = new Set<string>();

  for (const card of cards.slice(0, 12)) {
    const id =
      card.getAttribute("data-job-id") ??
      card.getAttribute("data-occludable-job-id") ??
      card.querySelector("[data-job-id]")?.getAttribute("data-job-id");
    if (!id || seen.has(id)) continue;
    seen.add(id);

    const titleNode = card.querySelector(
      "a.job-card-list__title--link, a.job-card-list__title, .job-card-list__title",
    );
    const title = text(titleNode) || titleNode?.getAttribute("aria-label") || "";
    if (!title) continue;

    const company = text(card.querySelector(".artdeco-entity-lockup__subtitle"));
    const label = company ? `${title} at ${company}` : title;
    const applied = appliedBadge(card);
    elements.push(
      element(refs.assign("b", card), "button", applied ? `${label} (Applied)` : label),
    );
  }

  if (!elements.length) return null;

  return {
    draft: {
      page_type: "search_results",
      job: jobOf("search", null, null, url),
      elements,
      chat: null,
      page_text_digest: digest(doc),
      signals,
    },
    refs: refs.bound,
  };
}

function jobDetail(
  doc: Document,
  url: string,
  jobId: string,
  signals: Signal[],
): ObserveResult | null {
  const scope =
    doc.querySelector(JOB_DETAILS) ?? doc.body ?? doc.documentElement;
  const easyApplyButton = findEasyApplyControl(scope);
  const otherApplyButton = findOtherApplyControl(scope);
  const externalNotice = EXTERNAL_APPLICATION_NOTICE.test(text(scope));
  const external = !easyApplyButton && (Boolean(otherApplyButton) || externalNotice);

  // An explicit off-platform notice identifies the job even when LinkedIn doesn't
  // expose an Apply control in the current DOM.
  if (!easyApplyButton && !otherApplyButton && !externalNotice) return null;

  const refs = new Refs();
  const elements: FormElement[] = [];

  if (easyApplyButton) {
    elements.push(
      element(refs.assign("b", easyApplyButton), "button", accessibleLabel(easyApplyButton)),
    );
  }

  for (const button of Array.from(doc.querySelectorAll("button"))
    .filter(
      (node) =>
        KEEP_BUTTON.test(text(node)) &&
        !DROP_BUTTON.test(text(node)) &&
        // Pagination is not part of the job pane.
        !/^\s*(next|previous)\s*$/i.test(text(node)),
    )
    .slice(0, 4)) {
    elements.push(element(refs.assign("b", button), "button", text(button)));
  }

  const title = jobTitle(doc);
  const company = text(
    doc.querySelector(
      ".job-details-jobs-unified-top-card__company-name, .job-details-jobs-unified-top-card__subtitle-primary-grouping a",
    ),
  );
  const location = text(doc.querySelector(".job-details-jobs-unified-top-card__bullet"));

  const applicationUrl = external
    ? externalApplicationUrl(scope, otherApplyButton, url) ?? url
    : url;

  const job: JobSummary = jobOf(jobId, title || null, company || null, applicationUrl, {
    location: location || null,
    external,
  });

  return {
    draft: {
      page_type: "job_detail",
      job,
      elements,
      chat: null,
      page_text_digest: digest(doc),
      signals,
    },
    refs: refs.bound,
  };
}

function applyForm(doc: Document, url: string, modal: Element, signals: Signal[]): ObserveResult {
  const refs = new Refs();
  const elements: FormElement[] = [];

  for (const field of Array.from(modal.querySelectorAll(FIELD)).slice(0, 20)) {
    const labelEl = field.querySelector(".fb-dash-form-element__label");
    const label = text(labelEl);
    if (!label) continue;

    const required =
      Boolean(field.querySelector("[data-test-text-entity-list-form-required]")) ||
      Boolean(labelEl?.className?.toString().includes("is-required"));

    const select = field.querySelector("select");
    const file = field.querySelector("input[type=file]");
    const checkbox = field.querySelector("input[type=checkbox]");
    const radios = Array.from(field.querySelectorAll("input[type=radio]"));
    const textInput = field.querySelector(
      "input[type=text], input[type=email], input[type=tel], input[type=number], textarea",
    );

    if (select) {
      elements.push(
        element(refs.assign("f", select), "select", label, {
          options: optionLabels(select.querySelectorAll("option")),
          required,
        }),
      );
    } else if (file) {
      elements.push(element(refs.assign("f", file), "file", label, { required }));
    } else if (radios.length) {
      const options = radios
        .map((radio) => {
          const id = radio.getAttribute("id");
          const forLabel = id
            ? Array.from(field.querySelectorAll("label")).find(
                (node) => node.getAttribute("for") === id,
              )
            : undefined;
          return text(forLabel) || radio.getAttribute("value") || "";
        })
        .filter(Boolean);
      elements.push(element(refs.assign("f", field), "radio", label, { options, required }));
    } else if (checkbox) {
      elements.push(element(refs.assign("f", checkbox), "checkbox", label, { required }));
    } else if (textInput) {
      elements.push(
        element(refs.assign("f", textInput), "text", label, {
          required,
          value: (textInput as HTMLInputElement).value || null,
        }),
      );
    }
  }

  // The resume step has no labelled fields, only the upload well.
  const fileInput = modal.querySelector("input[type=file]");
  const uploadWell = modal.querySelector(".jobs-document-upload__container");
  if (fileInput || (uploadWell && /upload/i.test(text(uploadWell)))) {
    const target = fileInput ?? uploadWell;
    if (target) {
      elements.push(element(refs.assign("f", target), "file", "Resume", { required: true }));
    }
  }

  for (const button of Array.from(modal.querySelectorAll("button"))
    .filter((node) => {
      const label = text(node);
      return KEEP_BUTTON.test(label) && !DROP_BUTTON.test(label) && label.length < 40;
    })
    .slice(0, 3)) {
    elements.push(element(refs.assign("b", button), "button", text(button)));
  }

  return {
    draft: {
      page_type: "apply_form",
      job: jobOf(
        jobIdFromUrl(url) ?? "unknown",
        doc.title.replace(/\s*\|\s*LinkedIn\s*$/i, ""),
        null,
        url,
      ),
      elements,
      chat: null,
      page_text_digest: digest(doc),
      signals,
    },
    refs: refs.bound,
  };
}

export const linkedin: PlatformAdapter = { observe };