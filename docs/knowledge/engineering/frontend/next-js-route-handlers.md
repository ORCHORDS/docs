# next-js-route-handlers

**Issue:** API routes in App Router differ from Pages Router api/ conventions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Next.js 13+ route handlers are colocated with UI segments and support all HTTP methods.

## Pattern / Solution
```ts
// app/api/posts/route.ts
import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const page = searchParams.get('page') ?? '1';
  const posts = await db.posts.findMany({ skip: (Number(page) - 1) * 10 });
  return NextResponse.json(posts);
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const post = await db.posts.create({ data: body });
  return NextResponse.json(post, { status: 201 });
}
```

## Gotchas
- Route handlers with no dynamic usage are statically cached; use cache: 'no-store' or dynamic export to opt out
- Dynamic segment: app/api/posts/[id]/route.ts receives params as second arg
- Avoid CORS issues by configuring headers in the response or via middleware

## Related
- `next-js-middleware-patterns.md`
- `next-js-app-router-patterns.md`
