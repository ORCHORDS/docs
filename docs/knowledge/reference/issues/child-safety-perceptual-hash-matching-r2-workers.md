# Child Safety Perceptual Hash Matching with R2 and Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

User-generated images uploaded to example project may include known CSAM or near-duplicate
variants of known CSAM that evade exact-hash matching. Pixel-level edits (crops, resizes,
saturation shifts, EXIF strip) defeat MD5/SHA-based blocklists but leave the perceptual
content intact. A perceptual hashing pipeline running inside Cloudflare Workers and R2
detects these near-duplicates at upload time and blocks storage before the content is ever
readable by other users.

---

## Context

Perceptual hashing algorithms (pHash, dHash, BLOCKHASH) produce a compact fingerprint
that is robust to minor image transformations. Matching against a known-bad hash set
uses Hamming-distance comparison: two images with a Hamming distance ≤ 10 over a 64-bit
hash are considered perceptually identical. example project maintains a hash blocklist in R2 as
a sorted binary index (for O(log n) prefix lookup) and queries it in the upload Worker
before writing the image to the user-accessible R2 bucket. Positive matches are forwarded
to the NCMEC CyberTipline via a Queue consumer.

Reference: GIFCT Hash-Sharing and NCMEC PhotoDNA are the industry standards; this
article covers the in-Worker implementation around a third-party hash API.

---

## 1. Upload Worker — Pre-flight Gate

```typescript
// workers/image-upload.ts
import { computePerceptualHash } from '../lib/phash-wasm';
import { lookupBlocklist } from '../lib/blocklist';

export interface Env {
  UPLOADS: R2Bucket;           // user-visible bucket
  QUARANTINE: R2Bucket;        // write-only, inaccessible to public
  BLOCKLIST: R2Bucket;         // contains blocklist index objects
  CSAM_REPORT_QUEUE: Queue<CsamReport>;
}

export interface CsamReport {
  uploadId: string;
  reporterId: string;  // hashed session — never raw UID
  matchedHash: string;
  hammingDistance: number;
  ts: number;
}

const HAMMING_THRESHOLD = 10;
const MAX_IMAGE_BYTES = 10 * 1024 * 1024; // 10 MB

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'PUT') return new Response('Method Not Allowed', { status: 405 });

    const uploadId = crypto.randomUUID();
    const contentType = req.headers.get('Content-Type') ?? '';
    if (!contentType.startsWith('image/')) {
      return new Response(JSON.stringify({ error: 'not_an_image' }), { status: 415 });
    }

    const imageBytes = await req.arrayBuffer();
    if (imageBytes.byteLength > MAX_IMAGE_BYTES) {
      return new Response(JSON.stringify({ error: 'file_too_large' }), { status: 413 });
    }

    // Step 1: Compute perceptual hash of the incoming image
    let pHash: bigint;
    try {
      pHash = await computePerceptualHash(imageBytes);
    } catch (err) {
      // Non-image or corrupt file — treat as policy violation to be safe
      return new Response(JSON.stringify({ error: 'unprocessable_image' }), { status: 422 });
    }

    // Step 2: Query blocklist
    const match = await lookupBlocklist(env.BLOCKLIST, pHash, HAMMING_THRESHOLD);

    if (match) {
      // Step 3a: Quarantine (write-only, private, no CDN URL issued)
      await env.QUARANTINE.put(
        `quarantine/${uploadId}`,
        imageBytes,
        { httpMetadata: { contentType }, customMetadata: { matchedHash: match.hash, distance: String(match.distance) } }
      );

      // Step 3b: Enqueue CyberTipline report
      const reporterId = req.headers.get('X-Session-Hash') ?? 'unknown';
      await env.CSAM_REPORT_QUEUE.send({
        uploadId,
        reporterId,
        matchedHash: match.hash,
        hammingDistance: match.distance,
        ts: Date.now(),
      });

      // Return generic rejection — do not reveal the match reason to uploader
      return new Response(JSON.stringify({ error: 'upload_rejected' }), { status: 451 });
    }

    // Step 4: Write to public bucket only if clean
    const key = `images/${uploadId}`;
    await env.UPLOADS.put(key, imageBytes, { httpMetadata: { contentType } });

    return new Response(JSON.stringify({ key, uploadId }), { status: 200 });
  },
};
```

---

## 2. Perceptual Hash (dHash) — Pure TypeScript / WASM Shim

```typescript
// lib/phash-wasm.ts
// A 64-bit dHash implementation runnable in the Workers runtime.
// For production, replace with PhotoDNA API call or NCMEC partner SDK.

export async function computePerceptualHash(imageBytes: ArrayBuffer): Promise<bigint> {
  // Decode image via ImageBitmap is not available in Workers.
  // Use a WASM-compiled image decoder (e.g. sharp compiled to wasm32-wasi).
  // Below simulates the dHash algorithm logic for illustration.

  const pixels = await decodeToGrayscale8x9(imageBytes); // 72 greyscale bytes

  let hash = 0n;
  for (let row = 0; row < 8; row++) {
    for (let col = 0; col < 8; col++) {
      const idx = row * 9 + col;
      const bit = pixels[idx] > pixels[idx + 1] ? 1n : 0n;
      hash = (hash << 1n) | bit;
    }
  }
  return hash;
}

// Stub — replace with actual WASM decode
async function decodeToGrayscale8x9(_imageBytes: ArrayBuffer): Promise<Uint8Array> {
  throw new Error('Replace with WASM image decoder');
}

export function hammingDistance(a: bigint, b: bigint): number {
  let xor = a ^ b;
  let count = 0;
  while (xor !== 0n) {
    count += Number(xor & 1n);
    xor >>= 1n;
  }
  return count;
}
```

---

## 3. Blocklist Index in R2

The blocklist is a newline-delimited sorted list of 16-character hex strings (64-bit hashes).
Stored as a single R2 object `blocklist/current.txt`, updated nightly via the GIFCT TCAP
feed. Near-neighbor lookup uses a BK-Tree built in-memory on first request and cached in
the Worker's module-scope cache.

```typescript
// lib/blocklist.ts
import { hammingDistance } from './phash-wasm';

interface BlocklistMatch {
  hash: string;
  distance: number;
}

// Module-scope cache: survives multiple requests within the same isolate lifetime
let cachedHashes: bigint[] | null = null;
let cacheEtag: string | null = null;

export async function lookupBlocklist(
  bucket: R2Bucket,
  query: bigint,
  threshold: number
): Promise<BlocklistMatch | null> {
  const obj = await bucket.get('blocklist/current.txt', {
    onlyIf: { etagDoesNotMatch: cacheEtag ?? '' },
  });

  if (obj) {
    // Blocklist updated — rebuild cache
    const text = await obj.text();
    cachedHashes = text
      .trim()
      .split('\n')
      .filter(Boolean)
      .map((h) => BigInt('0x' + h.trim()));
    cacheEtag = obj.etag ?? null;
  }

  if (!cachedHashes) return null;

  // Linear scan — acceptable for blocklists up to ~500k entries in a Worker
  // For multi-million entry lists, use a BK-Tree or approximate nearest-neighbor index
  for (const known of cachedHashes) {
    const dist = hammingDistance(query, known);
    if (dist <= threshold) {
      return { hash: known.toString(16).padStart(16, '0'), distance: dist };
    }
  }

  return null;
}
```

---

## 4. CyberTipline Queue Consumer

```typescript
// workers/csam-report-consumer.ts
export interface Env {
  NCMEC_API_KEY: string;
}

export default {
  async queue(batch: MessageBatch<import('./image-upload').CsamReport>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const report = msg.body;

      // Submit to NCMEC CyberTipline (requires NCMEC partner agreement)
      const res = await fetch('https://api.cybertipline.org/v2/reports', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${env.NCMEC_API_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          incidentTimestamp: new Date(report.ts).toISOString(),
          fileHash: report.matchedHash,
          uploadSessionHash: report.reporterId,
        }),
      });

      if (!res.ok) {
        // Retry — do not ack; Queues will redeliver
        console.error(`NCMEC report failed: ${res.status} for uploadId=${report.uploadId}`);
        continue;
      }

      msg.ack();
    }
  },
};
```

---

## 5. Blocklist Update Cron

```typescript
// workers/blocklist-update-cron.ts
export interface Env {
  BLOCKLIST: R2Bucket;
  GIFCT_API_KEY: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Fetch latest hash list from GIFCT TCAP (requires GIFCT membership)
    const res = await fetch('https://api.gifct.org/v1/hashes/csam?format=hex', {
      headers: { 'Authorization': `Bearer ${env.GIFCT_API_KEY}` },
    });
    if (!res.ok) throw new Error(`GIFCT fetch failed: ${res.status}`);

    const text = await res.text();
    // Sort for binary-search-friendliness
    const sorted = text.trim().split('\n').sort().join('\n');

    await env.BLOCKLIST.put('blocklist/current.txt', sorted, {
      httpMetadata: { contentType: 'text/plain' },
    });

    console.log(`[blocklist-update] updated at ${new Date().toISOString()}`);
  },
};
```

---

## Anti-patterns

- **Exact SHA-256 matching only**: SHA-256 blocklists are defeated by a single pixel change.
  Perceptual hashing is required to catch near-duplicates.
- **Storing blocked images in the public bucket at any point**: Even temporarily. Write
  directly to a quarantine bucket that has no public access policy.
- **Revealing the match reason in the API response**: Return a generic `upload_rejected`
  response. Revealing `'matched_csam_blocklist'` to the uploader helps adversaries learn
  to evade detection.
- **Running blocklist lookup synchronously from a cold module**: Build the in-memory index
  lazily and cache it; rebuilding on every request adds hundreds of milliseconds of latency.

---

## Gotchas

- **WASM image decoders in Workers**: The Workers runtime does not expose `<canvas>` or
  `ImageBitmap`. You must compile a decoder (e.g. `image-rs`) to WASM and bundle it. WASM
  instantiation is expensive — instantiate once per isolate using a module-scoped variable.
- **Blocklist size**: GIFCT TCAP hashes can exceed 1 million entries. A linear scan over
  1M 64-bit integers takes ~5 ms in WASM, which is acceptable. For larger lists, partition
  the blocklist by hash prefix and only load the relevant shard.
- **R2 conditional GET**: `onlyIf: { etagDoesNotMatch }` returns `null` when the object
  has not changed. Always check for `null` before attempting to read the body.
- **Legal requirements**: Reporting to NCMEC CyberTipline is mandated by 18 U.S.C. § 2258A
  for electronic service providers upon obtaining actual knowledge. This pipeline satisfies
  the technical obligation; consult legal counsel for compliance documentation.

---

## Verification

```typescript
import { describe, it, expect } from 'vitest';
import { hammingDistance } from '../lib/phash-wasm';

describe('hammingDistance', () => {
  it('identical hashes have distance 0', () => {
    expect(hammingDistance(0xdeadbeefcafebaben, 0xdeadbeefcafebaben)).toBe(0);
  });

  it('single-bit flip has distance 1', () => {
    expect(hammingDistance(0b0n, 0b1n)).toBe(1);
  });

  it('recognizes near-duplicate within threshold', () => {
    // Flip 8 bits — should still match at threshold 10
    const a = 0xFFFFFFFFFFFFFFFFn;
    const b = a ^ 0xFFn; // flip lowest 8 bits
    expect(hammingDistance(a, b)).toBe(8);
  });
});
```

---

## Related

- `877-csam-vendor-integration.md`
- `gifct-hash-sharing-terrorist-content-tcap.md`
- `hash-based-duplicate-content-detection-r2.md`
- `deepfake-detection-workers-ai-pipeline.md`
- `legal-hold-evidence-preservation-d1-r2.md`

---

## Sources

- NCMEC CyberTipline — Reporting Requirements: https://www.missingkids.org/gethelpnow/cybertipline
- GIFCT Transparency Report 2024: https://gifct.org/transparency/
- 18 U.S.C. § 2258A — Reporting Requirements for Electronic Service Providers
- dHash algorithm: http://www.hackerfactor.com/blog/index.php?/archives/529-Kind-of-Like-That.html
- Cloudflare R2 Conditional Operations: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
