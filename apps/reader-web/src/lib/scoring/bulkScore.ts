export type BulkScoreResult = {
  ok: boolean;
  entryId: number;
  error?: string;
};

export type BulkScoreSummary = {
  total: number;
  completed: number;
  succeeded: number;
  failed: number;
  results: BulkScoreResult[];
};

export async function scoreArticlesWithConcurrency(
  entryIds: number[],
  options: {
    limit: number;
    concurrency: number;
    scoreEntry: (entryId: number, force: boolean) => Promise<BulkScoreResult>;
    onProgress?: (summary: BulkScoreSummary) => void;
  },
): Promise<BulkScoreSummary> {
  const selectedIds = entryIds.slice(0, Math.max(0, options.limit));
  const workerCount = Math.max(1, Math.min(options.concurrency, selectedIds.length || 1));
  const results: BulkScoreResult[] = [];
  let nextIndex = 0;
  let completed = 0;
  let succeeded = 0;
  let failed = 0;

  function summary(): BulkScoreSummary {
    return {
      total: selectedIds.length,
      completed,
      succeeded,
      failed,
      results: [...results],
    };
  }

  async function runWorker() {
    while (nextIndex < selectedIds.length) {
      const entryId = selectedIds[nextIndex];
      nextIndex += 1;
      try {
        const result = await options.scoreEntry(entryId, true);
        results.push(result);
        if (result.ok) succeeded += 1;
        else failed += 1;
      } catch (error) {
        failed += 1;
        results.push({
          ok: false,
          entryId,
          error: error instanceof Error ? error.message : "score_failed",
        });
      } finally {
        completed += 1;
        options.onProgress?.(summary());
      }
    }
  }

  await Promise.all(Array.from({ length: workerCount }, () => runWorker()));
  return summary();
}
