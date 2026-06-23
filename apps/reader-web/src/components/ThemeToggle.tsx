"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "ai-reader.theme";
type Theme = "light" | "dark";

export function ThemeToggle() {
  // Render a stable placeholder on the server; the real theme is read after
  // mount from the attribute the anti-FOUC script already set on <html>.
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    const current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
    setTheme(current);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Persisting the preference is a convenience only.
    }
    setTheme(next);
  }

  const isDark = theme === "dark";
  const label = isDark ? "切换到浅色主题" : "切换到深色主题";

  return (
    <button
      type="button"
      className="themeToggle"
      onClick={toggle}
      aria-label={label}
      title={label}
    >
      <span aria-hidden="true" suppressHydrationWarning>
        {isDark ? "☀" : "☾"}
      </span>
    </button>
  );
}
