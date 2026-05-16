import type { ArticleContentStatus } from "@/lib/articles/types";

export type ArticleAgentArticle = {
  title: string;
  url: string;
  contentText: string;
  contentStatus: ArticleContentStatus;
  scoreReason: string;
  tags: string[];
};

export type BuildArticleAgentMessagesInput = {
  question: string;
  article: ArticleAgentArticle;
  selectedText?: string;
};

export type AgentChatMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};

const SYSTEM_PROMPT = [
  "你是 RSS 阅读器里的当前文章答疑助手，只能基于给定材料与用户问题作答。",
  "输出必须是中文，并严格使用下列 Markdown 小节标题（可按需保留空内容，但不要省略小节标题行）：",
  "## 结论",
  "## 依据",
  "## 引用",
  "## 不确定点",
  "## 行动建议",
  "不要输出思考过程、草稿、隐藏的推理链条或 XML/JSON 格式的内部标签。",
  "严禁输出 <think>、</think> 或其中的任何内容。",
  "如果正文状态是 RSS 片段，必须在“不确定点”说明材料可能不完整，不要假装已经联网或读取完整原文。",
  "“引用”中优先引用正文句子；若没有合适引用可以写“无”。",
].join("\n");

export function buildArticleAgentMessages(input: BuildArticleAgentMessagesInput): AgentChatMessage[] {
  const { question, article, selectedText } = input;
  const parts: string[] = [];

  parts.push(`## 用户问题\n${question.trim()}`);

  if (selectedText != null && selectedText.trim().length > 0) {
    parts.push(`## 用户选中文本\n${selectedText.trim()}`);
  }

  parts.push(
    [
      "## 文章元数据",
      `标题：${article.title}`,
      `链接：${article.url}`,
      `正文状态：${article.contentStatus === "partial" ? "RSS 片段，可能不是完整正文" : "完整或较完整正文"}`,
      `评分理由（系统）：${article.scoreReason}`,
      `标签：${article.tags.length > 0 ? article.tags.join(", ") : "（无）"}`,
    ].join("\n"),
  );

  parts.push(`## 文章正文\n${article.contentText}`);

  if (article.contentStatus === "partial") {
    parts.push("## 内容限制\n当前只提供 RSS 片段、文章元数据和评分信息；未联网搜索，也未保证读取到完整原文。");
  }

  const userPayload = parts.join("\n\n");

  return [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user", content: userPayload },
  ];
}
