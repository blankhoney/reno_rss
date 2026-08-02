"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { Article } from "@/lib/articles/types";
import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";
import { ScoreRing, tierLabel } from "./ScoreRing";
import { ArticleListSkeleton } from "./Skeleton";
import { SortMenu, type SortOption } from "./SortMenu";
import { FOCUS_ARTICLE_LIST_EVENT, isInteractiveKeyboardTarget } from "@/lib/commandPalette";
import { buildFocusReadHref } from "@/lib/articles/navigation";
import Link from "next/link";

type ArticleListProps = {
  articles: Article[];
  currentModule: string;
  currentSort: ArticleSortId;
  currentLang: SummaryLangId;
  currentQuery?: string;
  cursorStack?: (string | null)[];
  highlightArticleId?: number | null;
  pageIndex?: number;
  hasPrev?: boolean;
  hasNext?: boolean;
  isPaging?: boolean;
  isLoading?: boolean;
  loadError?: string | null;
  onPrev?: () => void;
  onNext?: () => void;
  onRetry?: () => void;
  onSortChange?: (nextSort: ArticleSortId) => void;
  onToggleRead?: (article: Article) => void;
  onToggleCandidate?: (article: Article) => void;
  onToggleProject?: (article: Article) => void;
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
  currentQuery: string,
  cursorStack: (string | null)[],
  articleId: number,
): string {
  return buildFocusReadHref(articleId, {
    module: currentModule,
    sort: currentSort,
    lang: currentLang,
    query: currentQuery,
    cursorStack,
  });
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
  currentQuery = "",
  cursorStack = [null],
  highlightArticleId = null,
  pageIndex = 0,
  hasPrev = false,
  hasNext = false,
  isPaging = false,
  isLoading = false,
  loadError = null,
  onPrev,
  onNext,
  onRetry,
  onSortChange,
  onToggleRead,
  onToggleCandidate,
  onToggleProject,
  notice,
}: ArticleListProps) {
  const isEmpty = articles.length === 0;
  const [selectedIndex, setSelectedIndex] = useState(0);
  const listRef = useRef<HTMLUListElement | null>(null);
  const retryButtonRef = useRef<HTMLButtonElement | null>(null);
  const shouldRestoreListFocusRef = useRef(false);

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
    if (loadError != null) {
      shouldRestoreListFocusRef.current = true;
      retryButtonRef.current?.focus();
      return;
    }
    if (!isLoading && !isPaging && shouldRestoreListFocusRef.current) {
      listRef.current?.focus();
      shouldRestoreListFocusRef.current = false;
    }
  }, [isLoading, isPaging, loadError]);

  function onListKeyDown(event: KeyboardEvent<HTMLUListElement>) {
    if (isInteractiveKeyboardTarget(event.target)) return;
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
      const href = readHref(currentModule, currentSort, currentLang, currentQuery, cursorStack, article.id);
      window.location.assign(href);
      return;
    }
    if ((event.key === "r" || event.key === "R") && onToggleRead) {
      const article = articles[selectedIndex];
      if (!article) return;
      event.preventDefault();
      onToggleRead(article);
      return;
    }
    if ((event.key === "s" || event.key === "S") && onToggleCandidate) {
      const article = articles[selectedIndex];
      if (!article) return;
      event.preventDefault();
      onToggleCandidate(article);
      return;
    }
    if ((event.key === "p" || event.key === "P") && onToggleProject) {
      const article = articles[selectedIndex];
      if (!article) return;
      event.preventDefault();
      onToggleProject(article);
      return;
    }
    if (event.key === "1" || event.key === "2" || event.key === "3") {
      // Dimension sort shortcuts: 1 score, 2 technical, 3 business
      event.preventDefault();
      if (event.key === "1") onSortChange?.("score");
      if (event.key === "2") onSortChange?.("technical");
      if (event.key === "3") onSortChange?.("business");
    }
  }

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
            <kbd>r</kbd>
            <kbd>s</kbd>
            <kbd>p</kbd>
            <kbd>1</kbd>
            <kbd>2</kbd>
            <kbd>3</kbd>
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
      {loadError != null ? (
        <section className="workbenchStatus" aria-live="polite">
          <p className="readerEmptyTitle">文章加载失败</p>
          <p className="readerEmptyHint">{loadError}</p>
          <button
            ref={retryButtonRef}
            type="button"
            className="readerToolbarBtn"
            onClick={onRetry}
            disabled={!onRetry}
          >
            重试
          </button>
          {hasPrev && onPrev ? (
            <button type="button" className="readerToolbarBtn" onClick={onPrev}>
              ‹ 上一页
            </button>
          ) : null}
        </section>
      ) : null}
      {isLoading ? <ArticleListSkeleton count={12} /> : null}
      {!isLoading && loadError == null && isEmpty ? (
        <div className="articleListEmpty">
          <p className="articleListEmptyTitle">暂无文章</p>
          <p className="articleListEmptyHint">当前模块没有可显示的文章。</p>
        </div>
      ) : null}
      {!isLoading && loadError == null ? (
        <ul
          ref={listRef}
          className={isPaging ? "articleList articleListPaging" : "articleList"}
          aria-busy={isPaging ? "true" : undefined}
          onKeyDown={onListKeyDown}
          tabIndex={0}
        >
          {articles.map((article, index) => {
            const score = article.score;
            const summary = articleSummary(article, currentLang);
            const focusHref = readHref(currentModule, currentSort, currentLang, currentQuery, cursorStack, article.id);
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
      {!isLoading && loadError == null && (!isEmpty || hasPrev) ? (
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
