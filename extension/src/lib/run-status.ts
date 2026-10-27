export function describeStep(status: string, reason?: string | null): string {
  if (reason === "external_redirect") {
    return "Added to Preferred — continuing to the next job.";
  }
  if (status === "continue") return "Filling the form…";
  if (status === "done") return "Job step complete — continuing the run.";
  if (status === "hitl") return `Needs you — ${(reason ?? "waiting").replace(/_/g, " ")}`;
  return `Stopped — ${(reason ?? "stopped").replace(/_/g, " ")}`;
}
