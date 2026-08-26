# react-router-v7-patterns

**Issue:** React Router v7 merges Remix patterns; migration from v6 requires significant changes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
v6 loaders and actions are not typed; nested routes with data loading require manual wiring.

## Pattern / Solution
```tsx
// routes/posts.$id.tsx
import type { Route } from './+types/posts.$id';

export async function loader({ params }: Route.LoaderArgs) {
  const post = await fetchPost(params.id);
  if (!post) throw new Response('Not Found', { status: 404 });
  return post;
}

export default function Post({ loaderData }: Route.ComponentProps) {
  return <h1>{loaderData.title}</h1>;
}

export async function action({ request, params }: Route.ActionArgs) {
  const formData = await request.formData();
  await updatePost(params.id, formData);
  return redirect('/posts');
}
```

## Gotchas
- v7 route types are auto-generated from the routes config; run `react-router typegen`
- Loaders run on the server in SSR mode; do not include secrets in loaderData returned to the client
- ErrorBoundary export from the route file handles errors for that segment

## Related
- `tanstack-router-patterns.md`
- `next-js-app-router-patterns.md`
