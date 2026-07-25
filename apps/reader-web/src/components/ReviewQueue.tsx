"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  listAnnotationReviewQueue,
  reviewAnnotation,
  type AnnotationReviewItem,
} from "@/lib/api/articles";

export function ReviewQueue() {
  const [items, setItems] = useState<AnnotationReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const reload = useCallback(() => {
    let active = true;
    setError(null);
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

  useEffect(() => reload(), [reload]);

  async function respond(item: AnnotationReviewItem, remembered: boolean) {
    setBusyId(item.id);
    setError(null);
    try {
      await reviewAnnotation(item.id, remembered);
      setItems((current) => (current ?? []).filter((row) => row.id !== item.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "提交复习结果失败");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="reviewQueuePane" aria-label="划线复习">
      <header className="articleListHeader">
        <h1 className="articleListTitle">划线复习</h1>
        <p className="workbenchRibbonMuted">
          只显示到期项（SM-2 lite：1→3→7→14→30 天）。记得 / 忘了 会推进间隔。
        </p>
      </header>
      {error ? (
        <p className="adminConsoleError" role="alert">
          {error}
          <button type="button" className="readerToolbarBtn" onClick={() => reload()}>
            重试
          </button>
        </p>
      ) : null}
      {items == null && !error ? <p className="workbenchRibbonMuted">加载中…</p> : null}
      {items && items.length === 0 ? (
        <div className="articleListEmpty">
          <p className="articleListEmptyTitle">今天没有到期划线</p>
          <p className="articleListEmptyHint">在精读页选中文字保存笔记后，到期时会回到这里。</p>
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
                <span>
                  间隔 {item.intervalDays} 天
                  {item.nextReviewAt ? ` · 到期 ${item.nextReviewAt.slice(0, 10)}` : null}
                </span>
              </div>
              <div className="reviewQueueActions">
                <button
                  type="button"
                  className="readerToolbarBtn readerToolbarBtnPrimary"
                  disabled={busyId === item.id}
                  onClick={() => void respond(item, true)}
                >
                  记得
                </button>
                <button
                  type="button"
                  className="readerToolbarBtn"
                  disabled={busyId === item.id}
                  onClick={() => void respond(item, false)}
                >
                  忘了
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
