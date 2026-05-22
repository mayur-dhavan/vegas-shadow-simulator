import { NextResponse } from "next/server";

export async function GET(): Promise<NextResponse> {
  let backendRes: Response;
  try {
    backendRes = await fetch("http://localhost:8000/default-map", {
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { error: "Cannot reach backend on localhost:8000" },
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
