import { getConfig } from "../config";

export type WebSearchResult = {
  title: string;
  url: string;
  snippet: string;
};

export type WebSearchStatus = "disabled" | "not_configured" | "searched" | "no_results" | "failed";

export type WebSearchOutcome = {
  status: WebSearchStatus;
  results: WebSearchResult[];
};

type BraveWebResult = {
  title?: string;
  url?: string;
  description?: string;
  snippet?: string;
};

export async function searchWeb(query: string): Promise<WebSearchResult[]> {
  return (await searchWebWithStatus(query)).results;
}

export async function searchWebWithStatus(query: string): Promise<WebSearchOutcome> {
  const config = getConfig();
  const provider = config.WEB_SEARCH_PROVIDER;
  const apiKey = config.WEB_SEARCH_API_KEY;

  if (provider !== "brave") {
    return { status: "not_configured", results: [] };
  }
  if (apiKey === undefined || apiKey.trim().length === 0) {
    return { status: "not_configured", results: [] };
  }

  const url = new URL("https://api.search.brave.com/res/v1/web/search");
  url.searchParams.set("q", query);
  url.searchParams.set("count", "5");

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method: "GET",
      headers: {
        Accept: "application/json",
        "X-Subscription-Token": apiKey,
        "Cache-Control": "no-store",
        Pragma: "no-cache",
      },
    });
  } catch {
    return { status: "failed", results: [] };
  }

  if (!response.ok) {
    return { status: "failed", results: [] };
  }

  const dataUnknown: unknown = await response.json().catch(() => null);

  function pickResults(payload: unknown): BraveWebResult[] {
    if (payload === null || typeof payload !== "object") return [];
    const webField = Reflect.get(payload, "web") as unknown;
    if (webField === null || typeof webField !== "object") return [];
    const resultsField = Reflect.get(webField, "results") as unknown;
    return Array.isArray(resultsField)
      ? (resultsField.filter((r) => r !== null && typeof r === "object") as BraveWebResult[])
      : [];
  }

  function textField(value: unknown): string {
    if (typeof value === "string") return value;
    return "";
  }

  const results = pickResults(dataUnknown).map((item) => {
    const snippet = textField(item.snippet).trim() || textField(item.description).trim();
    return {
      title: textField(item.title).trim(),
      url: textField(item.url).trim(),
      snippet,
    };
  });

  return {
    status: results.length > 0 ? "searched" : "no_results",
    results,
  };
}
