# React Native Skia Workers Server-Driven Canvas Rendering

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Design and growth teams want to push dynamic chart layouts, ad canvases, or branded
illustrations without a new app release. React Native Skia renders 2-D graphics at 60 fps on
the UI thread via JSI, but rendering instructions must come from a Cloudflare Worker that
serves a compact "paint spec" JSON — not raw SVG, which Skia cannot consume directly.

## Context

`@shopify/react-native-skia` (RN Skia) requires the New Architecture (Fabric + JSI) from
RN 0.74+. A Cloudflare Worker hosts a `/paint-spec` endpoint backed by KV for per-user or
A/B-tested canvas configurations. The device fetches the spec on mount and on
push-notification refresh. MMKV caches the last-good spec for offline resilience.
Snapshots tests mock Skia primitives so CI does not need a GPU.

---

## 1. Workers Paint-Spec KV Endpoint

```typescript
// worker/src/paint-spec.ts
export interface SpecElement {
  type: 'rect' | 'roundRect' | 'circle' | 'text';
  x?: number; y?: number;
  w?: number; h?: number; r?: number;
  cx?: number; cy?: number;
  value?: string; size?: number;
  color: string;
}

export interface PaintSpec {
  version: number;
  background: string;
  elements: SpecElement[];
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const userId = req.headers.get('x-user-id') ?? 'default';
    const raw = await env.CANVAS_KV.get(`spec:${userId}`, 'text');
    const spec: PaintSpec = raw ? JSON.parse(raw) : { version: 1, background: '#FFFFFF', elements: [] };
    return Response.json(spec, {
      headers: { 'Cache-Control': 'private, max-age=60' },
    });
  },
} satisfies ExportedHandler<Env>;
```

---

## 2. Spec Fetch with MMKV Offline Cache

```typescript
// lib/paintSpec.ts
import { MMKV } from 'react-native-mmkv';
import { useEffect, useState } from 'react';
import type { PaintSpec } from '../../worker/src/paint-spec';

const storage = new MMKV();
const CACHE_KEY = 'paint-spec';

async function fetchSpec(workerBase: string, userId: string): Promise<PaintSpec> {
  try {
    const res = await fetch(`${workerBase}/paint-spec`, {
      headers: { 'x-user-id': userId },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const spec: PaintSpec = await res.json();
    storage.set(CACHE_KEY, JSON.stringify(spec));
    return spec;
  } catch {
    const cached = storage.getString(CACHE_KEY);
    if (cached) return JSON.parse(cached) as PaintSpec;
    throw new Error('No paint spec available and no cache found');
  }
}

export function usePaintSpec(workerBase: string, userId: string) {
  const [spec, setSpec] = useState<PaintSpec | null>(null);
  useEffect(() => {
    fetchSpec(workerBase, userId).then(setSpec).catch(console.error);
  }, [workerBase, userId]);
  return spec;
}
```

---

## 3. Skia Canvas Renderer

```tsx
// components/ServerDrivenCanvas.tsx
import { Canvas, Rect, RoundedRect, Circle, Text, useFont } from '@shopify/react-native-skia';
import { usePaintSpec } from '../lib/paintSpec';
import type { SpecElement } from '../../worker/src/paint-spec';

const WORKER_BASE = 'https://canvas.example.com';

function renderElement(el: SpecElement, i: number, font: ReturnType<typeof useFont>) {
  switch (el.type) {
    case 'rect':
      return <Rect key={i} x={el.x!} y={el.y!} width={el.w!} height={el.h!} color={el.color} />;
    case 'roundRect':
      return <RoundedRect key={i} x={el.x!} y={el.y!} width={el.w!} height={el.h!} r={el.r ?? 8} color={el.color} />;
    case 'circle':
      return <Circle key={i} cx={el.cx!} cy={el.cy!} r={el.r!} color={el.color} />;
    case 'text':
      return font
        ? <Text key={i} x={el.x!} y={el.y!} text={el.value!} font={font} color={el.color} />
        : null;
    default:
      return null;
  }
}

interface Props { userId: string; width: number; height: number }

export function ServerDrivenCanvas({ userId, width, height }: Props) {
  const spec = usePaintSpec(WORKER_BASE, userId);
  const font = useFont(require('../assets/Inter-Regular.ttf'), 14);

  if (!spec) return null; // render loading state upstream

  return (
    <Canvas style={{ width, height }}>
      <Rect x={0} y={0} width={width} height={height} color={spec.background} />
      {spec.elements.map((el, i) => renderElement(el, i, font))}
    </Canvas>
  );
}
```

---

## 4. Push-Triggered Spec Refresh

```typescript
// worker/src/spec-update.ts — invalidate KV and enqueue push
export async function pushSpecUpdate(env: Env, userId: string, newSpec: PaintSpec) {
  await env.CANVAS_KV.put(`spec:${userId}`, JSON.stringify(newSpec), {
    expirationTtl: 86_400,
  });
  await env.PUSH_QUEUE.send({ type: 'CANVAS_SPEC_UPDATED', userId });
}
```

```tsx
// RN: react to FCM push
import messaging from '@react-native-firebase/messaging';

messaging().onMessage(async remote => {
  if (remote.data?.type === 'CANVAS_SPEC_UPDATED') {
    const fresh = await fetchSpec(WORKER_BASE, currentUserId);
    setSpec(fresh); // state lifted to parent
  }
});
```

---

## 5. Snapshot Test (Jest + Skia Mocks)

```tsx
// __tests__/ServerDrivenCanvas.test.tsx
import React from 'react';
import { render } from '@testing-library/react-native';
import { ServerDrivenCanvas } from '../components/ServerDrivenCanvas';

jest.mock('@shopify/react-native-skia', () => ({
  Canvas: ({ children }: any) => <>{children}</>,
  Rect: () => null,
  RoundedRect: () => null,
  Circle: () => null,
  Text: () => null,
  useFont: () => ({}),
}));

jest.mock('../lib/paintSpec', () => ({
  usePaintSpec: () => ({
    version: 1,
    background: '#FF0000',
    elements: [{ type: 'circle', cx: 50, cy: 50, r: 30, color: '#00FF00' }],
  }),
}));

it('renders without crashing', () => {
  const { toJSON } = render(<ServerDrivenCanvas userId="u1" width={300} height={200} />);
  expect(toJSON()).toMatchSnapshot();
});
```

---

## Anti-patterns

- Sending SVG or HTML canvas strings as the spec — Skia operates on typed draw calls; parse server data into `SpecElement` objects before rendering.
- Fetching the spec on every render pass — memoize with `useEffect` and invalidate only on push notification.
- Storing large image blobs in KV values — keep the spec to geometry/color tokens; reference images by R2 URL inside a `SkImage` element.
- Parsing JSON synchronously in the render function — decode in `useEffect` so the UI thread is not blocked during large spec hydration.

## Gotchas

- RN Skia requires `newArchEnabled=true` in `android/gradle.properties` and `RCT_NEW_ARCH_ENABLED=1` in the iOS Podfile from RN 0.74+.
- `useFont` returns `null` until the font asset is loaded; always guard text element rendering with a null check on `font`.
- KV `max-age=60` may serve a stale spec through HTTP caching layers; use `Cache-Control: no-store` for real-time canvas designs.
- Color strings in spec elements must be valid CSS hex or named colors; Skia does not accept `hsl()` or `rgba()` without prior conversion.

## Verification

```bash
# Push a new spec to KV
wrangler kv key put --binding=CANVAS_KV "spec:user-123" \
  '{"version":2,"background":"#F5F5F5","elements":[{"type":"circle","cx":100,"cy":100,"r":40,"color":"#3B82F6"}]}'

# Confirm the Worker returns it
curl -H "x-user-id: user-123" https://canvas.example.com/paint-spec | jq .

# Verify the element count
curl -s -H "x-user-id: user-123" https://canvas.example.com/paint-spec | \
  jq '.elements | length'
```

## Related

- `react-native-skia-custom-graphics.md`
- `react-native-workers-image-cache-r2-cdn.md`
- `react-native-reanimated-workers-animation-sync.md`
- `mobile-feature-flags-remote-config.md`

## Sources

- https://shopify.github.io/react-native-skia/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/queues/
- https://reactnative.dev/docs/new-architecture-intro
