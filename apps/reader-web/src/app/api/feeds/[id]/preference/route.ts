import { NextResponse } from "next/server";
import { getConfig } from "@/lib/config";
import { getPool } from "@/lib/scoring/db";
import { updateFeedPreference } from "@/lib/scoring/repository";

function parsePositiveIntId(raw: string): number | null {
  const id = Number(raw);
  if (!Number.isFinite(id) || !Number.isInteger(id) || id <= 0) return null;
  return id;
}

export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id: idRaw } = await params;
  const feedId = parsePositiveIntId(idRaw);
  if (feedId === null) {
    return NextResponse.json({ error: "Invalid id" }, { status: 400 });
  }

  const body = (await request.json().catch(() => null)) as { hidden?: unknown } | null;
  if (body === null || typeof body.hidden !== "boolean") {
    return NextResponse.json({ error: "hidden must be boolean" }, { status: 400 });
  }

  const preference = await updateFeedPreference(getPool(), {
    tenantId: getConfig().READER_TENANT_ID,
    feedId,
    hidden: body.hidden,
  });
  return NextResponse.json({ preference });
}
