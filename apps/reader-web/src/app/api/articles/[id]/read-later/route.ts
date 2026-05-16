import { NextResponse } from "next/server";
import { getConfig } from "@/lib/config";
import { getPool } from "@/lib/scoring/db";
import { upsertReadLater } from "@/lib/scoring/repository";

function parsePositiveIntId(raw: string): number | null {
  const id = Number(raw);
  if (!Number.isFinite(id) || !Number.isInteger(id) || id <= 0) return null;
  return id;
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id: idRaw } = await params;
  const minifluxEntryId = parsePositiveIntId(idRaw);
  if (minifluxEntryId === null) {
    return NextResponse.json({ error: "Invalid id" }, { status: 400 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }

  const rec = body as Record<string, unknown>;
  const keys = Object.keys(rec);
  if (keys.length !== 1 || keys[0] !== "readLater") {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }

  const { readLater } = rec;
  if (typeof readLater !== "boolean") {
    return NextResponse.json({ error: "readLater must be a boolean" }, { status: 400 });
  }

  const config = getConfig();
  const pool = getPool();
  await upsertReadLater(
    pool,
    config.READER_TENANT_ID,
    config.READER_MINIFLUX_USER_ID,
    minifluxEntryId,
    readLater,
  );
  return NextResponse.json({ ok: true });
}
