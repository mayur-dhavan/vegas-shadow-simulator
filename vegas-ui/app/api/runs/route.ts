import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const limit = request.nextUrl.searchParams.get("limit") ?? "30";
  let backendRes: Response;
  try {
    backendRes = await fetch(`http://localhost:8000/runs?limit=${limit}`, {
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { error: "Cannot reach backend on localhost:8000" },
      { status: 503 }
    );
  }
  const data = await backendRes.json();
  return NextResponse.json(data);
}
