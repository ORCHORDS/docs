# Client-Side Image Compression Before R2 Upload

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Mobile camera uploads (12 MP HEIC/JPEG, 5–18 MB raw) stall
on mobile networks, blow R2 egress budgets, and land
rotated 90° when iOS EXIF orientation is ignored.

## Context

example project stores user-generated photos in Cloudflare R2.
Target: ≤ 800 KB per image before the PUT lands in R2.
All compression is client-side; no intermediate server.
iOS 16.4+ and Android Chrome 97+ cover our active users —
both ship `OffscreenCanvas` and `createImageBitmap`.

---

## Camera Input and HEIC Detection

```html
<!-- 'capture="camera"' skips the file picker on mobile.
     Do NOT add image/heic to accept — Safari 17+ will
     re-save files as .heic, breaking non-Apple browsers. -->
<input type="file" accept="image/*" capture="camera" />
```

Detect HEIC by magic bytes in the worker (MIME is often
`''` from the Android picker):

```js
function isHeic(buffer) {
  const brand = String.fromCharCode(
    ...new Uint8Array(buffer, 4, 8)
  );
  return /^(heic|heix|mif1|msf1)/.test(brand);
}
```

---

## `createImageBitmap` + Orientation Fix

Safari decodes HEIC natively via `createImageBitmap`.
Pass `imageOrientation: 'from-image'` to apply EXIF
rotation (Safari 15.4+, Chrome 99+):

```js
// Inside the Web Worker
async function toBitmap(buffer, mime) {
  const blob = new Blob([buffer], {
    type: mime || 'image/jpeg',
  });
  return createImageBitmap(blob, {
    imageOrientation: 'from-image',
    premultiplyAlpha: 'none',
  });
  // Throws on Chrome for HEIC — handle below.
}
```

Chrome/Firefox users uploading HEIC (file picker) need the
`libheif-js` WASM decoder (~300 KB). Import it lazily:

```js
async function heicToBitmap(buffer) {
  const { createHeifDecoder } = await import('libheif-js');
  const decoder = createHeifDecoder();
  const [img] = decoder.decode(buffer);
  const w = img.get_width(), h = img.get_height();
  const rgba = await new Promise((res, rej) =>
    img.display(
      { data: new Uint8ClampedArray(w * h * 4), w, h },
      res, rej
    )
  );
  return createImageBitmap(new ImageData(rgba.data, w, h));
}
```

---

## OffscreenCanvas Compression

`OffscreenCanvas` is available in Workers since Safari 16.4,
Chrome 69, Firefox 105 (~95% global support as of 2026).

```js
async function compress(bitmap, {
  maxDim = 2048, quality = 0.82,
} = {}) {
  const scale = Math.min(
    1, maxDim / Math.max(bitmap.width, bitmap.height)
  );
  const w = Math.round(bitmap.width * scale);
  const h = Math.round(bitmap.height * scale);
  const canvas = new OffscreenCanvas(w, h);
  canvas.getContext('2d').drawImage(bitmap, 0, 0, w, h);
  bitmap.close(); // free GPU memory

  // WebP encoding unavailable in Safari < 17 —
  // check blob.size > 0 and fall back to JPEG.
  let blob = await canvas.convertToBlob({
    type: 'image/webp', quality,
  });
  if (!blob || blob.size === 0) {
    blob = await canvas.convertToBlob({
      type: 'image/jpeg', quality,
    });
  }
  return blob;
}
```

**Expected ratios at q=0.82, 2048 px max edge:**

| Source               | Raw      | JPEG     | WebP     |
|----------------------|----------|----------|----------|
| iPhone 15 HEIC       | 5–8 MB   | ~700 KB  | ~500 KB  |
| Pixel 8 JPEG         | 4–6 MB   | ~750 KB  | ~520 KB  |
| Samsung Galaxy WebP  | 3–5 MB   | ~680 KB  | ~480 KB  |

---

## Web Worker Pipeline

```js
// compression-worker.js
self.onmessage = async ({ data: { buffer, mime } }) => {
  let bitmap;
  try {
    bitmap = await toBitmap(buffer, mime);
  } catch {
    if (isHeic(buffer)) bitmap = await heicToBitmap(buffer);
  }
  if (!bitmap) {
    self.postMessage({ error: 'unsupported' }); return;
  }
  const blob = await compress(bitmap);
  const out = await blob.arrayBuffer();
  self.postMessage({ compressed: out, type: blob.type },
    [out]); // transfer — zero copy
};
```

Instantiate once and reuse across uploads. Transfer
ownership with the `[buffer]` transferable list to avoid
copying multi-MB buffers across the thread boundary.

---

## R2 Presigned PUT

```js
async function uploadToR2(blob) {
  const { url } = await fetch('/api/upload-url', {
    method: 'POST',
    body: JSON.stringify({ contentType: blob.type,
                           size: blob.size }),
    headers: { 'Content-Type': 'application/json' },
  }).then(r => r.json());

  const res = await fetch(url, {
    method: 'PUT', body: blob,
    headers: { 'Content-Type': blob.type },
  });
  if (!res.ok) throw new Error(`R2 PUT ${res.status}`);
}
```

---

## Anti-patterns

- Uploading raw camera files — 12 MP HEIC ≈ 15 MB,
  10+ second stall on typical 4G.
- `FileReader.readAsDataURL` — Base64 inflates by 33%
  and blocks the main thread; use `arrayBuffer()`.
- Omitting `imageOrientation: 'from-image'` — iOS
  landscape shots land rotated 90° everywhere except
  Safari (which re-applies EXIF at render time).
- Eagerly importing `libheif-js` — 300 KB WASM loaded
  on every page for a rare code path.
- Skipping the `blob.size > 0` guard — `convertToBlob`
  silently returns an empty blob for unsupported types
  in older Safari.

## Gotchas

- `OffscreenCanvas` is absent in Workers on iOS < 16.4;
  feature-detect with `typeof OffscreenCanvas !== 'undefined'`
  inside the worker and fall back to a main-thread canvas.
- HEIC carries both an EXIF Orientation tag AND an `irot`
  box; `createImageBitmap` may apply both, causing double
  rotation on some files. Use `libheif-js`'s
  `get_transform()` to read the `irot` value and skip
  redundant rotation.
- Presigned R2 PUT URLs expire (default 15 min). Generate
  them immediately before upload, not at page load.
- `canvas.toDataURL` is synchronous and returns a string —
  never use it in a Worker. Use `convertToBlob` only.

## Verification

- DevTools Network tab: PUT to R2 payload ≤ 800 KB for
  a stock 12 MP photo at default settings.
- Confirm `blob.type` is `image/webp` (Chrome) or
  `image/jpeg` (Safari fallback) — never empty string.
- Upload a landscape HEIC from an iPhone and view the
  stored object in Firefox; it should not be rotated.
- Chrome DevTools Performance panel: compression work
  appears only on the Worker thread, not Main Thread.

## Related

- `documentation/storage/r2-upload-patterns.md`
- `documentation/categories/mobile/pwa-service-worker-patterns.md`
- `documentation/categories/mobile/mobile-network-resilience.md`
- `documentation/categories/performance/web-worker-offloading.md`
- `documentation/categories/mobile/mobile-image-caching-patterns.md`

## Source URLs (verified 2026-08-17)

- https://caniuse.com/offscreencanvas
- https://developer.mozilla.org/en-US/docs/Web/API/OffscreenCanvas
- https://web-platform-dx.github.io/web-features-explorer/features/offscreen-canvas/
- https://github.com/WebKit/WebKit/commit/8758b1b9f85526f462e6edb74d5c85228e15d90d
- https://github.com/whatwg/html/issues/7210
- https://dev.to/forze-dev/why-heic-breaks-websites-and-how-i-built-a-browser-only-converter-to-fix-it-gp0
- https://developer.apple.com/forums/thread/743049
