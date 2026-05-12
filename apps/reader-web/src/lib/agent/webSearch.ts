import { getConfig } from "../config";

export type WebSearchResult = {
  title: string;
  url: string;
  snippet: string;
};

type BraveWebResult = {
  title?: string;
  url?: string;
  description?: string;
  snippet?: string;
};

export async function searchWeb(query: string): Promise<WebSearchResult[]> {
  const config = getConfig();
  const provider = config.WEB_SEARCH_PROVIDER;
  const apiKey = config.WEB_SEARCH_API_KEY;

  if (provider !== "brave") {
    return [];
  }
  if (apiKey === undefined || apiKey.trim().length === 0) {
    return [];
  }

  const url = new URL("https://api.search.brave.com/res/v1/web/search");
  url.searchParams.set("q", query);
  url.searchParams.set("count", "5");

  const response = await fetch(url.toString(), {
    method: "GET",
    headers: {
      Accept: "application/json",
      "X-Subscription-Token": apiKey,
      "Cache-Control": "no-store",
      Pragma: "no-cache",
    },
  });

  if (!response.ok) {
    return [];
  }

  const dataUnknown: unknown = await response.json();

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

  return pickResults(dataUnknown).map((item) => {
    const snippet = textField(item.snippet).trim() || textField(item.description).trim();
    return {
      title: textField(item.title).trim(),
      url: textField(item.url).trim(),
      snippet,
    };
  });
}
