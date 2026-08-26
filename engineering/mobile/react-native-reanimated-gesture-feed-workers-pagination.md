# React Native Reanimated Gesture-Driven Feed with Cloudflare Workers Pagination

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

The example project anonymous feed is a vertically snapping full-screen card feed, similar to TikTok's design but loading short-form anonymous posts from a Cloudflare Workers + D1 cursor-paginated API. Problems encountered:

- The feed freezes during pagination fetches because the data load runs on the JS thread, competing with Reanimated's UI-thread animations
- Cards jank when the user swipes quickly because the next page isn't prefetched early enough
- The snap animation fires before the new data is available, resulting in a blank card flash
- Overscrolling the last page shows an infinite spinner with no "end of feed" state
- Gesture conflicts between the vertical pan and the horizontal swipe-to-dismiss on individual cards

---

## Context

Stack: React Native 0.76+ (New Architecture / Fabric), `react-native-reanimated` v3, `react-native-gesture-handler` v2, TypeScript, Zustand, TanStack Query v5 for data fetching.

Cloudflare Worker pagination contract:
- `GET /feed?cursor=<opaque>&limit=10`
- Response: `{ posts: Post[], nextCursor: string | null }`
- `cursor` is a base64-encoded D1 row ID, not a page number
- `null` nextCursor means end of feed

The feed renders one post per screen height. Snap targets are multiples of `windowHeight`. Pagination triggers when the user reaches the 7th of 10 loaded cards (3 cards before the end).

---

## Cloudflare Worker: Cursor-Paginated Feed Endpoint

```typescript
// workers/src/feed/list.ts
import { D1Database } from '@cloudflare/workers-types';

interface Env { DB: D1Database; }

export async function handleFeedList(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const limit = Math.min(parseInt(url.searchParams.get('limit') ?? '10'), 50);
  const cursor = url.searchParams.get('cursor');

  let rowId: number | null = null;
  if (cursor) {
    try {
      rowId = parseInt(atob(cursor), 10);
    } catch {
      return new Response(JSON.stringify({ error: 'invalid_cursor' }), { status: 400 });
    }
  }

  const stmt = rowId
    ? env.DB.prepare(
        `SELECT id, content, created_at FROM posts
         WHERE id < ?1 AND deleted = 0
         ORDER BY id DESC LIMIT ?2`
      ).bind(rowId, limit + 1)
    : env.DB.prepare(
        `SELECT id, content, created_at FROM posts
         WHERE deleted = 0
         ORDER BY id DESC LIMIT ?1`
      ).bind(limit + 1);

  const rows = await stmt.all<{ id: number; content: string; created_at: string }>();

  const hasMore = rows.results.length > limit;
  const posts = rows.results.slice(0, limit);
  const nextCursor = hasMore ? btoa(String(posts[posts.length - 1].id)) : null;

  return new Response(
    JSON.stringify({ posts, nextCursor }),
    { headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } }
  );
}
```

---

## TanStack Query Infinite Feed Hook

```typescript
// src/hooks/useFeed.ts
import { useInfiniteQuery } from '@tanstack/react-query';
import { apiClient } from '../auth/apiClient';

export interface Post {
  id: number;
  content: string;
  created_at: string;
}

interface FeedPage {
  posts: Post[];
  nextCursor: string | null;
}

async function fetchFeedPage({ pageParam }: { pageParam: string | null }): Promise<FeedPage> {
  const url = pageParam
    ? `/feed?cursor=${encodeURIComponent(pageParam)}&limit=10`
    : '/feed?limit=10';
  const { data } = await apiClient.get<FeedPage>(url);
  return data;
}

export function useFeed() {
  return useInfiniteQuery({
    queryKey: ['feed'],
    queryFn: fetchFeedPage,
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    staleTime: 30_000,
  });
}
```

---

## Reanimated Vertical Snap Feed

The key insight: run the snap animation entirely on the UI thread via `useAnimatedGestureHandler` and `withSpring`. Never read from a React state variable inside an animation worklet.

```typescript
// src/components/SnapFeed.tsx
import React, { useCallback, useEffect } from 'react';
import { Dimensions, View, StyleSheet } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  runOnJS,
} from 'react-native-reanimated';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { useFeed, Post } from '../hooks/useFeed';

const { height: WINDOW_HEIGHT } = Dimensions.get('window');
const SNAP_THRESHOLD = WINDOW_HEIGHT * 0.25;
const PREFETCH_TRIGGER_INDEX = 7; // of 10 per page

interface SnapFeedProps {
  onIndexChange?: (index: number) => void;
}

export function SnapFeed({ onIndexChange }: SnapFeedProps) {
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useFeed();

  const posts: Post[] = data?.pages.flatMap((p) => p.posts) ?? [];
  const totalCount = posts.length;

  const translateY = useSharedValue(0);
  const currentIndex = useSharedValue(0);

  // Notify JS side of index changes for prefetch decisions
  const handleIndexChange = useCallback(
    (index: number) => {
      onIndexChange?.(index);
      if (index >= totalCount - (10 - PREFETCH_TRIGGER_INDEX) && hasNextPage && !isFetchingNextPage) {
        fetchNextPage();
      }
    },
    [totalCount, hasNextPage, isFetchingNextPage, fetchNextPage, onIndexChange]
  );

  const panGesture = Gesture.Pan()
    .activeOffsetY([-10, 10]) // only vertical pans activate
    .failOffsetX([-20, 20])   // horizontal gesture claims win — avoids conflict
    .onUpdate((e) => {
      translateY.value = -currentIndex.value * WINDOW_HEIGHT + e.translationY;
    })
    .onEnd((e) => {
      const velocity = e.velocityY;
      const moved = e.translationY;

      let nextIndex = currentIndex.value;

      if (moved < -SNAP_THRESHOLD || velocity < -500) {
        nextIndex = Math.min(currentIndex.value + 1, totalCount - 1);
      } else if (moved > SNAP_THRESHOLD || velocity > 500) {
        nextIndex = Math.max(currentIndex.value - 1, 0);
      }

      currentIndex.value = nextIndex;
      translateY.value = withSpring(-nextIndex * WINDOW_HEIGHT, {
        damping: 20,
        stiffness: 200,
        mass: 0.5,
      });

      // Crossing to JS is safe here — it's after the spring is dispatched
      runOnJS(handleIndexChange)(nextIndex);
    });

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: translateY.value }],
  }));

  return (
    <GestureDetector gesture={panGesture}>
      <Animated.View style={[styles.container, animatedStyle]}>
        {posts.map((post, index) => (
          <FeedCard key={post.id} post={post} index={index} />
        ))}
        {isFetchingNextPage && (
          <View style={styles.card}>
            {/* loading skeleton, not a spinner — avoids flash */}
            <CardSkeleton />
          </View>
        )}
      </Animated.View>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  card: { width: '100%', height: WINDOW_HEIGHT },
});
```

---

## Preventing Blank Card Flash on Page Boundary

When the last loaded card is swiped to, `fetchNextPage` fires. If `withSpring` settles before the next page arrives, the user sees an empty card at `totalCount` index.

Solution: gate the snap target to `Math.min(nextIndex, totalCount - 1)` and only advance past the last real card once `isFetchingNextPage` is false and new posts are available.

```typescript
// Revised onEnd handler addition
.onEnd((e) => {
  // ... compute rawNext as before ...
  const safeNext = Math.min(rawNext, totalCount - 1); // never snap beyond loaded data
  currentIndex.value = safeNext;
  translateY.value = withSpring(-safeNext * WINDOW_HEIGHT, { damping: 20, stiffness: 200 });
  runOnJS(handleIndexChange)(safeNext);
});
```

In `handleIndexChange`, when new posts arrive after a fetch, auto-advance if the user already attempted to scroll past:

```typescript
// src/hooks/useAutoAdvance.ts
import { useEffect, useRef } from 'react';

export function useAutoAdvance(
  totalCount: number,
  isFetchingNextPage: boolean,
  attemptedIndex: React.MutableRefObject<number>,
  snapTo: (index: number) => void
) {
  const prevFetching = useRef(isFetchingNextPage);

  useEffect(() => {
    // Fetch just completed
    if (prevFetching.current && !isFetchingNextPage) {
      if (attemptedIndex.current >= totalCount - (totalCount % 10 || 10)) {
        snapTo(attemptedIndex.current);
      }
    }
    prevFetching.current = isFetchingNextPage;
  }, [isFetchingNextPage, totalCount, snapTo]);
}
```

---

## Horizontal Swipe-to-React Gesture (Nested)

Individual cards support a horizontal swipe for reactions. Use `Gesture.Simultaneous` with priority.

```typescript
// src/components/FeedCard.tsx
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { useSharedValue, useAnimatedStyle, withSpring } from 'react-native-reanimated';

export function FeedCard({ post }: { post: Post }) {
  const cardX = useSharedValue(0);

  const horizontalSwipe = Gesture.Pan()
    .activeOffsetX([-15, 15])
    .failOffsetY([-10, 10]) // vertical pan claims win
    .onUpdate((e) => { cardX.value = e.translationX; })
    .onEnd((e) => {
      if (Math.abs(e.translationX) > 80) {
        // Reaction committed
        cardX.value = withSpring(0);
      } else {
        cardX.value = withSpring(0);
      }
    });

  const style = useAnimatedStyle(() => ({
    transform: [{ translateX: cardX.value }],
  }));

  return (
    <GestureDetector gesture={horizontalSwipe}>
      <Animated.View style={[{ height: Dimensions.get('window').height }, style]}>
        {/* card content */}
      </Animated.View>
    </GestureDetector>
  );
}
```

The parent `SnapFeed` pan has `failOffsetX([-20, 20])` and the child `FeedCard` pan has `failOffsetY([-10, 10])`. This creates natural disambiguation: a clearly horizontal gesture goes to the card, a clearly vertical gesture goes to the feed.

---

## Anti-patterns

- **Reading React state inside Reanimated worklets**: Worklets run on the UI thread. React state is on the JS thread. Accessing a `useState` variable from inside `onUpdate` or `onEnd` causes a "can't access JS thread" error in Reanimated v3 strict mode. Use `useSharedValue` for all animation-critical values.
- **`runOnJS` inside `onUpdate` (called 60+fps)**: Every `runOnJS` call schedules a message on the JS bridge. Calling it on every frame for `setCurrentIndex` saturates the bridge. Only call `runOnJS` in `onEnd`.
- **Putting `fetchNextPage` in a `useEffect` watching `currentIndex`**: `currentIndex` is a shared value; it can't be used as a `useEffect` dependency. Use `runOnJS(handleIndexChange)` from within the gesture handler instead.
- **Snapping by page number instead of row ID**: Using page numbers breaks if posts are deleted between fetches. Always use the opaque cursor from the Worker response.
- **Fetching next page on every render**: Ensure `isFetchingNextPage` is checked before calling `fetchNextPage()`. TanStack Query deduplicates but the check avoids unnecessary calls during rapid swiping.

---

## Gotchas

- **`Dimensions.get('window').height` vs. safe area**: On iPhone models with Dynamic Island or notch, the full `WINDOW_HEIGHT` includes unsafe areas. Cards should use `WINDOW_HEIGHT` as the snap unit, but their content should be padded with `useSafeAreaInsets`.
- **New Architecture (Fabric) and gesture handler**: Ensure `react-native-gesture-handler` v2.14+ and `react-native-reanimated` v3.6+ for full JSI/Fabric compatibility. Older versions silently fall back to bridge mode.
- **Android hardware back button**: When the user presses back on Android, the gesture handler may intercept it. Add a `useBackHandler` to handle navigation separately.
- **Memory growth from infinite data**: TanStack Query v5's `maxPages` option limits how many pages are kept in memory. Set `maxPages: 5` on the `useInfiniteQuery` to prevent unbounded memory growth when the user scrolls deep.
- **`withSpring` overshooting on fast flings**: High-velocity flings with low damping can overshoot to the next card's position, making it appear that two cards were skipped. Cap `velocity` input or clamp `nextIndex = clamp(currentIndex ± 1, 0, totalCount - 1)` to allow only one card per gesture.

---

## Verification

```bash
# 1. Verify pagination fires at correct index
# Add console.log in handleIndexChange, swipe through 7 cards — should see fetchNextPage called

# 2. Verify no bridge saturation
# React Native Profiler > JS FPS: should stay 60 fps during pan gesture
# Reanimated Debugger: onUpdate worklet should show <1ms per frame

# 3. End-of-feed test
# Mock Worker to return nextCursor: null after 2 pages
# Swipe to last card — should see "end of feed" state, not a spinner

# 4. Gesture conflict test
# Diagonal swipe at 45° — should snap vertically, not trigger horizontal reaction
# Horizontal swipe > 15px — should trigger reaction on card, not scroll feed

# 5. Memory test (dev build + Android profiler)
# Scroll through 20+ pages with maxPages: 5
# Heap should plateau, not grow linearly
```

---

## Related

- `react-native-reanimated.md`
- `react-native-gesture-handler.md`
- `react-native-reanimated-workers-animation-sync.md`
- `react-native-flatlist-optimization.md`
- `android-workers-paging3-cursor-pagination.md`
- `mobile-network-resilience-cloudflare-workers.md`

---

## Sources

- Reanimated v3 worklets guide: https://docs.swmansion.com/react-native-reanimated/docs/fundamentals/worklets/
- Gesture Handler gesture composition: https://docs.swmansion.com/react-native-gesture-handler/docs/gesture-composition/
- TanStack Query `useInfiniteQuery` + `maxPages`: https://tanstack.com/query/v5/docs/framework/react/reference/useInfiniteQuery
- Cloudflare D1 cursor pagination pattern: https://developers.cloudflare.com/d1/platform/client-api/
- React Native New Architecture Fabric: https://reactnative.dev/docs/the-new-architecture/landing-page
