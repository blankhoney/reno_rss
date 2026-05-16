import { NextResponse } from "next/server";
import { listFeedQualitySummaries } from "@/lib/feeds/server";

export async function GET() {
  const feeds = await listFeedQualitySummaries();
  return NextResponse.json({ feeds });
}
