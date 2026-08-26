# Zustand State Management with Workers API Optimistic Updates

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You use Zustand for client state and Cloudflare Workers as your API backend. UI actions
(item add, quantity change, delete) need to feel instant on mobile but the Worker response
is 50–200 ms away. Naively waiting for the fetch means the UI freezes. Naively applying
changes without rollback means users see incorrect state when the Worker returns an error.

The goal: apply mutations optimistically, queue them so concurrent actions don't race, and
roll back with a toast on failure — all without pulling in a full server-state library.

---

## Context

Zustand is a lean (~1 kB gzip) client state manager. Unlike React Query / SWR it has no
built-in server-state semantics. When you use Zustand to cache API data locally (common in
mobile apps that want instant local updates), you take on responsibility for:

- Applying the change immediately ("optimistic state")
- Tracking in-flight mutations
- Rolling back the slice to the pre-mutation snapshot on network failure
- Preventing concurrent mutations from clobbering each other

Cloudflare Workers add a wrinkle: edge functions are stateless by request. If the Worker
returns `HTTP 409 Conflict` (e.g., concurrency conflict in D1 or KV), the client must
interpret that as a rollback signal, not a network error.

---

## Section 1 — Store Shape with Optimistic Patch Stack

```ts
// store/cart-store.ts
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';

export interface CartItem {
  id: string;
  name: string;
  quantity: number;
  price: number;
}

interface CartSlice {
  items: CartItem[];
  // Stack of snapshots for rollback; one per in-flight mutation
  _snapshots: CartItem[][];
  _inflightCount: number;
}

interface CartActions {
  // Optimistic mutators — each returns a rollback function
  addItem: (item: CartItem) => () => void;
  updateQuantity: (id: string, qty: number) => () => void;
  removeItem: (id: string) => () => void;
  // Called after successful API response to confirm the mutation
  confirmMutation: () => void;
}

export const useCartStore = create<CartSlice & CartActions>()(
  immer((set, get) => ({
    items: [],
    _snapshots: [],
    _inflightCount: 0,

    addItem(item) {
      const snapshot = structuredClone(get().items);
      set((s) => {
        s._snapshots.push(snapshot);
        s._inflightCount++;
        const existing = s.items.find((i) => i.id === item.id);
        if (existing) {
          existing.quantity += item.quantity;
        } else {
          s.items.push(item);
        }
      });
      // Return rollback function
      return () =>
        set((s) => {
          const snap = s._snapshots.pop();
          if (snap) s.items = snap;
          s._inflightCount = Math.max(0, s._inflightCount - 1);
        });
    },

    updateQuantity(id, qty) {
      const snapshot = structuredClone(get().items);
      set((s) => {
        s._snapshots.push(snapshot);
        s._inflightCount++;
        const item = s.items.find((i) => i.id === id);
        if (item) item.quantity = qty;
        // Remove if zero
        if (qty <= 0) s.items = s.items.filter((i) => i.id !== id);
      });
      return () =>
        set((s) => {
          const snap = s._snapshots.pop();
          if (snap) s.items = snap;
          s._inflightCount = Math.max(0, s._inflightCount - 1);
        });
    },

    removeItem(id) {
      const snapshot = structuredClone(get().items);
      set((s) => {
        s._snapshots.push(snapshot);
        s._inflightCount++;
        s.items = s.items.filter((i) => i.id !== id);
      });
      return () =>
        set((s) => {
          const snap = s._snapshots.pop();
          if (snap) s.items = snap;
          s._inflightCount = Math.max(0, s._inflightCount - 1);
        });
    },

    confirmMutation() {
      set((s) => {
        s._snapshots.pop();
        s._inflightCount = Math.max(0, s._inflightCount - 1);
      });
    },
  }))
);
```

---

## Section 2 — Mutation Hook with Workers API

```ts
// hooks/use-cart-mutation.ts
import { useCallback, useRef } from 'react';
import { useCartStore } from '@/store/cart-store';
import { useToast } from '@/components/toast';
import type { CartItem } from '@/store/cart-store';

interface MutationQueue {
  promise: Promise<void>;
}

// Module-level queue: serialises all mutations so they don't race
const queue: MutationQueue = { promise: Promise.resolve() };

function enqueue(fn: () => Promise<void>): Promise<void> {
  return (queue.promise = queue.promise.then(fn, fn));
}

export function useCartMutation() {
  const { addItem, updateQuantity, removeItem, confirmMutation } = useCartStore();
  const { showToast } = useToast();

  const mutate = useCallback(
    (
      optimisticAction: () => () => void,
      apiFn: () => Promise<Response>
    ) => {
      const rollback = optimisticAction();
      enqueue(async () => {
        try {
          const res = await apiFn();
          if (!res.ok) {
            // Worker returned an error (409, 422, 500, …)
            const { message } = await res.json<{ message?: string }>().catch(() => ({}));
            rollback();
            showToast({ type: 'error', message: message ?? 'Action failed. Try again.' });
            return;
          }
          confirmMutation();
        } catch {
          // Network failure
          rollback();
          showToast({ type: 'error', message: 'Connection lost. Change reverted.' });
        }
      });
    },
    [confirmMutation, showToast]
  );

  return {
    addToCart(item: CartItem) {
      mutate(
        () => addItem(item),
        () => fetch('/api/cart', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ itemId: item.id, quantity: item.quantity }),
        })
      );
    },

    updateQty(id: string, qty: number) {
      mutate(
        () => updateQuantity(id, qty),
        () => fetch(`/api/cart/${id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ quantity: qty }),
        })
      );
    },

    removeFromCart(id: string) {
      mutate(
        () => removeItem(id),
        () => fetch(`/api/cart/${id}`, { method: 'DELETE' })
      );
    },
  };
}
```

---

## Section 3 — Hydrating Zustand from the Workers API (SSR-safe)

On first load, the cart should be populated from the server (not localStorage) so the user
sees an accurate server-authoritative state.

```ts
// store/cart-store.ts  (add to slice)
interface CartActions {
  // ...existing...
  hydrate: (items: CartItem[]) => void;
}

// inside create():
hydrate(items) {
  set((s) => { s.items = items; });
},
```

In the Next.js route (App Router server component):

```tsx
// app/layout.tsx or app/(shop)/cart/page.tsx
import { CartStoreHydrator } from '@/components/cart-store-hydrator';
import { fetchCartFromWorker } from '@/lib/cart-api';
import { cookies } from 'next/headers';

export default async function ShopLayout({ children }: { children: React.ReactNode }) {
  const sessionId = (await cookies()).get('session')?.value;
  const initialCart = sessionId ? await fetchCartFromWorker(sessionId) : [];

  return (
    <>
      {/* Hydrates the Zustand store with server data before any client interaction */}
      <CartStoreHydrator items={initialCart} />
      {children}
    </>
  );
}
```

```tsx
// components/cart-store-hydrator.tsx
'use client';
import { useEffect } from 'react';
import { useCartStore } from '@/store/cart-store';
import type { CartItem } from '@/store/cart-store';

export function CartStoreHydrator({ items }: { items: CartItem[] }) {
  const hydrate = useCartStore((s) => s.hydrate);
  // Run once on mount — items come from the server component
  useEffect(() => { hydrate(items); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}
```

---

## Section 4 — Derived Selectors and Pending-State UI

Use fine-grained selectors to avoid re-renders and show a pending indicator:

```tsx
// components/cart-badge.tsx
'use client';
import { useCartStore } from '@/store/cart-store';

export function CartBadge() {
  // Only re-renders when total count changes — not on every store write
  const totalQty = useCartStore((s) => s.items.reduce((acc, i) => acc + i.quantity, 0));
  const isPending = useCartStore((s) => s._inflightCount > 0);

  return (
    <div
      style={{ position: 'relative', display: 'inline-flex' }}
      aria-label={`Cart: ${totalQty} items${isPending ? ' (saving…)' : ''}`}
    >
      <CartIcon />
      {totalQty > 0 && (
        <span
          style={{
            // Mobile: ensure badge is outside the 44px tap target
            position: 'absolute',
            top: -6,
            right: -6,
            minWidth: 18,
            height: 18,
            borderRadius: '50%',
            background: isPending ? '#888' : '#e53e3e',
            color: '#fff',
            fontSize: 11,
            lineHeight: '18px',
            textAlign: 'center',
            padding: '0 4px',
            transition: 'background 200ms',
          }}
        >
          {totalQty}
        </span>
      )}
    </div>
  );
}
```

---

## Anti-patterns

- **Keeping full server responses in Zustand** — Zustand is for UI/client state; don't
  duplicate large payloads that React Query or SWR already manages. Use Zustand only for
  ephemeral local mutations and combine with a server-state layer for the canonical data.
- **Calling `get()` inside the queue closure** — by the time the async fn runs, the store
  may have changed. Capture any needed values before enqueuing.
- **`Promise.all` for concurrent mutations** — if two mutations race and both fail, both
  rollbacks fire against different snapshots. The module-level serial queue prevents this;
  don't bypass it with `Promise.all`.
- **Using `localStorage` as the rollback source** — the snapshot must come from in-memory
  state at mutation time. `localStorage` may be stale or unavailable in incognito.
- **Not handling `409 Conflict` from D1** — D1 serialises writes per row but can return
  conflicts on concurrent requests. Treat `409` as a soft rollback; show "Someone else
  updated this — refreshing…" and re-hydrate from the server.

---

## Gotchas

- `structuredClone` is available in Workers and modern browsers (Chrome 98+, Safari 15.4+).
  For older Safari (< 15.4), polyfill with `JSON.parse(JSON.stringify(...))` — works for
  plain objects without `Date` / `Map`.
- Zustand's `immer` middleware requires `immer` 9.x+. It patches the draft in place; the
  return value of a `set` call using immer is ignored — never `return` from an immer setter.
- The `enqueue` pattern is module-level — it persists across React renders and component
  unmounts. This is intentional for a cart, but can cause issues in tests. Reset in
  `beforeEach` with `queue.promise = Promise.resolve()`.
- Zustand slices are not per-user on SSR. When using Next.js App Router's per-request server
  components, never import a singleton Zustand store in a server component — create it in the
  client and hydrate via the `CartStoreHydrator` pattern above.

---

## Verification

1. Add an item to the cart. Confirm the badge updates before the network request completes
   (DevTools → Network → throttle to "Slow 4G", add item, watch badge increment immediately).
2. Force a 500 response from the Worker (temporarily). Confirm the badge reverts and a toast
   appears within ~300 ms of the error response.
3. Rapidly click "Add" 5 times. Confirm only one request is in-flight at a time (serial
   queue) and the final quantity is correct.
4. Disconnect network, add item, reconnect. Confirm rollback toast appears (offline failure
   path via `catch`).

---

## Related

- `react-state-management-zustand.md`
- `optimistic-ui-updates-rollback.md`
- `react-query-cache-invalidation-workers-api-versioning.md`
- `react-query-server-state-management.md`
- `toast-notification-system-architecture.md`

---

## Sources

- Zustand docs: https://docs.pmnd.rs/zustand/getting-started/introduction
- Immer middleware: https://docs.pmnd.rs/zustand/integrations/immer-middleware
- Cloudflare Workers D1 concurrency: https://developers.cloudflare.com/d1/reference/transactions/
- MDN structuredClone: https://developer.mozilla.org/en-US/docs/Web/API/structuredClone
