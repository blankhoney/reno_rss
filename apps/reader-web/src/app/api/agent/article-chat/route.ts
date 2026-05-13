import { buildArticleAgentMessages, shouldUseWebSearch } from "@/lib/agent/prompt";
import { streamMinimaxChat } from "@/lib/agent/minimax";
import { parseArticleAgentRequest } from "@/lib/agent/request";
import { searchWeb } from "@/lib/agent/webSearch";
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

  const searchResults = shouldUseWebSearch(question) ? await searchWeb(queryForSearch) : [];

  const messages = buildArticleAgentMessages({
    question,
    article: {
      title: article.title,
      url: article.url,
      contentText: article.contentText,
      scoreReason: article.scoreReason,
      tags: article.tags,
    },
    selectedText,
    searchResults,
  });

  try {
    const stream = await streamMinimaxChat(messages);
    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Upstream agent request failed.";
    return Response.json({ error: message }, { status: 502 });
  }
}
