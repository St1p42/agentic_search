import { NextRequest, NextResponse } from 'next/server';

const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8000';

function getBackendBaseUrl(): string {
  return (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || DEFAULT_BACKEND_URL).replace(/\/$/, '');
}

export async function POST(request: NextRequest) {
  const body = await request.text();
  const backendResponse = await fetch(`${getBackendBaseUrl()}/api/v1/search`, {
    method: 'POST',
    headers: {
      'Content-Type': request.headers.get('content-type') || 'application/json',
    },
    body,
    cache: 'no-store',
  });

  const responseText = await backendResponse.text();

  return new NextResponse(responseText, {
    status: backendResponse.status,
    headers: {
      'Content-Type': backendResponse.headers.get('content-type') || 'application/json',
    },
  });
}
