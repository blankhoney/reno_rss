import type { Metadata } from "next";
import { MotionRoot } from "@/components/MotionRoot";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Reader",
  description: "AI-assisted RSS reading workspace",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <MotionRoot>{children}</MotionRoot>
      </body>
    </html>
  );
}
