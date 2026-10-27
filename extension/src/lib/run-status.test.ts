import assert from "node:assert/strict";
import test from "node:test";
import { describeStep } from "./run-status.ts";

test("external applications are clearly reported as sent to Preferred", () => {
  assert.equal(
    describeStep("done", "external_redirect"),
    "Added to Preferred — continuing to the next job.",
  );
});

test("a completed job step is not described as a completed run", () => {
  assert.equal(describeStep("done"), "Job step complete — continuing the run.");
});
