# next-js-middleware-patterns

**Issue:** Authentication redirects and A/B rewrites need to run before rendering
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Protecting routes client-side flashes the protected content before redirecting.

## Pattern / Solution
```ts
// middleware.ts at project root
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const token = request.cookies.get('session')?.value;
  if (!token && request.nextUrl.pathname.startsWith('/dashboard')) {
    return NextResponse.redirect(new URL('/login', request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ['/dashboard/:path*', '/admin/:path*'],
};
```

## Gotchas
- Middleware runs on the Edge runtime; Node.js APIs are unavailable
- Do not do heavy DB work here; verify JWTs with lightweight crypto
- Matcher patterns are evaluated at build time; dynamic patterns need runtime checks

## Related
- `next-js-app-router-patterns.md`
- `next-js-route-handlers.md`
