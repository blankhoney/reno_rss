import { buildArticleAgentMessages, shouldUseWebSearch } from "@/lib/agent/prompt";
import { streamMinimaxChat } from "@/lib/agent/minimax";
import { parseArticleAgentRequest } from "@/lib/agent/request";
import { cleanOpenAICompatibleSseStream } from "@/lib/agent/stream";
import { searchWebWithStatus, type WebSearchOutcome } from "@/lib/agent/webSearch";
import { getConfig } from "@/lib/config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  getConfig();

  let parsed: unknown;
  try {
    parsed = await request.json();
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const parsedRequest = parseArticleAgentRequest(parsed);
  if (!parsedRequest.ok) {
    return Response.json({ error: parsedRequest.error }, { status: 400 });
  }
  const { question, article, selectedText } = parsedRequest.value;
  const queryForSearch = `${question} ${article.title}`;

  const searchOutcome: WebSearchOutcome = shouldUseWebSearch(question, article.contentStatus)
    ? await searchWebWithStatus(queryForSearch)
    : { status: "disabled", results: [] };

  const messages = buildArticleAgentMessages({
    question,
    article: {
      title: article.title,
      url: article.url,
      contentText: article.contentText,
      contentStatus: article.contentStatus,
      scoreReason: article.scoreReason,
      tags: article.tags,
    },
    selectedText,
    searchResults: searchOutcome.results,
    searchStatus: searchOutcome.status,
  });

  try {
    const upstream = await streamMinimaxChat(messages);
    return new Response(cleanOpenAICompatibleSseStream(upstream), {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Agent-Search-Status": searchOutcome.status,
        "X-Agent-Search-Count": String(searchOutcome.results.length),
      },
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Upstream agent request failed.";
    return Response.json({ error: message }, { status: 502 });
  }
}
