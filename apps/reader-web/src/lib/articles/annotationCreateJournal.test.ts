import assert from "node:assert/strict";
import test from "node:test";
import {
  clearAllAnnotationCreateJournalEntries,
  loadAnnotationCreateJournalEntries,
  persistAnnotationCreateJournalEntry,
  removeAnnotationCreateJournalEntry,
  type AnnotationCreateJournalEntry,
} from "./annotationCreateJournal";

class MemoryStorage implements Storage {
  private values = new Map<string, string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

const entry: AnnotationCreateJournalEntry = {
  storageVersion: 1,
  operationKind: "note",
  idempotencyKey: "550e8400-e29b-41d4-a716-446655440000",
  ownerId: "ada",
  articleId: 42,
  createdAtEpochMs: 1000,
  selectionRevision: 2,
  draftRevision: 3,
  rawDraft: "draft",
  payload: {
    content: "note",
    selectedText: "quote",
    type: "annotation",
    color: "yellow",
    tags: ["tag"],
  },
};

test("journal round-trips owner-scoped operation and removes exact entry", () => {
  const storage = new MemoryStorage();
  assert.equal(persistAnnotationCreateJournalEntry(entry, storage), true);
  assert.deepEqual(loadAnnotationCreateJournalEntries("ada", 42, 1001, storage), [entry]);
  assert.deepEqual(loadAnnotationCreateJournalEntries("babbage", 42, 1001, storage), []);
  removeAnnotationCreateJournalEntry(entry, storage);
  assert.deepEqual(loadAnnotationCreateJournalEntries("ada", 42, 1001, storage), []);
});

test("journal drops corrupt, expired, and mismatched-owner entries", () => {
  const storage = new MemoryStorage();
  persistAnnotationCreateJournalEntry(entry, storage);
  storage.setItem("ai-reader:annotation-create:v1:bad", "not json");
  assert.deepEqual(loadAnnotationCreateJournalEntries("ada", 42, 1000 + 24 * 60 * 60_000 + 1, storage), []);
  assert.equal(storage.length, 0);
});

test("journal cleanup preserves unrelated session storage keys", () => {
  const storage = new MemoryStorage();
  storage.setItem("other-session-state", "keep");
  persistAnnotationCreateJournalEntry(entry, storage);
  clearAllAnnotationCreateJournalEntries(storage);
  assert.equal(storage.getItem("other-session-state"), "keep");
  assert.equal(storage.length, 1);
});
