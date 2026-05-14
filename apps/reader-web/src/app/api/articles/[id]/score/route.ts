import { NextResponse } from "next/server";
import { getConfig } from "@/lib/config";
import { getPool } from "@/lib/scoring/db";
import { getScoringSettings } from "@/lib/scoring/repository";
import { parseScoreRequestBody, scoreEntryWithService } from "@/lib/scoring/service-client";

function parsePositiveIntId(raw: string): number | null {
  const id = Number(raw);
  if (!Number.isFinite(id) || !Number.isInteger(id) || id <= 0) return null;
  return id;
}

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id: idRaw } = await params;
  const id = parsePositiveIntId(idRaw);
  if (id === null) {
    return NextResponse.json({ error: "Invalid id" }, { status: 400 });
  }

  const body = await request.json().catch(() => null);
  const { force } = parseScoreRequestBody(body);
  const config = getConfig();
  const settings = await getScoringSettings(getPool(), config.READER_TENANT_ID);
  if (!settings.manualRescoreEnabled) {
    return NextResponse.json({ error: "manual_rescore_disabled" }, { status: 403 });
  }

  const result = await scoreEntryWithService(id, force);
  if (!result.ok) {
    return NextResponse.json(
      { error: result.error ?? "score_failed" },
      { status: result.error === "entry_not_found" ? 404 : 502 },
    );
  }
  return NextResponse.json(result);
}
