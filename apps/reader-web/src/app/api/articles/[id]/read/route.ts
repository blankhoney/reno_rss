import { NextResponse } from "next/server";
import { getConfig } from "@/lib/config";
import { getMinifluxClient } from "@/lib/miniflux/client";
import { getPool } from "@/lib/scoring/db";
import { markRead } from "@/lib/scoring/repository";

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
  const config = getConfig();
  try {
    await markRead(
      getPool(),
      config.READER_TENANT_ID,
      config.READER_MINIFLUX_USER_ID,
      id,
    );
  } catch {
    return NextResponse.json(
      { ok: true, warning: "reader_state_update_failed" },
      { status: 207 },
    );
  }
  return NextResponse.json({ ok: true });
}
