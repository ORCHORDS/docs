# Barcode Detection API — Cloudflare Pages + Workers Integration

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to scan QR codes or product barcodes directly in the browser for a Cloudflare Pages
SPA — without shipping a 200 KB barcode library. The native `BarcodeDetector` API uses
on-device ML to decode barcodes from a `<video>` stream or `ImageBitmap`, and a Cloudflare
Worker can then look up the scanned code against a D1 product catalog or validate a QR token.

---

## Context

`BarcodeDetector` is part of the Shape Detection API. It runs natively on Android Chrome
(via Google Play Services ML Kit) and macOS/iOS Safari (via Vision framework). On unsupported
platforms (most desktop Chrome, Firefox) you fall back to a WASM library. Cloudflare Pages
hosts the SPA; a Worker handles catalog lookups and QR token validation so no secrets leave
the edge. The camera stream stays client-side only — no frames are uploaded.

---

## Feature Detection + Supported Formats

```typescript
// src/lib/barcodeDetector.ts
export type BarcodeFormat =
  | 'aztec' | 'code_128' | 'code_39' | 'code_93'
  | 'codabar' | 'data_matrix' | 'ean_13' | 'ean_8'
  | 'itf' | 'pdf417' | 'qr_code' | 'upc_a' | 'upc_e' | 'unknown';

export async function getSupportedFormats(): Promise<BarcodeFormat[]> {
  if (!('BarcodeDetector' in window)) return [];
  return BarcodeDetector.getSupportedFormats() as Promise<BarcodeFormat[]>;
}

export function isBarcodeDetectorSupported(): boolean {
  return typeof window !== 'undefined' && 'BarcodeDetector' in window;
}
```

---

## Camera Stream + Detection Loop

```typescript
// src/lib/scanner.ts
import { isBarcodeDetectorSupported } from './barcodeDetector';

export interface ScanResult {
  rawValue: string;
  format: string;
  boundingBox: DOMRectReadOnly;
  cornerPoints: { x: number; y: number }[];
}

export class BarcodeScanner {
  private detector: BarcodeDetector | null = null;
  private stream: MediaStream | null = null;
  private animFrame: number | null = null;

  async init(formats: string[] = ['qr_code', 'ean_13', 'code_128']): Promise<boolean> {
    if (!isBarcodeDetectorSupported()) return false;
    this.detector = new BarcodeDetector({ formats });
    return true;
  }

  async startCamera(videoEl: HTMLVideoElement): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1280 } },
    });
    videoEl.srcObject = this.stream;
    await videoEl.play();
  }

  scan(
    videoEl: HTMLVideoElement,
    onResult: (result: ScanResult) => void
  ): void {
    if (!this.detector) throw new Error('BarcodeScanner not initialised');

    const tick = async () => {
      if (videoEl.readyState === videoEl.HAVE_ENOUGH_DATA) {
        try {
          const barcodes = await this.detector!.detect(videoEl);
          for (const code of barcodes) {
            onResult({
              rawValue: code.rawValue,
              format: code.format,
              boundingBox: code.boundingBox,
              cornerPoints: code.cornerPoints,
            });
          }
        } catch {
          // Frame not ready; continue
        }
      }
      this.animFrame = requestAnimationFrame(tick);
    };
    this.animFrame = requestAnimationFrame(tick);
  }

  stop(): void {
    if (this.animFrame !== null) cancelAnimationFrame(this.animFrame);
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
  }
}
```

---

## React Scanner Component

```tsx
// src/components/BarcodeScanner.tsx
import { useRef, useEffect, useCallback, useState } from 'react';
import { BarcodeScanner, ScanResult } from '../lib/scanner';
import { isBarcodeDetectorSupported } from '../lib/barcodeDetector';

interface Props {
  onScan: (value: string, format: string) => void;
}

export function BarcodeScannerView({ onScan }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const scannerRef = useRef(new BarcodeScanner());
  const [error, setError] = useState<string | null>(null);
  const [supported] = useState(isBarcodeDetectorSupported());

  const handleResult = useCallback(
    (result: ScanResult) => {
      scannerRef.current.stop();
      onScan(result.rawValue, result.format);
    },
    [onScan]
  );

  useEffect(() => {
    if (!supported || !videoRef.current) return;

    let active = true;
    const scanner = scannerRef.current;

    (async () => {
      const ok = await scanner.init(['qr_code', 'ean_13', 'code_128', 'data_matrix']);
      if (!ok || !active) return;
      try {
        await scanner.startCamera(videoRef.current!);
        if (active) scanner.scan(videoRef.current!, handleResult);
      } catch (e) {
        setError((e as Error).message);
      }
    })();

    return () => {
      active = false;
      scanner.stop();
    };
  }, [supported, handleResult]);

  if (!supported) {
    return (
      <p>
        Your browser does not support native barcode scanning.{' '}
        <a >Enter code manually</a>
      </p>
    );
  }

  if (error) return <p>Camera error: {error}</p>;

  return (
    <video
      ref={videoRef}
      style={{ width: '100%', maxWidth: 480, borderRadius: 8 }}
      playsInline
      muted
    />
  );
}
```

---

## Cloudflare Worker — Catalog Lookup

```typescript
// workers/catalog.ts  (GET /api/catalog/:barcode)
import { Hono } from 'hono';

type Env = { DB: D1Database };
const app = new Hono<{ Bindings: Env }>();

app.get('/api/catalog/:barcode', async (c) => {
  const barcode = c.req.param('barcode');

  // Basic validation — accept EAN-13, EAN-8, Code 128, QR alphanumeric
  if (!/^[A-Za-z0-9\-_.]{4,50}$/.test(barcode)) {
    return c.json({ error: 'Invalid barcode format' }, 400);
  }

  const product = await c.env.DB.prepare(
    'SELECT id, name, price_cents, stock FROM products WHERE barcode = ? LIMIT 1'
  )
    .bind(barcode)
    .first<{ id: string; name: string; price_cents: number; stock: number }>();

  if (!product) {
    return c.json({ error: 'Product not found' }, 404);
  }

  return c.json(product);
});

export default app;
```

---

## Cloudflare Worker — QR Token Validation

```typescript
// workers/qr-token.ts  (POST /api/qr/validate)
import { Hono } from 'hono';

type Env = { KV: KVNamespace };
const app = new Hono<{ Bindings: Env }>();

/**
 * QR codes contain a short-lived token: qr:<uuid>
 * Validate and consume it (one-time use).
 */
app.post('/api/qr/validate', async (c) => {
  const { token } = await c.req.json<{ token: string }>();

  if (!token?.startsWith('qr:')) {
    return c.json({ valid: false, reason: 'Not a QR token' }, 400);
  }

  const key = `qr:${token.slice(3)}`;
  const value = await c.env.KV.get(key);

  if (!value) {
    return c.json({ valid: false, reason: 'Token expired or not found' }, 404);
  }

  // Consume — one-time use
  await c.env.KV.delete(key);

  const payload = JSON.parse(value) as { userId: string; action: string; expiresAt: number };

  if (Date.now() > payload.expiresAt) {
    return c.json({ valid: false, reason: 'Token expired' }, 410);
  }

  return c.json({ valid: true, ...payload });
});

export default app;
```

---

## WASM Fallback for Unsupported Browsers

```typescript
// src/lib/fallbackScanner.ts
/**
 * Lazy-load zxing-wasm (76 KB gzipped) only on browsers without BarcodeDetector.
 * Cloudflare Pages serves the .wasm file from the /public directory.
 */
export async function loadFallbackScanner() {
  const { BrowserMultiFormatReader } = await import('@zxing/browser');
  return new BrowserMultiFormatReader();
}

export async function scanWithFallback(
  videoEl: HTMLVideoElement,
  onResult: (text: string) => void
): Promise<() => void> {
  const reader = await loadFallbackScanner();
  const controls = await reader.decodeFromVideoElement(videoEl, (result) => {
    if (result) onResult(result.getText());
  });
  return () => controls.stop();
}
```

---

## Anti-patterns

- **Uploading video frames to a Worker for server-side decoding** — barcode detection is intentionally client-side; sending frames adds latency and bandwidth cost.
- **Calling `detector.detect()` synchronously on every `requestAnimationFrame`** — awaiting every frame queues up; use a flag or debounce to avoid overlapping detect calls.
- **Not stopping the camera stream on unmount** — `MediaStreamTrack.stop()` must be called or the browser indicator stays active.
- **Trusting `rawValue` without server validation** — always validate QR token contents server-side (Worker); the client can forge `rawValue`.
- **Skipping format restriction** — passing no `formats` array scans all supported formats, which is slower on mobile ML Kit.

---

## Gotchas

- `BarcodeDetector` is not available in Firefox (as of 2026); always ship the WASM fallback behind dynamic import.
- On iOS Safari, camera access requires a user gesture — do not call `getUserMedia` on page load.
- `BarcodeDetector.detect()` accepts `HTMLVideoElement`, `HTMLImageElement`, `ImageBitmap`, `ImageData`, and `OffscreenCanvas`, but NOT a `MediaStream` directly.
- The `cornerPoints` array has exactly 4 points; use them to draw an overlay on a `<canvas>` for visual feedback.
- Cloudflare Pages serves `.wasm` files correctly but you must set `Content-Type: application/wasm` in `_headers` for browsers to instantiate them via streaming compilation.

---

## Verification

```bash
# Serve Pages locally and test camera scanning
wrangler pages dev ./dist --compatibility-date=2025-01-01

# Test catalog lookup
curl -s "http://localhost:8788/api/catalog/5901234123457" | jq .
# expect: {"id":"...","name":"...","price_cents":499,"stock":12}

# Test QR token validation
KV_TOKEN=$(wrangler kv key list --binding=KV | jq -r '.[0].name | ltrimstr("qr:")')
curl -X POST http://localhost:8788/api/qr/validate \
  -H 'Content-Type: application/json' \
  -d "{\"token\":\"qr:${KV_TOKEN}\"}"
# expect: {"valid":true,"userId":"...","action":"..."}
```

---

## Related

- `wasm-cloudflare-workers-image-transform.md`
- `browser-permissions-api.md`
- `progressive-enhancement-workers-form-actions.md`
- `hono-cloudflare-workers-frontend-api.md`
- `feature-flags-cloudflare-workers-kv-edge-config.md`

---

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/BarcodeDetector
- https://wicg.github.io/shape-detection-api/
- https://developer.chrome.com/docs/capabilities/shape-detection
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://github.com/zxing-js/browser
