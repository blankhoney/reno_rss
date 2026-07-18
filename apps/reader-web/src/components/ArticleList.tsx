"use client";

import { useEffect, useRef, useState } from "react";
import type { Article } from "@/lib/articles/types";
import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";
import { ScoreRing, tierLabel } from "./ScoreRing";
import { ArticleListSkeleton } from "./Skeleton";
import { SortMenu, type SortOption } from "./SortMenu";
import { FOCUS_ARTICLE_LIST_EVENT, isEditableKeyboardTarget } from "@/lib/commandPalette";
import Link from "next/link";

type ArticleListProps = {
  articles: Article[];
  currentModule: string;
  currentSort: ArticleSortId;
  currentLang: SummaryLangId;
  highlightArticleId?: number | null;
  pageIndex?: number;
  hasPrev?: boolean;
  hasNext?: boolean;
  isPaging?: boolean;
  isLoading?: boolean;
  onPrev?: () => void;
  onNext?: () => void;
  onSortChange?: (nextSort: ArticleSortId) => void;
  notice?: {
    title: string;
    body: string;
  };
};

const SORT_OPTIONS: SortOption[] = [
  { id: "default", label: "默认排序" },
  { id: "latest", label: "按最新" },
  { id: "score", label: "按总分" },
  { id: "technical", label: "按技术" },
  { id: "business", label: "按商业" },
  { id: "trend", label: "按趋势" },
];

function readHref(
  currentModule: string,
  currentSort: ArticleSortId,
  currentLang: SummaryLangId,
  articleId: number,
): string {
  const qs = new URLSearchParams({
    module: currentModule,
    sort: currentSort,
    lang: currentLang,
  });
  return `/read/${articleId}?${qs.toString()}`;
}

function articleSummary(
  article: Article,
  currentLang: SummaryLangId,
): { text: string; isEmpty: boolean } {
  const summary =
    currentLang === "original" ? article.summaryOriginal || article.summaryZh : article.summaryZh;
  const text = summary.trim();
  return text
    ? { text, isEmpty: false }
    : { text: "暂无摘要 — 评分完成后自动生成", isEmpty: true };
}

export function ArticleList({
  articles,
  currentModule,
  currentSort,
  currentLang,
  highlightArticleId = null,
  pageIndex = 0,
  hasPrev = false,
  hasNext = false,
  isPaging = false,
  isLoading = false,
  onPrev,
  onNext,
  onSortChange,
  notice,
}: ArticleListProps) {
  const isEmpty = articles.length === 0;
  const [selectedIndex, setSelectedIndex] = useState(0);
  const listRef = useRef<HTMLUListElement | null>(null);

  useEffect(() => {
    setSelectedIndex(0);
  }, [articles, pageIndex, currentModule]);

  useEffect(() => {
    function onFocusList() {
      listRef.current?.focus();
    }
    window.addEventListener(FOCUS_ARTICLE_LIST_EVENT, onFocusList);
    return () => window.removeEventListener(FOCUS_ARTICLE_LIST_EVENT, onFocusList);
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isEditableKeyboardTarget(event.target)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (articles.length === 0 || isLoading) return;

      if (event.key === "j" || event.key === "J") {
        event.preventDefault();
        setSelectedIndex((index) => Math.min(index + 1, articles.length - 1));
        return;
      }
      if (event.key === "k" || event.key === "K") {
        event.preventDefault();
        setSelectedIndex((index) => Math.max(index - 1, 0));
        return;
      }
      if (event.key === "Enter") {
        const article = articles[selectedIndex];
        if (!article) return;
        event.preventDefault();
        const href = readHref(currentModule, currentSort, currentLang, article.id);
        window.location.assign(href);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [articles, currentLang, currentModule, currentSort, isLoading, selectedIndex]);

  useEffect(() => {
    if (articles.length === 0) return;
    const selected = listRef.current?.querySelector<HTMLElement>(
      `[data-list-index="${selectedIndex}"]`,
    );
    selected?.scrollIntoView({ block: "nearest" });
  }, [articles.length, selectedIndex]);

  function updateSort(nextSort: ArticleSortId) {
    onSortChange?.(nextSort);
  }

  return (
    <section className="articleListPane" aria-label="文章列表">
      <header className="articleListHeader">
        <h1 className="articleListTitle">阅读工作台</h1>
        <div className="articleListActions">
          <span className="articleListKbdHint" title="命令面板与列表快捷键">
            <kbd>⌘K</kbd>
            <span className="articleListKbdHintSep">·</span>
            <kbd>j</kbd>
            <kbd>k</kbd>
          </span>
          <SortMenu currentSort={currentSort} options={SORT_OPTIONS} onChange={updateSort} />
        </div>
      </header>
      {notice ? (
        <div className="bulkScoreStatus" role="status">
          <p>
            <strong>{notice.title}</strong> {notice.body}
          </p>
        </div>
      ) : null}
      {isLoading ? <ArticleListSkeleton count={12} /> : null}
      {!isLoading && isEmpty ? (
        <div className="articleListEmpty">
          <p className="articleListEmptyTitle">暂无文章</p>
          <p className="articleListEmptyHint">当前模块没有可显示的文章。</p>
        </div>
      ) : null}
      {!isLoading ? (
        <ul
          ref={listRef}
          className={isPaging ? "articleList articleListPaging" : "articleList"}
          aria-busy={isPaging ? "true" : undefined}
          tabIndex={-1}
        >
          {articles.map((article, index) => {
            const score = article.score;
            const summary = articleSummary(article, currentLang);
            const focusHref = readHref(currentModule, currentSort, currentLang, article.id);
            const isHeadline = pageIndex === 0 && index === 0;
            const rowNumber = pageIndex === 0 ? index : index + 1;
            const isKeyboardSelected = index === selectedIndex;
            const cardClassName =
              [
                "articleCard",
                isHeadline ? "articleCardHeadline" : "",
                article.status === "read" ? "articleCardRead" : "",
                article.id === highlightArticleId ? "articleCardReturnTarget" : "",
                isKeyboardSelected ? "articleCardKeyboardSelected" : "",
              ]
                .filter(Boolean)
                .join(" ");
            return (
              <li key={article.id}>
                <Link
                  className={cardClassName}
                  href={focusHref}
                  prefetch={false}
                  aria-label={`${article.title}，进入专注阅读`}
                  data-article-id={article.id}
                  data-list-index={index}
                  aria-current={isKeyboardSelected ? "true" : undefined}
                >
                  {!isHeadline ? (
                    <span className="articleCardIndex" aria-hidden="true">
                      {String(rowNumber).padStart(2, "0")}
                    </span>
                  ) : null}
                  <div className="articleCardMeta">
                    <span className="articleFeed">{article.feedTitle}</span>
                    {article.categoryTitle ? (
                      <span className="articleCategory">{article.categoryTitle}</span>
                    ) : null}
                  </div>
                  <div className="articleCardTitle">{article.title}</div>
                  <p
                    className={
                      summary.isEmpty
                        ? "articleCardSummary articleCardSummaryEmpty"
                        : "articleCardSummary"
                    }
                  >
                    {summary.text}
                  </p>
                  <div className="articleCardFooter">
                    <div className="articleCardScoreBlock">
                      <ScoreRing value={score?.overall ?? null} tier={score?.tier ?? null} size={isHeadline ? 66 : 52} />
                      <span className="articleCardTier">{score ? (tierLabel(score.tier) ?? "未分层") : "未评"}</span>
                    </div>
                    <span className="articleReadLink" aria-hidden="true">
                      阅读
                    </span>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
      {!isLoading && !isEmpty ? (
        <nav className="articleListPager" aria-label="翻页">
          <button
            type="button"
            className="articleListPagerBtn"
            disabled={!hasPrev || isPaging || !onPrev}
            onClick={onPrev}
          >
            ‹ 上一页
          </button>
          <span className="articleListPagerStatus" aria-live="polite">
            第 {pageIndex + 1} 页
          </span>
          <button
            type="button"
            className="articleListPagerBtn"
            disabled={!hasNext || isPaging || !onNext}
            onClick={onNext}
          >
            下一页 ›
          </button>
        </nav>
      ) : null}
    </section>
  );
}
