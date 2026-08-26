# content-visibility: auto — Cloudflare Pages Render Performance

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

The example.com feed renders hundreds of post cards in a single scroll container. On mobile, this causes long initial layout times (5–10ms per card × 500 cards = 2.5–5 seconds of layout work) and high Interaction to Next Paint (INP) scores because the browser must compute style and layout for all off-screen cards even before the user sees them. `content-visibility: auto` tells the browser to skip rendering work for off-screen elements and cache that work for when the element scrolls into view.

## Context

Cloudflare Pages serves a React SPA where the feed is a server-rendered HTML list (via streaming SSR at the edge) with React hydrating on the client. The CSS `content-visibility` property is set on each post card component. Because the cards are statically generated and streamed from the edge, the browser can apply `content-visibility: auto` immediately from the first paint without waiting for JavaScript hydration. This makes it an excellent companion to Cloudflare's streaming HTML response pattern.

## content-visibility Property Overview

`content-visibility: auto` tells the browser that an element's contents can be skipped during rendering if they are not relevant to the viewport. "Relevant" is determined by the CSS containment spec: the element's border box must intersect the viewport's "skip contents" range. When skipped, the browser still paints a placeholder with the element's `contain-intrinsic-size` so the scroll bar remains accurate.

```css
/* Base styles for each post card */
.post-card {
  /* Skip paint, layout, and style for off-screen cards */
  content-visibility: auto;

  /* Reserve estimated space so scroll position is stable.
     Use measured average card height — 320px for example.com feed cards.
     The browser uses this while the card is off-screen. */
  contain-intrinsic-size: auto 320px;

  /* content-visibility implicitly sets contain: layout style paint.
     Adding size containment prevents intrinsic size queries from
     escaping the card boundary. */
  contain: layout style paint;
}
```

## Measuring the Impact

Use the Performance API to measure layout duration before and after applying `content-visibility: auto`. The `LayoutShift` entry type captures CLS, and `LayoutShiftAttribution` can pin layout thrash to specific cards.

```typescript
// src/lib/perf/measure-feed-layout.ts

interface FeedLayoutMetrics {
  cardCount: number;
  totalLayoutMs: number;
  avgLayoutMs: number;
  contentVisibilityEnabled: boolean;
}

async function measureFeedLayout(): Promise<FeedLayoutMetrics> {
  const cards = document.querySelectorAll('.post-card');
  const contentVisibilityEnabled =
    CSS.supports('content-visibility', 'auto');

  const mark = 'feed-layout-start';
  performance.mark(mark);

  // Force synchronous layout to measure
  cards.forEach((card) => {
    // Access offsetHeight to trigger layout
    void (card as HTMLElement).offsetHeight;
  });

  const measure = performance.measure('feed-layout', mark);

  return {
    cardCount: cards.length,
    totalLayoutMs: measure.duration,
    avgLayoutMs: measure.duration / cards.length,
    contentVisibilityEnabled,
  };
}

// Report to Cloudflare Workers RUM endpoint
async function reportMetrics(metrics: FeedLayoutMetrics): Promise<void> {
  await fetch('/api/telemetry/layout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(metrics),
    keepalive: true, // Ensure this fires even during page unload
  });
}
```

## React Component Integration

Apply the CSS class from the component. When the card is inside a React list with `key` props, `content-visibility: auto` still works because the browser ignores rendering for off-screen DOM nodes regardless of how they were created.

```typescript
// src/components/PostCard.tsx

import type { FC } from 'react';

interface Post {
  id: string;
  author: string;
  body: string;
  timestamp: string;
  imageUrl?: string;
}

interface PostCardProps {
  post: Post;
}

const PostCard: FC<PostCardProps> = ({ post }) => {
  return (
    // The CSS class applies content-visibility: auto
    // The browser skips rendering this card when off-screen
    <article className="post-card" data-post-id={post.id}>
      <header className="post-card__header">
        <span className="post-card__author">{post.author}</span>
        <time className="post-card__time" dateTime={post.timestamp}>
          {formatRelativeTime(post.timestamp)}
        </time>
      </header>
      <p className="post-card__body">{post.body}</p>
      {post.imageUrl && (
        <img
          className="post-card__image"
          src={post.imageUrl}
          alt=""
          loading="lazy"
          decoding="async"
          width={600}
          height={400}
        />
      )}
    </article>
  );
};

function formatRelativeTime(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

export default PostCard;
```

## Cloudflare Pages Streaming SSR — Server Side

When using React's `renderToPipeableStream` at the edge via a Cloudflare Pages Function, cards are streamed in document order. The CSS `content-visibility: auto` in the `<head>` stylesheet is applied by the browser before the first card arrives, so skipping begins immediately.

```typescript
// functions/feed/index.ts

import { renderToPipeableStream } from 'react-dom/server';
import type { PagesFunction } from '@cloudflare/workers-types';
import { FeedPage } from '../../src/pages/FeedPage';
import { fetchFeedPosts } from '../../src/lib/api';

export const onRequestGet: PagesFunction = async (ctx) => {
  const posts = await fetchFeedPosts(ctx);

  const { readable, writable } = new TransformStream();

  // The CSS for content-visibility is included in the <head>
  // which streams before any post cards — browser applies it immediately
  const { pipe } = renderToPipeableStream(
    <FeedPage posts={posts} />,
    {
      onShellReady() {
        pipe(writable.getWriter() as unknown as NodeJS.WritableStream);
      },
    }
  );

  return new Response(readable, {
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Transfer-Encoding': 'chunked',
      'X-Content-Type-Options': 'nosniff',
    },
  });
};
```

## contain-intrinsic-size with Dynamic Card Heights

Variable-height cards (posts with long text, multiple images) make a fixed `contain-intrinsic-size` cause layout shift when the card enters the viewport and the browser recalculates true height. Use `auto` prefix to let the browser remember the last known size after first render.

```css
.post-card {
  content-visibility: auto;

  /* 'auto' remembers the last rendered size.
     Falls back to 320px on first render (before any layout). */
  contain-intrinsic-size: auto 320px;
}

/* For cards with images, reserve additional height */
.post-card--with-image {
  contain-intrinsic-size: auto 560px;
}

/* For text-only cards (typically shorter) */
.post-card--text-only {
  contain-intrinsic-size: auto 180px;
}
```

Apply the modifier class at render time based on card content:

```typescript
// src/components/PostCard.tsx (updated)

const PostCard: FC<PostCardProps> = ({ post }) => {
  const modifier = post.imageUrl ? 'post-card--with-image' : 'post-card--text-only';

  return (
    <article className={`post-card ${modifier}`} data-post-id={post.id}>
      {/* ... */}
    </article>
  );
};
```

## Anti-patterns

- Applying `content-visibility: auto` to the scroll container itself rather than individual items — the container must remain visible so scrolling works; only the children should be skipped.
- Using `content-visibility: auto` without `contain-intrinsic-size` — the browser collapses off-screen items to zero height, causing the scrollbar to jump and scroll position to be inaccurate.
- Setting `content-visibility: auto` on elements that hold focus or contain focusable elements without testing — keyboard navigation to off-screen elements triggers rendering but may cause scroll jumps.
- Applying it to sticky headers inside the feed — sticky elements inside a `content-visibility: auto` container stop being sticky correctly.
- Using it alongside CSS `position: sticky` or `position: fixed` children — these create new stacking contexts that interact poorly with content-visibility's rendering skip.

## Gotchas

- `content-visibility: auto` is not supported in Firefox below 125. Use `@supports (content-visibility: auto)` to conditionally apply the property and avoid layout regressions.
- Screen readers in some configurations may skip off-screen content that has `content-visibility: auto` applied. Test with NVDA, JAWS, and VoiceOver to confirm landmark navigation works.
- `IntersectionObserver` callbacks still fire for elements with `content-visibility: auto` — the element is "visible" to the observer even when rendering is skipped. Use the `isVisible` field (if available) for accurate visibility state.
- `contain-intrinsic-size: auto X` stores the last rendered size in the browser but resets on hard reload. During SSR, the first paint will use the fallback value.
- Elements with `content-visibility: auto` are still in the accessibility tree regardless of whether they are rendered. This is correct behavior.
- DevTools "Rendering" panel in Chrome has a "Show content-visibility skips" option that highlights skipped regions — useful for debugging.

## Verification

1. Load the example.com feed page with 500 posts.
2. Open DevTools → Performance → Record → Reload.
3. In the flame chart, compare Layout task duration with and without `content-visibility: auto`.
4. Scroll down the feed — confirm cards render on demand without CLS (no scroll jump).
5. In the Rendering panel, enable "Content visibility" debugging — off-screen cards should be highlighted in green.
6. Test in Firefox 125+ and confirm cards render correctly.
7. Test with VoiceOver on macOS — confirm all posts are reachable via arrow key navigation.

## Related

- `browser-intersection-observer.md`
- `react-virtual-list.md`
- `html-lazy-loading-images.md`
- `html-web-vitals-cls.md`
- `html-web-vitals-inp.md`
- `streaming-html-workers-react-rendertopipeablestream.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/CSS/content-visibility
- https://developer.mozilla.org/en-US/docs/Web/CSS/contain-intrinsic-size
- https://web.dev/articles/content-visibility
- https://developers.cloudflare.com/pages/functions/
- https://www.w3.org/TR/css-contain-2/#content-visibility
- https://caniuse.com/css-content-visibility
