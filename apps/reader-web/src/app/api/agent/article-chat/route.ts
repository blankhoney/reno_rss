import { buildArticleAgentMessages, shouldUseWebSearch } from "@/lib/agent/prompt";
import { streamMinimaxChat } from "@/lib/agent/minimax";
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

  if (parsed === null || typeof parsed !== "object") {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const body = parsed as Record<string, unknown>;
  const question = body.question;

  if (typeof question !== "string" || question.trim().length === 0) {
    return Response.json({ error: "Missing or invalid question" }, { status: 400 });
  }

  const articleRaw = body.article;
  if (articleRaw === null || typeof articleRaw !== "object") {
    return Response.json({ error: "Missing or invalid article" }, { status: 400 });
  }

  const article = articleRaw as Record<string, unknown>;
  const title = article.title;
  const urlField = article.url;
  const contentText = article.contentText;
  const scoreReason = article.scoreReason;
  const tagsUnknown = article.tags;

  if (
    typeof title !== "string" ||
    title.trim().length === 0 ||
    typeof urlField !== "string" ||
    urlField.trim().length === 0 ||
    typeof contentText !== "string" ||
    typeof scoreReason !== "string" ||
    !Array.isArray(tagsUnknown) ||
    !tagsUnknown.every((t) => typeof t === "string")
  ) {
    return Response.json({ error: "Invalid article payload" }, { status: 400 });
  }

  const selectedText =
    typeof body.selectedText === "string" && body.selectedText.trim().length > 0
      ? body.selectedText
      : undefined;

  const tags = tagsUnknown as string[];

  const queryForSearch = `${question} ${title}`;

  const searchResults = shouldUseWebSearch(question) ? await searchWeb(queryForSearch) : [];

  const messages = buildArticleAgentMessages({
    question,
    article: {
      title,
      url: urlField,
      contentText,
      scoreReason,
      tags,
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
