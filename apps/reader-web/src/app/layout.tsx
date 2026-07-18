import type { Metadata } from "next";
import { Suspense } from "react";
import { Newsreader, Noto_Serif_SC } from "next/font/google";
import { CommandPaletteHost } from "@/components/CommandPalette";
import { MobileBottomNav } from "@/components/MobileBottomNav";
import { MotionRoot } from "@/components/MotionRoot";
import { ServiceWorkerRegister } from "@/components/ServiceWorkerRegister";
import { ToastHost } from "@/components/Toast";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Reader",
  description: "AI-assisted RSS reading workspace",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "AI Reader",
    statusBarStyle: "default",
  },
  other: {
    "mobile-web-app-capable": "yes",
  },
};

// Runs before first paint so the saved (or system) theme is applied without a
// flash of the wrong palette. Falls back to the OS preference when unset.
const themeInitScript = `(function(){try{var k='ai-reader.theme';var t=localStorage.getItem(k);if(t!=='light'&&t!=='dark'){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}document.documentElement.dataset.theme=t;}catch(e){}})();`;

const newsreader = Newsreader({
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["opsz"],
  variable: "--font-newsreader",
  display: "swap",
});

const notoSerifSC = Noto_Serif_SC({
  weight: ["400", "600", "700"],
  preload: false,
  variable: "--font-noto-serif-sc",
  display: "swap",
  adjustFontFallback: false,
});

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning className={`${newsreader.variable} ${notoSerifSC.variable}`}>
      <body>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <MotionRoot>{children}</MotionRoot>
        <Suspense fallback={null}>
          <MobileBottomNav />
        </Suspense>
        <CommandPaletteHost />
        <ToastHost />
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
