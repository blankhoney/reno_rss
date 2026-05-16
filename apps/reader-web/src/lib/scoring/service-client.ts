import { getConfig } from "@/lib/config";

export type ScoreServiceResponse = {
  ok: boolean;
  entryId?: number;
  score?: number;
  cached?: boolean;
  error?: string;
};

export function buildScoringServiceUrl(baseUrl: string, path: string): string {
  const url = new URL(path.replace(/^\/+/, ""), baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
  return url.toString();
}

export function buildScoringServiceAuthHeader(
  username: string | undefined,
  password: string | undefined,
): string | undefined {
  if (!username || !password) return undefined;
  return `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`;
}

export function parseScoreRequestBody(input: unknown): { force: boolean } {
  if (input !== null && typeof input === "object" && !Array.isArray(input)) {
    const force = (input as Record<string, unknown>).force;
    if (typeof force === "boolean") return { force };
  }
  return { force: true };
}

export async function scoreEntryWithService(
  entryId: number,
  force: boolean,
): Promise<ScoreServiceResponse> {
  const config = getConfig();
  const auth = buildScoringServiceAuthHeader(
    config.SCORING_SERVICE_USERNAME,
    config.SCORING_SERVICE_PASSWORD,
  );
  const response = await fetch(buildScoringServiceUrl(config.SCORING_SERVICE_URL, "/internal/score-entry"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(auth ? { Authorization: auth } : {}),
    },
    body: JSON.stringify({ entryId, force }),
    cache: "no-store",
    signal: AbortSignal.timeout(60_000),
  });
  const body = (await response.json().catch(() => null)) as ScoreServiceResponse | null;
  if (!response.ok) {
    return {
      ok: false,
      entryId,
      error: typeof body?.error === "string" ? body.error : `score_service_${response.status}`,
    };
  }
  return body ?? { ok: false, entryId, error: "score_service_invalid_response" };
}
