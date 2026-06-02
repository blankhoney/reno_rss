import { NextResponse } from "next/server";
import { getDemoAccessConfig, performDemoLogin } from "@/lib/demo/access";

export async function POST(request: Request) {
  const result = await performDemoLogin(request, getDemoAccessConfig());

  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: result.status });
  }

  const response = NextResponse.redirect(result.location, result.status);
  for (const cookie of result.cookies) {
    response.headers.append("set-cookie", cookie);
  }
  return response;
}
