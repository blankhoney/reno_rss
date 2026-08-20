import type { ArticleAnnotationAnchor } from "./annotationAnchor";

export const ANNOTATION_CREATE_JOURNAL_VERSION = 1;
export const ANNOTATION_CREATE_JOURNAL_TTL_MS = 24 * 60 * 60_000;
const PREFIX = "ai-reader:annotation-create:v1:";

export type AnnotationCreatePayload = {
  content: string;
  selectedText: string | null;
  type: string;
  color: string | null;
  tags: string[];
  anchor?: ArticleAnnotationAnchor;
};

export type AnnotationCreateMetadata = Pick<AnnotationCreatePayload, "color" | "tags">;

export function annotationCreateMetadataChanged(
  payload: AnnotationCreatePayload,
  desired: AnnotationCreateMetadata,
): boolean {
  return (
    payload.color !== desired.color ||
    payload.tags.length !== desired.tags.length ||
    payload.tags.some((tag, index) => tag !== desired.tags[index])
  );
}

export type AnnotationCreateJournalEntry = {
  storageVersion: 1;
  operationKind: "note" | "selection";
  idempotencyKey: string;
  ownerId: string;
  articleId: number;
  createdAtEpochMs: number;
  selectionRevision: number;
  draftRevision?: number;
  rawDraft?: string;
  payload: AnnotationCreatePayload;
};

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem" | "key" | "length">;

function browserStorage(): StorageLike | null {
  return typeof window === "undefined" ? null : window.sessionStorage;
}

function storageKey(entry: AnnotationCreateJournalEntry): string {
  return `${PREFIX}${entry.ownerId}:${entry.articleId}:${entry.operationKind}:${entry.idempotencyKey}`;
}

function isEntry(value: unknown): value is AnnotationCreateJournalEntry {
  if (value == null || typeof value !== "object") return false;
  const entry = value as Partial<AnnotationCreateJournalEntry>;
  const payload = entry.payload as Partial<AnnotationCreatePayload> | undefined;
  return (
    entry.storageVersion === ANNOTATION_CREATE_JOURNAL_VERSION &&
    (entry.operationKind === "note" || entry.operationKind === "selection") &&
    typeof entry.idempotencyKey === "string" &&
    typeof entry.ownerId === "string" &&
    Number.isInteger(entry.articleId) &&
    typeof entry.createdAtEpochMs === "number" &&
    Number.isInteger(entry.selectionRevision) &&
    payload != null &&
    typeof payload.content === "string" &&
    (payload.selectedText === null || typeof payload.selectedText === "string") &&
    typeof payload.type === "string" &&
    (payload.color === null || typeof payload.color === "string") &&
    Array.isArray(payload.tags) &&
    payload.tags.every((tag) => typeof tag === "string") &&
    (entry.operationKind !== "note" ||
      (Number.isInteger(entry.draftRevision) && typeof entry.rawDraft === "string"))
  );
}

export function persistAnnotationCreateJournalEntry(
  entry: AnnotationCreateJournalEntry,
  storage: StorageLike | null = browserStorage(),
): boolean {
  if (storage == null) return false;
  try {
    storage.setItem(storageKey(entry), JSON.stringify(entry));
    return true;
  } catch {
    return false;
  }
}

export function removeAnnotationCreateJournalEntry(
  entry: AnnotationCreateJournalEntry,
  storage: StorageLike | null = browserStorage(),
): void {
  if (storage == null) return;
  try {
    storage.removeItem(storageKey(entry));
  } catch {
    // The server operation remains safe to retry even if local cleanup fails.
  }
}

export function loadAnnotationCreateJournalEntries(
  ownerId: string,
  articleId: number,
  now = Date.now(),
  storage: StorageLike | null = browserStorage(),
): AnnotationCreateJournalEntry[] {
  if (storage == null) return [];
  const entries: AnnotationCreateJournalEntry[] = [];
  const keys: string[] = [];
  try {
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key?.startsWith(PREFIX)) keys.push(key);
    }
    for (const key of keys) {
      const raw = storage.getItem(key);
      let parsed: unknown;
      try {
        parsed = raw == null ? null : JSON.parse(raw);
      } catch {
        storage.removeItem(key);
        continue;
      }
      if (!isEntry(parsed)) {
        storage.removeItem(key);
        continue;
      }
      if (parsed.ownerId !== ownerId || now - parsed.createdAtEpochMs > ANNOTATION_CREATE_JOURNAL_TTL_MS) {
        storage.removeItem(key);
        continue;
      }
      if (parsed.articleId === articleId) entries.push(parsed);
    }
  } catch {
    return [];
  }
  return entries.sort((left, right) => left.createdAtEpochMs - right.createdAtEpochMs);
}

export function clearAllAnnotationCreateJournalEntries(
  storage: StorageLike | null = browserStorage(),
): void {
  if (storage == null) return;
  try {
    const keys: string[] = [];
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key?.startsWith(PREFIX)) keys.push(key);
    }
    for (const key of keys) storage.removeItem(key);
  } catch {
    // Logout must still clear the authenticated UI even if storage is unavailable.
  }
}
