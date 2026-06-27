import { useCallback, useEffect, useRef, useState } from "react";

export type TypewriterOptions = {
  intervalMs?: number;
  charsPerTick?: number;
  maxCharsPerTick?: number;
};

export function takeTypewriterChunk(
  buffer: string,
  charsPerTick: number,
  maxCharsPerTick: number,
): { chunk: string; rest: string } {
  const count = Math.max(1, Math.min(maxCharsPerTick, charsPerTick));
  return {
    chunk: buffer.slice(0, count),
    rest: buffer.slice(count),
  };
}

export function useTypewriterStream({
  intervalMs = 20,
  charsPerTick = 1,
  maxCharsPerTick = 4,
}: TypewriterOptions = {}) {
  const [revealed, setRevealed] = useState("");
  const [isRevealing, setIsRevealing] = useState(false);
  const bufferRef = useRef("");
  const finishedRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopTimer = useCallback(() => {
    if (timerRef.current != null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setIsRevealing(false);
  }, []);

  const tick = useCallback(() => {
    if (bufferRef.current.length === 0) {
      if (finishedRef.current) stopTimer();
      return;
    }

    const burstSize = bufferRef.current.length > 160 ? maxCharsPerTick : charsPerTick;
    const { chunk, rest } = takeTypewriterChunk(bufferRef.current, burstSize, maxCharsPerTick);
    bufferRef.current = rest;
    setRevealed((current) => current + chunk);
    if (rest.length === 0 && finishedRef.current) stopTimer();
  }, [charsPerTick, maxCharsPerTick, stopTimer]);

  const ensureTimer = useCallback(() => {
    if (timerRef.current == null) {
      timerRef.current = setInterval(tick, intervalMs);
    }
    setIsRevealing(true);
  }, [intervalMs, tick]);

  const push = useCallback(
    (text: string) => {
      if (text.length === 0) return;
      finishedRef.current = false;
      bufferRef.current += text;
      ensureTimer();
    },
    [ensureTimer],
  );

  const finish = useCallback(() => {
    finishedRef.current = true;
    if (bufferRef.current.length === 0) stopTimer();
  }, [stopTimer]);

  const reset = useCallback(() => {
    bufferRef.current = "";
    finishedRef.current = true;
    setRevealed("");
    stopTimer();
  }, [stopTimer]);

  useEffect(() => stopTimer, [stopTimer]);

  return {
    revealed,
    isRevealing,
    push,
    finish,
    reset,
  };
}
