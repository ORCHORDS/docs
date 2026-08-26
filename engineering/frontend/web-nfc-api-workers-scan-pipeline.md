# Web NFC API Workers Scan Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A PWA running on Cloudflare Pages needs to scan NFC tags (asset labels, event badges, product packaging) and route the raw NDEF payload through a Cloudflare Worker for validation, enrichment, or audit logging before updating the UI. The browser's Web NFC API fires synchronously on the main thread but the enrichment round-trip must be async and cancellable.

---

## Context

Web NFC is available on Android Chrome 89+ (HTTPS only; no iOS, no desktop). It surfaces `NDEFReader` on `window`. Scanning is gated on a transient user-activation gesture and requires the `"nfc"` Permissions-Policy header to be sent by the origin.

Cloudflare Pages can set that header in `_headers`, giving you control without a full Worker in front of every request.

The pattern here is:

1. User taps "Scan" → gesture activates `NDEFReader.scan()`.
2. `message` events arrive with `NDEFMessage` records.
3. Each NDEF payload is forwarded to a Worker endpoint (`POST /api/nfc/scan`).
4. Worker validates schema, writes to KV/D1, returns enriched metadata.
5. UI updates with enriched data; scan loop continues until the user stops it.

---

## Permissions-Policy header (Cloudflare Pages `_headers`)

```
# public/_headers
/*
  Permissions-Policy: nfc=self
```

This allows the same origin to use the NFC API. Cross-origin iframes are blocked unless listed explicitly.

---

## Feature Detection

```typescript
// src/nfc/support.ts
export function isNFCSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "NDEFReader" in window &&
    navigator.userAgent.includes("Android")
  );
}
```

iOS Safari and desktop Chrome both silently have no `NDEFReader`. Never assume support even on mobile — prompt gracefully.

---

## Scanner Service

```typescript
// src/nfc/scanner.ts
import type { ScanResult } from "./types";

export class NFCScanner {
  private reader: NDEFReader | null = null;
  private controller: AbortController | null = null;

  async start(onScan: (result: ScanResult) => void): Promise<void> {
    if (!("NDEFReader" in window)) {
      throw new Error("Web NFC not supported on this device");
    }

    this.controller = new AbortController();
    this.reader = new NDEFReader();

    this.reader.addEventListener(
      "reading",
      ({ message, serialNumber }: NDEFReadingEvent) => {
        const records = Array.from(message.records).map((r) =>
          decodeRecord(r)
        );
        onScan({ serialNumber, records, scannedAt: Date.now() });
      }
    );

    this.reader.addEventListener("readingerror", (event) => {
      console.warn("NFC read error:", event);
    });

    // scan() requires a prior user gesture — call from a click handler
    await this.reader.scan({ signal: this.controller.signal });
  }

  stop(): void {
    this.controller?.abort();
    this.controller = null;
    this.reader = null;
  }
}

function decodeRecord(record: NDEFRecord): DecodedRecord {
  const { recordType, mediaType, data } = record;

  if (recordType === "text") {
    const decoder = new TextDecoder(record.encoding ?? "utf-8");
    return { type: "text", value: decoder.decode(data) };
  }

  if (recordType === "url") {
    const decoder = new TextDecoder();
    return { type: "url", value: decoder.decode(data) };
  }

  if (recordType === "mime" && mediaType?.startsWith("application/json")) {
    try {
      const text = new TextDecoder().decode(data);
      return { type: "json", value: JSON.parse(text) };
    } catch {
      return { type: "binary", value: Array.from(new Uint8Array(data!)) };
    }
  }

  return { type: "unknown", recordType, mediaType: mediaType ?? null };
}
```

---

## Types

```typescript
// src/nfc/types.ts
export interface ScanResult {
  serialNumber: string;
  records: DecodedRecord[];
  scannedAt: number;
}

export type DecodedRecord =
  | { type: "text"; value: string }
  | { type: "url"; value: string }
  | { type: "json"; value: unknown }
  | { type: "binary"; value: number[] }
  | { type: "unknown"; recordType: string; mediaType: string | null };
```

---

## Forwarding to a Cloudflare Worker

```typescript
// src/nfc/pipeline.ts
import type { ScanResult } from "./types";

export interface EnrichedScan {
  tagId: string;
  asset: AssetRecord | null;
  auditId: string;
  processedAt: string;
}

export async function forwardScan(
  result: ScanResult,
  signal?: AbortSignal
): Promise<EnrichedScan> {
  const response = await fetch("/api/nfc/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(result),
    signal,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ message: "Unknown error" }));
    throw new Error(`NFC pipeline error ${response.status}: ${err.message}`);
  }

  return response.json() as Promise<EnrichedScan>;
}
```

---

## Cloudflare Worker — `/api/nfc/scan`

```typescript
// functions/api/nfc/scan.ts  (Cloudflare Pages Function)
import type { PagesFunction } from "@cloudflare/workers-types";

interface Env {
  NFC_ASSETS: KVNamespace;
  DB: D1Database;
}

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ message: "Invalid JSON" }, { status: 400 });
  }

  const scan = body as {
    serialNumber: string;
    records: Array<{ type: string; value: unknown }>;
    scannedAt: number;
  };

  if (!scan.serialNumber || !Array.isArray(scan.records)) {
    return Response.json({ message: "Missing required fields" }, { status: 422 });
  }

  // Look up asset in KV by NFC serial number
  const assetJson = await env.NFC_ASSETS.get(scan.serialNumber);
  const asset = assetJson ? JSON.parse(assetJson) : null;

  // Write audit record to D1
  const auditId = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO nfc_scans (id, serial_number, records_json, asset_id, scanned_at)
     VALUES (?, ?, ?, ?, ?)`
  )
    .bind(
      auditId,
      scan.serialNumber,
      JSON.stringify(scan.records),
      asset?.id ?? null,
      new Date(scan.scannedAt).toISOString()
    )
    .run();

  return Response.json({
    tagId: scan.serialNumber,
    asset,
    auditId,
    processedAt: new Date().toISOString(),
  });
};
```

---

## React Integration

```typescript
// src/components/NFCScanButton.tsx
import { useState, useCallback, useRef } from "react";
import { NFCScanner } from "../nfc/scanner";
import { forwardScan } from "../nfc/pipeline";
import type { EnrichedScan } from "../nfc/pipeline";

export function NFCScanButton() {
  const [scanning, setScanning] = useState(false);
  const [lastScan, setLastScan] = useState<EnrichedScan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scannerRef = useRef(new NFCScanner());
  const pipelineAbort = useRef<AbortController | null>(null);

  const handleStart = useCallback(async () => {
    setError(null);
    setScanning(true);

    try {
      await scannerRef.current.start(async (rawScan) => {
        pipelineAbort.current?.abort();
        pipelineAbort.current = new AbortController();

        try {
          const enriched = await forwardScan(rawScan, pipelineAbort.current.signal);
          setLastScan(enriched);
        } catch (err) {
          if ((err as Error).name !== "AbortError") {
            setError((err as Error).message);
          }
        }
      });
    } catch (err) {
      setError((err as Error).message);
      setScanning(false);
    }
  }, []);

  const handleStop = useCallback(() => {
    scannerRef.current.stop();
    pipelineAbort.current?.abort();
    setScanning(false);
  }, []);

  return (
    <div>
      {scanning ? (
        <button onClick={handleStop}>Stop Scanning</button>
      ) : (
        <button onClick={handleStart}>Start Scanning</button>
      )}
      {error && <p role="alert">{error}</p>}
      {lastScan && (
        <pre>{JSON.stringify(lastScan, null, 2)}</pre>
      )}
    </div>
  );
}
```

---

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS nfc_scans (
  id          TEXT PRIMARY KEY,
  serial_number TEXT NOT NULL,
  records_json TEXT NOT NULL,
  asset_id    TEXT,
  scanned_at  TEXT NOT NULL
);

CREATE INDEX idx_nfc_scans_serial ON nfc_scans (serial_number);
CREATE INDEX idx_nfc_scans_at     ON nfc_scans (scanned_at);
```

---

## Anti-patterns

- **Calling `reader.scan()` outside a click handler.** The browser requires a transient activation. A `useEffect` on mount will fail with `SecurityError`.
- **Not aborting the scan on unmount.** The scan loop continues even after a React component unmounts, causing memory leaks and state-on-unmounted-component warnings.
- **Storing raw NDEF bytes in KV directly.** Bytes are not UTF-8 safe for KV values. Encode to base64 or serialize to JSON first.
- **Blocking the `reading` callback on the Worker fetch.** Subsequent tag reads queue up but the UI stalls. Always kick off the pipeline asynchronously and update state separately.
- **Assuming the serial number is unique per tag.** Some tag types return a zero-padded or randomized UID. Treat it as an opaque identifier and join on your own asset registry.

---

## Gotchas

- `NDEFReader` is undefined in `localhost` over HTTP. You must use HTTPS even in development (`vite --https`, self-signed cert, or `mkcert`).
- The `Permissions-Policy: nfc=self` header is required in production on Pages. Without it, Chrome throws `NotAllowedError` regardless of user gesture.
- Multiple simultaneous `NDEFReader` instances on the same page throw `InvalidStateError`. Keep a single scanner instance per page session.
- NDEF records with `recordType === "smart-poster"` wrap nested records in their payload. You must recursively parse the inner `NDEFMessage` if you care about the URL inside a smart poster.
- Android Chrome 89–91 has a bug where `AbortController` signals passed to `scan()` do not reliably terminate the scan. Upgrade workers-types and ensure you're targeting Chrome 92+ in your support matrix.

---

## Verification

1. Serve the Pages site locally with HTTPS and open DevTools → Application → Manifest.
2. Click "Start Scanning" and confirm the browser requests NFC permission.
3. Tap a test tag; confirm the `reading` event fires in console.
4. Check the Worker logs in the Cloudflare dashboard for the POST to `/api/nfc/scan`.
5. Query D1: `SELECT * FROM nfc_scans ORDER BY scanned_at DESC LIMIT 5`.
6. Confirm `asset` is populated if the serial number exists in `NFC_ASSETS` KV.

---

## Related

- `web-serial-api-workers-device-bridge.md`
- `pwa-service-worker-cloudflare-pages.md`
- `indexeddb-offline-sync-cloudflare-d1-workers.md`
- `cloudflare-pages-headers-csp-mobile.md`
- `user-activation-transient-sticky-gating.md`

---

## Sources

- MDN Web NFC API: https://developer.mozilla.org/en-US/docs/Web/API/Web_NFC_API
- W3C Web NFC Specification: https://w3c.github.io/web-nfc/
- Permissions Policy NFC feature: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Permissions-Policy/nfc
- Cloudflare Pages Functions: https://developers.cloudflare.com/pages/functions/
- Cloudflare D1: https://developers.cloudflare.com/d1/
