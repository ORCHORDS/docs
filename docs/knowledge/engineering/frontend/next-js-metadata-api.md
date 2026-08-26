# next-js-metadata-api

**Issue:** Managing <head> tags for SEO in App Router without react-helmet
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Pages share identical meta descriptions and Open Graph images; dynamic routes have no route-specific metadata.

## Pattern / Solution
```tsx
// Static metadata
export const metadata = {
  title: 'My App',
  description: 'Description here',
  openGraph: { images: ['/og.png'] },
};

// Dynamic metadata
export async function generateMetadata({ params }) {
  const post = await fetchPost(params.id);
  return {
    title: post.title,
    description: post.excerpt,
    openGraph: {
      title: post.title,
      images: [post.coverImage],
    },
  };
}
```

## Gotchas
- Metadata is merged from parent to child layouts; child overrides parent
- generateMetadata runs server-side; it can call the DB directly
- Twitter card uses openGraph values as fallback if twitter: is omitted

## Related
- `next-js-app-router-patterns.md`
- `html-web-vitals-lcp.md`
