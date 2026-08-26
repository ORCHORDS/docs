# Vitest Workers R2 Presigned URL Expiry Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker generates presigned R2 URLs for direct browser uploads or downloads. Presigned URLs
encode an expiry timestamp and a HMAC signature. Tests must verify that:

1. A freshly generated URL is accepted within its validity window.
2. A URL that has passed its expiry returns 403 (not 200, not 500).
3. A tampered signature—even for a non-expired URL—is rejected.
4. The expiry window is exactly as configured (not longer, not shorter).

The challenge is that the current time is embedded in the URL's signature, so advancing a wall
clock or mocking `Date.now()` must propagate through the signing and verification code paths
consistently. This article covers how to achieve that in Vitest with `@cloudflare/vitest-pool-workers`.

---

## Context

Cloudflare R2 does not yet (as of 2026) have a native presigned URL API identical to S3's. The
common pattern is:

1. A Worker signs a URL using **HMAC-SHA256** over a canonical string that includes the expiry
   timestamp.
2. The browser hits a second Worker endpoint (or the same Worker at a different path) with the
   signed URL.
3. The second endpoint re-derives the expected signature and compares; if the current time is past
   the expiry it returns 403.

Alternatively some teams use `R2Bucket.createPresignedUrl()` via the Workers R2 binding when
available, but the HMAC pattern is more common and testable in isolation.

Key Vitest concepts used:
- `vi.setSystemTime` / `vi.useFakeTimers` to control `Date.now()` inside the Worker
- `SELF.fetch` (from `cloudflare:test`) to call the Worker in-process
- `env.R2` mock via the Miniflare pool

---

## Worker Code Under Test

```ts
// src/presigned.ts
const ALGORITHM = { name: "HMAC", hash: "SHA-256" };

export async function generatePresignedUrl(
  objectKey: string,
  expiresInSeconds: number,
  secret: string,
  baseUrl: string
): Promise<string> {
  const expiresAt = Math.floor(Date.now() / 1000) + expiresInSeconds;
  const canonical = `${objectKey}:${expiresAt}`;

  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    ALGORITHM,
    false,
    ["sign"]
  );
  const signatureBuffer = await crypto.subtle.sign(
    ALGORITHM.name,
    keyMaterial,
    new TextEncoder().encode(canonical)
  );
  const signature = btoa(String.fromCharCode(...new Uint8Array(signatureBuffer)));

  const url = new URL(`${baseUrl}/${objectKey}`);
  url.searchParams.set("expires", String(expiresAt));
  url.searchParams.set("sig", signature);
  return url.toString();
}

export async function verifyPresignedUrl(
  objectKey: string,
  expiresAt: number,
  signature: string,
  secret: string
): Promise<boolean> {
  if (Math.floor(Date.now() / 1000) > expiresAt) {
    return false; // expired
  }

  const canonical = `${objectKey}:${expiresAt}`;
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    ALGORITHM,
    false,
    ["verify"]
  );
  const sigBuffer = Uint8Array.from(atob(signature), (c) => c.charCodeAt(0));
  return crypto.subtle.verify(
    ALGORITHM.name,
    keyMaterial,
    sigBuffer,
    new TextEncoder().encode(canonical)
  );
}
```

---

## Vitest Config

```ts
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { cloudflareWorkersPool } from "@cloudflare/vitest-pool-workers";

export default defineConfig({
  test: {
    pool: cloudflareWorkersPool,
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
  },
});
```

---

## Test: Valid URL Within Expiry Window

```ts
// test/presigned.test.ts
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { generatePresignedUrl, verifyPresignedUrl } from "../src/presigned";

const SECRET = "test-hmac-secret-32-bytes-long!!";
const BASE_URL = "https://example.com/r2";
const KEY = "uploads/photo.jpg";

describe("presigned URL generation and verification", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("verifies a freshly generated URL as valid", async () => {
    vi.setSystemTime(new Date("2026-06-01T12:00:00Z"));

    const url = await generatePresignedUrl(KEY, 300, SECRET, BASE_URL);
    const parsed = new URL(url);
    const expiresAt = parseInt(parsed.searchParams.get("expires")!, 10);
    const sig = parsed.searchParams.get("sig")!;

    // Still within the 300-second window
    const isValid = await verifyPresignedUrl(KEY, expiresAt, sig, SECRET);
    expect(isValid).toBe(true);
  });
```

---

## Test: Expired URL Returns False

```ts
  it("rejects a URL whose expiry has passed", async () => {
    // Generate at T=0
    vi.setSystemTime(new Date("2026-06-01T12:00:00Z"));
    const url = await generatePresignedUrl(KEY, 300, SECRET, BASE_URL);
    const parsed = new URL(url);
    const expiresAt = parseInt(parsed.searchParams.get("expires")!, 10);
    const sig = parsed.searchParams.get("sig")!;

    // Advance clock by 301 seconds — past expiry
    vi.setSystemTime(new Date("2026-06-01T12:05:01Z"));

    const isValid = await verifyPresignedUrl(KEY, expiresAt, sig, SECRET);
    expect(isValid).toBe(false);
  });
```

---

## Test: URL Valid Up to Boundary, Invalid After

```ts
  it("is valid at exactly the expiry second, invalid one second later", async () => {
    const epoch = new Date("2026-06-01T12:00:00Z").getTime();
    vi.setSystemTime(epoch);

    const url = await generatePresignedUrl(KEY, 60, SECRET, BASE_URL);
    const parsed = new URL(url);
    const expiresAt = parseInt(parsed.searchParams.get("expires")!, 10);
    const sig = parsed.searchParams.get("sig")!;

    // Exactly at expiry (boundary: Date.now()/1000 === expiresAt)
    vi.setSystemTime(epoch + 60_000);
    const atBoundary = await verifyPresignedUrl(KEY, expiresAt, sig, SECRET);
    expect(atBoundary).toBe(true); // not yet expired (> not >=)

    // One second past expiry
    vi.setSystemTime(epoch + 61_000);
    const pastBoundary = await verifyPresignedUrl(KEY, expiresAt, sig, SECRET);
    expect(pastBoundary).toBe(false);
  });
```

---

## Test: Tampered Signature Rejected

```ts
  it("rejects a URL with a tampered signature", async () => {
    vi.setSystemTime(new Date("2026-06-01T12:00:00Z"));
    const url = await generatePresignedUrl(KEY, 300, SECRET, BASE_URL);
    const parsed = new URL(url);
    const expiresAt = parseInt(parsed.searchParams.get("expires")!, 10);

    const tamperedSig = "dGhpcyBpcyBmYWtl"; // base64 "this is fake"

    const isValid = await verifyPresignedUrl(KEY, expiresAt, tamperedSig, SECRET);
    expect(isValid).toBe(false);
  });
});
```

---

## End-to-End: Testing via SELF.fetch Against the Worker

```ts
// test/presigned-worker.test.ts
import { SELF, env } from "cloudflare:test";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

describe("Worker presigned URL endpoint", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("returns 200 for a valid presigned download request", async () => {
    vi.setSystemTime(new Date("2026-06-01T12:00:00Z"));

    // First call: get the presigned URL from the generate endpoint
    const genRes = await SELF.fetch("https://worker.test/presign/uploads/photo.jpg?ttl=300", {
      method: "POST",
    });
    expect(genRes.status).toBe(200);
    const { url } = await genRes.json<{ url: string }>();

    // Second call: use the presigned URL (clock is still T=0)
    const downloadRes = await SELF.fetch(url);
    expect(downloadRes.status).toBe(200);
  });

  it("returns 403 for an expired presigned download request", async () => {
    vi.setSystemTime(new Date("2026-06-01T12:00:00Z"));

    const genRes = await SELF.fetch("https://worker.test/presign/uploads/photo.jpg?ttl=60", {
      method: "POST",
    });
    const { url } = await genRes.json<{ url: string }>();

    // Advance past expiry
    vi.setSystemTime(new Date("2026-06-01T12:01:05Z")); // +65 seconds

    const downloadRes = await SELF.fetch(url);
    expect(downloadRes.status).toBe(403);

    const body = await downloadRes.json<{ error: string }>();
    expect(body.error).toBe("url_expired");
  });
});
```

---

## Anti-patterns

- **Testing only the happy path** — the expiry and tamper cases are where security bugs hide.
  Cover all three: valid, expired, tampered.
- **Not restoring real timers in `afterEach`** — fake timers leak into subsequent tests. Always
  call `vi.useRealTimers()` in `afterEach` or use Vitest's `fakeTimers` config block.
- **Comparing signatures with `===` instead of constant-time comparison** — this is fine in tests
  but flag it in the Worker code; use `crypto.subtle.verify` (constant-time) not string
  comparison.
- **Using a weak or short test secret** — HMAC-SHA256 with a 32-byte+ secret is required. A
  short secret like `"secret"` may pass tests but fail security review; use a real-length string
  in test fixtures.

---

## Gotchas

- `vi.useFakeTimers` in `@cloudflare/vitest-pool-workers` affects `Date.now()` inside the Worker
  pool. Confirm by logging `Date.now()` in the test and inside the Worker—they must agree.
- `crypto.subtle` is synchronous in some Node.js environments but always async in Workers. Always
  `await` it even in tests.
- The `expires` query parameter encodes Unix epoch seconds, not milliseconds. A common bug is
  dividing by 1000 inconsistently on one side.
- When testing via `SELF.fetch`, the Worker environment uses Miniflare's `R2Bucket` mock. If the
  Worker reads the object from R2 after URL verification, you must seed the R2 binding with a
  test object first using `env.R2.put("uploads/photo.jpg", "body")`.

---

## Verification

```bash
# Run presigned URL tests
npx vitest run test/presigned.test.ts test/presigned-worker.test.ts

# Watch mode
npx vitest test/presigned.test.ts --reporter=verbose

# Check all edge cases pass (expired, tampered, valid)
npx vitest run --reporter=verbose --testNamePattern="presigned"
```

---

## Related

- `vitest-r2-multipart-upload-testing.md`
- `r2-bucket-miniflare-testing.md`
- `vitest-workers-cache-api-miss-simulation.md`
- `miniflare-r2-event-notification-testing.md`

---

## Sources

- Cloudflare R2 presigned URLs overview — https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- Web Crypto API (HMAC-SHA256) — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign
- Vitest fake timers — https://vitest.dev/api/vi.html#vi-usefaketimers
- `@cloudflare/vitest-pool-workers` — https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
