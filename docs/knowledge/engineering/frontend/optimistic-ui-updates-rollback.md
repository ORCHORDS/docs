# optimistic-ui-updates-rollback

**Issue:** A like button takes 300ms of perceived lag because the UI waits for the mutation response before rendering; or worse, the UI updates instantly but a failed request leaves the app showing state the server never accepted. Teams want instant feedback for mutations (likes, toggles, reorders, inline edits) but hand-rolled optimistic updates break under concurrency: two rapid mutations, a failure, and a rollback that restores a snapshot older than the other mutation's result. The pattern needs a deliberate snapshot-cancel-restore discipline, and in React 19 there are now two layers to coordinate (`useOptimistic` for render-level UI, cache-layer updates for data).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When to be optimistic (and when not)

1. **Be optimistic for low-stakes, easily-reversible mutations.** Toggles, favorites, pin/unpin, reorder, mark-as-read: the user's intent is unambiguous, the payload is tiny, and failure is rare. Showing the result immediately and rolling back on error is strictly better UX than a spinner.
2. **Do not be optimistic for creation with server-assigned identity.** "Add comment" optimistically rendered without a real ID breaks reply threading, permalinks, and edit once the server response arrives. Either optimistically render with a temp ID clearly marked, or accept one round-trip and use a pending state.
3. **Do not be optimistic for anything with money or side effects.** Payments, sends, deletes-of-collections, and rate-limited actions should show explicit pending states. A wrong optimistic payment that flickers and rolls back destroys more trust than a 500ms spinner.
4. **Weigh server error rate.** Optimistic UI trades perceived speed for occasional visible rollback. If a mutation fails more than a few percent of the time (flaky mobile networks, strict validation), the rollback flash becomes the dominant experience — fix validation client-side first or go pessimistic.

## The canonical snapshot-cancel-restore pattern (TanStack Query)

1. **Cancel in-flight refetches before mutating the cache.** `await queryClient.cancelQueries({ queryKey: ['todos'] })` in `onMutate` prevents a background refetch from landing mid-mutation and overwriting your optimistic value with stale server data. This is the step everyone forgets.
2. **Snapshot the previous cache and return it as context.** `const previous = queryClient.getQueryData(['todos'])` then `return { previous }`. The value returned from `onMutate` is passed to `onError` and `onSettled` — this is the rollback payload, and it is per-mutation-instance, which is what makes concurrent mutations workable.
3. **Write the optimistic value with `setQueryData`.** Apply a minimal patch (update the one entity, append the one item), not a wholesale replacement. Structural sharing in TanStack Query means a minimal patch re-renders only affected components.
4. **Roll back in `onError` by restoring the snapshot.** `queryClient.setQueryData(['todos'], context?.previous)`. Pair this with a user-visible error toast — a silent rollback makes users think the tap did not register, so they tap again.
5. **Reconcile with the server in `onSettled` regardless of outcome.** Always `invalidateQueries` after the mutation settles. Optimistic state is a prediction; invalidation is the correction mechanism that guarantees eventual consistency even when the rollback itself races with a refetch.

## React 19 `useOptimistic` and how the two layers compose

1. **`useOptimistic` is a render-layer mechanism only.** It holds an optimistic value that overrides the real prop/state while a transition is pending and automatically reverts when the transition settles. It does not touch any cache, does not dedupe, and does not coordinate refetches — treating it as a cache replacement is the most common misuse.
2. **Use it for UI chrome, use the cache layer for data.** A "like" count from server cache + `useOptimistic` for the heart animation both driven by the same action works well. But the snapshot-rollback in the query cache is still needed for lists and detail views shared across routes.
3. **Pass the optimistic value through actions, not effects.** `useOptimistic` pairs with form actions: the action fires, the optimistic value shows immediately, the transition finishes and reality takes over. Triggering it from `useEffect` on a pending flag reintroduces the flicker it exists to remove.
4. **Server Actions make the rollback automatic but coarse.** With `useActionState`/Server Actions, React reverts optimistic state when the action settles, but you still own cache invalidation via `revalidatePath`/`revalidateTag` — a missing revalidation is why the UI "rolls forward" to stale data after a successful action.

## Concurrency and correctness traps

1. **The stale-rollback race.** Mutation A and B both snapshot version 5; A succeeds (cache now v6 with A applied); B fails and restores its snapshot v5 — silently undoing A. TkDodo's analysis fixes this with mutation counts or per-item optimistic flags (apply `optimistic: true` markers to items and roll back by removing markers, not by restoring whole-list snapshots).
2. **Out-of-order responses.** If mutation A (started first) resolves after mutation B, applying A's server response last can clobber B. Key cache patches to the entity ID and version/timestamp, and ignore responses older than the cache's current version for the same entity.
3. **Duplicated submissions.** Rapid double-clicks fire two mutations and one rollback. Disable the trigger during flight (or debounce), and give mutations idempotency keys server-side so a duplicate is a no-op rather than a double-like.
4. **Rollback that loses the user's input.** For inline-edit optimistic updates, keep the failed draft in local state (or re-open the editor with the attempted value) instead of reverting to the snapshot and discarding what the user typed.
5. **Optimistic updates to paginated lists.** Appending an item to page 3 while the server later inserts it on page 1 double-counts after refetch. For lists where position matters, be optimistic only about the item's existence (show it in a "your recent items" region) and let refetch place it canonically.

## Testing

1. **Test the failure path first.** Mock the mutation to reject and assert the cache returns to the snapshot AND the error UI appears. Most optimistic-update tests only assert the happy path, which is where bugs are not.
2. **Test two interleaved mutations.** Fire A then B, resolve B then A, then fail A — assert B's effect survives. This is the concurrency case that snapshot-restore gets wrong and marker-based rollback gets right.
3. **Assert on visible UI, not just cache internals.** A rollback that restores the cache but leaves the heart filled in (because the component derives from `useOptimistic` state nobody reset) passes cache assertions and still shows wrong UI. Use Testing Library queries against what the user sees.
4. **Related reading in this knowledge base:** `react-19-actions-useactionstate.md` for the action layer, `react-query-patterns.md` and `apollo-client-patterns.md` for cache mechanics, `swr-vs-react-query.md` for mutation-support tradeoffs.
