export type ArticleAgentArticle = {
  title: string;
  url: string;
  contentText: string;
  scoreReason: string;
  tags: string[];
};

export type ArticleAgentSearchResult = {
  title: string;
  url: string;
  snippet: string;
};

export type BuildArticleAgentMessagesInput = {
  question: string;
  article: ArticleAgentArticle;
  selectedText?: string;
  searchResults: ArticleAgentSearchResult[];
};

export type AgentChatMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};

const FRESHNESS_PATTERNS: RegExp[] = [
  /最新|是否最新|目前还|现在还|新版本|版本|版本号|changelog|release|releases|更新|EOL|弃用|deprecated|维护状况/,
  /推荐用吗|还推荐吗|现在还推荐|还值得吗|过时|近况|近况如何|近况怎样|近况怎么样|新闻|最新消息|官宣|发布公告|动向|竞品|替代品|融资|市场份额/,
  /公司|CEO|IPO|产品线|收购|宣布了/,
  /趋势|动态|舆情|热点/,
  /产品|发布会|路线图|roadmap|\bSKU\b|\bGA\b|\bpricing\b|\bproduct\b/im,
  /latest\s+version|breaking\s+changes|still\s+maintained|still\s+recommended|changelog|released|\bEOL\b|\bdeprecated\b|\bIPO\b|\bCEO\b|\bnews\b|\btrend(?:ing)?\b/i,
  /version\s+latest|freshness|up-?to-?date|product\s+(news|announcement)|company\s+(news|announcement)/i,
];

const SIMPLE_SUMMARY_PATTERNS: RegExp[] = [
  /总结这篇文章/,
  /概括这篇文章/,
  /这篇文章讲了什么/,
  /简述这篇文章/,
  /文章大意/,
  /^summarize\s+this\b/i,
  /^summary\b/i,
  /^tl;?dr\b/i,
];

export function shouldUseWebSearch(question: string): boolean {
  const q = question.trim();
  if (q.length === 0) return false;
  if (SIMPLE_SUMMARY_PATTERNS.some((p) => p.test(q))) return false;
  return FRESHNESS_PATTERNS.some((p) => p.test(q));
}

function formatSearchResultsBlock(results: ArticleAgentSearchResult[]): string {
  if (results.length === 0) {
    return "（无联网搜索结果；请主要依据下文文章与评分信息作答。）";
  }
  return results
    .map((r, i) => {
      return [`${i + 1}. ${r.title}`, `   链接：${r.url}`, `   摘要：${r.snippet}`].join("\n");
    })
    .join("\n\n");
}

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
  "若联网搜索结果与正文冲突，要明确标注不确定点并在“依据”中分别说明出处。",
  "“引用”中优先引用正文句子或搜索结果条目；若没有合适引用可以写“无”。",
].join("\n");

export function buildArticleAgentMessages(input: BuildArticleAgentMessagesInput): AgentChatMessage[] {
  const { question, article, selectedText, searchResults } = input;
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
      `评分理由（系统）：${article.scoreReason}`,
      `标签：${article.tags.length > 0 ? article.tags.join(", ") : "（无）"}`,
    ].join("\n"),
  );

  parts.push(`## 文章正文\n${article.contentText}`);

  parts.push(["## 联网搜索结果（若为空请忽略）", formatSearchResultsBlock(searchResults)].join("\n"));

  const userPayload = parts.join("\n\n");

  return [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user", content: userPayload },
  ];
}
