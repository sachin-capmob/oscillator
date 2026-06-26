import { NextRequest, NextResponse } from "next/server";

// Server-side proxy to the FastAPI insights API. Injects the bearer token so
// it stays out of the browser bundle. Forwards the path + query string as-is.

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";
const TOKEN = process.env.DASHBOARD_AUTH_TOKEN ?? "";

export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  { params }: { params: { path: string[] } },
) {
  const path = params.path.join("/");
  const search = req.nextUrl.search;
  try {
    const upstream = await fetch(`${API_BASE_URL}/api/insights/${path}${search}`, {
      headers: { Authorization: `Bearer ${TOKEN}` },
      cache: "no-store",
    });
    const body = await upstream.text();
    return new NextResponse(body, {
      status: upstream.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return NextResponse.json(
      { detail: "Backend API is unreachable. Is the FastAPI server running?" },
      { status: 502 },
    );
  }
}
