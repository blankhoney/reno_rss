import { NextResponse } from "next/server";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return NextResponse.json(
    { error: "Article detail data source is not connected yet", id },
    { status: 501 },
  );
}
