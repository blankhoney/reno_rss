"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  listAnnotationReviewQueue,
  reviewAnnotation,
  type AnnotationReviewItem,
} from "@/lib/api/articles";
import {
  clearExactPendingSeq,
  ownsAnnotationLoad,
  ownsReviewAttempt as ownsReviewAttemptPredicate,
  type AnnotationLoadAttempt,
  type PendingReviewAttempt,
} from "@/lib/articles/annotationAsync";

type PendingRefreshAttempt = AnnotationLoadAttempt & { hadFocus: boolean };

export function ReviewQueue() {
  const [items, setItems] = useState<AnnotationReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyAttempt, setBusyAttempt] = useState<PendingReviewAttempt | null>(null);
  const [pendingRefreshSeq, setPendingRefreshSeq] = useState<number | null>(null);
  const mountedRef = useRef(false);
  const loadSeqRef = useRef(0);
  const mutationEpochRef = useRef(0);
  const pendingRefreshRef = useRef<PendingRefreshAttempt | null>(null);
  const refreshButtonRef = useRef<HTMLButtonElement | null>(null);
  const reviewSeqRef = useRef(0);
  const pendingReviewRef = useRef<PendingReviewAttempt | null>(null);

  const ownsLoadAttempt = useCallback((attempt: AnnotationLoadAttempt) => ownsAnnotationLoad(attempt, {
    mounted: mountedRef.current,
    articleId: 0,
    requestSeq: loadSeqRef.current,
    mutationEpoch: mutationEpochRef.current,
  }), []);

  const reload = useCallback((manual = false) => {
    if (manual && pendingRefreshRef.current != null) return;
    const attempt: PendingRefreshAttempt = {
      articleId: 0,
      requestSeq: ++loadSeqRef.current,
      mutationEpoch: mutationEpochRef.current,
      hadFocus: manual && document.activeElement === refreshButtonRef.current,
    };
    if (manual) {
      pendingRefreshRef.current = attempt;
      setPendingRefreshSeq(attempt.requestSeq);
    }
    setError(null);
    listAnnotationReviewQueue(30)
      .then((next) => {
        if (!ownsLoadAttempt(attempt)) return;
        setItems(next);
        setError(null);
      })
      .catch((caught) => {
        if (!ownsLoadAttempt(attempt)) return;
        setError(caught instanceof Error ? caught.message : "加载复习队列失败");
      })
      .finally(() => {
        if (!manual || pendingRefreshRef.current?.requestSeq !== attempt.requestSeq) return;
        pendingRefreshRef.current = null;
        setPendingRefreshSeq((current) => clearExactPendingSeq(current, attempt.requestSeq));
        if (!attempt.hadFocus) return;
        window.requestAnimationFrame(() => {
          const button = refreshButtonRef.current;
          const active = document.activeElement;
          if (!mountedRef.current || button == null) return;
          if (active === document.body || active === button || active?.isConnected === false) {
            button.focus({ preventScroll: true });
          }
        });
      });
  }, [ownsLoadAttempt]);

  useEffect(() => {
    mountedRef.current = true;
    reload();
    return () => {
      mountedRef.current = false;
      loadSeqRef.current += 1;
      pendingRefreshRef.current = null;
      reviewSeqRef.current += 1;
      pendingReviewRef.current = null;
    };
  }, [reload]);

  function ownsReviewAttempt(attempt: PendingReviewAttempt): boolean {
    return ownsReviewAttemptPredicate(attempt, {
      mounted: mountedRef.current,
      pending: pendingReviewRef.current,
    });
  }

  async function respond(item: AnnotationReviewItem, remembered: boolean) {
    if (!mountedRef.current || pendingReviewRef.current != null) return;
    const attempt = { seq: ++reviewSeqRef.current, id: item.id };
    pendingReviewRef.current = attempt;
    setBusyAttempt(attempt);
    setError(null);
    try {
      await reviewAnnotation(item.id, remembered);
      if (!ownsReviewAttempt(attempt)) return;
      mutationEpochRef.current += 1;
      setItems((current) => (current ?? []).filter((row) => row.id !== item.id));
    } catch (caught) {
      if (!ownsReviewAttempt(attempt)) return;
      setError(caught instanceof Error ? caught.message : "提交复习结果失败");
    } finally {
      if (!ownsReviewAttempt(attempt)) return;
      pendingReviewRef.current = null;
      setBusyAttempt((current) => current?.seq === attempt.seq && current.id === attempt.id ? null : current);
    }
  }

  return (
    <section className="reviewQueuePane" aria-label="划线复习">
      <header className="articleListHeader">
        <div>
          <h1 className="articleListTitle">划线复习</h1>
          <p className="workbenchRibbonMuted">
            只显示到期项（SM-2 lite：1→3→7→14→30 天）。记得 / 忘了 会推进间隔。
          </p>
        </div>
        <button
          ref={refreshButtonRef}
          type="button"
          className="readerToolbarBtn"
          aria-label="刷新队列"
          aria-busy={pendingRefreshSeq != null}
          disabled={pendingRefreshSeq != null}
          onClick={() => reload(true)}
        >
          {pendingRefreshSeq != null ? "刷新中…" : "刷新队列"}
        </button>
      </header>
      {error ? (
        <p className="adminConsoleError" role="alert">
          {error}
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
          {items.map((item) => {
            const itemBusy = busyAttempt?.id === item.id;
            return (
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
                    disabled={busyAttempt != null}
                    onClick={() => void respond(item, true)}
                  >
                    {itemBusy ? "提交中…" : "记得"}
                  </button>
                  <button
                    type="button"
                    className="readerToolbarBtn"
                    disabled={busyAttempt != null}
                    onClick={() => void respond(item, false)}
                  >
                    {itemBusy ? "提交中…" : "忘了"}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
