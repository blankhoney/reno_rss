import { NextResponse } from "next/server";
import { getMinifluxClient } from "@/lib/miniflux/client";

function parsePositiveIntId(raw: string): number | null {
  const id = Number(raw);
  if (!Number.isFinite(id) || !Number.isInteger(id) || id <= 0) return null;
  return id;
}

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id: idRaw } = await params;
  const id = parsePositiveIntId(idRaw);
  if (id === null) {
    return NextResponse.json({ error: "Invalid id" }, { status: 400 });
  }

  await getMinifluxClient().updateEntries([id], "read");
  return NextResponse.json({ ok: true });
}
