import type { Platform } from "../lib/contract.ts";

/**
 * Signed-in detection and page risk markers.
 *
 * These are the most fragile selectors in the extension, so they live together,
 * use several fallbacks, and are allowed to answer "unknown" rather than guess.
 * A wrong "signed in" starts a run that hits a login wall; "unknown" only delays
 * the prompt.
 *
 * Every function takes a Document so it can be exercised against saved fixtures.
 */

export function detectSignedIn(
  platform: Platform,
  doc: Document = globalThis.document,
): boolean | null {
  return platform === "linkedin" ? linkedinSignedIn(doc) : naukriSignedIn(doc);
}

function linkedinSignedIn(doc: Document): boolean | null {
  const me = doc.querySelector(
    ".global-nav__me, img.global-nav__me-photo, a[data-test-global-nav-link='me'], " +
      ".global-nav__primary-item--overflow a[href*='/in/']",
  );
  if (me) return true;

  const signIn = doc.querySelector(
    "a.nav__button-secondary, a[data-tracking-control-name='guest_homepage-basic_nav-header-signin'], " +
      "a[href*='/login'], a[href*='signup']",
  );
  if (signIn) return false;

  return null;
}

function naukriSignedIn(doc: Document): boolean | null {
  const me = doc.querySelector(
    ".nI-gNb-drawer, .nI-gNb-drawer__icon, [class*='nI-gNb-drawer'], .view-profile-wrapper",
  );
  if (me) return true;

  const signIn = doc.querySelector(
    "#login_Layer, .loginLayer, a[href*='login.naukri.com'], .nI-gNb-lg-rg__login",
  );
  if (signIn) return false;

  return null;
}

export interface PageSignals {
  captcha: boolean;
  checkpoint: boolean;
  warningBanner: boolean;
  forcedLogout: boolean;
  rateLimited: boolean;
}

/**
 * LinkedIn ships a hidden reCAPTCHA iframe on ordinary pages, so a selector match
 * alone is not a captcha. Only count widgets that actually occupy space.
 */
function isVisible(element: Element): boolean {
  const node = element as HTMLElement;
  const rect = node.getBoundingClientRect?.();
  if (!rect || rect.width < 2 || rect.height < 2) return false;
  const style = node.style;
  if (style && (style.display === "none" || style.visibility === "hidden")) return false;
  return true;
}

/**
 * Any of these must stop the run immediately. Checked on every observation.
 *
 * Deliberately strict: a false positive stops every run, which is far worse than
 * missing a subtle banner. Loose `[class*='captcha']` / `[class*='warning']`
 * matches fire on ordinary pages (LinkedIn ships hidden captcha inputs), so the
 * markers here are specific, visible, or text-based.
 */
export function detectSignals(doc: Document = globalThis.document): PageSignals {
  const body = doc.body;
  const visible = (body?.textContent ?? "").replace(/\s+/g, " ").slice(0, 4000).toLowerCase();
  const has = (re: RegExp) => re.test(visible);
  const alerts = Array.from(doc.querySelectorAll("[role='alert'], [role='status']"));

  const captchaWidget = Array.from(
    doc.querySelectorAll(
      "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[src*='captcha'], " +
        "#captcha-internal, .captcha-image, img[src*='captcha']",
    ),
  ).some(isVisible);

  const challengeWidget = Array.from(
    doc.querySelectorAll("#challenge, [data-test-id='challenge'], .challenge-page"),
  ).some(isVisible);

  return {
    captcha:
      captchaWidget ||
      has(/enter the characters you see|verify you are human|please solve this puzzle|complete the captcha/),
    checkpoint:
      challengeWidget ||
      has(/unusual activity|verify your identity|we.ve restricted your account|security verification/),
    warningBanner: alerts.some(
      (node) =>
        isVisible(node) &&
        /warning|restrict|suspend|unusual|verify your/i.test((node.textContent ?? "").replace(/\s+/g, " ")),
    ),
    forcedLogout: has(/sign in to continue|session expired|you.ve been signed out/),
    rateLimited: has(/too many requests|rate limit exceeded/),
  };
}