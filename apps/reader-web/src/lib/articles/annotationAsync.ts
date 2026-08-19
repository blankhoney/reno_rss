export type AnnotationLoadAttempt = {
  articleId: number;
  requestSeq: number;
  mutationEpoch: number;
};

export type AnnotationLoadOwner = AnnotationLoadAttempt & {
  mounted: boolean;
};

export type SelectionCreateAttempt = {
  seq: number;
  articleId: number;
  selectionRevision: number;
};

export type PendingReviewAttempt = {
  seq: number;
  id: number;
};

export function ownsAnnotationLoad(
  attempt: AnnotationLoadAttempt,
  current: AnnotationLoadOwner,
): boolean {
  return (
    current.mounted &&
    current.articleId === attempt.articleId &&
    current.requestSeq === attempt.requestSeq &&
    current.mutationEpoch === attempt.mutationEpoch
  );
}

export function ownsSelectionCreateAttempt(
  attempt: SelectionCreateAttempt,
  current: {
    mounted: boolean;
    articleId: number;
    selectionRevision: number;
    pending: SelectionCreateAttempt | null;
  },
): boolean {
  return (
    current.mounted &&
    current.articleId === attempt.articleId &&
    current.selectionRevision === attempt.selectionRevision &&
    current.pending?.seq === attempt.seq &&
    current.pending.articleId === attempt.articleId &&
    current.pending.selectionRevision === attempt.selectionRevision
  );
}

export function ownsReviewAttempt(
  attempt: PendingReviewAttempt,
  current: { mounted: boolean; pending: PendingReviewAttempt | null },
): boolean {
  return (
    current.mounted &&
    current.pending?.seq === attempt.seq &&
    current.pending.id === attempt.id
  );
}

export function clearExactPendingSeq(currentSeq: number | null, ownedSeq: number): number | null {
  return currentSeq === ownedSeq ? null : currentSeq;
}
