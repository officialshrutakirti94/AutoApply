import type { Application, ApplicationStatus } from "@/lib/api";

/**
 * The three buckets the dashboard is built around.
 *
 * `needs_attention` is split by *why* it stopped, because the two halves need
 * completely different things from the user:
 *
 *   waiting - the agent would not answer a question on its own. It is waiting for
 *             the user to confirm an answer, and the application can still be sent.
 *   cantSend - structural dead ends (external site, already applied, CAPTCHA...).
 *             Nothing for the user to do, so it is only informational.
 */
export type Bucket = "sent" | "waiting" | "preferred" | "cantSend";

const QUESTION_REASONS = new Set([
  "sensitive_question",
  "unknown_question",
  "low_confidence",
]);

export function bucketOf(application: Application): Bucket {
  if (application.status === "applied" || application.status === "dry_run") return "sent";
  if (
    application.status === "needs_attention" &&
    QUESTION_REASONS.has(application.reason ?? "")
  ) {
    return "waiting";
  }
  // Applies on the company's own site: the user does this one by hand, so it gets
  // its own inbox instead of being buried in "can't send".
  if (application.status === "skipped" && application.reason === "external_redirect") {
    return "preferred";
  }
  return "cantSend";
}

export function split(applications: Application[]) {
  const sent: Application[] = [];
  const waiting: Application[] = [];
  const preferred: Application[] = [];
  const cantSend: Application[] = [];

  for (const application of applications) {
    // Resolved items are archived: they belong in no bucket.
    if (application.status === "resolved") continue;
    const bucket = bucketOf(application);
    if (bucket === "sent") sent.push(application);
    else if (bucket === "waiting") waiting.push(application);
    else if (bucket === "preferred") preferred.push(application);
    else cantSend.push(application);
  }

  return { sent, waiting, preferred, cantSend };
}

export function isQuestionBlocked(application: Application): boolean {
  return bucketOf(application) === "waiting";
}

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  applied: "Applied",
  dry_run: "Practice run",
  skipped: "Skipped",
  needs_attention: "Needs you",
  resolved: "Resolved",
  failed: "Failed",
};
