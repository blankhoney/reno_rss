"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  listAnnotationReviewQueue,
  type AnnotationReviewItem,
} from "@/lib/api/articles";

export function ReviewQueue() {
  const [items, setItems] = useState<AnnotationReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listAnnotationReviewQueue(30)
      .then((next) => {
        if (active) setItems(next);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof Error ? caught.message : "加载复习队列失败");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <section className="reviewQueuePane" aria-label="划线复习">
      <header className="articleListHeader">
        <h1 className="articleListTitle">划线复习</h1>
        <p className="workbenchRibbonMuted">私有高亮与笔记，按最近创建时间 resurface（Readwise 式复习入口）</p>
      </header>
      {error ? <p className="adminConsoleError">{error}</p> : null}
      {items == null && !error ? <p className="workbenchRibbonMuted">加载中…</p> : null}
      {items && items.length === 0 ? (
        <div className="articleListEmpty">
          <p className="articleListEmptyTitle">还没有划线</p>
          <p className="articleListEmptyHint">在精读页选中文字保存笔记后，会在这里回来找你。</p>
        </div>
      ) : null}
      {items && items.length > 0 ? (
        <ul className="reviewQueueList">
          {items.map((item) => (
            <li key={item.id} className="reviewQueueItem">
              <blockquote className="reviewQueueQuote">
                {item.selectedText?.trim() || item.content}
              </blockquote>
              {item.selectedText && item.content !== item.selectedText ? (
                <p className="reviewQueueNote">{item.content}</p>
              ) : null}
              <div className="reviewQueueMeta">
                {item.articleId > 0 ? (
                  <Link href={`/read/${item.articleId}?module=review&sort=default&lang=zh`} prefetch={false}>
                    {item.articleTitle || `文章 #${item.articleId}`}
                  </Link>
                ) : (
                  <span>{item.articleTitle || "未知文章"}</span>
                )}
                {item.createdAt ? <time dateTime={item.createdAt}>{item.createdAt.slice(0, 10)}</time> : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
