import { detectPlatform } from "@/lib/platforms";
import { runActions } from "@/lib/actions";
import { adapterFor } from "@/platforms";
import {
  closestLinkedInEasyApplyModal,
  findLinkedInEasyApplyModal,
} from "@/platforms/linkedin-modal";
import { detectSignedIn } from "@/platforms/detect";
import { mergeVisitedJobIds } from "@/lib/job-queue";
import type { Action } from "@/lib/contract";

/**
 * Content script: a stateless DOM adapter.
 *
 * It owns no timers and no run state. The service worker asks what the page looks
 * like and tells it what to do, which is what keeps the loop alive while the tab
 * sits in the background.
 *
 * The ref map is kept here, per page, because refs only mean something in the
 * observation that produced them.
 */

export default defineContentScript({
  matches: ["*://*.linkedin.com/*", "*://*.naukri.com/*"],
  runAt: "document_idle",
  main() {
    const detected = detectPlatform(location.href);
    if (!detected) return;

    const plugin = detected;
    const adapter = adapterFor(plugin);
    let refs = new Map<string, Element>();
    let submitAttempted = false;
    /** Cards already dealt with this run, so the agent never re-opens one. */
    const visited = new Set<string>();

    chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
      const type = (message as { type?: string })?.type;

      if (type === "ping") {
        sendResponse({
          platform: plugin,
          signedIn: detectSignedIn(plugin),
          url: location.href,
          ready: document.readyState === "complete",
        });
        return false;
      }

      if (type === "settle") {
        void settle().then(() => sendResponse({ ok: true }));
        return true;
      }

      if (type === "mark-visited") {
        const jobId = (message as { jobId?: string }).jobId;
        if (jobId) visited.add(jobId);
        sendResponse({ ok: true });
        return false;
      }

      if (type === "observe") {
        // LinkedIn opens the job pane lazily: observing immediately returns the
        // list with no apply control. Wait for the pane before describing it.
        void (async () => {
        const messageVisited = (message as { visitedJobIds?: unknown }).visitedJobIds;
        const visitedIds = mergeVisitedJobIds(visited, messageVisited);

        if (plugin === "linkedin" && (/[?&]currentJobId=/.test(location.href) || /\/jobs\/view\//.test(location.pathname))) {
          await waitForApplyControl(4500);
        }

        let result = adapter.observe(document, location.href);

        if (
          plugin === "linkedin" &&
          submitAttempted &&
          result.draft.page_type !== "confirmation"
        ) {
          result = {
            draft: {
              ...result.draft,
              page_type: "unknown",
              elements: [],
              signals: [...new Set([...result.draft.signals, "unknown_page" as const])],
              page_text_digest:
                "The submit action was attempted, but LinkedIn did not show an application confirmation.",
            },
            refs: new Map(),
          };
        } else if (plugin === "linkedin" && result.draft.page_type === "confirmation") {
          submitAttempted = false;
        }

        // Drop cards this run has already handled. The backend always picks the
        // first match, so use the service worker's persisted visited IDs too:
        // this content script is recreated whenever LinkedIn navigates.
        if (result.draft.page_type === "search_results") {
          result.draft.elements = unvisitedElements(result, visitedIds);

          // LinkedIn virtualizes and lazily loads its result list. An empty
          // filtered list only means the currently rendered batch is done.
          if (plugin === "linkedin" && result.draft.elements.length === 0) {
              const wasSearchResults = result.draft.page_type === "search_results";
            const loaded = await loadMoreLinkedInResults(visitedIds);
            if (loaded) {
              result = adapter.observe(document, location.href);
              if (result.draft.page_type === "search_results") {
                result.draft.elements = unvisitedElements(result, visitedIds);
              }
            }
            refs = result.refs;
            sendResponse({
              ok: true,
              draft: result.draft,
              nextCard: result.draft.page_type === "job_detail" ? nextUnvisitedCard(visitedIds) : null,
              queueExhausted:
                wasSearchResults &&
                result.draft.page_type === "search_results" &&
                result.draft.elements.length === 0,
            });
            return;
          }
        }
        refs = result.refs;

        // LinkedIn auto-selects the first job when the search loads, so after a
        // job is finished the run lands back on it. Hand the parent the next card
        // it has not dealt with yet.
        const nextCard =
          result.draft.page_type === "job_detail" ? nextUnvisitedCard(visitedIds) : null;

        sendResponse({ ok: true, draft: result.draft, nextCard });
        })();
        return true;
      }

      if (type === "act") {
        const actions = (message as { actions: Action[] }).actions ?? [];
        const clickTarget = actions
          .filter((action) => action.type === "click")
          .map((action) => (action.ref ? refs.get(action.ref) : null))
          .find((target): target is Element => Boolean(target));
        const clickLabel = clickTarget
          ? `${clickTarget.textContent ?? ""} ${clickTarget.getAttribute("aria-label") ?? ""}`
              .replace(/\s+/g, " ")
              .trim()
          : "";
        const modalBefore = Boolean(findLinkedInEasyApplyModal(document));
        const modalSignatureBefore = modalStageSignature();

        void (async () => {
          const outcome = await runActions(actions, refs, {
            baseUrl: location.href,
            attachResume: fetchResume,
          });
          if (!outcome.ok) {
            sendResponse(outcome);
            return;
          }

          if (
            plugin === "linkedin" &&
            clickTarget &&
            (closestLinkedInEasyApplyModal(clickTarget) || /\beasy\s*apply\b/i.test(clickLabel))
          ) {
            await waitForModalTransition(modalBefore, modalSignatureBefore, 6000);
            await settle(180, 1200);
          }

          if (plugin === "linkedin" && outcome.submitted) {
            submitAttempted = true;
            await waitForApplicationConfirmation(8000);
          }
          sendResponse(outcome);
        })();
        return true;
      }

      return false;
    });

    // The in-page prompt. Only when signed in, and only once per page load.
    void showBannerIfReady();

    /** Resolve as soon as an apply control exists, or when time runs out. */
    function waitForApplyControl(timeoutMs: number): Promise<void> {
      return new Promise((resolve) => {
        const started = Date.now();
        const found = () =>
          Boolean(
            document.querySelector("button.jobs-apply-button, .jobs-apply-button") ||
              Array.from(document.querySelectorAll("button, a[role='button']")).some((node) =>
                /^\s*(easy\s*)?apply\s*$/i.test((node.textContent ?? "").trim()),
              ),
          );

        if (found()) return resolve();
        const timer = window.setInterval(() => {
          if (found() || Date.now() - started > timeoutMs) {
            window.clearInterval(timer);
            resolve();
          }
        }, 250);
      });
    }

    /** The next job card this run has not opened yet, as a URL. */
    function unvisitedElements(
      result: ReturnType<typeof adapter.observe>,
      visitedIds: Set<string>,
    ) {
      return result.draft.elements.filter((field) => {
        const node = result.refs.get(field.ref);
        const card = node?.closest(
          "[data-job-id], [data-occludable-job-id], .srp-jobtuple-wrapper",
        );
        const jobId =
          card?.getAttribute("data-job-id") ??
          card?.getAttribute("data-occludable-job-id") ??
          null;
        return !jobId || !visitedIds.has(jobId);
      });
    }

    /** Scroll LinkedIn's result pane until a fresh card appears or loading stalls. */
    async function loadMoreLinkedInResults(visitedIds: Set<string>): Promise<boolean> {
      let previousIds = currentLinkedInCardIds().join(",");
      let unchangedAttempts = 0;
      for (let attempt = 0; attempt < 4; attempt += 1) {
        scrollLinkedInResults();
        await new Promise((resolve) => window.setTimeout(resolve, 1200));
        await settle(250, 1600);

        const current = adapter.observe(document, location.href);
        if (
          current.draft.page_type === "search_results" &&
          unvisitedElements(current, visitedIds).length > 0
        ) {
          return true;
        }

        const currentIds = currentLinkedInCardIds().join(",");
        if (currentIds === previousIds) {
          unchangedAttempts += 1;
          if (unchangedAttempts >= 2) return false;
        } else {
          unchangedAttempts = 0;
        }
        previousIds = currentIds;
      }
      return false;
    }

    function currentLinkedInCardIds(): string[] {
      return Array.from(
        document.querySelectorAll(
          "div.job-card-container[data-job-id], li[data-occludable-job-id]",
        ),
      )
        .map(
          (card) =>
            card.getAttribute("data-job-id") ??
            card.getAttribute("data-occludable-job-id") ??
            "",
        )
        .filter(Boolean);
    }

    function scrollLinkedInResults(): void {
      const card = document.querySelector<HTMLElement>(
        "div.job-card-container[data-job-id], li[data-occludable-job-id]",
      );
      let parent = card?.parentElement ?? null;
      while (parent && parent !== document.body) {
        const style = window.getComputedStyle(parent);
        if (
          parent.scrollHeight > parent.clientHeight + 20 &&
          /(auto|scroll)/.test(style.overflowY)
        ) {
          parent.scrollTop = parent.scrollHeight;
          return;
        }
        parent = parent.parentElement;
      }

      const lastCard = document.querySelector<HTMLElement>(
        "div.job-card-container[data-job-id]:last-of-type, li[data-occludable-job-id]:last-of-type",
      );
      lastCard?.scrollIntoView({ block: "end" });
      window.scrollTo(0, document.documentElement.scrollHeight);
    }

    function nextUnvisitedCard(visitedIds: Set<string>): string | null {
      const cards = Array.from(
        document.querySelectorAll(
          "div.job-card-container[data-job-id], li[data-occludable-job-id]",
        ),
      );
      for (const card of cards) {
        const id =
          card.getAttribute("data-job-id") ?? card.getAttribute("data-occludable-job-id");
        if (!id || visitedIds.has(id)) continue;
        // Go to the bare job page: the tracked search link bounces back into the
        // two-pane results, which is exactly what this is trying to escape.
        if (location.hostname.endsWith("linkedin.com")) {
          return `${location.origin}/jobs/view/${id}/`;
        }
        const anchor = card.querySelector("a[href]");
        const href = anchor?.getAttribute("href");
        if (href) {
          try {
            return new URL(href, location.href).toString();
          } catch {
            continue;
          }
        }
      }
      return null;
    }

    async function fetchResume(): Promise<File> {
      const answer = (await chrome.runtime.sendMessage({ type: "resume-url" })) as {
        ok: boolean;
        url?: string;
        error?: string;
      };
      if (!answer.ok || !answer.url) throw new Error(answer.error ?? "No resume available");

      const response = await fetch(answer.url);
      if (!response.ok) throw new Error(`Resume download failed (${response.status})`);
      const blob = await response.blob();
      const name = blob.type.includes("wordprocessingml")
        ? "resume.docx"
        : "resume.pdf";
      return new File([blob], name, { type: blob.type || "application/octet-stream" });
    }

    /** Resolve when the DOM has been quiet for a moment: SPAs swap content without navigating. */
    function settle(quietMs = 320, maxMs = 6000): Promise<void> {
      return new Promise((resolve) => {
        let timer = 0;
        const done = () => {
          observer.disconnect();
          clearTimeout(timer);
          clearTimeout(cap);
          resolve();
        };
        const observer = new MutationObserver(() => {
          clearTimeout(timer);
          timer = window.setTimeout(done, quietMs);
        });
        const cap = window.setTimeout(done, maxMs);
        observer.observe(document.body, { childList: true, subtree: true, attributes: true });
        timer = window.setTimeout(done, quietMs);
      });
    }

    function modalStageSignature(): string | null {
      const modal = findLinkedInEasyApplyModal(document);
      if (!modal) return null;
      const content =
        modal.querySelector(".jobs-easy-apply-modal__content") ?? modal;
      return (content.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 3000);
    }

    function waitForModalTransition(
      wasOpen: boolean,
      before: string | null,
      timeoutMs: number,
    ): Promise<void> {
      return waitForDomCondition(
        () => {
          const after = modalStageSignature();
          return wasOpen ? after !== null && after !== before : after !== null;
        },
        timeoutMs,
      );
    }

    function waitForApplicationConfirmation(timeoutMs: number): Promise<void> {
      return waitForDomCondition(
        () => adapter.observe(document, location.href).draft.page_type === "confirmation",
        timeoutMs,
      );
    }

    function waitForDomCondition(
      condition: () => boolean,
      timeoutMs: number,
    ): Promise<void> {
      return new Promise((resolve) => {
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          observer.disconnect();
          window.clearTimeout(timer);
          resolve();
        };
        const check = () => {
          if (condition()) finish();
        };
        const observer = new MutationObserver(check);
        observer.observe(document.documentElement, {
          childList: true,
          subtree: true,
          characterData: true,
          attributes: true,
        });
        const timer = window.setTimeout(finish, timeoutMs);
        check();
      });
    }

    async function showBannerIfReady(): Promise<void> {
      const state = (await chrome.runtime.sendMessage({ type: "get-state" })) as {
        connected: boolean;
        running: unknown;
      };
      if (!state.connected || state.running) return;
      if (detectSignedIn(plugin) === false) return;

      const host = document.createElement("div");
      host.style.cssText = "position:fixed;right:20px;bottom:20px;z-index:2147483647";
      const root = host.attachShadow({ mode: "closed" });
      root.innerHTML = `
        <style>
          .card{font:13px/1.45 -apple-system,"Segoe UI",sans-serif;width:300px;background:#101014;
                color:#f4f4f6;border:1px solid rgba(255,255,255,.16);border-radius:4px;
                padding:14px;box-shadow:0 18px 40px -20px rgba(0,0,0,.8)}
          .row{display:flex;align-items:center;gap:8px;margin-bottom:10px}
          .dot{width:7px;height:7px;border-radius:50%;background:#e8402a}
          .label{font:10px/1 ui-monospace,Consolas,monospace;letter-spacing:.12em;
                 text-transform:uppercase;color:#6f6f7c}
          p{margin:0 0 12px;color:#a6a6b2}
          button{width:100%;height:36px;border:0;border-radius:2px;background:#e8402a;color:#fff;
                 font:600 13px -apple-system,"Segoe UI",sans-serif;cursor:pointer}
          button:hover{background:#ff4b32}
          .dismiss{position:absolute;top:8px;right:10px;background:none;border:0;color:#6f6f7c;
                   cursor:pointer;font-size:15px;width:auto;height:auto}
          .card{position:relative}
        </style>
        <div class="card">
          <button class="dismiss" aria-label="Dismiss">×</button>
          <div class="row"><span class="dot"></span><span class="label">AutoApply</span></div>
          <p>Live run: AutoApply may submit supported applications in ${plugin === "linkedin" ? "LinkedIn" : "Naukri"} using your profile and saved answers.</p>
          <button id="go">Start live run</button>
        </div>`;

      root.querySelector(".dismiss")?.addEventListener("click", () => host.remove());
      root.querySelector("#go")?.addEventListener("click", async () => {
        const button = root.querySelector<HTMLButtonElement>("#go");
        if (button) button.textContent = "Starting…";
        const answer = (await chrome.runtime.sendMessage({
          type: "start-run",
          platform: plugin,
        })) as { ok: boolean; error?: string };
        if (!answer.ok) {
          const paragraph = root.querySelector("p");
          if (paragraph) paragraph.textContent = answer.error ?? "Could not start.";
          if (button) button.textContent = "Start live run";
        } else {
          host.remove();
        }
      });

      document.documentElement.appendChild(host);
    }
  },
});