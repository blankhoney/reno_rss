import assert from "node:assert/strict";
import test from "node:test";
import {
  clearExactPendingSeq,
  ownsAnnotationLoad,
  ownsReviewAttempt,
  ownsSelectionCreateAttempt,
  type AnnotationLoadAttempt,
  type PendingReviewAttempt,
  type SelectionCreateAttempt,
} from "./annotationAsync";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

for (const mutation of ["create", "edit", "delete", "review"] as const) {
  test(`${mutation} success invalidates an older annotation GET`, async () => {
    const request = deferred<string[]>();
    const attempt: AnnotationLoadAttempt = { articleId: 7, requestSeq: 1, mutationEpoch: 0 };
    const owner = { mounted: true, articleId: 7, requestSeq: 1, mutationEpoch: 0 };
    const committed: string[][] = [];
    const settled = request.promise.then((items) => {
      if (ownsAnnotationLoad(attempt, owner)) committed.push(items);
    });
    owner.mutationEpoch += 1;
    request.resolve(["stale"]);
    await settled;
    assert.deepEqual(committed, []);
  });

  test(`${mutation} failure does not invalidate an otherwise current annotation GET`, async () => {
    const request = deferred<string[]>();
    const attempt: AnnotationLoadAttempt = { articleId: 7, requestSeq: 1, mutationEpoch: 0 };
    const owner = { mounted: true, articleId: 7, requestSeq: 1, mutationEpoch: 0 };
    const committed: string[][] = [];
    const settled = request.promise.then((items) => {
      if (ownsAnnotationLoad(attempt, owner)) committed.push(items);
    });
    request.resolve(["current"]);
    await settled;
    assert.deepEqual(committed, [["current"]]);
  });
}

test("later annotation GET wins when responses resolve out of order", async () => {
  const first = deferred<string>();
  const second = deferred<string>();
  const owner = { mounted: true, articleId: 7, requestSeq: 2, mutationEpoch: 0 };
  const committed: string[] = [];
  const firstAttempt = { articleId: 7, requestSeq: 1, mutationEpoch: 0 };
  const secondAttempt = { articleId: 7, requestSeq: 2, mutationEpoch: 0 };
  const waits = [
    first.promise.then((value) => ownsAnnotationLoad(firstAttempt, owner) && committed.push(value)),
    second.promise.then((value) => ownsAnnotationLoad(secondAttempt, owner) && committed.push(value)),
  ];
  second.resolve("new");
  first.resolve("old");
  await Promise.all(waits);
  assert.deepEqual(committed, ["new"]);
});

test("article ABA and unmount reject stale annotation load success and failure", () => {
  const oldA = { articleId: 7, requestSeq: 1, mutationEpoch: 0 };
  assert.equal(ownsAnnotationLoad(oldA, { mounted: true, articleId: 9, requestSeq: 2, mutationEpoch: 0 }), false);
  assert.equal(ownsAnnotationLoad(oldA, { mounted: true, articleId: 7, requestSeq: 3, mutationEpoch: 0 }), false);
  assert.equal(ownsAnnotationLoad(oldA, { mounted: false, articleId: 7, requestSeq: 1, mutationEpoch: 0 }), false);
});

test("selection ownership is exact and old finally cannot clear a new attempt", () => {
  const oldAttempt: SelectionCreateAttempt = { seq: 1, articleId: 7, selectionRevision: 10 };
  const newAttempt: SelectionCreateAttempt = { seq: 3, articleId: 7, selectionRevision: 11 };
  assert.equal(ownsSelectionCreateAttempt(oldAttempt, {
    mounted: true,
    articleId: 7,
    selectionRevision: 11,
    pending: newAttempt,
  }), false);
  assert.equal(clearExactPendingSeq(newAttempt.seq, oldAttempt.seq), newAttempt.seq);
  assert.equal(ownsSelectionCreateAttempt(newAttempt, {
    mounted: true,
    articleId: 7,
    selectionRevision: 11,
    pending: newAttempt,
  }), true);
});

test("selection revision cancellation synchronously permits the new attempt", () => {
  let sequence = 1;
  let pending: SelectionCreateAttempt | null = { seq: 1, articleId: 7, selectionRevision: 10 };
  let renderPending: number | null = 1;
  const nextRevision = 11;
  const cancelled = pending;
  pending = null;
  sequence += 1;
  renderPending = clearExactPendingSeq(renderPending, cancelled.seq);
  const next = { seq: ++sequence, articleId: 7, selectionRevision: nextRevision };
  pending = next;
  renderPending = next.seq;
  assert.deepEqual(pending, next);
  assert.equal(renderPending, 3);
  assert.equal(clearExactPendingSeq(renderPending, cancelled.seq), 3);
});

test("review duplicate entry and exact cleanup preserve the new busy attempt", () => {
  let sequence = 0;
  let pending: PendingReviewAttempt | null = null;
  let posts = 0;
  function start(id: number) {
    if (pending != null) return null;
    const attempt = { seq: ++sequence, id };
    pending = attempt;
    posts += 1;
    return attempt;
  }
  const first = start(41)!;
  start(41);
  assert.equal(posts, 1);
  pending = null;
  const next = start(42)!;
  assert.equal(ownsReviewAttempt(first, { mounted: true, pending }), false);
  assert.equal(clearExactPendingSeq(next.seq, first.seq), next.seq);
  assert.equal(ownsReviewAttempt(next, { mounted: true, pending }), true);
});

test("ordinary note and selection attempts remain independent", () => {
  const notePending = { seq: 1, snapshot: { articleId: 7 } };
  const selectionPending = { seq: 2, articleId: 7, selectionRevision: 4 };
  assert.notEqual(notePending, selectionPending);
  assert.equal(ownsSelectionCreateAttempt(selectionPending, {
    mounted: true,
    articleId: 7,
    selectionRevision: 4,
    pending: selectionPending,
  }), true);
});
