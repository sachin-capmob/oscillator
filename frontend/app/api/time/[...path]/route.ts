import { NextRequest, NextResponse } from "next/server";

// Server-side proxy to the FastAPI time-tracking API. Mirrors the insights
// proxy pattern — bearer token is injected server-side so it never reaches
// the browser. Forwards the full path + query string + request body as-is.

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";
const TOKEN = process.env.DASHBOARD_AUTH_TOKEN ?? "";

export const dynamic = "force-dynamic";

async function proxy(req: NextRequest, params: { path: string[] }) {
  const path = params.path.join("/");
  const search = req.nextUrl.search;
  const method = req.method;

  try {
    const body = method !== "GET" && method !== "HEAD" ? await req.text() : undefined;
    const upstream = await fetch(`${API_BASE_URL}/api/time/${path}${search}`, {
      method,
      headers: {
        Authorization: `Bearer ${TOKEN}`,
        "content-type": "application/json",
      },
      body,
      cache: "no-store",
    });
    const responseBody = await upstream.text();
    return new NextResponse(responseBody, {
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

export async function GET(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params);
}

export async function POST(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params);
}
