"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";

export type ToastVariant = "success" | "info" | "error";

export type ToastAction = {
  href: string;
  label: string;
};

export type ToastPayload = {
  title: string;
  body?: string;
  variant?: ToastVariant;
  action?: ToastAction | null;
};

type ToastItem = Required<Pick<ToastPayload, "title" | "variant">> &
  Pick<ToastPayload, "body" | "action"> & {
    id: number;
  };

export const TOAST_EVENT = "ai-reader:toast";
const TOAST_TTL_MS = 3600;
const TOAST_LIMIT = 2;

let nextToastId = 1;

export function clampToastQueue(items: ToastItem[]): ToastItem[] {
  return items.slice(-TOAST_LIMIT);
}

export function emitToast(payload: ToastPayload) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<ToastPayload>(TOAST_EVENT, {
      detail: payload,
    }),
  );
}

export function ToastHost() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    function onToast(event: Event) {
      const detail = event instanceof CustomEvent ? event.detail : null;
      if (detail == null || typeof detail.title !== "string" || detail.title.trim().length === 0) return;
      const item: ToastItem = {
        id: nextToastId,
        title: detail.title.trim(),
        body: typeof detail.body === "string" && detail.body.trim().length > 0 ? detail.body.trim() : undefined,
        variant: detail.variant === "error" || detail.variant === "info" ? detail.variant : "success",
        action: detail.action ?? null,
      };
      nextToastId += 1;
      setItems((current) => clampToastQueue([...current, item]));
      window.setTimeout(() => {
        setItems((current) => current.filter((toast) => toast.id !== item.id));
      }, TOAST_TTL_MS);
    }

    window.addEventListener(TOAST_EVENT, onToast);
    return () => window.removeEventListener(TOAST_EVENT, onToast);
  }, []);

  return (
    <div className="toastHost" role="status" aria-live="polite" aria-atomic="true">
      <AnimatePresence initial={false}>
        {items.map((item) => (
          <motion.div
            className={`toastCard toastCard-${item.variant}`}
            key={item.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.19, ease: "easeOut" }}
          >
            <p className="toastTitle">{item.title}</p>
            {item.body ? <p className="toastBody">{item.body}</p> : null}
            {item.action ? (
              item.action.href.startsWith("/") ? (
                <Link className="toastAction" href={item.action.href} prefetch={false}>
                  {item.action.label}
                </Link>
              ) : (
                <a className="toastAction" href={item.action.href}>
                  {item.action.label}
                </a>
              )
            ) : null}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
