import assert from "node:assert/strict";
import test from "node:test";
import { addVisitedJobId, mergeVisitedJobIds } from "./job-queue.ts";

test("visited job IDs from the run survive content-script navigation", () => {
  const visited = mergeVisitedJobIds(["current-page-job"], ["first-job", "second-job"]);

  assert.deepEqual([...visited], ["current-page-job", "first-job", "second-job"]);
});

test("visited job IDs are deduplicated without dropping earlier jobs", () => {
  const visited = Array.from({ length: 500 }, (_, index) => `job-${index}`);
  const updated = addVisitedJobId(visited, "job-500");

  assert.equal(updated.length, 501);
  assert.equal(addVisitedJobId(updated, "job-0"), updated);
});
