import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { parseHTML } from "linkedom";
import { linkedin } from "./linkedin.ts";
import { naukri } from "./naukri.ts";

/**
 * Runs the extractors against the real pages you captured, so selector changes
 * show up as test failures instead of a broken run.
 */
const FIXTURES = path.resolve(import.meta.dirname, "../../fixtures");

function load(relative: string): Document {
  const html = fs.readFileSync(path.join(FIXTURES, relative), "utf8");
  return parseHTML(html).document as unknown as Document;
}

const has = (file: string) => fs.existsSync(path.join(FIXTURES, file));

test("linkedin: search results become clickable cards", { skip: !has("linkedin/search.html") }, () => {
  const { draft } = linkedin.observe(load("linkedin/search.html"), "https://www.linkedin.com/jobs/search/?keywords=x");

  assert.equal(draft.page_type, "search_results");
  assert.ok(draft.elements.length >= 5, `expected cards, got ${draft.elements.length}`);
  assert.ok(draft.elements.every((el) => el.kind === "button"));
  assert.ok(
    draft.elements.every((el) => /^b[0-9]{1,4}$/.test(el.ref)),
    "refs must match the contract pattern",
  );
  // The label is what the backend matches against the user's roles.
  assert.ok(draft.elements.some((el) => (el.label ?? "").includes(" at ")), "labels should read 'Title at Company'");
  // A normal search page must not look like a security check.
  assert.deepEqual(draft.signals, [], "no signals on an ordinary results page");
});

test("linkedin: the Easy Apply modal becomes a form", { skip: !has("linkedin/apply-questions.html") }, () => {
  const url = "https://www.linkedin.com/jobs/view/4481438787/";
  const { draft } = linkedin.observe(load("linkedin/apply-questions.html"), url);

  assert.equal(draft.page_type, "apply_form");
  assert.equal(draft.job.id, "4481438787");

  const select = draft.elements.find((el) => el.kind === "select");
  assert.ok(select, "the email dropdown should be a select");
  assert.match(select!.label ?? "", /email/i);
  assert.ok(select!.options?.some((option) => option.includes("@")), "options must include the real choice");
  assert.ok(
    !select!.options?.some((option) => /select an option/i.test(option)),
    "placeholder options must be dropped",
  );

  assert.ok(draft.elements.some((el) => el.kind === "button"), "the modal needs its Next/Submit button");
  assert.ok(
    draft.elements.some((el) => el.kind === "select" && /country code/i.test(el.label ?? "")),
    "the phone country code is a select too",
  );
});

test("linkedin: an empty job pane needs a human, it is not an external job", () => {
  // Live regression: LinkedIn rewrites the URL before the pane has drawn, so the
  // observation had no apply control at all. Reporting that as "external" quietly
  // skipped every job in the run.
  const doc = parseHTML(
    "<body><button>Next</button><div>Software Engineer</div></body>",
  ).document as unknown as Document;

  const url = "https://www.linkedin.com/jobs/view/4474904063/";
  const { draft } = linkedin.observe(doc, url);

  assert.equal(draft.page_type, "unknown");
  assert.ok(draft.signals.length > 0, "an unreadable pane must raise a signal");
  assert.equal(draft.job.external, false, "must never be mistaken for an external job");
});

test(
  "linkedin: an off-platform Apply job is queued for the dashboard",
  { skip: !has("linkedin/search.html") },
  () => {
  const url = "https://www.linkedin.com/jobs/view/4468380998/";
  const { draft } = linkedin.observe(load("linkedin/search.html"), url);

  assert.equal(draft.page_type, "job_detail");
  assert.equal(draft.job.external, true);
  assert.ok(draft.job.title, "the pane must yield a title");
  assert.doesNotMatch(
    draft.job.title ?? "",
    /\d+ .*jobs in/i,
    "the page title leaked into the job title before",
  );
  assert.equal(draft.job.job_url, url, "fall back to the LinkedIn job when no destination URL is exposed");
  assert.equal(
    draft.elements.some((el) => el.kind === "button" && /apply/i.test(el.label ?? "")),
    false,
    "do not ask the agent to click a company-site Apply control",
  );
  },
);

test("linkedin: Easy Apply stays in the automated application flow", () => {
  const doc = parseHTML(`
    <body>
      <div class="jobs-details__main-content">
        <h1 class="job-details-jobs-unified-top-card__job-title">Software Engineer</h1>
        <span class="job-details-jobs-unified-top-card__company-name">Acme</span>
        <p>Responses managed off LinkedIn</p>
        <button class="jobs-apply-button" aria-label="Easy Apply to Software Engineer">Easy Apply</button>
      </div>
    </body>
  `).document as unknown as Document;
  const { draft } = linkedin.observe(doc, "https://www.linkedin.com/jobs/view/4484005106/");

  assert.equal(draft.page_type, "job_detail");
  assert.equal(draft.job.external, false, "Easy Apply takes precedence over off-platform markers");
  assert.ok(draft.elements.some((el) => /easy apply/i.test(el.label ?? "")));
});

test("linkedin: company-site destination is captured when LinkedIn exposes it", () => {
  const doc = parseHTML(`
    <body>
      <div class="jobs-details__main-content">
        <h1 class="job-details-jobs-unified-top-card__job-title">Software Engineer</h1>
        <p>Responses managed off LinkedIn</p>
        <a aria-label="Apply on company website" href="https://careers.example.com/jobs/42">Apply</a>
      </div>
    </body>
  `).document as unknown as Document;
  const { draft } = linkedin.observe(doc, "https://www.linkedin.com/jobs/view/4484005106/");

  assert.equal(draft.page_type, "job_detail");
  assert.equal(draft.job.external, true);
  assert.equal(draft.job.job_url, "https://careers.example.com/jobs/42");
});

test("linkedin: a generic external link does not misclassify an unfinished job pane", () => {
  const doc = parseHTML(`
    <body>
      <a href="https://example.com">Company website</a>
      <div class="jobs-details__main-content">
        <h1>Software Engineer</h1>
      </div>
    </body>
  `).document as unknown as Document;
  const { draft } = linkedin.observe(doc, "https://www.linkedin.com/jobs/view/4484005106/");

  assert.equal(draft.page_type, "unknown");
  assert.equal(draft.job.external, false);
});

test(
  "linkedin: a results page that auto-selected a job still yields cards",
  { skip: !has("linkedin/search.html") },
  () => {
    // LinkedIn adds currentJobId to the results URL while auto-selecting the first job.
    const url =
      "https://www.linkedin.com/jobs/search/?currentJobId=4481868961&f_TPR=r86400&keywords=AI%20Engineer&location=Bengaluru";
    const { draft } = linkedin.observe(load("linkedin/search.html"), url);

    assert.equal(draft.page_type, "search_results");
    assert.ok(draft.elements.length >= 5, `expected cards, got ${draft.elements.length}`);
    assert.ok(draft.elements.every((el) => (el.label ?? "").includes(" at ") || el.label));
  },
);

test("naukri: search results become clickable cards", { skip: !has("Naukri/search.html") }, () => {
  const { draft } = naukri.observe(load("Naukri/search.html"), "https://www.naukri.com/ai-engineer-jobs?jobAge=1");

  assert.equal(draft.page_type, "search_results");
  assert.ok(draft.elements.length >= 5, `expected cards, got ${draft.elements.length}`);
  assert.ok(draft.elements.some((el) => / at /.test(el.label ?? "")));
});

test("naukri: a yes/no chat question becomes one choice field", { skip: !has("Naukri/apply-chat-selected.html") }, () => {
  const { draft } = naukri.observe(
    load("Naukri/apply-chat-selected.html"),
    "https://www.naukri.com/job-listings-assistant-professor-261026017589",
  );

  assert.equal(draft.page_type, "chat_question");

  const choice = draft.elements.find((el) => el.kind === "select");
  assert.ok(choice, "the radio group should be a select");
  // The question is the last thing the bot said, and it is also the field label.
  assert.match(choice!.label ?? "", /link/i);
  assert.deepEqual(choice!.options, ["Yes - Interested", "No - Not interested"]);

  assert.ok(
    draft.elements.some((el) => el.kind === "button" && /save/i.test(el.label ?? "")),
    "Save submits the answer",
  );
  assert.equal(draft.job.external, true, "the forms.gle link makes this an external application");
});

test("naukri: a free-text chat question exposes the input", { skip: !has("Naukri/apply-chat-text.html") }, () => {
  const { draft } = naukri.observe(
    load("Naukri/apply-chat-text.html"),
    "https://www.naukri.com/job-listings-ai-engineer-261026000001",
  );

  assert.equal(draft.page_type, "chat_question");
  assert.match(draft.chat?.question ?? "", /years of experience/i);
  assert.match(draft.chat?.input_ref ?? "", /^c[0-9]{1,4}$/);
  assert.equal(draft.elements.some((el) => el.kind === "select"), false, "a text question has no options");
});
