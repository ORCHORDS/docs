# React useOptimistic with Cloudflare Workers API

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

UI updates feel laggy because the component waits for the Workers API response before reflecting the user's action. A "like" button, a todo toggle, or a cart quantity increment should update the UI immediately and roll back only if the server call fails. React 19's `useOptimistic` hook provides a built-in mechanism for this pattern without third-party state managers.

## Context

`useOptimistic` (stable in React 19) returns an optimistic state value and an updater. Inside an async transition or a Server Action, React holds the "real" state while displaying the optimistic overlay. When the async operation settles, the overlay is discarded and the real state (returned from the server) takes over. On Cloudflare Workers, the "server" is a Worker endpoint returning JSON; the pattern works identically to React Server Actions because `useOptimistic` is a client-side hook that does not require Next.js or a framework with built-in actions.

---

## Basic useOptimistic Toggle

```typescript
// src/components/LikeButton.tsx
'use client';

import { useOptimistic, useTransition } from 'react';

interface Props {
  postId: string;
  initialLiked: boolean;
  initialCount: number;
}

interface LikeState {
  liked: boolean;
  count: number;
}

async function toggleLikeOnWorker(
  postId: string,
  liked: boolean,
): Promise<LikeState> {
  const res = await fetch(`/api/posts/${postId}/like`, {
    method: liked ? 'DELETE' : 'POST',
    headers: { 'content-type': 'application/json' },
  });
  if (!res.ok) throw new Error(`Like failed: ${res.status}`);
  return res.json() as Promise<LikeState>;
}

export function LikeButton({ postId, initialLiked, initialCount }: Props) {
  const [serverState, setServerState] = React.useState<LikeState>({
    liked: initialLiked,
    count: initialCount,
  });

  const [optimisticState, setOptimistic] = useOptimistic(
    serverState,
    (current, newLiked: boolean) => ({
      liked: newLiked,
      count: current.count + (newLiked ? 1 : -1),
    }),
  );

  const [isPending, startTransition] = useTransition();

  function handleClick() {
    startTransition(async () => {
      const nextLiked = !serverState.liked;
      setOptimistic(nextLiked);           // renders immediately

      try {
        const result = await toggleLikeOnWorker(postId, serverState.liked);
        setServerState(result);           // server truth replaces optimistic
      } catch {
        // setOptimistic rolled back automatically when transition ends
        // setServerState is NOT called, so serverState remains unchanged
      }
    });
  }

  return (
    <button
      onClick={handleClick}
      disabled={isPending}
      aria-pressed={optimisticState.liked}
      aria-label={`${optimisticState.liked ? 'Unlike' : 'Like'} post`}
    >
      {optimisticState.liked ? '♥' : '♡'} {optimisticState.count}
    </button>
  );
}
```

---

## Cloudflare Worker Endpoint

```typescript
// functions/api/posts/[postId]/like.ts
import type { PagesFunction } from '@cloudflare/workers-types';

interface Env {
  LIKES: KVNamespace;
}

interface LikeState {
  liked: boolean;
  count: number;
}

async function getCount(kv: KVNamespace, postId: string): Promise<number> {
  const raw = await kv.get(`likes:count:${postId}`);
  return raw ? parseInt(raw, 10) : 0;
}

export const onRequestPost: PagesFunction<Env> = async ({ params, env, request }) => {
  const postId = String(params.postId);
  const userId = request.headers.get('x-user-id') ?? 'anon';

  const alreadyLiked = await env.LIKES.get(`likes:user:${userId}:${postId}`);
  if (alreadyLiked) {
    return Response.json({ liked: true, count: await getCount(env.LIKES, postId) });
  }

  await env.LIKES.put(`likes:user:${userId}:${postId}`, '1');
  const count = (await getCount(env.LIKES, postId)) + 1;
  await env.LIKES.put(`likes:count:${postId}`, String(count));

  return Response.json({ liked: true, count } satisfies LikeState);
};

export const onRequestDelete: PagesFunction<Env> = async ({ params, env, request }) => {
  const postId = String(params.postId);
  const userId = request.headers.get('x-user-id') ?? 'anon';

  await env.LIKES.delete(`likes:user:${userId}:${postId}`);
  const count = Math.max(0, (await getCount(env.LIKES, postId)) - 1);
  await env.LIKES.put(`likes:count:${postId}`, String(count));

  return Response.json({ liked: false, count } satisfies LikeState);
};
```

---

## Optimistic List Mutation (Add Item)

```typescript
// src/components/TodoList.tsx
'use client';

import { useOptimistic, useTransition, useState } from 'react';

interface Todo {
  id: string;
  text: string;
  done: boolean;
}

async function addTodo(text: string): Promise<Todo> {
  const res = await fetch('/api/todos', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error('Failed to add todo');
  return res.json() as Promise<Todo>;
}

export function TodoList({ initialTodos }: { initialTodos: Todo[] }) {
  const [todos, setTodos] = useState<Todo[]>(initialTodos);
  const [optimisticTodos, addOptimistic] = useOptimistic(
    todos,
    (current, newTodo: Todo) => [...current, newTodo],
  );

  const [, startTransition] = useTransition();

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const text = String(fd.get('text') ?? '').trim();
    if (!text) return;
    (e.currentTarget as HTMLFormElement).reset();

    const tempId = `optimistic-${Date.now()}`;

    startTransition(async () => {
      addOptimistic({ id: tempId, text, done: false });

      try {
        const created = await addTodo(text);
        setTodos((prev) => [...prev, created]);
      } catch {
        // Optimistic item disappears automatically; show a toast externally
        console.error('Failed to create todo; rolling back');
      }
    });
  }

  return (
    <>
      <form onSubmit={handleSubmit}>
        <input name="text" placeholder="New task…" required />
        <button type="submit">Add</button>
      </form>
      <ul>
        {optimisticTodos.map((todo) => (
          <li
            key={todo.id}
            style={{ opacity: todo.id.startsWith('optimistic-') ? 0.6 : 1 }}
          >
            {todo.text}
          </li>
        ))}
      </ul>
    </>
  );
}
```

---

## Combining useOptimistic with React 19 Form Actions

React 19 `<form action={serverAction}>` integrates directly with `useOptimistic` when using Next.js or Remix with Workers adapters.

```typescript
// app/actions.ts (Next.js App Router on Cloudflare)
'use server';

import { revalidatePath } from 'next/cache';

export async function toggleLike(formData: FormData): Promise<void> {
  const postId = String(formData.get('postId'));
  // Call internal Worker endpoint or D1 directly
  await fetch(`${process.env.WORKER_INTERNAL}/api/posts/${postId}/like`, {
    method: 'POST',
  });
  revalidatePath(`/posts/${postId}`);
}
```

```typescript
// app/components/LikeFormButton.tsx
'use client';

import { useOptimistic } from 'react';
import { toggleLike } from '../actions';

export function LikeFormButton({
  postId,
  liked,
  count,
}: { postId: string; liked: boolean; count: number }) {
  const [optimistic, setOptimistic] = useOptimistic({ liked, count });

  return (
    <form
      action={async (fd) => {
        setOptimistic({ liked: !liked, count: count + (liked ? -1 : 1) });
        await toggleLike(fd);
      }}
    >
      <input type="hidden" name="postId" value={postId} />
      <button type="submit">
        {optimistic.liked ? '♥' : '♡'} {optimistic.count}
      </button>
    </form>
  );
}
```

---

## Error Recovery and Toast Integration

```typescript
// useOptimisticWithToast.ts
import { useOptimistic, useTransition } from 'react';

type MutationFn<T, A> = (arg: A) => Promise<T>;
type Reducer<T, A> = (state: T, arg: A) => T;

export function useOptimisticMutation<T, A>(
  state: T,
  reducer: Reducer<T, A>,
  mutate: MutationFn<T, A>,
  onSuccess: (result: T) => void,
  onError: (err: unknown) => void,
) {
  const [optimistic, setOptimistic] = useOptimistic(state, reducer);
  const [isPending, startTransition] = useTransition();

  function dispatch(arg: A) {
    startTransition(async () => {
      setOptimistic(arg);
      try {
        const result = await mutate(arg);
        onSuccess(result);
      } catch (err) {
        onError(err);
      }
    });
  }

  return { optimistic, isPending, dispatch };
}
```

---

## Anti-patterns

- **Calling `setOptimistic` outside a `startTransition`** – `useOptimistic` updates are tied to transitions; without `startTransition`, the optimistic value does not display before the await.
- **Using `useOptimistic` for local UI state** – it is designed for async mutations; for immediate local state, use `useState` with manual rollback.
- **Assuming rollback is automatic for all errors** – rollback only happens when the transition completes without calling `setRealState`; if you call `setRealState(errorValue)` on failure, you must manage rollback yourself.
- **Mutating the optimistic state directly** – always return a new object/array from the reducer; mutation bypasses React's reconciler.
- **Not reflecting the returned server state** – after the await, call `setServerState(serverResult)` to sync; without it, the UI snaps back to the pre-mutation state.

---

## Gotchas

- `useOptimistic` is exported from `react` in React 19; in React 18 it lives in `react-dom` as an experimental API — the import path differs.
- The `isPending` from `useTransition` is true during the entire async operation including the Workers round-trip; disable inputs during this window to prevent double submissions.
- Cloudflare Workers respond in ~10–50 ms globally; the optimistic state is visible for a very short time, but users on poor connections (~200–500 ms RTT) will see it clearly — make the visual treatment intentional (opacity, spinner).
- `useOptimistic` does not debounce; rapid clicks generate rapid transitions; implement a guard or use a queue if the endpoint is not idempotent.
- When using with Remix `useFetcher`, `useOptimistic` is redundant — Remix already exposes `fetcher.formData` for in-flight optimistic data.

---

## Verification

```typescript
// __tests__/LikeButton.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LikeButton } from '../LikeButton';

global.fetch = vi.fn().mockResolvedValue(
  new Response(JSON.stringify({ liked: true, count: 6 }), { status: 200 }),
);

test('shows optimistic like count before server responds', async () => {
  render(<LikeButton postId="1" initialLiked={false} initialCount={5} />);
  fireEvent.click(screen.getByRole('button'));

  // Optimistic state shows immediately
  expect(screen.getByText(/6/)).toBeInTheDocument();
  expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true');

  // Server state confirms
  await waitFor(() => {
    expect(screen.getByText(/6/)).toBeInTheDocument();
  });
});
```

---

## Related

- `react-query-optimistic-mutations-cloudflare-workers.md`
- `optimistic-ui-updates-rollback.md`
- `react-19-actions-useactionstate.md`
- `react-server-actions.md`
- `zustand-workers-api-optimistic-updates.md`

---

## Sources

- https://react.dev/reference/react/useOptimistic
- https://react.dev/reference/react/useTransition
- https://developers.cloudflare.com/kv/
- https://react.dev/blog/2024/12/05/react-19
