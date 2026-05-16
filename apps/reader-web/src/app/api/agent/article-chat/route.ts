import { buildArticleAgentMessages } from "@/lib/agent/prompt";
import { streamMinimaxChat } from "@/lib/agent/minimax";
import { parseArticleAgentRequest } from "@/lib/agent/request";
import { cleanOpenAICompatibleSseStream } from "@/lib/agent/stream";
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
  });

  try {
    const upstream = await streamMinimaxChat(messages);
    return new Response(cleanOpenAICompatibleSseStream(upstream), {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Agent-Search-Status": "disabled",
        "X-Agent-Search-Count": "0",
      },
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Upstream agent request failed.";
    return Response.json({ error: message }, { status: 502 });
  }
}
