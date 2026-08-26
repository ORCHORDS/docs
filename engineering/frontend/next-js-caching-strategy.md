# next-js-caching-strategy

**Issue:** App Router has four overlapping cache layers that interact in non-obvious ways
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Invalidating a page does not clear the browser cache; or Server Actions update the DB but the page still shows stale data.

## Pattern / Solution
```
1. Request Memoization  - dedupes identical fetch() calls within one render pass
2. Data Cache           - persists fetch() results across requests (revalidate/tags)
3. Full Route Cache     - caches rendered HTML/RSC payload at build time
4. Router Cache         - client-side cache of visited segments (30s soft TTL)
```

```tsx
// Opt out of data cache
fetch(url, { cache: 'no-store' });

// Tag-based invalidation from Server Action
import { revalidateTag } from 'next/cache';
export async function deletePost(id) {
  'use server';
  await db.delete(id);
  revalidateTag('posts');
}
```

## Gotchas
- Router Cache cannot be programmatically cleared by revalidatePath alone on the client; router.refresh() flushes it
- cookies() or headers() in a layout opts the entire route into dynamic rendering
- next: { tags: ['posts'] } must be set at fetch time to use revalidateTag

## Related
- `next-js-data-fetching.md`
- `next-js-middleware-patterns.md`
