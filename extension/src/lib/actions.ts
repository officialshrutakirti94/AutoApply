import type { Action } from "./contract";
import { closestLinkedInEasyApplyModal } from "@/platforms/linkedin-modal";

/**
 * The hands. Executes an allow-listed action batch against the live page.
 *
 * Two rules are enforced here, not just on the server:
 *   1. Never navigate off-platform, whatever a click resolves to.
 *   2. Never act on an element that was not in the observation that produced the
 *      action (the ref map comes from that observation).
 */

export interface ActionOutcome {
  ok: boolean;
  error?: string;
  submitted?: boolean;
}

export type AttachResume = () => Promise<File>;

export const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

function setNativeValue(element: HTMLInputElement | HTMLTextAreaElement, value: string): void {
  // React tracks its own value; assigning `.value` alone is ignored on re-render.
  const descriptor = Object.getOwnPropertyDescriptor(
    Object.getPrototypeOf(element) as object,
    "value",
  ) as PropertyDescriptor | undefined;
  descriptor?.set?.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

function labelFor(root: Element, input: Element): Element | null {
  const id = input.getAttribute("id");
  if (!id) return null;
  return Array.from(root.querySelectorAll("label")).find(
    (label) => label.getAttribute("for") === id,
  ) ?? null;
}

function isOffPlatform(element: Element, base: string): boolean {
  const anchor = element.closest("a[href]") ?? (element.matches("a[href]") ? element : null);
  if (!anchor) return false;
  const href = anchor.getAttribute("href") ?? "";
  if (!href || href.startsWith("#") || href.startsWith("javascript:")) return false;
  try {
    return new URL(href, base).hostname !== new URL(base).hostname;
  } catch {
    return true;
  }
}

function matchOption<T extends Element>(candidates: T[], value: string, label: (node: T) => string): T | null {
  const wanted = value.trim().toLowerCase();
  return (
    candidates.find((node) => label(node).trim().toLowerCase() === wanted) ??
    candidates.find((node) => {
      const text = label(node).trim().toLowerCase();
      return text.includes(wanted) || wanted.includes(text);
    }) ??
    null
  );
}

export async function runActions(
  actions: Action[],
  refs: Map<string, Element>,
  options: { attachResume: AttachResume; baseUrl: string },
): Promise<ActionOutcome> {
  let submitted = false;

  for (const action of actions) {
    const target = action.ref ? refs.get(action.ref) : null;
    if (action.ref && !target) {
      return { ok: false, error: `Unknown ref ${action.ref}` };
    }

    switch (action.type) {
      case "wait":
        await sleep(Math.min(Math.max(action.ms ?? 500, 100), 30_000));
        break;

      case "fill_text": {
        const value = action.value ?? "";
        if (!target) return { ok: false, error: "fill_text without a target" };
        if (target instanceof HTMLElement && target.isContentEditable) {
          target.focus();
          target.textContent = value;
          target.dispatchEvent(new InputEvent("input", { bubbles: true, data: value }));
        } else if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) {
          target.focus();
          setNativeValue(target, value);
          target.blur();
        } else {
          return { ok: false, error: "fill_text target is not an input" };
        }
        break;
      }

      case "select_option": {
        const value = action.value ?? "";
        if (!target) return { ok: false, error: "select_option without a target" };

        if (target instanceof HTMLSelectElement) {
          const option = matchOption(
            Array.from(target.options),
            value,
            (node) => node.textContent ?? "",
          );
          if (!option) return { ok: false, error: `No option matching "${value}"` };
          target.value = option.value;
          target.dispatchEvent(new Event("input", { bubbles: true }));
          target.dispatchEvent(new Event("change", { bubbles: true }));
          break;
        }

        const radios = Array.from(target.querySelectorAll<HTMLInputElement>("input[type=radio]"));
        if (radios.length) {
          const radio = matchOption(
            radios,
            value,
            (node) => labelFor(target, node)?.textContent ?? node.value,
          );
          if (!radio) return { ok: false, error: `No choice matching "${value}"` };
          (labelFor(target, radio) as HTMLElement | null)?.click();
          radio.click();
          break;
        }

        if (target instanceof HTMLElement && target.isContentEditable) {
          target.focus();
          target.textContent = value;
          target.dispatchEvent(new InputEvent("input", { bubbles: true, data: value }));
          break;
        }

        return { ok: false, error: "select_option target is not a choice" };
      }

      case "check": {
        if (!target) return { ok: false, error: "check without a target" };
        const input: HTMLInputElement | null =
          target instanceof HTMLInputElement
            ? target
            : target.querySelector<HTMLInputElement>("input[type=checkbox]");
        if (!input) return { ok: false, error: "check target is not a checkbox" };
        if (!input.checked) input.click();
        break;
      }

      case "attach_resume": {
        if (!target) return { ok: false, error: "attach_resume without a target" };
        const file = await options.attachResume();
        const input =
          target instanceof HTMLInputElement ? target : target.querySelector("input[type=file]");
        if (!(input instanceof HTMLInputElement)) {
          return { ok: false, error: "No file input to attach to" };
        }
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
        await sleep(400);
        break;
      }

      case "click": {
        if (!target) return { ok: false, error: "click without a target" };
        if (isOffPlatform(target, options.baseUrl)) {
          return { ok: false, error: "Refused to click an off-platform link" };
        }

        // A job card is a link. Clicking it often opens a new tab or does nothing
        // (React handlers, disabled anchors), so navigate in place instead: that
        // guarantees the job page and a URL we can recognise.
        const link = jobLink(target);
        if (link) {
          location.assign(link);
          return { ok: true, submitted };
        }

        target.scrollIntoView({ block: "center", behavior: "instant" as ScrollBehavior });
        (target as HTMLElement).click();
        break;
      }

      case "submit": {
        if (!(target instanceof HTMLElement)) {
          return { ok: false, error: "submit without an observed control" };
        }
        const modal = closestLinkedInEasyApplyModal(target);
        const label =
          (target.textContent ?? "").replace(/\s+/g, " ").trim() ||
          target.getAttribute("aria-label")?.trim() ||
          "";
        const hidden = target.getClientRects().length === 0;
        if (
          !modal ||
          !target.matches("button, [role='button']") ||
          hidden ||
          target.getAttribute("aria-disabled") === "true" ||
          (target instanceof HTMLButtonElement && target.disabled) ||
          !/^\s*(submit|submit application|submit your application|send application|confirm and submit)\s*$/i.test(
            label,
          )
        ) {
          return { ok: false, error: "Observed control is not the final submit button" };
        }
        target.scrollIntoView({ block: "center", behavior: "instant" as ScrollBehavior });
        target.click();
        submitted = true;
        break;
      }

      case "finish":
        break;

      default:
        return { ok: false, error: `Unsupported action ${String(action.type)}` };
    }
  }

  return { ok: true, submitted };
}

/** Returns the job-detail URL behind an element, when it is a job card link. */
function jobLink(element: Element): string | null {
  const anchor = element.closest("a[href]") ?? (element.matches("a[href]") ? element : null);
  const href = anchor?.getAttribute("href") ?? "";
  const card = element.closest("[data-job-id], [data-occludable-job-id]");
  const cardId =
    card?.getAttribute("data-job-id") ?? card?.getAttribute("data-occludable-job-id");

  if (!/\/jobs\/view\/|naukri\.com\/job-listings-|jobId=/.test(href) && !cardId) return null;

  try {
    const url = new URL(href || "/", location.href);
    if (url.origin !== location.origin) return null;

    // Linkedin sends a job URL that carries search tracking params straight back
    // into the two-pane results, which never renders in a narrow window. The bare
    // job page always works.
    const viewId = url.pathname.match(/\/jobs\/view\/(\d+)/)?.[1] ?? cardId;
    if (location.hostname.endsWith("linkedin.com") && viewId) {
      return `${location.origin}/jobs/view/${viewId}/`;
    }

    return url.toString();
  } catch {
    return null;
  }
}
