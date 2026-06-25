import { apiGet, apiPost } from "./client";
import type { components } from "./generated/schema";

export type CandidateWindow = "today" | "last_3_days" | "custom";

export type AdminJob = {
  jobId: number;
  jobType: string;
  status: string;
};

export type ScoringBatchItem = {
  id: number;
  batchId: number;
  articleId: number;
  status: string;
  baseScoreId: number | null;
  error: string | null;
};

export type ScoringBatch = {
  id: number;
  name: string | null;
  status: string;
  triggerType: string;
  candidateWindow: CandidateWindow;
  articleCount: number;
  createdBy: string | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  items: ScoringBatchItem[];
};

export type CreateScoringBatchInput = {
  name?: string | null;
  candidateWindow: CandidateWindow;
  articleIds: number[];
};

export type StartedScoringJob = {
  batchId: number;
  jobId: number;
  status: string;
};

type AdminSyncResponse = {
  job_id: number;
  job_type: string;
  status: string;
};

type ApiScoringBatchItem = {
  id: number;
  batch_id: number;
  article_id: number;
  status: string;
  base_score_id: number | null;
  error: string | null;
};

type ApiScoringBatch = {
  id: number;
  name: string | null;
  status: string;
  trigger_type: string;
  candidate_window: CandidateWindow;
  article_count: number;
  created_by: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  items: ApiScoringBatchItem[];
};

type ApiScoringBatchResponse = {
  batch: ApiScoringBatch;
};

type ApiStartedScoringJob = {
  batch_id: number;
  job_id: number;
  status: string;
};

function scoringBatchFromApi(batch: ApiScoringBatch): ScoringBatch {
  return {
    id: batch.id,
    name: batch.name,
    status: batch.status,
    triggerType: batch.trigger_type,
    candidateWindow: batch.candidate_window,
    articleCount: batch.article_count,
    createdBy: batch.created_by,
    createdAt: batch.created_at,
    startedAt: batch.started_at,
    finishedAt: batch.finished_at,
    items: batch.items.map((item) => ({
      id: item.id,
      batchId: item.batch_id,
      articleId: item.article_id,
      status: item.status,
      baseScoreId: item.base_score_id,
      error: item.error,
    })),
  };
}

export async function enqueueAdminSync({ limit }: { limit: number }): Promise<AdminJob> {
  const body: components["schemas"]["SyncMinifluxRequest"] = { limit };
  const payload = await apiPost<AdminSyncResponse, components["schemas"]["SyncMinifluxRequest"]>(
    "/api/admin/sync",
    body,
  );
  return {
    jobId: payload.job_id,
    jobType: payload.job_type,
    status: payload.status,
  };
}

export async function createScoringBatch(input: CreateScoringBatchInput): Promise<ScoringBatch> {
  const body: components["schemas"]["CreateScoringBatchRequest"] = {
    name: input.name ?? null,
    candidate_window: input.candidateWindow,
    article_ids: input.articleIds,
  };
  const payload = await apiPost<
    ApiScoringBatchResponse,
    components["schemas"]["CreateScoringBatchRequest"]
  >("/api/admin/scoring-batches", body);
  return scoringBatchFromApi(payload.batch);
}

export async function getScoringBatch(batchId: number): Promise<ScoringBatch> {
  const payload = await apiGet<ApiScoringBatchResponse>(`/api/admin/scoring-batches/${batchId}`);
  return scoringBatchFromApi(payload.batch);
}

export async function startScoringBatch(batchId: number): Promise<StartedScoringJob> {
  const payload = await apiPost<ApiStartedScoringJob, undefined>(
    `/api/admin/scoring-batches/${batchId}/start`,
  );
  return {
    batchId: payload.batch_id,
    jobId: payload.job_id,
    status: payload.status,
  };
}
