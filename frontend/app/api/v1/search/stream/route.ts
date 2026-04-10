import { NextRequest, NextResponse } from 'next/server';

const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8000';

function getBackendBaseUrl(): string {
  return (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || DEFAULT_BACKEND_URL).replace(/\/$/, '');
}

export async function GET(request: NextRequest) {
  const backendUrl = new URL(`${getBackendBaseUrl()}/api/v1/search/stream`);
  const query = request.nextUrl.searchParams.get('query');
  const requestId = request.nextUrl.searchParams.get('request_id');

  if (query) {
    backendUrl.searchParams.set('query', query);
  }
  if (requestId) {
    backendUrl.searchParams.set('request_id', requestId);
  }

  const backendResponse = await fetch(backendUrl, {
    headers: {
      Accept: 'text/event-stream',
    },
    cache: 'no-store',
  });

  if (!backendResponse.body) {
    return NextResponse.json({ error: 'Streaming response body unavailable' }, { status: 502 });
  }

  return new NextResponse(backendResponse.body, {
    status: backendResponse.status,
    headers: {
      'Content-Type': backendResponse.headers.get('content-type') || 'text/event-stream',
      'Cache-Control': backendResponse.headers.get('cache-control') || 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  });
}
