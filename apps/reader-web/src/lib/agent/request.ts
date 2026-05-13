export const ARTICLE_AGENT_LIMITS = {
  question: 1_000,
  selectedText: 5_000,
  contentText: 20_000,
} as const;

export type ArticleAgentRequest = {
  question: string;
  selectedText?: string;
  article: {
    title: string;
    url: string;
    contentText: string;
    scoreReason: string;
    tags: string[];
  };
};

export type ArticleAgentRequestParseResult =
  | { ok: true; value: ArticleAgentRequest }
  | { ok: false; error: string };

export function parseArticleAgentRequest(parsed: unknown): ArticleAgentRequestParseResult {
  if (parsed === null || typeof parsed !== "object") {
    return { ok: false, error: "Invalid JSON body" };
  }

  const body = parsed as Record<string, unknown>;
  const question = body.question;

  if (typeof question !== "string" || question.trim().length === 0) {
    return { ok: false, error: "Missing or invalid question" };
  }
  if (question.length > ARTICLE_AGENT_LIMITS.question) {
    return { ok: false, error: "Question is too long" };
  }

  const articleRaw = body.article;
  if (articleRaw === null || typeof articleRaw !== "object") {
    return { ok: false, error: "Missing or invalid article" };
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
    return { ok: false, error: "Invalid article payload" };
  }
  if (contentText.length > ARTICLE_AGENT_LIMITS.contentText) {
    return { ok: false, error: "Article content is too long" };
  }

  const selectedText =
    typeof body.selectedText === "string" && body.selectedText.trim().length > 0
      ? body.selectedText
      : undefined;
  if (
    selectedText !== undefined &&
    selectedText.length > ARTICLE_AGENT_LIMITS.selectedText
  ) {
    return { ok: false, error: "Selected text is too long" };
  }

  return {
    ok: true,
    value: {
      question,
      selectedText,
      article: {
        title,
        url: urlField,
        contentText,
        scoreReason,
        tags: tagsUnknown as string[],
      },
    },
  };
}
