import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);
  try {
    const body = await request.arrayBuffer();
    const baseUrl = (process.env.BACKEND_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
    const response = await fetch(`${baseUrl}/pv-economics/calculate`, {
      method: "POST", body, signal: controller.signal,
      headers: { "content-type": request.headers.get("content-type") || "application/json", accept: "application/json" },
      cache: "no-store",
    });
    return new Response(response.body, { status: response.status, headers: { "content-type": response.headers.get("content-type") || "application/json" } });
  } catch {
    return NextResponse.json({ detail: "Die Berechnung ist momentan nicht erreichbar." }, { status: 503 });
  } finally { clearTimeout(timeout); }
}
