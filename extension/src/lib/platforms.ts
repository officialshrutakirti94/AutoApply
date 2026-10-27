import type { Platform, SearchPlan } from "./contract";

/**
 * Platform identity and the 24-hour search URL.
 *
 * URL building is a pure function so it can be unit-tested without a browser, and
 * so every platform's quirks stay in one file.
 *
 * The recency filters (`f_TPR`, `jobAge`) are the platform's own; if they change,
 * only this file changes.
 */

const LINKEDIN_SEARCH = "https://www.linkedin.com/jobs/search/";
const NAUKRI_HOME = "https://www.naukri.com";

export function detectPlatform(url: string): Platform | null {
  try {
    const { hostname } = new URL(url);
    if (hostname.endsWith("linkedin.com")) return "linkedin";
    if (hostname.endsWith("naukri.com")) return "naukri";
    return null;
  } catch {
    return null;
  }
}

export function platformLabel(platform: Platform): string {
  return platform === "linkedin" ? "LinkedIn" : "Naukri";
}

function slug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/**
 * LinkedIn search, matching the format that actually loads:
 *
 *   /jobs/search/?keywords=AI+Engineer&location=India&f_TPR=r86400
 *
 * The location is not optional. LinkedIn redirects a location-less search to
 * /jobs/, which lands the run on a page with no job cards at all. `India` is the
 * default when the user has not chosen a location; `f_TPR=r86400` is "posted in
 * the last 24 hours".
 */
export const DEFAULT_LINKEDIN_LOCATION = "India";

export function linkedinSearchUrl(search: SearchPlan): string {
  const params = new URLSearchParams();
  params.set("keywords", search.roles[0]?.trim() || "Software Engineer");
  params.set("location", search.locations[0]?.trim() || DEFAULT_LINKEDIN_LOCATION);
  params.set("f_TPR", "r86400");

  return `${LINKEDIN_SEARCH}?${params.toString()}`;
}

/**
 * Naukri search, matching the format that loads:
 *
 *   https://www.naukri.com/ai-engineer-jobs?jobAge=1
 *
 * The newer Naukri front end returns "Oops! Something went wrong" for the old
 * `/<role>-jobs-in-<city>` path and for `sort=dd`, so the location is left to the
 * account's own defaults and only the role and the one-day window are sent.
 */
export function naukriSearchUrl(search: SearchPlan): string {
  const role = slug(search.roles[0] ?? "");
  const path = role ? `/${role}-jobs` : "/jobs";
  const params = new URLSearchParams({ jobAge: "1" });

  return `${NAUKRI_HOME}${path}?${params.toString()}`;
}

export function searchUrlFor(platform: Platform, search: SearchPlan): string {
  return platform === "linkedin" ? linkedinSearchUrl(search) : naukriSearchUrl(search);
}

/** Where the "open the portal" button should go before a run exists. */
export function portalHomeUrl(platform: Platform): string {
  return platform === "linkedin"
    ? "https://www.linkedin.com/jobs/"
    : `${NAUKRI_HOME}/jobs`;
}

export function isOnSearchPage(platform: Platform, url: string): boolean {
  try {
    const parsed = new URL(url);
    if (platform === "linkedin") return parsed.pathname.startsWith("/jobs/search");
    return parsed.hostname.endsWith("naukri.com");
  } catch {
    return false;
  }
}