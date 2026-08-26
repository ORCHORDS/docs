# React Native Workers Image Cache CDN R2

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your React Native app loads user-generated or product images directly from R2.
Without a caching layer, every cold app launch re-fetches all images, hammers R2
egress costs, and causes visible loading flashes on slow connections. You need a
Workers CDN layer that serves images with long-lived Cache-Control headers, handles
on-the-fly resizing for different screen densities, and falls back to on-device
disk cache via `react-native-fast-image`.

---

## Context

Cloudflare R2 public buckets are served via a subdomain but lack fine-grained
Cache-Control and image transform support. Putting a Worker in front of R2 lets
you:
- Serve images through Cloudflare's global cache with proper headers.
- Resize and convert to WebP on the fly via `fetch` with `cf.image` options.
- Validate access tokens without R2 being public.

Stack:
- React Native 0.75+
- `react-native-fast-image` (disk cache layer)
- Cloudflare Workers (TypeScript) + R2 + Cache API

---

## 1. Image CDN Worker

```typescript
// workers/src/image-cdn.ts
interface Env {
  IMAGES: R2Bucket
  JWT_SECRET: string
}

const CACHE_MAX_AGE = 60 * 60 * 24 * 30  // 30 days

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url)

    // Expected path: /images/<object-key>?w=400&h=400&fit=cover&f=webp
    if (!url.pathname.startsWith('/images/')) {
      return new Response('Not found', { status: 404 })
    }

    const objectKey = url.pathname.slice('/images/'.length)
    if (!objectKey) return new Response('Bad request', { status: 400 })

    const cacheUrl = new URL(request.url)
    const cache = caches.default
    let response = await cache.match(cacheUrl.toString())
    if (response) return response

    // Fetch from R2
    const object = await env.IMAGES.get(objectKey)
    if (!object) return new Response('Not found', { status: 404 })

    const body = await object.arrayBuffer()
    const contentType = object.httpMetadata?.contentType ?? 'image/jpeg'

    // Apply image transforms via Cloudflare Image Resizing if available
    const w = url.searchParams.get('w')
    const h = url.searchParams.get('h')
    const fit = url.searchParams.get('fit') ?? 'cover'
    const format = url.searchParams.get('f') ?? 'webp'

    let finalBody: ArrayBuffer = body
    let finalContentType = contentType

    if (w || h) {
      const resizeResp = await fetch(request, {
        cf: {
          image: {
            width: w ? parseInt(w, 10) : undefined,
            height: h ? parseInt(h, 10) : undefined,
            fit: fit as 'cover' | 'contain' | 'scale-down',
            format: format as 'webp' | 'avif' | 'json',
          },
        },
      } as RequestInit)
      if (resizeResp.ok) {
        finalBody = await resizeResp.arrayBuffer()
        finalContentType = resizeResp.headers.get('Content-Type') ?? finalContentType
      }
    }

    response = new Response(finalBody, {
      headers: {
        'Content-Type': finalContentType,
        'Cache-Control': `public, max-age=${CACHE_MAX_AGE}, immutable`,
        'Vary': 'Accept',
        'ETag': object.etag,
        'CF-Cache-Status': 'MISS',
      },
    })

    ctx.waitUntil(cache.put(cacheUrl.toString(), response.clone()))
    return response
  },
}
```

---

## 2. Upload Endpoint — Write to R2 with Signed URL

```typescript
// workers/src/image-upload.ts (companion route)
import { Hono } from 'hono'
import { verify } from '@tsndr/cloudflare-worker-jwt'

interface Env {
  IMAGES: R2Bucket
  JWT_SECRET: string
}

const app = new Hono<{ Bindings: Env }>()

app.post('/images/upload', async (c) => {
  const token = c.req.header('Authorization')?.slice(7)
  const valid = await verify(token ?? '', c.env.JWT_SECRET)
  if (!valid) return c.json({ error: 'unauthorized' }, 401)

  const formData = await c.req.formData()
  const file = formData.get('file') as File | null
  if (!file) return c.json({ error: 'no_file' }, 400)

  const key = `uploads/${crypto.randomUUID()}.${file.name.split('.').pop()}`
  await c.env.IMAGES.put(key, await file.arrayBuffer(), {
    httpMetadata: { contentType: file.type },
  })

  const cdnUrl = `https://cdn.example.com/images/${key}`
  return c.json({ url: cdnUrl, key })
})

export default app
```

---

## 3. React Native Image Component with Fast Image

```typescript
// src/components/CdnImage.tsx
import React, { useMemo } from 'react'
import FastImage, { FastImageProps, ResizeMode } from 'react-native-fast-image'
import { PixelRatio, useWindowDimensions } from 'react-native'

const CDN_BASE = 'https://cdn.example.com'

interface CdnImageProps extends Omit<FastImageProps, 'source'> {
  imageKey: string
  width: number
  height: number
  resizeMode?: ResizeMode
}

export const CdnImage: React.FC<CdnImageProps> = ({
  imageKey,
  width,
  height,
  resizeMode = 'cover',
  ...rest
}) => {
  const pixelRatio = PixelRatio.get()

  const uri = useMemo(() => {
    const w = Math.round(width * pixelRatio)
    const h = Math.round(height * pixelRatio)
    return `${CDN_BASE}/images/${imageKey}?w=${w}&h=${h}&fit=${resizeMode}&f=webp`
  }, [imageKey, width, height, pixelRatio, resizeMode])

  return (
    <FastImage
      {...rest}
      source={{
        uri,
        priority: FastImage.priority.normal,
        cache: FastImage.cacheControl.immutable,  // never revalidate if cached
      }}
      style={[rest.style, { width, height }]}
      resizeMode={resizeMode}
    />
  )
}
```

---

## 4. Prefetch List on App Start

```typescript
// src/lib/imagePrefetch.ts
import FastImage from 'react-native-fast-image'

const CDN_BASE = 'https://cdn.example.com'

export function prefetchImages(keys: string[], width = 200, height = 200): void {
  const sources = keys.map((key) => ({
    uri: `${CDN_BASE}/images/${key}?w=${width}&h=${height}&fit=cover&f=webp`,
  }))
  FastImage.preload(sources)
}

// Usage at app launch:
// prefetchImages(userProfile.recentImageKeys, 80, 80)
```

---

## 5. Cache Invalidation via Workers KV Flag

```typescript
// workers/src/image-cdn.ts (extended)
// When an image is deleted or replaced, write a tombstone to KV
// and check it before serving cached responses.

interface Env {
  IMAGES: R2Bucket
  INVALIDATED: KVNamespace
}

async function isInvalidated(key: string, env: Env): Promise<boolean> {
  return (await env.INVALIDATED.get(key)) !== null
}

// In the DELETE handler elsewhere:
// await env.INVALIDATED.put(objectKey, '1', { expirationTtl: 60 * 60 * 24 })
// Then in fetch handler above, add before cache.match():
// if (await isInvalidated(objectKey, env)) {
//   await cache.delete(cacheUrl.toString())
// }
```

---

## Anti-patterns

- **Serving R2 objects directly as public bucket**: you lose Cache-Control control,
  image resizing, and the ability to add auth without making the bucket fully public.
- **Using the same URL for different device densities**: `FastImage` caches by URL;
  include `?w=&h=` in the URL so 1x and 3x devices get independent cache entries.
- **Not setting `immutable` in `Cache-Control`**: without `immutable`, browsers and
  `FastImage` may still revalidate with a `304` request, wasting round-trips.
- **Skipping cache invalidation logic**: if a user replaces their avatar, stale CDN
  caches will serve the old image; always include a KV tombstone check or URL
  version stamp.

---

## Gotchas

- Cloudflare Image Resizing (`cf.image`) is available only on Workers Paid with
  Image Resizing enabled; the Worker must be on a zone, not a `workers.dev` subdomain.
- `react-native-fast-image` disk cache has no explicit size limit by default; advise
  users to clear it via `FastImage.clearDiskCache()` in a settings screen.
- R2 object keys that contain `+` or spaces must be URL-encoded when constructing
  CDN URLs; use `encodeURIComponent` on individual path segments.
- `caches.default.put()` only caches responses with a `Cache-Control` header that
  includes `max-age` > 0; ensure the header is set before `cache.put`.

---

## Verification

```bash
# Confirm CDN header on Workers response
curl -I "https://cdn.example.com/images/uploads/test.jpg?w=200&h=200&f=webp"
# Expect: Cache-Control: public, max-age=2592000, immutable
# Second request:
curl -I "https://cdn.example.com/images/uploads/test.jpg?w=200&h=200&f=webp"
# Expect: CF-Cache-Status: HIT

# Check R2 object exists
wrangler r2 object get IMAGES uploads/test.jpg --pipe | file -

# React Native: log FastImage cache hit in development
# FastImage's debug mode logs cache HIT/MISS to the Metro console
```

---

## Related

- `react-native-r2-multipart-upload-progress.md`
- `mobile-image-caching-patterns.md`
- `image-upload-compression-client-side.md`
- `capacitor-workers-camera-r2-upload.md`
- `flutter-workers-image-transform-cdn.md`

---

## Sources

- Cloudflare R2: https://developers.cloudflare.com/r2/
- Cloudflare Image Resizing: https://developers.cloudflare.com/images/image-resizing/
- Cloudflare Cache API: https://developers.cloudflare.com/workers/runtime-apis/cache/
- react-native-fast-image: https://github.com/DylanVann/react-native-fast-image
