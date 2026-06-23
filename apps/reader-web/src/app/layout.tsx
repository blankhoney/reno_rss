import type { Metadata } from "next";
import { MotionRoot } from "@/components/MotionRoot";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Reader",
  description: "AI-assisted RSS reading workspace",
};

// Runs before first paint so the saved (or system) theme is applied without a
// flash of the wrong palette. Falls back to the OS preference when unset.
const themeInitScript = `(function(){try{var k='ai-reader.theme';var t=localStorage.getItem(k);if(t!=='light'&&t!=='dark'){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}document.documentElement.dataset.theme=t;}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <MotionRoot>{children}</MotionRoot>
      </body>
    </html>
  );
}
