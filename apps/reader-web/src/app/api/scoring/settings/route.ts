import { NextResponse } from "next/server";
import { getConfig } from "@/lib/config";
import { getPool } from "@/lib/scoring/db";
import {
  getScoringSettings,
  normalizeScoringSettingsPatch,
  updateScoringSettings,
} from "@/lib/scoring/repository";

export async function GET() {
  const config = getConfig();
  const settings = await getScoringSettings(getPool(), config.READER_TENANT_ID);
  return NextResponse.json({ settings });
}

export async function PUT(request: Request) {
  const body = await request.json().catch(() => null);
  const settings = normalizeScoringSettingsPatch(body);
  const config = getConfig();
  const saved = await updateScoringSettings(getPool(), config.READER_TENANT_ID, settings);
  return NextResponse.json({ settings: saved });
}
