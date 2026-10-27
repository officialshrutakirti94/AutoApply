import assert from "node:assert/strict";
import test from "node:test";
import {
  detectPlatform,
  linkedinSearchUrl,
  naukriSearchUrl,
  platformLabel,
  portalHomeUrl,
  searchUrlFor,
} from "./platforms.ts";
import type { SearchPlan } from "./contract.ts";

const base: SearchPlan = {
  roles: ["Backend Engineer"],
  locations: ["Pune"],
  work_mode: ["remote", "hybrid"],
  remote_first: true,
};

test("linkedin search asks for the last 24 hours", () => {
  const url = new URL(linkedinSearchUrl(base));
  assert.equal(url.origin + url.pathname, "https://www.linkedin.com/jobs/search/");
  assert.equal(url.searchParams.get("keywords"), "Backend Engineer");
  assert.equal(url.searchParams.get("location"), "Pune");
  assert.equal(url.searchParams.get("f_TPR"), "r86400");
});

test("linkedin always sends a location, defaulting to India", () => {
  // No location used to make LinkedIn redirect the search to /jobs/, where there
  // are no job cards and the run stalled.
  const url = new URL(linkedinSearchUrl({ ...base, locations: [] }));
  assert.equal(url.searchParams.get("location"), "India");
  assert.equal(url.searchParams.get("keywords"), "Backend Engineer");
});

test("linkedin keyword and location use + for spaces, like the URL that works", () => {
  const raw = linkedinSearchUrl({ ...base, roles: ["AI Engineer"], locations: [] });
  assert.ok(raw.includes("keywords=AI+Engineer"), raw);
  assert.ok(raw.includes("location=India"), raw);
  assert.ok(raw.endsWith("f_TPR=r86400"), raw);
});

test("naukri matches the URL that actually loads", () => {
  const raw = naukriSearchUrl({ ...base, roles: ["AI Engineer"], locations: ["Bengaluru"] });
  assert.equal(raw, "https://www.naukri.com/ai-engineer-jobs?jobAge=1");
});

test("naukri does not put a city in the path", () => {
  // `/<role>-jobs-in-<city>` returns "Oops! Something went wrong" on the current site.
  const url = new URL(naukriSearchUrl(base));
  assert.equal(url.pathname, "/backend-engineer-jobs");
  assert.equal(url.searchParams.get("jobAge"), "1");
  assert.equal(url.searchParams.has("sort"), false);
});

test("naukri falls back to a plain jobs search without a role", () => {
  const url = new URL(naukriSearchUrl({ ...base, roles: [] }));
  assert.equal(url.pathname, "/jobs");
});

test("naukri slugs punctuation and multi-word roles", () => {
  const url = new URL(naukriSearchUrl({ ...base, roles: ["Data & AI Engineer"] }));
  assert.equal(url.pathname, "/data-ai-engineer-jobs");
});

test("naukri copes with an empty search plan", () => {
  const url = new URL(naukriSearchUrl({ roles: [], locations: [], work_mode: [], remote_first: false }));
  assert.equal(url.pathname, "/jobs");
});

test("detectPlatform only claims the two platforms", () => {
  assert.equal(detectPlatform("https://www.linkedin.com/jobs/search/"), "linkedin");
  assert.equal(detectPlatform("https://in.linkedin.com/jobs/view/123"), "linkedin");
  assert.equal(detectPlatform("https://www.naukri.com/backend-jobs?jobAge=1"), "naukri");
  assert.equal(detectPlatform("https://example.com/linkedin.com"), null);
  assert.equal(detectPlatform("not a url"), null);
});

test("labels and portal home pages", () => {
  assert.equal(platformLabel("linkedin"), "LinkedIn");
  assert.equal(platformLabel("naukri"), "Naukri");
  assert.equal(portalHomeUrl("linkedin"), "https://www.linkedin.com/jobs/");
  assert.equal(portalHomeUrl("naukri"), "https://www.naukri.com/jobs");
});

test("searchUrlFor dispatches per platform", () => {
  assert.ok(searchUrlFor("linkedin", base).startsWith("https://www.linkedin.com/jobs/search/"));
  assert.ok(searchUrlFor("naukri", base).startsWith("https://www.naukri.com/backend-engineer"));
});