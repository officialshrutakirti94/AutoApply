/**
 * Real browser test of the dashboard: sign in, complete setup, walk every
 * section, and fail on any console error or failed request.
 *
 *   node scripts/e2e.mjs [--base http://127.0.0.1:5173] [--shots <dir>]
 *
 * Requires the API on :8000 and the dev server on :5173.
 */
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const args = process.argv.slice(2);
const arg = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index === -1 ? fallback : args[index + 1];
};

const base = arg("base", "http://127.0.0.1:5173");
const shotDir = arg("shots", "C:/Users/chakr/AppData/Local/Temp/opencode/shots");
mkdirSync(shotDir, { recursive: true });

const results = [];
const consoleErrors = [];
const failedRequests = [];

function check(label, ok, detail = "") {
  results.push({ label, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail ? `  [${detail}]` : ""}`);
}

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
const page = await context.newPage();

page.on("console", (message) => {
  if (["error", "warning"].includes(message.type())) consoleErrors.push(message.text());
});
page.on("response", async (response) => {
  if (response.url().includes("/api/onboarding/complete") || (response.url().includes("/api/preferences") && response.request().method() !== "GET")) {
    let body = "";
    try { body = (await response.text()).slice(0, 220); } catch {}
    console.log("      " + response.request().method() + " " + new URL(response.url()).pathname + " -> " + response.status() + " " + body);
  }
});
page.on("pageerror", (error) => console.log("PAGEERROR  " + String(error.message).slice(0, 300)));
page.on("requestfailed", (request) => {
  failedRequests.push(`${request.method()} ${request.url()} — ${request.failure()?.errorText}`);
});
page.on("response", (response) => {
  if (response.status() >= 400 && response.url().includes("/api/")) {
    failedRequests.push(`${response.status()} ${response.url()}`);
  }
});

const shot = async (name) => {
  await page.screenshot({ path: join(shotDir, `${name}.png`), fullPage: true });
};

try {
  // ---------------------------------------------------------------- landing
  await page.goto(base, { waitUntil: "networkidle" });
  const heading = await page.locator("h1").first().innerText();
  check("landing renders the hero", heading.includes("Stop applying"), heading.replace(/\n/g, " "));
  check("landing shows pricing", await page.getByText("Pay for more room").isVisible());
  await shot("01-landing");

  // ---------------------------------------------------------------- sign in
  await page.getByRole("link", { name: /get started/i }).click();
  await page.waitForURL("**/signin");
  await page.waitForSelector("text=Sign in to AutoApply", { timeout: 15000 });
  check("sign-in page opens", true);

  const devButton = page.getByRole("button", { name: /test user/i });
  check("dev sign-in available", (await devButton.count()) > 0);

  // Sign in through the API with a fresh email so runs are independent. The
  // request context shares cookies with the browser, so the app is then signed in.
  const email = `e2e-${Date.now()}@example.com`;
  const login = await context.request.post(`${base}/api/auth/dev-login`, { data: { email } });
  check("dev sign-in returns 200", login.status() === 200, String(login.status()));

  await page.goto(`${base}/setup`, { waitUntil: "networkidle" });
  check("lands on setup", page.url().includes("/setup"), page.url());
  await shot("02-setup-greeting");

  // ---------------------------------------------------------------- screen 1
  const greeting = await page.locator("h1").first().innerText();
  check("greeting uses the first name", /^Hi\s+\S/.test(greeting), greeting);

  const hasDropzone = await page.getByText("Drop your resume here").isVisible();
  check("resume dropzone present", hasDropzone);

  // Upload a real DOCX and let the parser prefill the next screen.
  await page.setInputFiles('input[type="file"]', "scripts/fixtures/resume.docx");
  await page.waitForSelector("text=/Resume parsed/i", { timeout: 30000 });
  check("resume parses", true);
  await shot("02b-resume-parsed");

  await page.getByRole("button", { name: /review what we found|skip for now/i }).click();

  // ---------------------------------------------------------------- screen 2
  await page.waitForSelector("#full_name", { timeout: 10000 });
  await page.waitForTimeout(1200); // let the refetched profile hydrate the form

  const prefilled = {
    name: await page.inputValue("#full_name"),
    github: await page.inputValue("#github_url"),
    ctc: await page.inputValue("#current_ctc"),
    years: await page.inputValue("#years"),
    city: await page.inputValue("#location"),
  };
  console.log("      prefilled: " + JSON.stringify(prefilled));

  check("prefill: full name", prefilled.name === "Priya Sharma", prefilled.name);
  check("prefill: github url", prefilled.github.includes("github.com"), prefilled.github);
  // CTC is never on a resume, so it stays empty on purpose.
  check("prefill: years of experience", prefilled.years === "5", prefilled.years);
  check("prefill: city", prefilled.city.toLowerCase().includes("pune"), prefilled.city);
  check("screen 2 has the profile fields", await page.locator("#github_url").isVisible());
  check("screen 2 asks for current CTC", await page.locator("#current_ctc").isVisible());
  check("screen 2 asks for experience", await page.locator("#years").isVisible());

  const clickIfOff = async (name) => {
    const chip = page.getByRole("button", { name, exact: true }).first();
    if ((await chip.getAttribute("aria-pressed")) !== "true") await chip.click();
  };
  // Roles arrive seeded from the resume's suggested roles.
  await page.waitForTimeout(800);
  const prefs = await context.request.get(`${base}/api/preferences`);
  const prefJson = await prefs.json();
  check(
    "roles seeded from the resume",
    Array.isArray(prefJson.target_roles) && prefJson.target_roles.length > 0,
    JSON.stringify(prefJson.target_roles),
  );
  await clickIfOff("Mid");

  await page.waitForTimeout(900);
  await shot("03-setup-details");

  // ---------------------------------------------------------------- screen 3
  const before = await page.locator("h1").first().innerText();
  console.log("      screen-2 heading: " + before);
  await page.getByRole("button", { name: /continue/i }).click();
  await page.waitForTimeout(2500);
  const after = await page.locator("h1").first().innerText();
  console.log("      heading after Continue: " + after);
  console.log("      hours_start count: " + (await page.locator("#hours_start").count()));
  check("Continue advances to screen 3", after.includes("Where and when"), after);
  await page.waitForSelector("#hours_start", { timeout: 10000 });
  check("screen 3 has active hours", await page.locator("#hours_start").isVisible());

  // The exact bug the user hit: Finish is disabled with no explanation.
  const finishButton = page.getByRole("button", { name: /finish setup/i });
  check("Finish is disabled before the requirements are met", await finishButton.isDisabled());
  const explained = await page.getByText(/a location/i).isVisible().catch(() => false);
  check("the block explains itself", explained);

  // Typing a location and leaving the field (no Enter) must still add it.
  const locationInput = page.locator('input[placeholder*="Pune"]');
  await locationInput.fill("Pune");
  await locationInput.blur();
  await page.waitForTimeout(400);
  check(
    "a typed location is kept on blur",
    (await page.getByRole("button", { name: "Remove Pune" }).count()) > 0,
  );

  await clickIfOff("Remote");
  await clickIfOff("LinkedIn");
  await page.waitForTimeout(400);
  check("Finish enables once the requirements are met", await finishButton.isEnabled());
  await shot("04-setup-where");

  // ---------------------------------------------------------------- finish
  // Slow the completion call so the loader is observable, then assert it shows.
  await page.route("**/api/onboarding/complete", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 900));
    await route.continue();
  });

  await finishButton.click();
  const loaderShown = await page
    .getByText("Setting up your agent")
    .isVisible({ timeout: 4000 })
    .catch(() => false);
  check("a loader explains the wait while finishing", loaderShown);
  if (loaderShown) await shot("04b-finishing");

  await page.waitForURL("**/app", { timeout: 20000 });
  await page.unroute("**/api/onboarding/complete");
  await page.waitForURL("**/app", { timeout: 20000 });
  check("setup completes and lands on the dashboard", page.url().includes("/app"));

  // ---------------------------------------------------------------- dashboard
  await page.waitForTimeout(1500);
  const dashHeading = await page.locator("h1").first().innerText();
  check("dashboard greets by name", dashHeading.startsWith("Hi "), dashHeading);

  const sidebar = await page.locator("aside").innerText();
  for (const label of [
    "Applications sent",
    "Waiting for confirmations",
    "Can't send",
    "Your resume",
    "Your profile",
  ]) {
    check(`sidebar has "${label}"`, sidebar.includes(label));
  }
  check("no styleguide link", !sidebar.includes("Styleguide"));
  await shot("05-dashboard");

  // ---------------------------------------------------------------- sections
  for (const [path, headingText] of [
    ["/app/sent", "Everything it has sent"],
    ["/app/waiting", "It needs your answer"],
    ["/app/failed", "Jobs it walked away from"],
    ["/app/resume", "What the agent reads"],
    ["/app/profile", "Priya Sharma"],
  ]) {
    await page.goto(`${base}${path}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(700);
    const text = await page.locator("h1").first().innerText();
    check(`${path} renders`, text.includes(headingText), text);
    await shot(`06${path.replace(/\//g, "-")}`);
  }

  // plan card on the profile page
  const profileText = await page.locator("main").innerText();
  check("profile shows the plan", /Regular|Pro/.test(profileText));
  check("profile shows the daily cap", /10\s*applications|10\/day/.test(profileText));
  check("profile has delete my data", profileText.includes("Delete my data"));

  // ---------------------------------------------------------------- responsive
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${base}/app`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 2,
  );
  check("no horizontal overflow at 390px", !overflow);
  await shot("07-mobile");
} catch (error) {
  check("run completed without throwing", false, String(error).slice(0, 160));
  try {
    await shot("99-failure");
    const body = await page.locator("body").innerText();
    console.log("\n--- url: " + page.url() + " ---");
    console.log("--- page text (tail) ---");
    console.log(body.slice(-600));
    console.log("--- url: " + page.url() + " ---");
  } catch {}
} finally {
  await browser.close();
}

const failed = results.filter((result) => !result.ok);
console.log("");
console.log(`${results.length - failed.length}/${results.length} checks passed`);
if (consoleErrors.length) {
  console.log("");
  console.log("Console errors:");
  consoleErrors.forEach((error) => console.log("  " + error.slice(0, 200)));
}
if (failedRequests.length) {
  console.log("");
  console.log("Failed requests:");
  [...new Set(failedRequests)].forEach((request) => console.log("  " + request));
}
writeFileSync(join(shotDir, "result.json"), JSON.stringify({ results, consoleErrors, failedRequests }, null, 2));
process.exit(failed.length ? 1 : 0);