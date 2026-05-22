import { NextRequest, NextResponse } from "next/server";

/**
 * Same-origin proxy to the Python FastAPI backend.
 * Avoids CORS issues — the browser talks to Next.js, Next.js talks to FastAPI.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const body = await request.json();

  let backendRes: Response;
  try {
    backendRes = await fetch("http://localhost:8000/run", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });
  } catch {
    return NextResponse.json(
      { error: "Cannot reach backend on localhost:8000 — is uvicorn running?" },
      { status: 503 }
    );
  }

  const data = await backendRes.json();
  if (!backendRes.ok) {
    return NextResponse.json(
      { error: data.detail ?? "Backend error" },
      { status: backendRes.status }
    );
  }
  return NextResponse.json(data);
}
