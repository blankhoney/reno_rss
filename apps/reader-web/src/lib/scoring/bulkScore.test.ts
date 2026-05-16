import assert from "node:assert/strict";
import test from "node:test";
import { scoreArticlesWithConcurrency } from "./bulkScore";

test("scoreArticlesWithConcurrency scores only the current list prefix with force=true", async () => {
  const calls: Array<{ entryId: number; force: boolean }> = [];

  const result = await scoreArticlesWithConcurrency([1, 2, 3, 4], {
    limit: 2,
    concurrency: 3,
    scoreEntry: async (entryId, force) => {
      calls.push({ entryId, force });
      return { ok: true, entryId };
    },
  });

  assert.deepEqual(calls, [
    { entryId: 1, force: true },
    { entryId: 2, force: true },
  ]);
  assert.equal(result.total, 2);
  assert.equal(result.succeeded, 2);
  assert.equal(result.failed, 0);
});

test("scoreArticlesWithConcurrency limits concurrency and keeps partial failures", async () => {
  let active = 0;
  let maxActive = 0;
  const completed: number[] = [];

  const result = await scoreArticlesWithConcurrency([1, 2, 3, 4, 5], {
    limit: 5,
    concurrency: 3,
    scoreEntry: async (entryId) => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      await new Promise((resolve) => setTimeout(resolve, 5));
      active -= 1;
      completed.push(entryId);
      return entryId === 3
        ? { ok: false, entryId, error: "score_failed" }
        : { ok: true, entryId };
    },
  });

  assert.equal(maxActive, 3);
  assert.deepEqual(completed.sort((a, b) => a - b), [1, 2, 3, 4, 5]);
  assert.equal(result.succeeded, 4);
  assert.equal(result.failed, 1);
  assert.equal(result.results.find((item) => item.entryId === 3)?.ok, false);
});
