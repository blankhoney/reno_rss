import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json(
    { error: "Article list data source is not connected yet" },
    { status: 501 },
  );
}
