# next-js-data-fetching

**Issue:** Choosing between static, dynamic, and incremental data fetching in App Router
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Pages that should be cached are fetching on every request; dynamic pages serve stale data.

## Pattern / Solution
```tsx
// Static (build time) - default
const data = await fetch('https://api.example.com/posts');

// Revalidate every 60s (ISR)
const data = await fetch('https://api.example.com/posts', {
  next: { revalidate: 60 },
});

// Dynamic (per-request)
const data = await fetch('https://api.example.com/posts', {
  cache: 'no-store',
});

// On-demand revalidation
import { revalidatePath, revalidateTag } from 'next/cache';
await revalidatePath('/posts');
await revalidateTag('posts');
```

## Gotchas
- fetch in Server Components is automatically deduped within a request
- Dynamic functions (cookies(), headers()) opt the whole route into dynamic rendering
- Use unstable_cache for non-fetch data sources like database calls

## Related
- `next-js-caching-strategy.md`
- `next-js-app-router-patterns.md`
