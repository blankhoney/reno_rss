"use client";

import { useEffect, useState } from "react";
import type { Article } from "@/lib/articles/types";
import { createThinkTagFilter, extractOpenAICompatibleEventText } from "@/lib/agent/stream";
import type { DimensionKey } from "@/lib/scoring/repository";
import { ScoreBadge } from "./ScoreBadge";

const DIMENSION_ROWS: { key: DimensionKey | "overall"; label: string }[] = [
  { key: "overall", label: "总分" },
  { key: "importance", label: "重要性" },
  { key: "usefulness", label: "实用性" },
  { key: "timeliness", label: "时效" },
  { key: "depth", label: "深度" },
  { key: "technical_value", label: "技术价值" },
  { key: "business_value", label: "商业价值" },
  { key: "trend_value", label: "趋势价值" },
];

function htmlToText(html: string): string {
  const element = document.createElement("div");
  element.innerHTML = html;
  return (element.textContent ?? element.innerText ?? "").replace(/\s+/g, " ").trim();
}

function articleContextText(article: Article): string {
  const body = htmlToText(article.contentHtml);
  const parts = [
    `标题：${article.title}`,
    `链接：${article.url}`,
    article.score?.reason ? `评分理由：${article.score.reason}` : "",
    body,
  ].filter((part) => part.trim().length > 0);
  return parts.join("\n\n").slice(0, 20000);
}

function selectedTextFromPage(): string | undefined {
  const text = window.getSelection()?.toString().trim();
  return text && text.length > 0 ? text : undefined;
}

function appendAgentStreamChunk(
  chunk: string,
  pending: string,
  thinkFilter: ReturnType<typeof createThinkTagFilter>,
  append: (text: string) => void,
): string {
  const combined = pending + chunk;
  const events = combined.split(/\r?\n\r?\n/);
  const nextPending = events.pop() ?? "";

  for (const event of events) {
    const dataLines = event
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice("data:".length).trimStart());

    if (dataLines.length === 0) {
      append(thinkFilter.push(event));
      continue;
    }

    for (const data of dataLines) {
      append(thinkFilter.push(extractOpenAICompatibleEventText(data)));
    }
  }

  return nextPending;
}

export function ArticleReader({ article }: { article: Article | null }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [agentError, setAgentError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isAsking, setIsAsking] = useState(false);
  const [isScoring, setIsScoring] = useState(false);
  const [isProjecting, setIsProjecting] = useState(false);
  const [isTogglingCandidate, setIsTogglingCandidate] = useState(false);

  useEffect(() => {
    setQuestion("");
    setAnswer("");
    setAgentError(null);
    setActionMessage(null);
    setActionError(null);
  }, [article?.id]);

  if (article == null) {
    return (
      <article className="articleReaderPane" aria-label="文章内容">
        <div className="readerEmpty">
          <p className="readerEmptyTitle">未选择文章</p>
          <p className="readerEmptyHint">从左侧列表选择一篇以阅读正文与评分。</p>
        </div>
      </article>
    );
  }

  const score = article.score;
  const canAsk = question.trim().length > 0 && !isAsking;

  async function postArticleAction(path: string, body?: unknown) {
    if (article == null) return;
    setActionMessage(null);
    setActionError(null);
    const response = await fetch(`/api/articles/${article.id}/${path}`, {
      method: "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
      const data = (await response.json().catch(() => null)) as { error?: unknown } | null;
      throw new Error(typeof data?.error === "string" ? data.error : "操作失败");
    }
  }

  async function scoreNow() {
    setIsScoring(true);
    try {
      await postArticleAction("score", { force: true });
      setActionMessage("评分已更新");
      window.location.reload();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "评分失败");
    } finally {
      setIsScoring(false);
    }
  }

  async function toggleCandidate() {
    if (article == null) return;
    const wasStarred = article.starred;
    setIsTogglingCandidate(true);
    try {
      await postArticleAction("star");
      setActionMessage(wasStarred ? "已移出候选" : "已加入候选");
      window.location.reload();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "候选状态更新失败");
    } finally {
      setIsTogglingCandidate(false);
    }
  }

  async function enqueueProject() {
    setIsProjecting(true);
    try {
      await postArticleAction("project");
      setActionMessage("已立项");
      window.location.reload();
    } catch (error) {
      const message = error instanceof Error ? error.message : "立项失败";
      setActionError(message === "article_not_candidate" ? "请先加入候选再立项" : message);
    } finally {
      setIsProjecting(false);
    }
  }

  async function askAgent() {
    if (article == null || question.trim().length === 0) return;

    setIsAsking(true);
    setAnswer("");
    setAgentError(null);

    try {
      const response = await fetch("/api/agent/article-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          selectedText: selectedTextFromPage(),
          article: {
            title: article.title,
            url: article.url,
            contentText: articleContextText(article),
            scoreReason: article.score?.reason ?? "",
            tags: article.score?.tags ?? [],
          },
        }),
      });

      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { error?: unknown } | null;
        throw new Error(typeof body?.error === "string" ? body.error : "Agent request failed.");
      }

      const stream = response.body;
      if (stream == null) throw new Error("Agent response missing stream.");

      const reader = stream.getReader();
      const decoder = new TextDecoder();
      const thinkFilter = createThinkTagFilter();
      let pending = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        pending = appendAgentStreamChunk(
          decoder.decode(value, { stream: true }),
          pending,
          thinkFilter,
          (text) => {
            if (text.length > 0) setAnswer((current) => current + text);
          },
        );
      }

      const tail = decoder.decode();
      pending = appendAgentStreamChunk(tail, pending, thinkFilter, (text) => {
        if (text.length > 0) setAnswer((current) => current + text);
      });
      if (pending.trim().length > 0) {
        appendAgentStreamChunk("\n\n", pending, thinkFilter, (text) => {
          if (text.length > 0) setAnswer((current) => current + text);
        });
      }
      const finalText = thinkFilter.flush();
      if (finalText.length > 0) setAnswer((current) => current + finalText);
    } catch (error) {
      setAgentError(error instanceof Error ? error.message : "Agent request failed.");
    } finally {
      setIsAsking(false);
    }
  }

  return (
    <article className="articleReaderPane" aria-label="文章内容">
      <header className="readerHeader">
        <div className="readerToolbar" role="toolbar" aria-label="阅读操作">
          <a
            className="readerToolbarBtn readerToolbarBtnPrimary"
            href={article.url}
            target="_blank"
            rel="noreferrer"
          >
            打开原文
          </a>
          <button type="button" className="readerToolbarBtn" disabled>
            专注阅读
          </button>
          <button
            type="button"
            className="readerToolbarBtn"
            disabled={isScoring}
            onClick={() => void scoreNow()}
          >
            {isScoring ? "评分中" : "实时评分"}
          </button>
          <button
            type="button"
            className="readerToolbarBtn"
            disabled={isTogglingCandidate}
            onClick={() => void toggleCandidate()}
          >
            {article.starred ? "移出候选" : "加入候选"}
          </button>
          <button
            type="button"
            className="readerToolbarBtn"
            disabled={isProjecting}
            onClick={() => void enqueueProject()}
          >
            {isProjecting ? "立项中" : "立项"}
          </button>
        </div>
        {actionMessage ? <p className="readerActionMessage">{actionMessage}</p> : null}
        {actionError ? <p className="readerActionError">{actionError}</p> : null}
        <h2 className="readerTitle">{article.title}</h2>
      </header>

      <section className="scoreSection" aria-label="评分">
        <div className="scoreGrid">
          {DIMENSION_ROWS.map((row) => {
            const value =
              row.key === "overall"
                ? (score?.overall ?? null)
                : (score?.dimensions[row.key] ?? null);
            return <ScoreBadge key={row.key} label={row.label} value={value} />;
          })}
        </div>
        <p className="scoreReason">
          <span className="scoreReasonLabel">理由</span>
          {score?.reason?.trim()
            ? score.reason
            : "暂无评分说明（可能没有对应评分记录）。"}
        </p>
      </section>

      <section className="agentPanel" aria-label="当前文章问答">
        <div className="agentHeader">
          <h3 className="agentTitle">文章问答</h3>
          <button
            type="button"
            className="readerToolbarBtn readerToolbarBtnPrimary"
            disabled={!canAsk}
            onClick={() => void askAgent()}
          >
            {isAsking ? "生成中" : "询问"}
          </button>
        </div>
        <textarea
          className="agentQuestion"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="问当前文章..."
          rows={3}
        />
        {agentError != null ? <p className="agentError">{agentError}</p> : null}
        {answer.trim().length > 0 ? <pre className="agentAnswer">{answer}</pre> : null}
      </section>

      <div
        className="articleContent content"
        dangerouslySetInnerHTML={{ __html: article.contentHtml }}
      />
    </article>
  );
}
