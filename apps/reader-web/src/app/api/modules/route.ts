import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    modules: [
      { id: "all", title: "最新", defaultSort: "published_at" },
      { id: "unread", title: "未读", defaultSort: "overall" },
      { id: "read", title: "已读", defaultSort: "last_read_at" },
      { id: "starred", title: "收藏", defaultSort: "overall" },
      { id: "read-later", title: "稍后读", defaultSort: "overall" },
      { id: "technical", title: "技术", defaultSort: "technical_value" },
      { id: "business", title: "商业", defaultSort: "business_value" },
      { id: "trend", title: "趋势", defaultSort: "trend_value" },
      { id: "ai", title: "AI", defaultSort: "technical_value" },
      { id: "product", title: "产品", defaultSort: "usefulness" },
      { id: "security", title: "安全", defaultSort: "importance" },
    ],
  });
}
