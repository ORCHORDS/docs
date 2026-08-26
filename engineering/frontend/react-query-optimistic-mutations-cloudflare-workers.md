# React Query Optimistic Mutations with Cloudflare Workers API

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

You have a Cloudflare Worker handling your REST API and a React frontend using TanStack Query (React Query v5). When users submit mutations — adding items, toggling flags, editing records — the UI lags while the Worker round-trip completes. You want the UI to update immediately, then roll back cleanly if the Worker returns an error, without stale data leaking into the cache.

---

## Context

React Query's `useMutation` hook exposes `onMutate`, `onError`, and `onSettled` lifecycle hooks specifically for optimistic updates. The pattern is:

1. **`onMutate`** — snapshot the current cache, write the optimistic value, return the snapshot as rollback context.
2. **`onError`** — restore the snapshot if the Worker responds with an error.
3. **`onSettled`** — invalidate the query so the server's authoritative state replaces the optimistic value.

Cloudflare Workers return errors as JSON with a non-2xx status. React Query's default `queryFn` does **not** throw on non-2xx responses (unlike Axios) unless you explicitly check `response.ok`. Missing this causes the optimistic value to persist even after a failed mutation.

---

## Section 1: Worker API returning structured errors

```typescript
// workers/api/items.ts
export interface ApiError {
  error: string;
  code: string;
}

export async function handleUpdateItem(
  request: Request,
  env: Env,
): Promise<Response> {
  const { id, title } = await request.json<{ id: string; title: string }>();

  if (!title || title.trim().length === 0) {
    return Response.json(
      { error: "Title is required", code: "VALIDATION_ERROR" } satisfies ApiError,
      { status: 422 },
    );
  }

  const result = await env.DB.prepare(
    "UPDATE items SET title = ? WHERE id = ?",
  )
    .bind(title.trim(), id)
    .run();

  if (result.meta.changes === 0) {
    return Response.json(
      { error: "Item not found", code: "NOT_FOUND" } satisfies ApiError,
      { status: 404 },
    );
  }

  return Response.json({ id, title: title.trim() });
}
```

---

## Section 2: Typed fetch helper that throws on non-2xx

```typescript
// lib/api.ts
import type { ApiError } from "../workers/api/items";

export class ApiResponseError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiResponseError";
  }
}

export async function apiFetch<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    let body: ApiError = { error: res.statusText, code: "UNKNOWN" };
    try {
      body = await res.json();
    } catch {
      // response body was not JSON — use statusText fallback above
    }
    throw new ApiResponseError(res.status, body.code, body.error);
  }

  return res.json() as Promise<T>;
}
```

Without this wrapper, `fetch` resolves even on 422/404, and React Query treats the mutation as successful.

---

## Section 3: Query key factory and typed data shapes

```typescript
// lib/queries.ts
export interface Item {
  id: string;
  title: string;
  done: boolean;
  updatedAt: string;
}

export const itemKeys = {
  all: ["items"] as const,
  list: (filter?: string) => [...itemKeys.all, "list", filter ?? ""] as const,
  detail: (id: string) => [...itemKeys.all, "detail", id] as const,
} as const;

export async function fetchItems(filter?: string): Promise<Item[]> {
  const url = filter ? `/api/items?filter=${encodeURIComponent(filter)}` : "/api/items";
  return apiFetch<Item[]>(url);
}

export async function updateItem(payload: {
  id: string;
  title: string;
}): Promise<Item> {
  return apiFetch<Item>(`/api/items/${payload.id}`, {
    method: "PATCH",
    body: JSON.stringify({ title: payload.title }),
  });
}
```

---

## Section 4: Optimistic mutation hook with rollback

```typescript
// hooks/useUpdateItem.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { itemKeys, updateItem, type Item } from "../lib/queries";
import { ApiResponseError } from "../lib/api";

interface MutationContext {
  previousItems: Item[] | undefined;
  previousDetail: Item | undefined;
}

export function useUpdateItem(filter?: string) {
  const queryClient = useQueryClient();

  return useMutation<Item, ApiResponseError, { id: string; title: string }, MutationContext>({
    mutationFn: updateItem,

    onMutate: async (variables) => {
      // Cancel in-flight refetches to prevent them from overwriting the optimistic value
      await queryClient.cancelQueries({ queryKey: itemKeys.list(filter) });
      await queryClient.cancelQueries({ queryKey: itemKeys.detail(variables.id) });

      // Snapshot current cache values for rollback
      const previousItems = queryClient.getQueryData<Item[]>(itemKeys.list(filter));
      const previousDetail = queryClient.getQueryData<Item>(
        itemKeys.detail(variables.id),
      );

      // Optimistically update the list cache
      queryClient.setQueryData<Item[]>(itemKeys.list(filter), (old) =>
        old?.map((item) =>
          item.id === variables.id
            ? { ...item, title: variables.title, updatedAt: new Date().toISOString() }
            : item,
        ),
      );

      // Optimistically update the detail cache
      queryClient.setQueryData<Item>(itemKeys.detail(variables.id), (old) =>
        old ? { ...old, title: variables.title, updatedAt: new Date().toISOString() } : old,
      );

      return { previousItems, previousDetail };
    },

    onError: (_error, variables, context) => {
      // Roll back to the snapshots captured in onMutate
      if (context?.previousItems !== undefined) {
        queryClient.setQueryData(itemKeys.list(filter), context.previousItems);
      }
      if (context?.previousDetail !== undefined) {
        queryClient.setQueryData(
          itemKeys.detail(variables.id),
          context.previousDetail,
        );
      }
    },

    onSettled: (_data, _error, variables) => {
      // Always invalidate after the Worker responds — success or error —
      // so the cache reflects the authoritative server state.
      void queryClient.invalidateQueries({ queryKey: itemKeys.list(filter) });
      void queryClient.invalidateQueries({
        queryKey: itemKeys.detail(variables.id),
      });
    },
  });
}
```

---

## Section 5: Component wiring with error feedback

```tsx
// components/ItemRow.tsx
import { useState } from "react";
import { useUpdateItem } from "../hooks/useUpdateItem";
import { ApiResponseError } from "../lib/api";

interface Props {
  item: { id: string; title: string };
  filter?: string;
}

export function ItemRow({ item, filter }: Props) {
  const [draft, setDraft] = useState(item.title);
  const { mutate, isPending, error, reset } = useUpdateItem(filter);

  const isApiError = error instanceof ApiResponseError;

  function handleBlur() {
    if (draft === item.title) return;
    mutate(
      { id: item.id, title: draft },
      {
        onError: () => {
          // Reset local draft to the rolled-back server value
          setDraft(item.title);
        },
      },
    );
  }

  return (
    <li>
      <input
        value={draft}
        onChange={(e) => {
          reset(); // clear previous error before next attempt
          setDraft(e.target.value);
        }}
        onBlur={handleBlur}
        disabled={isPending}
        aria-invalid={isApiError ? "true" : undefined}
        aria-describedby={isApiError ? `error-${item.id}` : undefined}
      />
      {isPending && <span aria-live="polite">Saving…</span>}
      {isApiError && (
        <span id={`error-${item.id}`} role="alert" style={{ color: "red" }}>
          {error.message}
        </span>
      )}
    </li>
  );
}
```

---

## Section 6: Invalidation scoping to avoid over-fetching

`onSettled` above invalidates both list and detail. If the list query is expensive (large dataset, complex D1 query), prefer a targeted `setQueryData` on success instead:

```typescript
onSettled: (data, error, variables) => {
  if (data) {
    // Success: write the authoritative server response directly — no refetch
    queryClient.setQueryData<Item[]>(itemKeys.list(filter), (old) =>
      old?.map((item) => (item.id === data.id ? data : item)),
    );
    queryClient.setQueryData(itemKeys.detail(variables.id), data);
  } else {
    // Error path already handled in onError; still invalidate to resync
    void queryClient.invalidateQueries({ queryKey: itemKeys.list(filter) });
  }
},
```

This pattern is especially useful when the Worker response includes the full updated entity (as it should for PATCH endpoints).

---

## Anti-patterns

- **Not checking `response.ok`** — `fetch` resolves on 4xx/5xx. Without a throwing wrapper, `onError` never fires and the optimistic value sticks permanently.
- **Skipping `cancelQueries` in `onMutate`** — an in-flight background refetch can land after `onMutate` and overwrite the optimistic value before the mutation settles.
- **Rolling back in `onSettled` instead of `onError`** — `onSettled` fires on both success and error. Rollback logic belongs only in `onError`.
- **Using `queryClient.refetchQueries` in `onSettled`** — this triggers a network request immediately. Prefer `invalidateQueries`, which refetches only when the query's observer is active.
- **Forgetting `void` on `invalidateQueries`** — React Query v5 returns a Promise; not awaiting or voiding it can surface unhandled-rejection warnings.
- **Sharing mutation state across instances** — `useMutation` is per-component. If two components can mutate the same item, coordinate via the query cache, not the mutation state.

---

## Gotchas

- **Workers rate-limit on free tier** — 100,000 requests/day. Rapid optimistic saves from debounced inputs can exhaust this. Debounce or batch mutations.
- **D1's eventual consistency** — D1 writes are synchronous within a request, but if you read from a replica shortly after a write, you may get stale data. `onSettled` invalidation triggers a refetch that might hit a replica. Add a small delay or skip the refetch in favour of `setQueryData` with the response payload.
- **React Query v5 `error` type** — In v5, `error` is typed as `Error | null` by default. Use the generic `useMutation<Data, ErrorType, Variables, Context>` signature for proper `ApiResponseError` narrowing.
- **Multiple optimistic updates in flight** — if the user edits the same item twice rapidly, `onMutate` for the second call snapshots the optimistically-modified state from the first call, not the server state. Use a ref to track the "last known good" server state instead of relying on the cache snapshot.

---

## Verification

```bash
# 1. Start the Worker in local dev mode
npx wrangler dev --port 8787

# 2. Run the frontend dev server against the local Worker
VITE_API_URL=http://localhost:8787 npx vite

# 3. In the browser: edit an item title, confirm the UI updates before the
#    network request completes (Network tab → throttle to Slow 3G).

# 4. Force a 422 by submitting an empty title. Confirm:
#    - The UI rolls back to the original title.
#    - An error message appears.
#    - The Network tab shows a 422 from the Worker.

# 5. Unit test the hook with @testing-library/react and msw:
npx vitest run hooks/useUpdateItem.test.ts
```

---

## Related

- `react-query-cache-invalidation-workers-api-versioning.md`
- `optimistic-ui-updates-rollback.md`
- `zustand-workers-api-optimistic-updates.md`
- `form-validation-zod-workers-endpoint.md`
- `react-query-patterns.md`

---

## Sources

- TanStack Query v5 docs — Optimistic Updates: https://tanstack.com/query/v5/docs/framework/react/guides/optimistic-updates
- TanStack Query v5 docs — Mutations: https://tanstack.com/query/v5/docs/framework/react/guides/mutations
- Cloudflare D1 consistency model: https://developers.cloudflare.com/d1/learning/replication-and-consistency/
- Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/
