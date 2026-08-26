# react-server-components

**Issue:** Client bundles include data-fetching logic and secrets that belong on the server
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Large database SDKs appear in the client bundle; client-side fetching waterfalls add latency.

## Pattern / Solution
```tsx
// app/page.tsx - Server Component by default in App Router
export default async function Page() {
  const data = await db.query('SELECT * FROM posts'); // server only
  return <PostList posts={data} />;
}

// Client component opt-in
'use client';
import { useState } from 'react';
export function LikeButton() { /* interactive */ }

// Pass server data to client components via props
<LikeButton initialCount={post.likes} />
```

## Gotchas
- No hooks, browser APIs, or event handlers in Server Components
- Importing a client component from a server component is fine; reverse is not
- Context does not work across the server/client boundary

## Related
- `react-server-actions.md`
- `next-js-app-router-patterns.md`
