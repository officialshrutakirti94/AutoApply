import type { FormElement, Signal } from "@/lib/contract";
import {
  Refs,
  digest,
  element,
  jobOf,
  text,
  type ObserveResult,
  type PlatformAdapter,
} from "./types.ts";
import { detectSignals } from "./detect.ts";

/**
 * Naukri.
 *
 * The apply flow is a side-panel chatbot whose ids carry a random suffix
 * (`_8pb2nhveeMessages`), so everything keys off stable class names:
 *   .chatbot_MessageContainer    the panel
 *   .botItem .botMsg span        each bot message (the last one is the question)
 *   .ssrc__radio / .ssrc__label  a yes/no style choice
 *   .textArea[contenteditable]   a free-text answer
 *   .sendMsg                     the submit control, labelled "Save"
 *
 * Listing class names are hashed too, except `srp-jobtuple-wrapper[data-job-id]`,
 * `a.title` and `a.comp-name`.
 */

const CHAT = ".chatbot_MessageContainer";
const CARD = "div.srp-jobtuple-wrapper[data-job-id]";

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

function jobFromJsonLd(
  doc: Document,
): { id: string | null; title: string | null; company: string | null } {
  for (const node of Array.from(doc.querySelectorAll("script[type='application/ld+json']"))) {
    try {
      const parsed = JSON.parse(node.textContent ?? "") as Record<string, unknown>;
      const entries = Array.isArray(parsed) ? parsed : [parsed];
      for (const entry of entries as Array<Record<string, unknown>>) {
        if (entry?.["@type"] !== "JobPosting") continue;
        const identifier = entry.identifier as { value?: string } | undefined;
        const org = entry.hiringOrganization as { name?: string } | undefined;
        return {
          id: identifier?.value ?? null,
          title: typeof entry.title === "string" ? entry.title : null,
          company: org?.name ?? null,
        };
      }
    } catch {
      continue;
    }
  }
  return { id: null, title: null, company: null };
}

function observe(doc: Document, url: string): ObserveResult {
  const signals = signalsOf(doc);

  const panel = doc.querySelector(CHAT);
  if (panel) return chatPanel(doc, url, panel, signals);

  const search = searchResults(doc, url, signals);
  if (search) return search;

  const detail = jobDetail(doc, url, signals);
  if (detail) return detail;

  const job = jobFromJsonLd(doc);
  return {
    draft: {
      page_type: "unknown",
      job: jobOf(job.id, job.title, job.company, url),
      elements: [],
      chat: null,
      page_text_digest: digest(doc),
      signals: [...signals, "unknown_page"],
    },
    refs: new Map(),
  };
}

function chatPanel(doc: Document, url: string, panel: Element, signals: Signal[]): ObserveResult {
  const refs = new Refs();
  const messages = Array.from(panel.querySelectorAll(".botItem .botMsg span"))
    .map((node) => text(node))
    .filter(Boolean);
  const question = messages.at(-1) ?? "";

  // A recruiter pointing at an off-platform form makes this an external
  // application: we never follow it, it comes back as a Preferred job. The link is
  // usually plain text, so scan the message text as well as anchors.
  const messageText = Array.from(panel.querySelectorAll(".botItem"))
    .map((node) => node.textContent ?? "")
    .join(" ");
  const candidates = [
    ...Array.from(panel.querySelectorAll(".botItem a[href]")).map(
      (anchor) => anchor.getAttribute("href") ?? "",
    ),
    ...(messageText.match(/https?:\/\/[^\s"'<>]+/gi) ?? []),
  ];
  const external = candidates.some((href) => {
    if (!href) return false;
    try {
      return !new URL(href, url).hostname.endsWith("naukri.com");
    } catch {
      return false;
    }
  });

  const job = jobFromJsonLd(doc);

  if (!question) {
    return {
      draft: {
        page_type: "unknown",
        job: jobOf(job.id, job.title, job.company, url, { external }),
        elements: [],
        chat: null,
        page_text_digest: digest(doc),
        signals: [...signals, "unknown_page"],
      },
      refs: new Map(),
    };
  }

  const elements: FormElement[] = [];
  const radios = Array.from(panel.querySelectorAll(".ssrc__radio"));

  if (radios.length) {
    // A choice question is one field with options, so the backend answers it
    // through the same path as a dropdown.
    const options = radios
      .map((radio) => {
        const id = radio.getAttribute("id");
        const forLabel = id
          ? Array.from(panel.querySelectorAll(".ssrc__label")).find(
              (node) => node.getAttribute("for") === id,
            )
          : undefined;
        return text(forLabel) || radio.getAttribute("value") || "";
      })
      .filter(Boolean);
    const first = radios[0];
    const group = first?.parentElement?.parentElement ?? first;
    elements.push(
      element(refs.assign("f", group ?? first!), "select", question, {
        options,
        required: true,
      }),
    );
  }

  const sendButton = panel.querySelector(".sendMsg") ?? doc.querySelector(".sendMsg");
  if (sendButton) {
    elements.push(element(refs.assign("b", sendButton), "button", text(sendButton) || "Save"));
  }

  const editable = panel.querySelector<HTMLElement>(".textArea[contenteditable='true']");
  const chat = editable ? { question, input_ref: refs.assign("c", editable) } : null;

  return {
    draft: {
      page_type: "chat_question",
      job: jobOf(job.id, job.title, job.company, url, { external }),
      elements,
      chat,
      page_text_digest: digest(doc),
      signals,
    },
    refs: refs.bound,
  };
}

/**
 * A Naukri job page offers two ways in: "Apply" (the in-site flow, which opens the
 * recruiters' chat) and "Apply on company site" (off-platform). We only ever hand
 * the first one to the agent; the second becomes a Preferred job.
 */
function jobDetail(doc: Document, url: string, signals: Signal[]): ObserveResult | null {
  const job = jobFromJsonLd(doc);
  if (!job.id && !job.title) return null;

  const candidates = Array.from(doc.querySelectorAll("button, a[role='button'], a")).filter(
    (node) => /apply/i.test(text(node)),
  );
  if (!candidates.length) return null;

  const inSite = candidates.find(
    (node) => !/company|external|website/i.test(text(node)) && /^\s*apply\s*$/i.test(text(node)),
  );
  const companySite = candidates.find((node) => /company|external|website/i.test(text(node)));

  const refs = new Refs();
  const elements: FormElement[] = [];

  if (inSite) {
    elements.push(element(refs.assign("b", inSite), "button", "Apply"));
  }

  return {
    draft: {
      page_type: "job_detail",
      job: jobOf(job.id, job.title, job.company, url, {
        // Only when the in-site flow does not exist does this become our problem
        // to hand back rather than attempt.
        external: !inSite && Boolean(companySite),
      }),
      elements,
      chat: null,
      page_text_digest: digest(doc),
      signals,
    },
    refs: refs.bound,
  };
}

function searchResults(doc: Document, url: string, signals: Signal[]): ObserveResult | null {
  const cards = Array.from(doc.querySelectorAll(CARD));
  if (!cards.length) return null;

  const refs = new Refs();
  const elements: FormElement[] = [];
  const seen = new Set<string>();

  for (const card of cards.slice(0, 12)) {
    const id = card.getAttribute("data-job-id");
    const titleNode = card.querySelector("a.title");
    const title = text(titleNode) || titleNode?.getAttribute("title") || "";
    if (!id || !title || seen.has(id)) continue;
    seen.add(id);

    const company = text(card.querySelector("a.comp-name"));
    const applied = /\bapplied\b/i.test(text(card));
    const label = company ? `${title} at ${company}` : title;
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

export const naukri: PlatformAdapter = { observe };