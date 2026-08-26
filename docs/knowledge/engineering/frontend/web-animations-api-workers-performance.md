# Web Animations API (WAAPI) Performance Patterns with Cloudflare Workers

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You need programmatic, JS-driven animations that run on the compositor thread, avoid layout thrashing, and can be paused, reversed, or scrubbed — capabilities CSS-only animations lack. Keyframe data is too large or too dynamic to hardcode in CSS, so it is fetched from Cloudflare Workers and applied at runtime via the Web Animations API.

## Context
The Web Animations API (`element.animate()` and `document.timeline`) provides a unified model for creating animations in JavaScript while keeping the actual painting on the compositor thread (for `transform` and `opacity`). Unlike `requestAnimationFrame` loops, WAAPI animations are owned by the browser engine and not blocked by the main thread. Cloudflare Workers serve as the keyframe configuration backend: animation presets are stored in KV, generated from user state in D1, and delivered as JSON that the client hydrates into `KeyframeEffect` objects.

## Fetching Keyframe Presets from Workers KV

```typescript
// workers/animations-api.ts
import { Env } from "./types";

interface KeyframePreset {
  keyframes: Keyframe[];
  options: KeyframeEffectOptions;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const preset = url.pathname.replace(/^\/animations\//, "");

    if (!preset || !/^[\w-]+$/.test(preset)) {
      return new Response(JSON.stringify({ error: "invalid preset name" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const cached = await env.ANIM_KV.get<KeyframePreset>(preset, "json");

    if (!cached) {
      return new Response(JSON.stringify({ error: "preset not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response(JSON.stringify(cached), {
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
      },
    });
  },
};

// Example KV value for the "slide-in" preset:
// {
//   "keyframes": [
//     { "transform": "translateX(-100%)", "opacity": 0 },
//     { "transform": "translateX(0)",    "opacity": 1 }
//   ],
//   "options": { "duration": 300, "easing": "cubic-bezier(0.4, 0, 0.2, 1)", "fill": "both" }
// }
```

## Core WAAPI Patterns

```typescript
// lib/animations.ts

export interface AnimationConfig {
  keyframes: Keyframe[];
  options: KeyframeEffectOptions;
}

// Animate a single element with cleanup on removal (no memory leaks)
export function animate(
  el: Element,
  config: AnimationConfig,
  signal?: AbortSignal
): Animation {
  const effect = new KeyframeEffect(el, config.keyframes, config.options);
  const animation = new Animation(effect, document.timeline);

  signal?.addEventListener("abort", () => animation.cancel(), { once: true });

  animation.play();
  return animation;
}

// Stagger a list of elements with an index-based delay
export function staggerAnimate(
  elements: Element[],
  config: AnimationConfig,
  staggerMs = 50,
  signal?: AbortSignal
): Animation[] {
  return elements.map((el, i) =>
    animate(
      el,
      {
        ...config,
        options: { ...config.options, delay: i * staggerMs },
      },
      signal
    )
  );
}

// Group animations and await all finishing
export async function animateGroup(
  animations: Animation[]
): Promise<void> {
  await Promise.all(animations.map((a) => a.finished));
}

// Crossfade between two elements (exit + enter)
export async function crossfade(
  exiting: Element,
  entering: Element,
  config: AnimationConfig
): Promise<void> {
  const exitAnim = animate(exiting, {
    keyframes: config.keyframes.slice().reverse(),
    options: { ...config.options, fill: "forwards" },
  });

  // Start enter animation at the halfway point
  const halfDuration = (Number(config.options.duration) || 300) / 2;
  await exitAnim.ready;
  await new Promise((r) => setTimeout(r, halfDuration));

  const enterAnim = animate(entering, config);
  await animateGroup([exitAnim, enterAnim]);

  // Clean up fill mode to avoid painting artifacts
  exiting.getAnimations().forEach((a) => a.cancel());
}
```

## React Hook: Lazy Keyframe Loading from Workers

```tsx
// hooks/useWorkerAnimation.ts
import { useEffect, useRef, useCallback, useState } from "react";
import { AnimationConfig, animate } from "@/lib/animations";

const presetCache = new Map<string, AnimationConfig>();

async function fetchPreset(preset: string): Promise<AnimationConfig> {
  if (presetCache.has(preset)) return presetCache.get(preset)!;
  const res = await fetch(`/animations/${preset}`);
  if (!res.ok) throw new Error(`Animation preset "${preset}" not found`);
  const config: AnimationConfig = await res.json();
  presetCache.set(preset, config);
  return config;
}

export function useWorkerAnimation(preset: string, trigger: boolean) {
  const ref = useRef<HTMLElement | null>(null);
  const animRef = useRef<Animation | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [ready, setReady] = useState(false);

  // Prefetch the preset on mount
  useEffect(() => {
    fetchPreset(preset).then(() => setReady(true)).catch(console.error);
  }, [preset]);

  const play = useCallback(async () => {
    if (!ref.current || !ready) return;

    // Cancel any in-progress animation
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    const config = await fetchPreset(preset);
    animRef.current = animate(ref.current, config, abortRef.current.signal);

    try {
      await animRef.current.finished;
    } catch {
      // Cancelled — normal on rapid re-triggers
    }
  }, [preset, ready]);

  useEffect(() => {
    if (trigger) play();
  }, [trigger, play]);

  useEffect(() => () => abortRef.current?.abort(), []);

  return ref;
}
```

## Scroll-Triggered WAAPI Without Scroll-Driven CSS

For environments where CSS `animation-timeline: scroll()` is not yet available, use `IntersectionObserver` + WAAPI.

```typescript
// lib/scroll-trigger.ts
import { AnimationConfig, animate } from "./animations";

export function observeAndAnimate(
  selector: string,
  config: AnimationConfig,
  root?: Element
): () => void {
  const elements = document.querySelectorAll<HTMLElement>(selector);
  const animations = new Map<Element, Animation>();

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting && !animations.has(entry.target)) {
          const anim = animate(entry.target, config);
          animations.set(entry.target, anim);
          // Stop observing after first trigger (one-shot)
          observer.unobserve(entry.target);
        }
      }
    },
    { root, threshold: 0.15 }
  );

  elements.forEach((el) => {
    // Set initial state to match first keyframe to avoid flash
    const firstKf = config.keyframes[0];
    if (firstKf) {
      Object.entries(firstKf).forEach(([prop, val]) => {
        if (prop !== "offset" && prop !== "easing" && prop !== "composite") {
          (el.style as unknown as Record<string, string>)[prop] = String(val);
        }
      });
    }
    observer.observe(el);
  });

  return () => observer.disconnect();
}
```

## Performance Constraints and Compositor Thread Safety

```typescript
// lib/compositor-safe.ts

// Only these properties are guaranteed to run on the compositor thread
// (no main-thread style recalculation or layout)
const COMPOSITOR_SAFE = new Set(["transform", "opacity", "filter"]);

export function assertCompositorSafe(keyframes: Keyframe[]): void {
  const allProps = new Set(
    keyframes.flatMap((kf) =>
      Object.keys(kf).filter(
        (k) => !["offset", "easing", "composite"].includes(k)
      )
    )
  );

  const unsafe = [...allProps].filter((p) => !COMPOSITOR_SAFE.has(p));
  if (unsafe.length > 0) {
    console.warn(
      `[WAAPI] Non-compositor properties detected: ${unsafe.join(", ")}. ` +
        "These may cause layout thrashing."
    );
  }
}

// Helper: animate height from 0 to auto using FLIP technique
// (avoids animating `height` directly, which triggers layout)
export async function expandHeight(el: HTMLElement): Promise<void> {
  const startHeight = el.getBoundingClientRect().height;
  el.style.height = "auto";
  const targetHeight = el.getBoundingClientRect().height;
  el.style.height = `${startHeight}px`;

  // Force style recalc before animating
  el.getBoundingClientRect();

  const anim = el.animate(
    [{ height: `${startHeight}px` }, { height: `${targetHeight}px` }],
    { duration: 250, easing: "ease-out", fill: "forwards" }
  );

  await anim.finished;
  el.style.height = ""; // Let CSS take over
  anim.cancel();
}
```

## Anti-patterns

- **Animating `width`, `height`, or `top`/`left`** — These trigger layout on every frame. Prefer `transform: translate()` / `scale()` for position and size changes.
- **Creating a new `Animation` object on every render cycle** — Cache animations in refs (`useRef`) and call `.cancel()` before reassigning to avoid memory leaks and overlapping animations.
- **Not using `fill: "both"` with staggered animations** — Without `fill: "forwards"` (or `"both"`), elements snap back to their pre-animation style after the animation ends, producing a flash.
- **Using `document.getAnimations()` to manage unrelated animations** — It returns all animations on the document; filter by `effect.target` or maintain your own Map.
- **Forgetting `prefers-reduced-motion`** — WAAPI bypasses CSS `@media (prefers-reduced-motion)`. Always check `window.matchMedia("(prefers-reduced-motion: reduce)").matches` before playing decorative animations.

## Gotchas

- **`animation.finished` rejects on cancel** — Wrap `await animation.finished` in try/catch when you call `.cancel()` on cleanup; otherwise React's strict mode will produce unhandled promise rejections.
- **KV propagation delay** — Updated animation presets stored in KV may take up to 60 seconds to propagate globally. The `stale-while-revalidate` cache header keeps old animations showing while new ones propagate.
- **`KeyframeEffect` constructor availability** — Safari 13.1+ supports it, but older WebViews do not. Use the `element.animate()` shorthand as a fallback.
- **`composite: "add"` and `"accumulate"`** — Not fully supported in all engines. Stick with `"replace"` (the default) for production.
- **`document.timeline.currentTime` is `null` before first user interaction in some Safari versions** — Guard against null before using it for scrubbing.

## Verification

1. Store a `slide-in` preset in Workers KV and fetch `/animations/slide-in` — confirm valid JSON with `keyframes` and `options` fields.
2. Open DevTools Performance tab, record an animation triggered by `useWorkerAnimation`; confirm no layout or paint entries in the flame chart for `transform`/`opacity` keyframes.
3. Toggle `prefers-reduced-motion` in DevTools (Rendering panel) and verify animations are skipped.
4. Call `.cancel()` on an in-flight animation and confirm the `finished` promise rejects (catch it silently).
5. Run `expandHeight` on a collapsed `<details>` element and verify no layout jank in the frame timeline.

## Related

- `css-scroll-driven-animations.md` — CSS-native alternative for scroll-linked animations
- `css-view-transitions-api.md` — page-level transition animations
- `feature-flags-cloudflare-workers-kv-edge-config.md` — KV patterns for runtime configuration
- `react-suspense-cloudflare-pages-ssr-edge.md` — coordinating animations with Suspense boundaries

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/Web_Animations_API
- https://web.dev/animations-guide/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
