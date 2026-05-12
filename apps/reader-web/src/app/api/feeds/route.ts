import { NextResponse } from "next/server";
import { getMinifluxClient } from "@/lib/miniflux/client";

function isValidFeedUrl(feedUrl: string): boolean {
  const trimmed = feedUrl.trim();
  if (!trimmed) return false;
  try {
    const u = new URL(trimmed);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

export async function GET() {
  const feeds = await getMinifluxClient().getFeeds();
  return NextResponse.json({ feeds });
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (body === null || typeof body !== "object") {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }

  const rec = body as Record<string, unknown>;
  const feedUrl = rec.feedUrl;
  if (typeof feedUrl !== "string") {
    return NextResponse.json({ error: "feedUrl must be a string" }, { status: 400 });
  }
  if (!isValidFeedUrl(feedUrl)) {
    return NextResponse.json({ error: "Invalid feedUrl" }, { status: 400 });
  }

  const categoryId = Number(rec.categoryId);
  if (
    rec.categoryId === undefined ||
    !Number.isFinite(categoryId) ||
    !Number.isInteger(categoryId) ||
    categoryId <= 0
  ) {
    return NextResponse.json({ error: "Invalid categoryId" }, { status: 400 });
  }

  const feedId = await getMinifluxClient().createFeed(feedUrl.trim(), categoryId);
  return NextResponse.json({ feedId }, { status: 201 });
}
