# TanStack Query v5 Optimistic Mutations with a Cloudflare Workers Backend

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a React app that talks to a Cloudflare Workers API backed by D1. You want mutations (create, update, delete) to feel instant by updating the UI before the network round-trip completes, then rolling back automatically if the Worker returns an error.

## Context

TanStack Query v5 changed `useMutation` options—`onMutate`, `onError`, and `onSettled` are now passed directly to `useMutation` (not to `mutate()`). The Workers endpoint validates input, writes to D1, and returns the canonical record. The optimistic update lives only in the query cache; if the Worker rejects the request the cache is restored from the snapshot taken in `onMutate`.

## Optimistic Mutation with Workers Backend

```typescript
// src/hooks/useCreateItem.ts
import {
  useMutation,
  useQueryClient,
  type InfiniteData,
} from '@tanstack/react-query';

interface Item {
  id: string;
  name: string;
  status: 'active' | 'archived';
  createdAt: string;
}

interface CreateItemInput {
  name: string;
}

async function createItem(input: CreateItemInput): Promise<Item> {
  const res = await fetch('/api/items', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const { error } = await res.json<{ error: string }>();
    throw new Error(error ?? 'Failed to create item');
  }
  return res.json<Item>();
}

export function useCreateItem() {
  const queryClient = useQueryClient();
  const QUERY_KEY = ['items'] as const;

  return useMutation({
    mutationFn: createItem,

    // 1. Snapshot current cache, then write optimistic entry
    async onMutate(newItem) {
      // Cancel any in-flight refetches so they don't overwrite our optimistic update
      await queryClient.cancelQueries({ queryKey: QUERY_KEY });

      // Snapshot the previous value for rollback
      const snapshot = queryClient.getQueryData<Item[]>(QUERY_KEY);

      // Optimistically prepend the new item with a temporary id
      queryClient.setQueryData<Item[]>(QUERY_KEY, (old = []) => [
        {
          id: `optimistic-${Date.now()}`,
          name: newItem.name,
          status: 'active',
          createdAt: new Date().toISOString(),
        },
        ...old,
      ]);

      // Return the snapshot so onError can roll back
      return { snapshot };
    },

    // 2. On Workers error: restore the snapshot
    onError(_error, _newItem, context) {
      if (context?.snapshot !== undefined) {
        queryClient.setQueryData<Item[]>(QUERY_KEY, context.snapshot);
      }
    },

    // 3. Always re-sync with the server after success or failure
    onSettled() {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}
```

```typescript
// workers/src/handlers/items.ts  — Cloudflare Workers endpoint
import { Env } from '../types';

export async function handleCreateItem(
  request: Request,
  env: Env
): Promise<Response> {
  let body: { name?: string };

  try {
    body = await request.json<{ name?: string }>();
  } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const name = body.name?.trim();
  if (!name || name.length < 2) {
    return Response.json(
      { error: 'name must be at least 2 characters' },
      { status: 422 }
    );
  }

  const id = crypto.randomUUID();
  const createdAt = new Date().toISOString();

  await env.DB.prepare(
    `INSERT INTO items (id, name, status, created_at)
     VALUES (?, ?, 'active', ?)`
  )
    .bind(id, name, createdAt)
    .run();

  const item = { id, name, status: 'active', createdAt };
  return Response.json(item, { status: 201 });
}
```

```typescript
// src/components/CreateItemForm.tsx
import { useCreateItem } from '../hooks/useCreateItem';

export function CreateItemForm() {
  const { mutate, isPending, isError, error } = useCreateItem();

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const name = (form.elements.namedItem('name') as HTMLInputElement).value;
    mutate({ name }, { onSuccess: () => form.reset() });
  }

  return (
    <form onSubmit={handleSubmit}>
      <input name="name" required minLength={2} />
      <button type="submit" disabled={isPending}>
        {isPending ? 'Saving...' : 'Add item'}
      </button>
      {isError && <p role="alert">{error.message}</p>}
    </form>
  );
}
```

## Cache Invalidation After Successful Mutation

`onSettled` always fires regardless of success or failure, making it the right place for `invalidateQueries`. This triggers a background refetch that reconciles the optimistic entry (with its temporary id) against the real server record.

If your list is paginated with `useInfiniteQuery`, invalidate the same key—TanStack Query refetches all loaded pages:

```typescript
onSettled() {
  queryClient.invalidateQueries({ queryKey: ['items'], exact: false });
}
```

## Workers Validation Pattern

Return `422 Unprocessable Entity` for validation failures (not `400`). The client `mutationFn` checks `res.ok` and throws with the server error message, which TanStack Query surfaces as `error.message` in the component. Do not throw on 404 for a create—treat it as a routing bug.

## Anti-patterns

- Placing `invalidateQueries` in `onSuccess` only—if the mutation succeeds but `onSettled` is not called on error, the cache stays stale after a rollback.
- Mutating the old array in `setQueryData` directly—always return a new array.
- Using the optimistic `id` (`optimistic-*`) in downstream logic—it is replaced after `invalidateQueries` refetches.
- Forgetting `cancelQueries` in `onMutate`—a concurrent background refetch can overwrite the optimistic state before the mutation completes.

## Gotchas

- TanStack Query v5 removed the `variables` argument from `onError` at the top level—the input is passed as the second argument of `onError(_err, variables, context)`.
- `useQueryClient()` must be called inside a component tree wrapped by `<QueryClientProvider>`.
- Workers D1 `run()` does not return inserted rows; use `RETURNING` or a separate `SELECT` if you need the full record back.
- If the Workers response is a non-JSON error page (e.g., a 522 from Cloudflare itself), `res.json()` throws—guard with try/catch in `mutationFn`.

## Verification

```bash
# Start Workers dev server
npx wrangler dev workers/src/index.ts --local

# In another terminal, start the React dev server
npm run dev

# Throttle the network in DevTools to "Slow 3G" and submit the form
# The optimistic item should appear immediately, then get a real id on refetch

# Simulate a 422: submit a single-character name — the optimistic entry
# should disappear and the form should show the server error message
```

## Related

- `nextjs-app-router-cloudflare-pages-adapter.md`
- `htmx-cloudflare-workers-hypermedia.md`

## Sources

- https://tanstack.com/query/v5/docs/framework/react/guides/optimistic-updates
- https://developers.cloudflare.com/d1/
- https://tanstack.com/query/v5/docs/framework/react/reference/useMutation
